"""SQLite persistence layer that makes the V5 pipeline idempotent and resumable.

Single file (datapipeline/cache.db) covering all collections. Never deleted
between runs. Keyed on (chunk_id, content_hash) so changed content is a miss.

Stage-cache dependency graph: classification/annotation/merged rows record the
canonical hash of the upstream artifact(s) they were computed from (see
`Cache.canonical_hash`), in addition to their own prompt_hash/model/temperature.
A stage cache hit is only valid when its own identity AND every upstream
artifact hash it depends on still match current values — this is checked by
the caller (stages/enrich.py), not by this module, but the columns exist here
so that identity can be persisted and compared. Legacy rows written before
this existed simply have NULL in the new columns, which can never equal a
real hash/temperature/schema_version, so they safely miss and are recomputed
rather than being trusted.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sqlite3
from datetime import datetime, timezone

# Bump when the shape of cached artifacts changes in a way that must
# invalidate old rows even though prompt/model/temperature look unchanged.
ENRICHMENT_SCHEMA_VERSION = 1


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

    @staticmethod
    def canonical_hash(data) -> str:
        """Deterministic hash of a JSON-serializable structure: sorted object
        keys, stable separators, UTF-8, list order preserved. Used to hash
        generation/classification/annotation artifacts so a downstream cache
        entry can detect that an upstream artifact actually changed, instead
        of only checking its own prompt hash. Callers must only pass
        semantically relevant fields (facet id/text/takeaway/question;
        label facet_id/grounding/evidence/kind/kind_secondary; annotation
        text) — never volatile fields like timestamps, token usage, or
        request ids.
        """
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def embedding_input_hash(text: str) -> str:
        """Hash of the exact string sent to the embedding model. This, not
        chunk_id/content_hash/array-position, is the embedding cache's real
        identity — two different facet texts at the same position must never
        share a cached vector."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _ensure_column(self, table: str, column: str, coltype: str) -> None:
        """Additive migration: adds `column` to `table` if not already
        present. Never drops or rewrites existing data — pre-existing rows
        simply get NULL in the new column, which is exactly the "legacy row,
        treat as unproven" signal callers rely on."""
        cols = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

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
                raw_facets TEXT NOT NULL,
                prompt_hash TEXT NOT NULL, model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, content_hash));

            CREATE TABLE IF NOT EXISTS enrichment_classification (
                chunk_id TEXT NOT NULL, content_hash TEXT NOT NULL,
                labels TEXT NOT NULL, prompt_hash TEXT NOT NULL, model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, content_hash));

            CREATE TABLE IF NOT EXISTS enrichment_annotation (
                chunk_id TEXT NOT NULL, content_hash TEXT NOT NULL,
                annotation TEXT NOT NULL, prompt_hash TEXT NOT NULL, model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, content_hash));

            CREATE TABLE IF NOT EXISTS chunk_enrichment_status (
                chunk_id TEXT NOT NULL, content_hash TEXT NOT NULL,
                status TEXT NOT NULL, raw_response TEXT, validation_errors TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, content_hash));

            CREATE TABLE IF NOT EXISTS embeddings (
                input_hash TEXT NOT NULL, model TEXT NOT NULL, dimensions INTEGER NOT NULL,
                vector BLOB NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY (input_hash, model, dimensions));

            CREATE TABLE IF NOT EXISTS collection_enrichment_status (
                collection TEXT PRIMARY KEY, total_chunks INTEGER NOT NULL,
                enriched INTEGER NOT NULL DEFAULT 0,
                complete INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
            """
        )
        # Additive dependency-hash / config-identity columns (see module docstring).
        self._ensure_column("enrichment_generation", "temperature", "REAL")
        self._ensure_column("enrichment_generation", "schema_version", "INTEGER")

        self._ensure_column("enrichment_classification", "temperature", "REAL")
        self._ensure_column("enrichment_classification", "schema_version", "INTEGER")
        self._ensure_column("enrichment_classification", "generation_hash", "TEXT")

        self._ensure_column("enrichment_annotation", "temperature", "REAL")
        self._ensure_column("enrichment_annotation", "schema_version", "INTEGER")
        self._ensure_column("enrichment_annotation", "generation_hash", "TEXT")
        self._ensure_column("enrichment_annotation", "classification_hash", "TEXT")

        self._ensure_column("enrichment", "generation_hash", "TEXT")
        self._ensure_column("enrichment", "classification_hash", "TEXT")
        self._ensure_column("enrichment", "annotation_hash", "TEXT")
        self._ensure_column("enrichment", "schema_version", "INTEGER")
        self.conn.commit()

    # --- generation (Pass 1) ---
    def get_generation(self, chunk_id: str, content_hash: str) -> dict | None:
        row = self.conn.execute(
            "SELECT raw_facets, prompt_hash, model, temperature, schema_version "
            "FROM enrichment_generation WHERE chunk_id=? AND content_hash=?",
            (chunk_id, content_hash)).fetchone()
        if row is None:
            return None
        return {"raw_facets": json.loads(row["raw_facets"]),
                "prompt_hash": row["prompt_hash"], "model": row["model"],
                "temperature": row["temperature"], "schema_version": row["schema_version"]}

    def put_generation(self, chunk_id, content_hash, raw_facets, prompt_hash, model, *,
                       temperature=None, schema_version=None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO enrichment_generation "
            "(chunk_id, content_hash, raw_facets, prompt_hash, model, temperature, "
            "schema_version, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (chunk_id, content_hash, json.dumps(raw_facets), prompt_hash, model,
             temperature, schema_version, _now()))
        self.conn.commit()

    # --- classification (Pass 2) ---
    def get_classification(self, chunk_id, content_hash) -> dict | None:
        row = self.conn.execute(
            "SELECT labels, prompt_hash, model, temperature, schema_version, generation_hash "
            "FROM enrichment_classification WHERE chunk_id=? AND content_hash=?",
            (chunk_id, content_hash)).fetchone()
        if row is None:
            return None
        return {"labels": json.loads(row["labels"]), "prompt_hash": row["prompt_hash"],
                "model": row["model"], "temperature": row["temperature"],
                "schema_version": row["schema_version"], "generation_hash": row["generation_hash"]}

    def put_classification(self, chunk_id, content_hash, labels, prompt_hash, model, *,
                           temperature=None, schema_version=None, generation_hash=None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO enrichment_classification "
            "(chunk_id, content_hash, labels, prompt_hash, model, temperature, "
            "schema_version, generation_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (chunk_id, content_hash, json.dumps(labels), prompt_hash, model,
             temperature, schema_version, generation_hash, _now()))
        self.conn.commit()

    # --- annotation (Pass 3) ---
    def get_annotation(self, chunk_id, content_hash) -> dict | None:
        row = self.conn.execute(
            "SELECT annotation, prompt_hash, model, temperature, schema_version, "
            "generation_hash, classification_hash FROM enrichment_annotation "
            "WHERE chunk_id=? AND content_hash=?", (chunk_id, content_hash)).fetchone()
        if row is None:
            return None
        return {"annotation": row["annotation"], "prompt_hash": row["prompt_hash"],
                "model": row["model"], "temperature": row["temperature"],
                "schema_version": row["schema_version"], "generation_hash": row["generation_hash"],
                "classification_hash": row["classification_hash"]}

    def put_annotation(self, chunk_id, content_hash, annotation, prompt_hash, model, *,
                       temperature=None, schema_version=None, generation_hash=None,
                       classification_hash=None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO enrichment_annotation "
            "(chunk_id, content_hash, annotation, prompt_hash, model, temperature, "
            "schema_version, generation_hash, classification_hash, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (chunk_id, content_hash, annotation, prompt_hash, model, temperature,
             schema_version, generation_hash, classification_hash, _now()))
        self.conn.commit()

    # --- per-chunk failure status (classification_failed / annotation_failed) ---
    def get_chunk_status(self, chunk_id, content_hash) -> dict | None:
        row = self.conn.execute(
            "SELECT status, raw_response, validation_errors FROM chunk_enrichment_status "
            "WHERE chunk_id=? AND content_hash=?", (chunk_id, content_hash)).fetchone()
        return dict(row) if row else None

    def set_chunk_status(self, chunk_id, content_hash, status, *,
                         raw_response=None, validation_errors=None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO chunk_enrichment_status "
            "(chunk_id, content_hash, status, raw_response, validation_errors, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (chunk_id, content_hash, status, raw_response, validation_errors, _now()))
        self.conn.commit()

    # --- merged enrichment ---
    def get_enrichment(self, chunk_id, content_hash) -> dict | None:
        row = self.conn.execute(
            "SELECT facets, annotation, generation_hash, classification_hash, "
            "annotation_hash, schema_version FROM enrichment "
            "WHERE chunk_id=? AND content_hash=?", (chunk_id, content_hash)).fetchone()
        if row is None:
            return None
        return {"facets": json.loads(row["facets"]), "annotation": row["annotation"],
                "generation_hash": row["generation_hash"],
                "classification_hash": row["classification_hash"],
                "annotation_hash": row["annotation_hash"],
                "schema_version": row["schema_version"]}

    def put_enrichment(self, chunk_id, content_hash, facets, annotation, *,
                       generation_hash=None, classification_hash=None,
                       annotation_hash=None, schema_version=None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO enrichment "
            "(chunk_id, content_hash, facets, annotation, generation_hash, "
            "classification_hash, annotation_hash, schema_version, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (chunk_id, content_hash, json.dumps(facets), annotation, generation_hash,
             classification_hash, annotation_hash, schema_version, _now()))
        self.conn.commit()

    # --- embeddings (content-addressed: exact input text + model + dimensions) ---
    def get_embedding(self, input_hash: str, model: str, dimensions: int) -> list[float] | None:
        row = self.conn.execute(
            "SELECT vector FROM embeddings WHERE input_hash=? AND model=? AND dimensions=?",
            (input_hash, model, dimensions)).fetchone()
        return pickle.loads(row["vector"]) if row else None

    def put_embedding(self, input_hash: str, model: str, dimensions: int, vector) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO embeddings "
            "(input_hash, model, dimensions, vector, created_at) VALUES (?,?,?,?,?)",
            (input_hash, model, dimensions, pickle.dumps(list(vector)), _now()))
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
