"""V5 ingestion entry point: stage engine, gates, dry-run/cost, status, sample, import-backup.

Usage examples:
    python pipeline.py --collection church-fathers --stage enrich
    python pipeline.py --collection summa --stages parse,reader,enrich,embed
    python pipeline.py --stages bm25-content-fit
    python pipeline.py --collection all --stages all --yes
    python pipeline.py --collection church-fathers --stage enrich --sample 10
    python pipeline.py --status
    python pipeline.py --import-backup enrichments/church-fathers.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass

from config import settings

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache.db")
ENRICH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enrichments")
SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
CONTENT_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bm25_content_model.bin")
ANNOTATION_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bm25_annotation_model.bin")

# per-chunk token priors from the spec's cost estimate
_GEN_IN, _GEN_OUT = 350, 250
_CLS_IN, _CLS_OUT = 250, 80
_ANN_IN, _ANN_OUT = 300, 150


class PipelineError(Exception):
    pass


@dataclass(frozen=True)
class StageSpec:
    scope: str            # "collection" | "global"
    depends_on: tuple[str, ...]


STAGES: dict[str, StageSpec] = {
    "parse": StageSpec("collection", ()),
    "reader": StageSpec("collection", ("parse",)),
    "enrich": StageSpec("collection", ("parse",)),
    "embed": StageSpec("collection", ("parse", "enrich")),
    "bm25-content-fit": StageSpec("global", ("reader",)),
    "bm25-annotation-fit": StageSpec("global", ("enrich",)),
    "bm25-index": StageSpec("collection", ("bm25-content-fit", "bm25-annotation-fit")),
}

_ALL_ORDER = ["parse", "reader", "enrich", "embed",
              "bm25-content-fit", "bm25-annotation-fit", "bm25-index"]


def resolve_stages(requested: list[str]) -> list[str]:
    if requested == ["all"]:
        return list(_ALL_ORDER)
    for s in requested:
        if s not in STAGES:
            raise PipelineError(f"unknown stage '{s}'. valid: {sorted(STAGES)}")
    return sorted(requested, key=_ALL_ORDER.index)


# Collection-scoped stages that run BEFORE the global BM25 fits, the global
# fits themselves, and the collection-scoped stages that run AFTER them. The
# split exists because a global fit reads the whole corpus out of Postgres, so
# every collection must have finished reader/enrich before either fit runs.
_PRE_GLOBAL = ("parse", "reader", "enrich", "embed")
_GLOBAL = ("bm25-content-fit", "bm25-annotation-fit")
_POST_GLOBAL = ("bm25-index",)


def execution_plan(stages: list[str], collections: list[str]) -> list[tuple[str, str | None]]:
    """Expands the requested stages across the requested collections into the
    concrete (stage, collection) sequence to execute, with `None` as the
    collection for global stages. Ordering rule: all pre-global stages for
    every collection, then the global fits once, then the post-global stages
    for every collection."""
    order: list[tuple[str, str | None]] = []
    for c in collections:
        for s in _PRE_GLOBAL:
            if s in stages:
                order.append((s, c))
    for s in _GLOBAL:
        if s in stages:
            order.append((s, None))
    for c in collections:
        for s in _POST_GLOBAL:
            if s in stages:
                order.append((s, c))
    return order


def all_execution_order(collections: list[str]) -> list[tuple[str, str | None]]:
    return execution_plan(_ALL_ORDER, collections)


def validate_dependencies(collection, stage, cache, model_paths: dict) -> None:
    if stage == "embed":
        st = cache.get_collection_status(collection)
        if st is None or not st.get("complete"):
            raise PipelineError(
                f"cannot run 'embed' for {collection}: enrich is not complete. Run enrich first.")
    if stage == "bm25-index":
        if not model_paths.get("content") or not os.path.exists(model_paths["content"]):
            raise PipelineError("cannot run 'bm25-index': bm25_content_model.bin missing. "
                                "Run bm25-content-fit first.")
        if not model_paths.get("annotation") or not os.path.exists(model_paths["annotation"]):
            raise PipelineError("cannot run 'bm25-index': bm25_annotation_model.bin missing. "
                                "Run bm25-annotation-fit first.")


def estimate_enrich_cost(chunk_count: int) -> dict:
    # Pass 1 (generation) runs on Opus; Pass 2 (classification) + Pass 3 (annotation
    # assembly) both run on Sonnet.
    gen_input = chunk_count * _GEN_IN
    gen_output = chunk_count * _GEN_OUT
    sonnet_input = chunk_count * (_CLS_IN + _ANN_IN)
    sonnet_output = chunk_count * (_CLS_OUT + _ANN_OUT)
    usd = (gen_input / 1_000_000) * settings.OPUS_INPUT_COST_PER_M + \
          (gen_output / 1_000_000) * settings.OPUS_OUTPUT_COST_PER_M + \
          (sonnet_input / 1_000_000) * settings.SONNET_INPUT_COST_PER_M + \
          (sonnet_output / 1_000_000) * settings.SONNET_OUTPUT_COST_PER_M
    return {"input_tokens": gen_input + sonnet_input, "output_tokens": gen_output + sonnet_output,
            "usd": round(usd, 2)}


# ---- runtime wiring (integration; exercised by the Task 19 smoke run) ----


class _Resources:
    """Lazily-created shared clients, closed once when the run ends.

    Stages are dispatched as a loop over (stage, collection) pairs, so a runner
    that opened its own pool/client would reconnect for every collection and
    every stage. Everything here is built on first use and reused for the rest
    of the run; nothing is created for a run that never asks for it (a
    parse-only run opens no sockets at all).
    """

    def __init__(self) -> None:
        self._cache = None
        self._pool = None
        self._qdrant = None
        self._embed_client = None

    def cache(self):
        if self._cache is None:
            from cache import Cache
            self._cache = Cache(CACHE_PATH)
            self._cache.init_schema()
        return self._cache

    async def pool(self):
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0)
        return self._pool

    def qdrant(self):
        if self._qdrant is None:
            from writers.qdrant import get_client
            self._qdrant = get_client()
        return self._qdrant

    def embed_client(self):
        if self._embed_client is None:
            from embeddings import EmbeddingClient
            self._embed_client = EmbeddingClient(settings.OPENAI_API_KEY, settings.EMBEDDING_MODEL)
        return self._embed_client

    async def aclose(self) -> None:
        if self._embed_client is not None:
            await self._embed_client.close()
        if self._qdrant is not None:
            await self._qdrant.close()
        if self._pool is not None:
            await self._pool.close()
        if self._cache is not None:
            self._cache.close()


def load_bm25_model(path: str):
    """Reconstructs a SparseTextEmbedding encoder from the JSON config written
    by the bm25 fit stages. Those files keep a `.bin` extension for continuity
    with the plan doc but hold UTF-8 JSON, not a pickle — see
    stages/bm25_content_fit.py's module docstring."""
    import json

    from fastembed import SparseTextEmbedding

    with open(path) as f:
        config = json.load(f)
    return SparseTextEmbedding(
        model_name=config["model_name"],
        **{k: v for k, v in config.items() if k != "model_name"})


async def _run_reader(collection: str, docs, res: _Resources) -> None:
    from stages import reader

    pool = await res.pool()
    async with pool.acquire() as conn:
        await reader.write(conn, collection, docs)
    print(f"reader {collection}: wrote {len(docs)} document(s), "
          f"{sum(len(d.passages) for d in docs)} passage(s)")


async def _run_embed(collection: str, docs, res: _Resources) -> None:
    from qdrant_schema import ensure_facets, ensure_questions
    from stages.embed import embed_collection
    from writers.qdrant import ensure_collection

    qdrant = res.qdrant()
    # Idempotent: each only creates the Qdrant collection if it is missing.
    await ensure_collection(qdrant)
    await ensure_facets(qdrant)
    await ensure_questions(qdrant)

    await embed_collection(docs, res.cache(), res.embed_client(), qdrant)
    print(f"embed {collection}: {sum(len(d.passages) for d in docs)} passage(s) processed")


async def _run_bm25_content_fit(res: _Resources) -> None:
    from stages.bm25_content_fit import fit, load_content_corpus

    pool = await res.pool()
    async with pool.acquire() as conn:
        corpus = await load_content_corpus(conn)
    fit(corpus, CONTENT_MODEL)
    print(f"bm25-content-fit: {len(corpus)} document(s) -> {CONTENT_MODEL}")


async def _run_bm25_annotation_fit(res: _Resources) -> None:
    from stages.bm25_annotation_fit import fit, load_annotation_corpus

    pool = await res.pool()
    async with pool.acquire() as conn:
        corpus = await load_annotation_corpus(conn)
    fit(corpus, ANNOTATION_MODEL)
    print(f"bm25-annotation-fit: {len(corpus)} annotation(s) -> {ANNOTATION_MODEL}")


async def _run_bm25_index(collection: str, res: _Resources, models: dict) -> None:
    from stages.bm25_index import index_collection

    pool = await res.pool()
    async with pool.acquire() as conn:
        n = await index_collection(collection, conn, res.qdrant(),
                                   models["content"], models["annotation"])
    print(f"bm25-index {collection}: {n} chunk(s) updated with sparse vectors")


async def _run_enrich(collection: str, docs, res: _Resources, *,
                      sample: int | None, yes: bool) -> None:
    from enrichment.backup import Backup
    from enrichment.client import EnrichmentClient
    from stages.enrich import EnrichDeps, enrich_collection, enrich_one
    from stages.enrich_io import make_annotation_writer
    from samples import SampleWriter

    api_key = settings.require_anthropic()
    gen_client = EnrichmentClient(api_key, settings.ANTHROPIC_ENRICH_MODEL, settings.OPUS_CONCURRENCY)
    classify_client = EnrichmentClient(api_key, settings.ANTHROPIC_CLASSIFY_MODEL,
                                       settings.CLASSIFY_CONCURRENCY)

    if sample is not None:
        writer = SampleWriter(collection, SAMPLE_DIR)
        deps = EnrichDeps(cache=None, gen_client=gen_client, classify_client=classify_client,
                          backup=None, annotation_writer=None)
        chosen = [(d, p) for d in docs for p in d.passages][:sample]
        try:
            for d, p in chosen:
                merged, usage = await enrich_one(d, p, deps, sample=True)
                rec = {"chunk_id": p.anchor, "reference": p.reference,
                       "content": p.content, "merged": merged.model_dump()}
                writer.write(rec)
                print(writer.preview(merged, p))
        finally:
            await gen_client.close(); await classify_client.close()
        print(f"\nSample written to {writer.path}")
        return

    total = sum(len(d.passages) for d in docs)
    est = estimate_enrich_cost(total)
    print(f"enrich {collection}: {total} chunks — est ${est['usd']} "
          f"({est['input_tokens']:,} in / {est['output_tokens']:,} out tokens)")
    if not yes:
        if input("Proceed? [y/N] ").strip().lower() != "y":
            print("aborted."); await gen_client.close(); await classify_client.close(); return

    # cache/pool belong to _Resources and stay open for later stages in the
    # same run — only the two Anthropic clients are this runner's to close.
    pool = await res.pool()
    deps = EnrichDeps(cache=res.cache(), gen_client=gen_client, classify_client=classify_client,
                      backup=Backup(ENRICH_DIR), annotation_writer=make_annotation_writer(pool))
    try:
        stats = await enrich_collection(docs, collection, deps, sample=False)
        gen_cost = stats.usage.cost(settings.OPUS_INPUT_COST_PER_M, settings.OPUS_OUTPUT_COST_PER_M)
        print(f"enrich {collection}: {stats.processed} processed, {stats.from_cache} from cache, "
              f"~${gen_cost:.2f} (approximate — mixed Opus/Sonnet usage)")
    finally:
        await gen_client.close(); await classify_client.close()


def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="TheoCorpus V5 ingestion pipeline.")
    ap.add_argument("--collection")
    ap.add_argument("--stage")
    ap.add_argument("--stages")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--sample", type=int)
    ap.add_argument("--sample-offset", type=int, default=0)
    ap.add_argument("--sample-random", action="store_true")
    ap.add_argument("--sample-reclassify")
    ap.add_argument("--import-backup")
    return ap.parse_args(argv)


async def _main(args: argparse.Namespace) -> None:
    from stages.parse import parse

    if args.import_backup:
        from enrichment.backup import import_backup
        from cache import Cache
        cache = Cache(CACHE_PATH); cache.init_schema()
        n = 0
        for rec in import_backup(args.import_backup):
            if rec.get("stage") == "generation":
                cache.put_generation(rec["chunk_id"], rec["content_hash"],
                                     rec["raw_facets"], rec["prompt_hash"], rec["model"])
            elif rec.get("stage") == "classification":
                cache.put_classification(rec["chunk_id"], rec["content_hash"],
                                         rec["labels"], rec["prompt_hash"], rec["model"])
            elif rec.get("stage") == "annotation":
                cache.put_annotation(rec["chunk_id"], rec["content_hash"],
                                     rec["annotation"], rec["prompt_hash"], rec["model"])
            n += 1
        cache.close()
        print(f"imported {n} backup records into {CACHE_PATH}")
        return

    if args.status:
        from cache import Cache
        cache = Cache(CACHE_PATH); cache.init_schema()
        from stages.parse import BUILDERS
        for col in BUILDERS:
            st = cache.get_collection_status(col)
            if st:
                print(f"{col:26s} enrich {st['enriched']}/{st['total_chunks']} "
                      f"{'complete' if st['complete'] else 'partial'}")
            else:
                print(f"{col:26s} enrich —")
        print(f"content model: {'present' if os.path.exists(CONTENT_MODEL) else 'missing'}")
        print(f"annotation model: {'present' if os.path.exists(ANNOTATION_MODEL) else 'missing'}")
        cache.close()
        return

    requested = [args.stage] if args.stage else (args.stages.split(",") if args.stages else [])
    stages = resolve_stages(requested)

    if args.dry_run:
        from cache import Cache
        cache = Cache(CACHE_PATH); cache.init_schema()
        for s in stages:
            if s == "enrich" and args.collection and args.collection != "all":
                docs = parse(args.collection)
                total = sum(len(d.passages) for d in docs)
                print(f"[dry-run] enrich {args.collection}: {estimate_enrich_cost(total)}")
            else:
                print(f"[dry-run] {s}")
        cache.close()
        return

    from stages.parse import BUILDERS

    if not stages:
        raise PipelineError("nothing to run: pass --stage, --stages, or --stages all")

    if args.collection == "all":
        collections = list(BUILDERS)
    elif args.collection:
        if args.collection not in BUILDERS:
            raise PipelineError(
                f"unknown collection '{args.collection}'. valid: {sorted(BUILDERS)}")
        collections = [args.collection]
    elif set(stages) <= set(_GLOBAL):
        collections = []          # global-only run needs no collection
    else:
        raise PipelineError(
            f"stage(s) {[s for s in stages if s not in _GLOBAL]} are per-collection: "
            "pass --collection <name> or --collection all")

    if args.sample is not None and stages != ["enrich"]:
        raise PipelineError("--sample only applies to a lone '--stage enrich' run")

    plan = execution_plan(stages, collections)
    res = _Resources()
    docs_by_collection: dict[str, list] = {}
    bm25_models: dict = {}

    def _docs(collection: str) -> list:
        # parse() re-reads and re-chunks source files, which is the slowest
        # non-network step; several stages in one run need the same result.
        if collection not in docs_by_collection:
            docs_by_collection[collection] = parse(collection)
        return docs_by_collection[collection]

    try:
        for stage, collection in plan:
            # Only 'embed' consults the cache to gate on enrich completeness.
            # Everything else must not touch it: res.cache() calls init_schema(),
            # which would create cache.db and break the guarantee that a
            # --sample run writes nothing outside samples/.
            gate_cache = res.cache() if stage == "embed" else None
            validate_dependencies(collection, stage, gate_cache,
                                  {"content": CONTENT_MODEL, "annotation": ANNOTATION_MODEL})
            if stage == "parse":
                docs = _docs(collection)
                print(f"parse {collection}: {len(docs)} document(s), "
                      f"{sum(len(d.passages) for d in docs)} passage(s)")
            elif stage == "reader":
                await _run_reader(collection, _docs(collection), res)
            elif stage == "enrich":
                await _run_enrich(collection, _docs(collection), res,
                                  sample=args.sample, yes=args.yes)
            elif stage == "embed":
                await _run_embed(collection, _docs(collection), res)
            elif stage == "bm25-content-fit":
                await _run_bm25_content_fit(res)
            elif stage == "bm25-annotation-fit":
                await _run_bm25_annotation_fit(res)
            elif stage == "bm25-index":
                # Loaded once per run, after validate_dependencies has confirmed
                # both config files exist.
                if not bm25_models:
                    bm25_models = {"content": load_bm25_model(CONTENT_MODEL),
                                   "annotation": load_bm25_model(ANNOTATION_MODEL)}
                await _run_bm25_index(collection, res, bm25_models)
            else:  # pragma: no cover — resolve_stages already rejects unknowns
                raise PipelineError(f"no runner wired for stage '{stage}'")
    finally:
        await res.aclose()


def main(argv=None) -> None:
    args = _parse_args(argv)
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
