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


def all_execution_order(collections: list[str]) -> list[tuple[str, str | None]]:
    order: list[tuple[str, str | None]] = []
    for c in collections:
        for s in ("parse", "reader", "enrich", "embed"):
            order.append((s, c))
    order.append(("bm25-content-fit", None))
    order.append(("bm25-annotation-fit", None))
    for c in collections:
        order.append(("bm25-index", c))
    return order


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

async def _run_enrich(collection: str, docs, *, sample: int | None, yes: bool) -> None:
    from cache import Cache
    from enrichment.backup import Backup
    from enrichment.client import EnrichmentClient
    from stages.enrich import EnrichDeps, enrich_collection, enrich_one
    from stages.enrich_io import make_annotation_writer
    from samples import SampleWriter
    import asyncpg

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

    cache = Cache(CACHE_PATH); cache.init_schema()
    pool = await asyncpg.create_pool(dsn=settings.DATABASE_URL, min_size=1, max_size=5,
                                     statement_cache_size=0)
    deps = EnrichDeps(cache=cache, gen_client=gen_client, classify_client=classify_client,
                      backup=Backup(ENRICH_DIR), annotation_writer=make_annotation_writer(pool))
    try:
        stats = await enrich_collection(docs, collection, deps, sample=False)
        gen_cost = stats.usage.cost(settings.OPUS_INPUT_COST_PER_M, settings.OPUS_OUTPUT_COST_PER_M)
        print(f"enrich {collection}: {stats.processed} processed, {stats.from_cache} from cache, "
              f"~${gen_cost:.2f} (approximate — mixed Opus/Sonnet usage)")
    finally:
        await gen_client.close(); await classify_client.close(); await pool.close(); cache.close()


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

    # execution: only the enrich stage runner is fully wired here; other stages
    # follow the same load-parse-run shape and are verified by the smoke run.
    if stages == ["enrich"] and args.collection and args.collection != "all":
        docs = parse(args.collection)
        await _run_enrich(args.collection, docs, sample=args.sample, yes=args.yes)
        return

    raise PipelineError(
        "this build wires the 'enrich' single-collection runner (incl. --sample) end-to-end; "
        "reader/embed/bm25 runners are invoked per stage in the same shape — extend _main to "
        "dispatch them following all_execution_order().")


def main(argv=None) -> None:
    args = _parse_args(argv)
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
