"""Summa Theologica ingestion — separate collection from Church Fathers."""
from __future__ import annotations

import asyncio
import os
import sys

from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document  # noqa: E402
from ingest.common import parse_thml  # noqa: E402

_SRC = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "sources", "church-fathers", "summa.xml"
)


async def main(pool=None) -> None:
    _own_pool = pool is None
    if _own_pool:
        pool = await get_pool()
    try:
        print(f"Parsing Summa Theologica from {_SRC}...")
        doc = parse_thml(_SRC)
        print(f"  {len(doc.chunks)} article chunks extracted.")

        doc_id = await upsert_document(
            pool,
            collection="summa",
            title=doc.title,
            translation="",
            author=doc.author,
            year=doc.year,
            metadata={"source_file": "summa.xml"},
        )

        with tqdm(total=len(doc.chunks), unit="chunk", desc="Summa") as pbar:
            for content, reference, position in doc.chunks:
                await upsert_chunk(pool, doc_id, content, position, reference)
                pbar.update(1)

        print(f"  Done. {len(doc.chunks)} chunks written for summa.")
    finally:
        if _own_pool:
            await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
