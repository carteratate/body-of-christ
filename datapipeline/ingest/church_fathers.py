"""Church Fathers ingestion.

Walks sources/church-fathers/*.xml, skips .Zone.Identifier files,
calls parse_thml() for each, then upserts documents and chunks to the DB.
"""
from __future__ import annotations

import asyncio
import os
import sys
from glob import glob

from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document  # noqa: E402
from ingest.common import parse_thml  # noqa: E402

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "church-fathers")


async def main(pool) -> None:
    """Ingest Church Fathers texts into the database."""
    xml_files = sorted(
        f for f in glob(os.path.join(_SRC_DIR, "*.xml"))
        if not f.endswith(".Zone.Identifier")
    )
    print(f"Found {len(xml_files)} ThML files in {_SRC_DIR}")

    total_chunks = 0
    with tqdm(total=len(xml_files), unit="file", desc="Church Fathers") as pbar:
        for path in xml_files:
            filename = os.path.basename(path)
            if filename == "summa.xml":
                pbar.update(1)
                continue
            try:
                doc = parse_thml(path)
            except Exception as exc:
                print(f"\n  WARNING: Failed to parse {filename}: {exc}", file=sys.stderr)
                pbar.update(1)
                continue

            if not doc.chunks:
                print(f"\n  WARNING: No chunks extracted from {filename}", file=sys.stderr)
                pbar.update(1)
                continue

            doc_id = await upsert_document(
                pool,
                collection="church-fathers",
                title=doc.title,
                translation="",
                author=doc.author,
                year=doc.year,
                metadata={"source_file": filename},
            )

            for content, reference, position, meta in doc.chunks:
                chunk_meta = (meta or {}) | {"source_file": filename}
                await upsert_chunk(pool, doc_id, content, position, reference, metadata=chunk_meta)

            total_chunks += len(doc.chunks)
            pbar.set_postfix({"file": filename, "chunks": len(doc.chunks)})
            pbar.update(1)

    print(f"  Done. {total_chunks} total chunks written for church-fathers.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
