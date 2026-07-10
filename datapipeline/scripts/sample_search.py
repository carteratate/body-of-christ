"""Run isolated sample enrichment on chunks matched by content/reference search.

Unlike `pipeline.py --sample N` (which takes the first N chunks in parse order),
this targets specific passages by substring — e.g. a verse reference or a phrase
from the text — so you can test prompt changes against exactly the content you
care about (a known typological passage, a specific canon, etc).

Reuses the exact same isolated sample code path as `pipeline.py --sample`
(EnrichDeps with cache=None/backup=None/annotation_writer=None, enrich_one with
sample=True, three-pass generation/classification/annotation flow) — zero
writes to cache.db, Supabase, or the enrichments/ backup.
Results are written only to datapipeline/samples/, same as pipeline.py.

    cd datapipeline && python3 scripts/sample_search.py --collection bible --query "Isaiah 53"
    cd datapipeline && python3 scripts/sample_search.py --collection church-fathers --query "the flood" --limit 3
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from samples import SampleWriter

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")


def find_matches(docs, query: str, limit: int) -> list[tuple]:
    q = query.lower()
    matches = []
    for d in docs:
        for p in d.passages:
            if q in p.content.lower() or q in p.reference.lower():
                matches.append((d, p))
                if len(matches) >= limit:
                    return matches
    return matches


async def main(collection: str, query: str, limit: int) -> None:
    from stages.parse import parse
    from enrichment.client import EnrichmentClient
    from stages.enrich import EnrichDeps, enrich_one

    docs = parse(collection)
    matches = find_matches(docs, query, limit)
    if not matches:
        print(f"No chunks in '{collection}' matched {query!r}.")
        return
    print(f"Found {len(matches)} match(es) in '{collection}' for {query!r}.\n")

    api_key = settings.require_anthropic()
    gen_client = EnrichmentClient(api_key, settings.ANTHROPIC_ENRICH_MODEL, settings.OPUS_CONCURRENCY)
    classify_client = EnrichmentClient(api_key, settings.ANTHROPIC_CLASSIFY_MODEL,
                                       settings.CLASSIFY_CONCURRENCY)
    writer = SampleWriter(collection, SAMPLE_DIR)
    deps = EnrichDeps(cache=None, gen_client=gen_client, classify_client=classify_client,
                      backup=None, annotation_writer=None)
    try:
        for d, p in matches:
            merged, _usage = await enrich_one(d, p, deps, sample=True)
            rec = {"chunk_id": p.anchor, "reference": p.reference,
                   "content": p.content, "merged": merged.model_dump()}
            writer.write(rec)
            print(writer.preview(merged, p))
    finally:
        await gen_client.close(); await classify_client.close()
    print(f"\nSample written to {writer.path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True)
    ap.add_argument("--query", required=True,
                    help="Case-insensitive substring matched against chunk content or reference")
    ap.add_argument("--limit", type=int, default=1, help="Max number of matches to enrich")
    a = ap.parse_args()
    asyncio.run(main(a.collection, a.query, a.limit))
