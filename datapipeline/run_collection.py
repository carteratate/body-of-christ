"""Command-line adapter for publishing one TheoCorpus collection."""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

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
        "--clean",
        action="store_true",
        help=(
            "deprecated alias for --reset-search-index; retained during expansion "
            "and removed by the contraction ticket"
        ),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: CollectionPublicationRunner | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.clean:
        print(
            "warning: --clean is deprecated; use --reset-search-index",
            file=sys.stderr,
        )

    request = PublicationRequest(
        collection=args.collection,
        target=PublicationTarget(args.target),
        limit=args.limit,
        reset_search_index=args.reset_search_index or args.clean,
        wipe_reader=args.wipe_reader,
        wipe_reader_confirmation=args.confirm_reader_wipe,
    )
    try:
        result = asyncio.run((runner or production_runner()).publish(request))
    except ValueError as error:
        parser.error(str(error))

    print(
        f"{result.collection}: published {result.document_count} documents, "
        f"{result.passage_count} passages to {result.target.value}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
