"""Pass 1 takeaway-redesign pilot diff report.

Runs ONLY Pass 1 (generation) for a small, explicit list of chunks (via
--chunks-csv, columns: collection,anchor — same format as
scripts/enrichment_sample_run.py) and reports, per collection:

- % of takeaways failing each hard-validation check on the first attempt
  (sentence_count, word_count, banned_opener, concreteness, anti_copy), and
  the retry-success rate (how often the one allowed retry fixes it).
- The anti-copy rate specifically, as a named canary (should be ~0 after the
  hard check — this duplicates one column of the per-check breakdown above,
  surfaced on its own since it's the check most likely to silently regress).
- Word-count and sentence-count distributions for takeaways, and a separate
  sentence-count distribution for the raw working text (a cluster of uniform
  5s in the working-text distribution suggests the model is padding rather
  than writing a genuinely deeper treatment).
- Content-word Jaccard overlap between each question and its takeaway
  (stopwords removed) — high overlap means the question is still just
  restating the takeaway rather than adding real search-phrasing coverage.
- A random sample of up to 50 (working_text, takeaway) pairs, dumped for
  manual review. The two failure signatures to look for by eye: a takeaway
  asserting something absent from the working text (drift), and a takeaway
  carrying two claims at different interpretive distances (the weld came
  back — the very thing the takeaway was introduced to prevent).

This only exercises Pass 1 — no Pass 2/3 calls, no cache/backup/DB writes.
Does NOT run against anything until you supply real chunk IDs via
--chunks-csv; there is no bundled default chunk list.

    cd datapipeline && python3 scripts/pass1_pilot_diff_report.py \\
        --chunks-csv chunks.csv
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from enrichment.validation import check_takeaway, split_sentences
from scripts.enrichment_sample_run import group_by_collection, read_chunk_list

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "as", "is", "are", "was", "were", "be", "been",
    "being", "this", "that", "these", "those", "it", "its", "his", "her",
    "he", "she", "they", "their", "them", "who", "whom", "which", "what",
    "how", "why", "when", "where", "does", "do", "did", "has", "have", "had",
    "not", "no", "so", "if", "than", "then", "also", "into", "about", "over",
}
_WORD_RE = re.compile(r"[A-Za-z']+")


def _content_words(text: str) -> set[str]:
    return {w for w in (m.lower() for m in _WORD_RE.findall(text))
            if w not in _STOPWORDS and len(w) > 2}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def distribution(values: list[int]) -> dict:
    if not values:
        return {"n": 0}
    sv = sorted(values)
    n = len(sv)

    def pct(p: float) -> int:
        return sv[min(n - 1, int(p * n))]

    return {"n": n, "min": sv[0], "p25": pct(0.25), "median": pct(0.5),
            "p75": pct(0.75), "max": sv[-1]}


@dataclass
class FacetRecord:
    collection: str
    anchor: str
    text: str
    takeaway: str
    question: str


@dataclass
class CollectionStats:
    facets_checked: int = 0
    check_failure_counts: Counter = field(default_factory=Counter)
    chunks_needing_retry: int = 0
    chunks_retry_succeeded: int = 0
    chunks_hard_failed: int = 0


async def _generate_with_instrumentation(gen_client, gen_system: str, context: str,
                                         passage_content: str):
    """Runs Pass 1 once, checking every facet's takeaway with check_takeaway().
    If any facet fails, retries once (mirroring production's retry-with-errors
    policy) and re-checks. Returns (final_generation_or_None,
    first_attempt_check_failures: dict[int, list[str]], retried: bool,
    retry_succeeded: bool | None, first_attempt_facet_count: int) — this
    duplicates the *shape* of the production retry loop deliberately:
    production's _call_with_retry doesn't expose intermediate per-attempt state
    (by design, since it only needs to know success/failure), but this report
    specifically needs it.
    """
    generation, _usage = await gen_client.generate(gen_system, context)
    first_failures: dict[int, list[str]] = {}
    for i, f in enumerate(generation.facets):
        failures = check_takeaway(f.takeaway, f.text, passage_content)
        if failures:
            first_failures[i] = failures
    facet_count = len(generation.facets)

    if not first_failures:
        return generation, first_failures, False, None, facet_count

    error_text = "; ".join(
        f"facet[{i}] {msg}" for i, msgs in first_failures.items() for msg in msgs)
    retry_generation, _usage2 = await gen_client.generate(gen_system, context, retry_errors=error_text)
    retry_failed = any(
        check_takeaway(f.takeaway, f.text, passage_content) for f in retry_generation.facets)
    final = None if retry_failed else retry_generation
    return final, first_failures, True, (not retry_failed), facet_count


def build_report(stats_by_collection: dict[str, CollectionStats],
                 facet_records: list[FacetRecord]) -> str:
    lines = ["=" * 78, "PASS 1 TAKEAWAY PILOT DIFF REPORT", "=" * 78, ""]

    lines.append("--- Per-check first-attempt failure rate & retry-success rate ---")
    header = f"{'collection':26s} {'facets':>7s} {'retried':>8s} {'retry-ok':>9s}"
    lines.append(header)
    lines.append("-" * len(header))
    for collection in sorted(stats_by_collection):
        s = stats_by_collection[collection]
        retry_rate = f"{s.chunks_retry_succeeded}/{s.chunks_needing_retry}" if s.chunks_needing_retry else "0/0"
        lines.append(f"{collection:26s} {s.facets_checked:>7d} {s.chunks_needing_retry:>8d} {retry_rate:>9s}")
        if s.check_failure_counts:
            pct = {tag: f"{count}/{s.facets_checked} ({100 * count / s.facets_checked:.0f}%)"
                  for tag, count in sorted(s.check_failure_counts.items())}
            lines.append(f"    first-attempt failures by check: {pct}")
        lines.append(f"    hard-failed (never recovered): {s.chunks_hard_failed}")

    lines.append("")
    lines.append("--- Anti-copy canary (should be ~0 after the hard check) ---")
    for collection in sorted(stats_by_collection):
        s = stats_by_collection[collection]
        anti_copy = s.check_failure_counts.get("anti_copy", 0)
        rate = f"{100 * anti_copy / s.facets_checked:.1f}%" if s.facets_checked else "n/a"
        lines.append(f"{collection:26s} anti_copy rate: {rate}")

    lines.append("")
    lines.append("--- Word/sentence-count distributions (final, successful takeaways) ---")
    takeaway_words = [len(r.takeaway.split()) for r in facet_records]
    takeaway_sentences = [len(split_sentences(r.takeaway)) for r in facet_records]
    working_sentences = [len(split_sentences(r.text)) for r in facet_records]
    lines.append(f"takeaway word count:     {distribution(takeaway_words)}")
    lines.append(f"takeaway sentence count: {distribution(takeaway_sentences)}")
    lines.append(f"working_text sentence count: {distribution(working_sentences)}  "
                 f"(a spike at a uniform value suggests padding)")

    lines.append("")
    lines.append("--- Question/takeaway content-word Jaccard overlap ---")
    jaccards = [jaccard(_content_words(r.question), _content_words(r.takeaway)) for r in facet_records]
    lines.append(f"jaccard distribution: {distribution([int(j * 100) for j in jaccards])}  (x100, i.e. percent)")
    if jaccards:
        threshold_idx = max(0, int(0.9 * len(jaccards)) - 1)
        top_decile_threshold = sorted(jaccards)[threshold_idx]
        flagged = [r for r, j in zip(facet_records, jaccards) if j >= top_decile_threshold and j > 0]
        lines.append(f"top-decile (jaccard >= {top_decile_threshold:.2f}) — {len(flagged)} flagged for manual reading:")
        for r in flagged[:20]:
            lines.append(f"    [{r.collection}:{r.anchor}] Q: {r.question!r}  TAKEAWAY: {r.takeaway!r}")

    lines.append("")
    lines.append("--- Random sample of (working_text, takeaway) pairs for manual review ---")
    sample = random.sample(facet_records, min(50, len(facet_records))) if facet_records else []
    for r in sample:
        lines.append(f"[{r.collection}:{r.anchor}]")
        lines.append(f"  WORKING:  {r.text}")
        lines.append(f"  TAKEAWAY: {r.takeaway}")
        lines.append("")

    return "\n".join(lines)


async def run(chunks_csv: str, out_path: str | None) -> str:
    from stages.parse import parse
    from enrichment.client import EnrichmentClient
    from enrichment.render import build_context, enrichment_content
    from enrichment.prompts.generation import generation_system

    rows = read_chunk_list(chunks_csv)
    if not rows:
        raise SystemExit(f"No chunk rows found in {chunks_csv}. Expected columns: collection,anchor")
    grouped = group_by_collection(rows)

    api_key = settings.require_anthropic()
    gen_client = EnrichmentClient(api_key, settings.ANTHROPIC_ENRICH_MODEL, settings.OPUS_CONCURRENCY)

    stats_by_collection: dict[str, CollectionStats] = defaultdict(CollectionStats)
    facet_records: list[FacetRecord] = []

    try:
        for collection, anchors in grouped.items():
            docs = parse(collection)
            by_anchor = {p.anchor: (d, p) for d in docs for p in d.passages}
            gen_system = generation_system(collection)
            stats = stats_by_collection[collection]

            for anchor in anchors:
                found = by_anchor.get(anchor)
                if found is None:
                    continue
                doc, passage = found
                context = build_context(doc, passage)
                passage_content = enrichment_content(passage)

                final, first_failures, retried, retry_succeeded, facet_count = \
                    await _generate_with_instrumentation(gen_client, gen_system, context, passage_content)

                stats.facets_checked += facet_count
                for msgs in first_failures.values():
                    for msg in msgs:
                        tag = msg.split(":", 1)[0]
                        stats.check_failure_counts[tag] += 1
                if retried:
                    stats.chunks_needing_retry += 1
                    if retry_succeeded:
                        stats.chunks_retry_succeeded += 1
                    else:
                        stats.chunks_hard_failed += 1

                if final is not None:
                    for f in final.facets:
                        facet_records.append(FacetRecord(
                            collection=collection, anchor=anchor,
                            text=f.text, takeaway=f.takeaway, question=f.question))
    finally:
        await gen_client.close()

    report = build_report(stats_by_collection, facet_records)

    if out_path is None:
        os.makedirs(SAMPLE_DIR, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M")
        out_path = os.path.join(SAMPLE_DIR, f"pass1_pilot_diff_report-{ts}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
        f.write("\n")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunks-csv", required=True,
                    help="CSV with columns: collection,anchor (optional header row)")
    ap.add_argument("--out", default=None,
                    help="Output report path (default: samples/pass1_pilot_diff_report-<ts>.txt)")
    args = ap.parse_args()
    written_to = asyncio.run(run(args.chunks_csv, args.out))
    print(f"Report written to {written_to}")
