"""SQLite persistence layer that makes the V5 pipeline idempotent and resumable.

Single file (datapipeline/cache.db) covering all collections. Never deleted
between runs. Keyed on (chunk_id, content_hash) so changed content is a miss.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Cache:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def prompt_hash(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS enrichment (
                chunk_id TEXT NOT NULL, content_hash TEXT NOT NULL,
                facets TEXT NOT NULL, annotation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, content_hash));

            CREATE TABLE IF NOT EXISTS enrichment_generation (
                chunk_id TEXT NOT NULL, content_hash TEXT NOT NULL,
                raw_facets TEXT NOT NULL, annotation TEXT NOT NULL,
                prompt_hash TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, content_hash));

            CREATE TABLE IF NOT EXISTS enrichment_classification (
                chunk_id TEXT NOT NULL, content_hash TEXT NOT NULL,
                labels TEXT NOT NULL, prompt_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, content_hash));

            CREATE TABLE IF NOT EXISTS embeddings (
                chunk_id TEXT NOT NULL, content_hash TEXT NOT NULL,
                vector_type TEXT NOT NULL, vector BLOB NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, content_hash, vector_type));

            CREATE TABLE IF NOT EXISTS collection_enrichment_status (
                collection TEXT PRIMARY KEY, total_chunks INTEGER NOT NULL,
                enriched INTEGER NOT NULL DEFAULT 0,
                complete INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
            """
        )
        self.conn.commit()

    # --- generation ---
    def get_generation(self, chunk_id: str, content_hash: str) -> dict | None:
        row = self.conn.execute(
            "SELECT raw_facets, annotation, prompt_hash FROM enrichment_generation "
            "WHERE chunk_id=? AND content_hash=?", (chunk_id, content_hash)).fetchone()
        if row is None:
            return None
        return {"raw_facets": json.loads(row["raw_facets"]),
                "annotation": row["annotation"], "prompt_hash": row["prompt_hash"]}

    def put_generation(self, chunk_id, content_hash, raw_facets, annotation, prompt_hash) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO enrichment_generation "
            "(chunk_id, content_hash, raw_facets, annotation, prompt_hash, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (chunk_id, content_hash, json.dumps(raw_facets), annotation, prompt_hash, _now()))
        self.conn.commit()

    # --- classification ---
    def get_classification(self, chunk_id, content_hash) -> dict | None:
        row = self.conn.execute(
            "SELECT labels, prompt_hash FROM enrichment_classification "
            "WHERE chunk_id=? AND content_hash=?", (chunk_id, content_hash)).fetchone()
        if row is None:
            return None
        return {"labels": json.loads(row["labels"]), "prompt_hash": row["prompt_hash"]}

    def put_classification(self, chunk_id, content_hash, labels, prompt_hash) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO enrichment_classification "
            "(chunk_id, content_hash, labels, prompt_hash, created_at) VALUES (?,?,?,?,?)",
            (chunk_id, content_hash, json.dumps(labels), prompt_hash, _now()))
        self.conn.commit()

    # --- merged enrichment ---
    def get_enrichment(self, chunk_id, content_hash) -> dict | None:
        row = self.conn.execute(
            "SELECT facets, annotation FROM enrichment "
            "WHERE chunk_id=? AND content_hash=?", (chunk_id, content_hash)).fetchone()
        if row is None:
            return None
        return {"facets": json.loads(row["facets"]), "annotation": row["annotation"]}

    def put_enrichment(self, chunk_id, content_hash, facets, annotation) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO enrichment "
            "(chunk_id, content_hash, facets, annotation, created_at) VALUES (?,?,?,?,?)",
            (chunk_id, content_hash, json.dumps(facets), annotation, _now()))
        self.conn.commit()

    # --- embeddings ---
    def get_embedding(self, chunk_id, content_hash, vector_type) -> list[float] | None:
        row = self.conn.execute(
            "SELECT vector FROM embeddings WHERE chunk_id=? AND content_hash=? AND vector_type=?",
            (chunk_id, content_hash, vector_type)).fetchone()
        return pickle.loads(row["vector"]) if row else None

    def put_embedding(self, chunk_id, content_hash, vector_type, vector) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO embeddings "
            "(chunk_id, content_hash, vector_type, vector, created_at) VALUES (?,?,?,?,?)",
            (chunk_id, content_hash, vector_type, pickle.dumps(list(vector)), _now()))
        self.conn.commit()

    # --- collection status ---
    def set_collection_status(self, collection, total_chunks, enriched, complete) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO collection_enrichment_status "
            "(collection, total_chunks, enriched, complete, updated_at) VALUES (?,?,?,?,?)",
            (collection, total_chunks, enriched, 1 if complete else 0, _now()))
        self.conn.commit()

    def get_collection_status(self, collection) -> dict | None:
        row = self.conn.execute(
            "SELECT total_chunks, enriched, complete FROM collection_enrichment_status "
            "WHERE collection=?", (collection,)).fetchone()
        return dict(row) if row else None
