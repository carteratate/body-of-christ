"""Reader stage: clear + write documents/chunks to Supabase (existing reader_writer)."""
from __future__ import annotations

from model import Document
from writers import reader_writer


async def write(conn, collection: str, docs: list[Document]) -> None:
    await reader_writer.clear_collection(conn, collection)
    for d in docs:
        await reader_writer.write_document(conn, d)
