"""Build and check one TheoCorpus collection without writing anything (a dry run).

Publishing goes through `publish.py` (2.2w): stage, report, apply. This command no
longer writes, and its old `--target`, `--wipe-reader`, `--confirm-reader-wipe` and
`--reset-search-index` flags are gone, since each wrote to or deleted from the live
stores.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

import contents
from model import Document
from publication import SOURCE_ADAPTERS, build, prepare

LIVE_PUBLISH_MOVED = (
    "run_collection.py only builds and checks a collection (--dry-run). To publish, use "
    "publish.py: `publish.py stage --collection <name> --release <name>`, then `report`, "
    "then `apply` (datapipeline/README.md, \"Publish one collection\")."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and check one collection's canonical passages; writes nothing."
    )
    parser.add_argument(
        "--collection",
        required=True,
        choices=sorted(SOURCE_ADAPTERS),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="build only the first N documents",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=("build and check the collection, print its counts, and write nothing "
              "(the catechism also writes its local alignment report)"),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    builder: Callable[..., list[Document]] = build,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.dry_run:
        parser.error(LIVE_PUBLISH_MOVED)
    try:
        documents, _ = prepare(builder(args.collection, limit=args.limit))
    except ValueError as error:
        parser.error(str(error))
    passages = {passage.id for document in documents for passage in document.passages}
    print(
        f"{args.collection}: dry run, {len(documents)} documents, "
        f"{len(passages)} passages; nothing written"
    )
    for document in documents:
        if document.contents is None:
            continue
        unreached = contents.check(document)
        nodes = len(contents.flatten(document.contents))
        line = f"  contents tree: {document.title}, {nodes} nodes"
        if unreached:
            line += (f"; WARNING {len(unreached)} chapters no node opens, "
                     f"first {unreached[0]!r}")
        print(line)
    if args.collection == "catechism":
        return _catechism_report()
    return 0


def _catechism_report() -> int:
    """The US-edition alignment and live identity report (#279, B4). Exit 1 when it
    finds something Carter must decide before a publish."""
    from checks import catechism_us

    out, result = catechism_us.write()
    stops = catechism_us.stops(result)
    print(f"  US-edition report: {out}")
    print(f"  stops for Carter: {', '.join(stops) if stops else 'none'}")
    return 1 if stops else 0


if __name__ == "__main__":
    raise SystemExit(main())
