"""Delete all Qdrant points for one collection. Run BEFORE re-ingesting it.

    cd datapipeline && python3 scripts/delete_collection_qdrant.py --collection church-fathers
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from writers.qdrant import get_client, delete_collection_points  # noqa: E402


async def main(collection: str) -> None:
    client = get_client()
    try:
        await delete_collection_points(client, collection)
        print(f"Deleted all Qdrant points where collection == {collection!r}.")
    finally:
        await client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True)
    args = ap.parse_args()
    asyncio.run(main(args.collection))
