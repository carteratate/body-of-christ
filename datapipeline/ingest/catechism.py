"""Catechism of the Catholic Church ingestion.

The Catechism is ingested from nossbigg/catechism-ccc-json (v0.0.2).

JSON structure:
  {
    "page_nodes": {
      "toc-N": {
        "paragraphs": [
          {
            "elements": [
              {"type": "ref-ccc", "ref_number": 1},
              {"type": "text", "text": "..."},
              {"type": "ref", "number": ...},
              ...
            ]
          }
        ]
      }
    }
  }

Each paragraph may contain:
  - "ref-ccc": the paragraph number in the Catechism (e.g., CCC §1)
  - "text": content to be concatenated
  - "ref": footnote references (ignored)
  - other types: ignored

Paragraphs without a "ref-ccc" element are skipped.
Paragraphs with total text < _MIN_LENGTH are skipped.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document  # noqa: E402

_MIN_LENGTH = 30
_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "catechism", "ccc.json")


def parse_ccc_paragraphs(data: dict) -> list[tuple[int, str]]:
    """Return sorted list of (para_num, content) from the ccc.json page_nodes structure.

    - Skips paragraphs without a ref-ccc element
    - Concatenates all text elements (separated by spaces)
    - Skips paragraphs with total content < _MIN_LENGTH
    - Returns list sorted by paragraph number
    """
    result: list[tuple[int, str]] = []
    for node in data.get("page_nodes", {}).values():
        for para in node.get("paragraphs", []):
            elements = para.get("elements", [])
            ref_num: int | None = None
            text_parts: list[str] = []
            for el in elements:
                if el.get("type") == "ref-ccc":
                    ref_num = el.get("ref_number")
                elif el.get("type") == "text":
                    text_parts.append(el.get("text", ""))
            if ref_num is None:
                continue
            content = " ".join(text_parts).strip()
            if len(content) < _MIN_LENGTH:
                continue
            result.append((ref_num, content))
    result.sort(key=lambda x: x[0])
    return result


async def main(pool) -> None:
    """Ingest the Catechism into the database."""
    print("Reading CCC JSON...")
    with open(_SRC, encoding="utf-8") as f:
        data = json.load(f)

    paragraphs = parse_ccc_paragraphs(data)
    print(f"  Found {len(paragraphs)} CCC paragraphs.")

    doc_id = await upsert_document(
        pool,
        collection="catechism",
        title="Catechism of the Catholic Church",
        translation="",
        author="Catholic Church",
        year=1992,
        metadata={"source": "nossbigg/catechism-ccc-json"},
    )

    with tqdm(total=len(paragraphs), unit="para", desc="Catechism") as pbar:
        for position, (para_num, content) in enumerate(paragraphs):
            await upsert_chunk(
                pool,
                document_id=doc_id,
                content=content,
                position=position,
                reference=f"CCC §{para_num}",
            )
            pbar.update(1)

    print(f"  Done. {len(paragraphs)} chunks written for catechism.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
