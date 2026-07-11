"""Questions-index cosine audit (Pass 1 takeaway redesign).

Runs Pass 1 (generation) for a small, explicit list of chunks (via
--chunks-csv, columns: collection,anchor — same format as
scripts/enrichment_sample_run.py), embeds each facet's `question` and its
`takeaway` with the production embedding model, and reports the cosine
similarity distribution (median, p10, p90) — overall and per collection.

This audit answers one question only: now that questions are retargeted at
the takeaway (rather than the old, richer facet text), how close is each
question's embedding to its takeaway's embedding? It does NOT decide whether
the `questions` Qdrant collection should stay, be dropped, or be regenerated —
that decision belongs to a human reading these numbers. This script never
touches the `questions` collection itself, only produces the numbers.

Does NOT run against anything until you supply real chunk IDs via
--chunks-csv; there is no bundled default chunk list.

    cd datapipeline && python3 scripts/pass1_questions_cosine_audit.py \\
        --chunks-csv chunks.csv
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from scripts.enrichment_sample_run import group_by_collection, read_chunk_list
from scripts.pass1_pilot_diff_report import _generate_with_instrumentation

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    sv = sorted(values)
    idx = min(len(sv) - 1, int(p * len(sv)))
    return sv[idx]


@dataclass
class QuestionTakeawayPair:
    collection: str
    anchor: str
    question: str
    takeaway: str
    cosine: float | None = None


async def embed_all(embed_client, texts: list[str], batch_size: int) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        vectors.extend(await embed_client.embed(texts[i:i + batch_size]))
    return vectors


def build_report(pairs: list[QuestionTakeawayPair]) -> str:
    lines = ["=" * 78, "QUESTIONS-INDEX COSINE AUDIT (Pass 1 takeaway redesign)", "=" * 78, ""]
    lines.append(
        "This does not decide whether the `questions` Qdrant collection stays, "
        "dies, or gets regenerated — that decision is for a human reading these "
        "numbers. Produces numbers only.\n"
    )

    cosines = [p.cosine for p in pairs if p.cosine is not None]
    lines.append(f"OVERALL (n={len(cosines)}): "
                 f"median={percentile(cosines, 0.5):.4f}  "
                 f"p10={percentile(cosines, 0.10):.4f}  "
                 f"p90={percentile(cosines, 0.90):.4f}" if cosines else "OVERALL: no pairs")
    lines.append("")

    by_collection: dict[str, list[float]] = defaultdict(list)
    for p in pairs:
        if p.cosine is not None:
            by_collection[p.collection].append(p.cosine)

    lines.append("--- Per collection ---")
    for collection in sorted(by_collection):
        vals = by_collection[collection]
        lines.append(f"{collection:26s} n={len(vals):>4d}  "
                     f"median={percentile(vals, 0.5):.4f}  "
                     f"p10={percentile(vals, 0.10):.4f}  "
                     f"p90={percentile(vals, 0.90):.4f}")

    return "\n".join(lines)


async def run(chunks_csv: str, out_path: str | None) -> str:
    from stages.parse import parse
    from enrichment.client import EnrichmentClient
    from enrichment.render import build_context, enrichment_content
    from enrichment.prompts.generation import generation_system
    from embeddings import EmbeddingClient

    rows = read_chunk_list(chunks_csv)
    if not rows:
        raise SystemExit(f"No chunk rows found in {chunks_csv}. Expected columns: collection,anchor")
    grouped = group_by_collection(rows)

    api_key = settings.require_anthropic()
    gen_client = EnrichmentClient(api_key, settings.ANTHROPIC_ENRICH_MODEL, settings.OPUS_CONCURRENCY)
    embed_client = EmbeddingClient(settings.OPENAI_API_KEY, settings.EMBEDDING_MODEL)

    pairs: list[QuestionTakeawayPair] = []

    try:
        for collection, anchors in grouped.items():
            docs = parse(collection)
            by_anchor = {p.anchor: (d, p) for d in docs for p in d.passages}
            gen_system = generation_system(collection)

            for anchor in anchors:
                found = by_anchor.get(anchor)
                if found is None:
                    continue
                doc, passage = found
                context = build_context(doc, passage)
                passage_content = enrichment_content(passage)

                final, _first_failures, _retried, _retry_ok, _count = \
                    await _generate_with_instrumentation(gen_client, gen_system, context, passage_content)
                if final is None:
                    continue  # hard-failed generation; excluded from the audit

                for f in final.facets:
                    pairs.append(QuestionTakeawayPair(
                        collection=collection, anchor=anchor,
                        question=f.question, takeaway=f.takeaway))

        if pairs:
            questions = [p.question for p in pairs]
            takeaways = [p.takeaway for p in pairs]
            q_vectors = await embed_all(embed_client, questions, settings.EMBEDDING_BATCH_SIZE)
            t_vectors = await embed_all(embed_client, takeaways, settings.EMBEDDING_BATCH_SIZE)
            for pair, qv, tv in zip(pairs, q_vectors, t_vectors):
                pair.cosine = cosine_similarity(qv, tv)
    finally:
        await gen_client.close()
        await embed_client.close()

    report = build_report(pairs)

    if out_path is None:
        os.makedirs(SAMPLE_DIR, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M")
        out_path = os.path.join(SAMPLE_DIR, f"pass1_questions_cosine_audit-{ts}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
        f.write("\n")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunks-csv", required=True,
                    help="CSV with columns: collection,anchor (optional header row)")
    ap.add_argument("--out", default=None,
                    help="Output report path (default: samples/pass1_questions_cosine_audit-<ts>.txt)")
    args = ap.parse_args()
    written_to = asyncio.run(run(args.chunks_csv, args.out))
    print(f"Report written to {written_to}")
