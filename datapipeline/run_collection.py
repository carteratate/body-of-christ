"""Command-line adapter for publishing one TheoCorpus collection."""
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from identity import passage_id
from publication import (
    CollectionPublicationRunner,
    PublicationRequest,
    PublicationTarget,
    SOURCE_ADAPTERS,
    production_runner,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build canonical passages and reconcile one collection into the selected "
            "reader-store and search-index targets."
        )
    )
    parser.add_argument(
        "--collection",
        required=True,
        choices=sorted(SOURCE_ADAPTERS),
    )
    parser.add_argument(
        "--target",
        default=PublicationTarget.BOTH.value,
        choices=[target.value for target in PublicationTarget],
        help="publication target (default: both)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="publish only the first N documents; collection-wide pruning is disabled",
    )
    parser.add_argument(
        "--reset-search-index",
        action="store_true",
        help="delete the selected collection's search-index points before writing",
    )
    parser.add_argument(
        "--wipe-reader",
        action="store_true",
        help=(
            "delete the selected collection from the reader store before writing; "
            "cascades to user-owned records and requires --confirm-reader-wipe"
        ),
    )
    parser.add_argument(
        "--confirm-reader-wipe",
        metavar="COLLECTION",
        help="must exactly match --collection when --wipe-reader is used",
    )
    parser.add_argument(
        "--release",
        metavar="RELEASE_ID",
        help=(
            "release this publish belongs to; a live write needs an entry for this "
            "collection and release in PUBLISH_LOCK.json"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build and check the collection, print its counts, and write nothing",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: CollectionPublicationRunner | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    request = PublicationRequest(
        collection=args.collection,
        target=PublicationTarget(args.target),
        limit=args.limit,
        reset_search_index=args.reset_search_index,
        wipe_reader=args.wipe_reader,
        wipe_reader_confirmation=args.confirm_reader_wipe,
        release=args.release,
    )
    runner = runner or production_runner()
    if args.dry_run:
        try:
            documents = runner.build(request)
        except ValueError as error:
            parser.error(str(error))
        passages = {
            passage_id(document.id, passage.anchor)
            for document in documents
            for passage in document.passages
        }
        print(
            f"{request.collection}: dry run, {len(documents)} documents, "
            f"{len(passages)} passages; nothing written"
        )
        return 0

    try:
        result = asyncio.run(runner.publish(request))
    except ValueError as error:
        parser.error(str(error))

    print(
        f"{result.collection}: published {result.document_count} documents, "
        f"{result.passage_count} passages to {result.target.value}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
