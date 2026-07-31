#!/usr/bin/env python
"""Batch evaluation: run N pipelines over a query suite and judge each query.

Runs in-process (no HTTP server) so a run is one command. Appends one JSON line
per query as it completes, and skips already-completed queries on restart — a
throttled Cohere key makes these runs long, and losing a partial run wastes quota
that cannot be recovered.

Usage:
    python scripts/run_eval_suite.py --out /tmp/eval.jsonl
    python scripts/run_eval_suite.py --queries 0 1 2 --out /tmp/smoke.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
for _n in ("app.rag.steps.rerank_cohere", "app.rag.steps.rerank",
           "app.rag.steps.llm_rerank.listwise", "app.rag.compare.judge"):
    logging.getLogger(_n).setLevel(logging.INFO)

# Round 3 shipping comparison: production plus the two credible lower-cost
# Cohere→listwise challengers. Retired round-2 variants remain available through
# ``--pipelines`` for targeted follow-up work.
PIPELINES = [
    "hyde_haiku",               # production baseline (pointwise Haiku)
    "hyde_cohere_haiku",        # two-stage, listwise Haiku
    "hyde_cohere_luna",         # two-stage, listwise Luna
]

COLLECTIONS = ["bible", "catechism", "summa", "encyclicals", "church-fathers"]

# Each query targets a different retrieval behaviour, not just a different topic.
QUERIES: list[tuple[str, str, str]] = [
    ("Why does God allow suffering? What is the Christian answer to evil and pain?",
     "doctrinal", "broad; every collection has material"),
    ("Is it ever right to lie? Does intention matter, or is deception always wrong?",
     "moral_practical", "moral reasoning; should favour Summa + Catechism"),
    ("What does the Church teach about angels?",
     "doctrinal_narrow", "SHORT query, sparse topic — recall stress"),
    ("What does the tradition say about spiritual dryness, when God feels absent?",
     "devotional", "should favour church-fathers; tests sparse-collection surfacing"),
    ("Can a person be obligated to disobey a law or authority? When does conscience "
     "override obedience?",
     "juridical_moral", "tests a collection easily crowded out"),
    ("What is the purpose of confession? How does absolution actually work?",
     "doctrinal_juridical", "sacramental mechanics"),
    ("How do grace and free will coexist? If God knows everything, how can choices be free?",
     "philosophical", "Summa-dominant; per-title cap stress"),
    ("What does the Church teach about killing in war and in self-defense?",
     "moral_contested", "doctrinal development; multi-angle stress"),
    ("What is the soul, and what happens to it after death?",
     "doctrinal_crosscutting", "every collection applies; redundancy stress"),
    ("Scripture says God is love and God is truth. In what sense does God not merely "
     "have these qualities but is them, and are there other things God simply is?",
     "doctrinal_technical", "LONGEST query; HyDE + query-length stress"),

    # --- Queries 10-19: register diversity ---------------------------------------
    # Queries 0-9 are all written in a formal, third-person, propositional voice
    # ("What does the Church teach about X"), which is close to how the corpus
    # itself is written. That under-exercises HyDE, whose entire job is bridging the
    # gap between how a user phrases something and how a 13th-century text does.
    # These ten deliberately vary REGISTER as well as topic: first-person, objection-
    # laden, second-hand, grieving, colloquial. Corpus support for each was checked
    # against the five eval collections before inclusion.
    ("How do I know what God actually wants me to do with my life?",
     "vocational_reflective",
     "first-person and abstract with NO keyword anchor - the purest HyDE test here. "
     "Corpus support is thin (no Ignatian discernment literature), so a low ceiling "
     "for every pipeline is expected; it measures graceful degradation"),
    ("Why does the Church say sex belongs only in marriage? It feels arbitrary.",
     "moral_contested_objection",
     "objection embedded in the query; encyclical-dominant. NOTE: Humanae Vitae and "
     "Theology of the Body are NOT in the eval collections, so Casti Connubii and "
     "Veritatis Splendor carry this alone - partly measures a corpus gap"),
    ("What's happening when Jacob wrestles with God at the Jabbok, and why does he "
     "get a new name?",
     "scriptural_narrative",
     "narrative retrieval: the right answer is one pericope plus commentary, not a "
     "survey. Tests whether a reranker trained on propositional relevance can handle "
     "a story, and stresses best_passage_selection"),
    ("My friend says the Eucharist is just a symbol. What's the actual argument that "
     "it's really Jesus?",
     "apologetic_secondhand",
     "adversarial framing at one remove, colloquial register"),
    ("Someone I love died and I can't bring myself to pray. Is that okay?",
     "pastoral_grief",
     "low keyword density, emotionally framed, non-propositional - the corpus never "
     "says 'it's okay', so retrieval must bridge to consolation material"),
    ("Is it wrong to want to be wealthy? What do I actually owe the poor?",
     "moral_social",
     "inverts the suite's Summa gravity: encyclicals + Bible dominant"),
    ("What if I'm not sure I believe any of this anymore?",
     "reflective_doubt",
     "near-neighbour discrimination - must NOT simply return query 3's spiritual "
     "dryness material; doubt and desolation are adjacent but distinct"),
    ("Why do Catholics pray to Mary? Isn't that worshipping her?",
     "apologetic_lexical_gap",
     "pure lexical mismatch: the user says 'worship'/'pray to', the corpus says "
     "veneration, dulia, intercession. The sharpest test of what FTS contributes"),
    ("How can the Church be holy when priests abused people and bishops covered it up?",
     "contested_selfcritical",
     "the corpus is self-authored, so this tests whether retrieval surfaces genuinely "
     "self-critical material or defensive material; modern framing with no direct "
     "patristic vocabulary"),
    ("I get distracted every single time I try to pray. How do you actually pray?",
     "practical_prayer",
     "a near-exact match exists (CCC 2725-2745 on distraction in prayer), so this "
     "tests whether pipelines find the obvious right passage or drift to abstraction"),

    # --- Queries 20-79: Round 3 expansion -----------------------------------------
    ("What does the Church mean by the Trinity—one God in three persons?",
     "canonical_doctrine", "central dogma; canonical-section selection across collections"),
    ("Why did God become human? What did the Incarnation accomplish that could not happen otherwise?",
     "canonical_doctrine", "Incarnation and atonement; must beat generic Christmas material"),
    ("What is original sin, and in what sense are people born with it if they did not personally commit Adam's sin?",
     "doctrinal_distinction", "inherited condition versus personal guilt"),
    ("What happens in baptism? Is it only a public symbol, or does baptism actually do something?",
     "sacramental_apologetic", "sacramental causality rather than generic baptism references"),
    ("Why does the Church teach that Mary remained a virgin?",
     "marian_doctrine", "Marian doctrine distinct from intercession and worship"),
    ("What does 'the resurrection of the body' mean? Do Christians become embodied again after death?",
     "eschatology_distinction", "final resurrection versus the intermediate state of the soul"),
    ("What is purgatory, and why would someone who is already saved still need purification?",
     "eschatology_doctrinal", "purification versus hell, suffering, or loss of salvation"),
    ("What is the communion of saints?",
     "doctrinal_narrow", "short-query recall across ecclesiology and eschatology"),
    ("What does it mean to say the Church is one, holy, catholic, and apostolic?",
     "ecclesiology_multifacet", "four required facets with clear canonical treatments"),
    ("What is providence? Does God actively govern everything that happens?",
     "doctrinal_philosophical", "divine governance distinct from foreknowledge and theodicy"),

    ("What is the difference between the Immaculate Conception and the Virgin Birth?",
     "near_neighbor", "two commonly confused Marian doctrines"),
    ("What is the difference between Christ's Ascension and Mary's Assumption?",
     "near_neighbor", "similar vocabulary but different subjects and claims"),
    ("How is the Trinity different from saying that God appears in three different modes?",
     "heresy_distinction", "orthodox Trinity versus modalism"),
    ("What is the difference between mortal and venial sin?",
     "moral_distinction", "requires criteria and consequences, not generic sin passages"),
    ("What is the difference between temptation and sin? Have I sinned merely because an evil thought occurred to me?",
     "pastoral_moral", "involuntary movement versus consent and moral action"),
    ("How are contrition, confession, penance, and absolution different?",
     "sacramental_multifacet", "four related concepts that must not be collapsed"),
    ("What is the difference between worship, veneration, and honor?",
     "doctrinal_distinction", "technical distinctions behind devotional practice"),
    ("How is papal infallibility different from saying the pope cannot make mistakes?",
     "authority_distinction", "infallibility versus impeccability, prudence, or omniscience"),
    ("What is the difference between natural law and whatever laws a government happens to enact?",
     "juridical_distinction", "moral law versus positive civil law"),
    ("How can Jesus be fully God and fully human without being two persons?",
     "christology_technical", "nature versus person and canonical Christological formulation"),

    ("Is stealing food ever morally permissible if someone's family is starving?",
     "moral_case", "property, necessity, intention, and circumstances"),
    ("Can an action with a good effect and a bad effect ever be morally permitted?",
     "moral_implicit_concept", "retrieve double-effect reasoning without naming it"),
    ("Is refusing extraordinary medical treatment the same as euthanasia?",
     "bioethics_distinction", "omission versus direct killing; corpus-ceiling check"),
    ("Do I have to forgive someone who has never apologized and may hurt me again?",
     "pastoral_moral", "forgiveness versus reconciliation, justice, and safety"),
    ("When does anger become sinful? Is anger at injustice ever good?",
     "moral_distinction", "passion versus consent, righteous anger versus excess"),
    ("Can private property be morally legitimate if the goods of creation are meant for everyone?",
     "social_doctrine", "ownership versus universal destination of goods"),
    ("Is civil disobedience ever justified?",
     "political_moral", "public lawbreaking distinct from private conscience"),
    ("Are people morally responsible for actions done under fear, coercion, addiction, or severe pressure?",
     "moral_multifacet", "voluntariness and diminished culpability across conditions"),
    ("Is the death penalty compatible with Christian teaching?",
     "moral_development", "development and corpus-era tension; report by source date"),
    ("Can Christians use wealth to enjoy good things, or must everything beyond basic necessity be given away?",
     "moral_practical", "moderation and use of goods rather than the existing duty-to-poor framing"),

    ("Why does God ask Abraham to sacrifice Isaac?",
     "scriptural_narrative", "difficult narrative, testing, obedience, and typology"),
    ("What does Jesus mean when he says to turn the other cheek?",
     "scriptural_moral", "specific saying requiring qualified moral interpretation"),
    ("Why does Jesus cry, 'My God, my God, why have you forsaken me?' if he is divine?",
     "scriptural_christology", "Passion, Psalm 22, and Christology"),
    ("What does Paul mean when he says we are justified by faith apart from works?",
     "scriptural_soteriology", "Pauline justification with balancing qualifications"),
    ("How should Catholics understand James saying that a person is justified by works and not by faith alone?",
     "scriptural_soteriology", "paired faith-and-works interpretation from James"),
    ("Why does Jesus call Peter the rock, and what does that passage establish?",
     "scriptural_ecclesiology", "exact pericope plus Petrine-authority interpretation"),
    ("What does it mean to be 'born again' or 'born from above' in John 3?",
     "scriptural_sacramental", "translation ambiguity, conversion, and baptism"),
    ("Why are some of the Psalms so violent? Can Christians pray for judgment against enemies?",
     "scriptural_genre", "imprecation, genre, spiritual interpretation, and pastoral use"),
    ("How can doctrine develop without the Church changing what Christians are required to believe?",
     "development_historical", "continuity versus contradiction"),
    ("Why were councils needed if the apostles already taught the faith?",
     "authority_historical", "heresy, clarification, and conciliar authority"),

    ("Why should Christians trust Sacred Tradition? How is it different from merely human traditions?",
     "authority_apologetic", "apostolic Tradition versus changeable customs and traditions of men"),
    ("How did the Church know which books belong in the Bible if the Bible does not contain its own table of contents?",
     "canon_historical", "canon formation and ecclesial authority; validate patristic coverage"),
    ("What is apostolic succession, and why does an unbroken line of bishops matter?",
     "ecclesiology_historical", "continuity of office and teaching across Scripture and Fathers"),
    ("Are Catholics required to agree with every statement made by a pope or bishop?",
     "authority_adversarial", "levels of authority, assent, and prudential judgment"),
    ("If salvation is a gift of grace, in what sense can Christians merit anything before God?",
     "soteriology_distinction", "grace-enabled merit versus independently earning salvation"),
    ("Does God predestine some people to salvation? Does he also predestine anyone to damnation?",
     "soteriology_contested", "predestination, freedom, and reprobation with qualifications"),
    ("Can someone lose salvation after truly believing and being baptized?",
     "soteriology_apologetic", "perseverance, mortal sin, grace, and restoration"),
    ("Does the Church teach that anyone is definitely in hell, or that hell might be empty?",
     "eschatology_contested", "defined doctrine versus theological hope; corpus-risk query"),
    ("What is an annulment? Is it just a Catholic version of divorce?",
     "sacramental_apologetic", "marital validity versus dissolution"),
    ("Why can someone be excommunicated? Does excommunication mean the Church believes that person is damned?",
     "canonical_pastoral", "medicinal discipline versus final judgment; corpus-risk query"),

    ("Why does the Church have binding rules about fasting and abstinence? Can an external practice actually help someone spiritually?",
     "ascetical_practical", "bodily discipline, obedience, penance, and interior conversion"),
    ("I keep confessing the same sins. Does that mean my repentance is not real or that confession is not working?",
     "pastoral_repetitive_sin", "habit, contrition, perseverance, and sacramental practice"),
    ("How can I tell the difference between a guilty conscience and scrupulosity?",
     "pastoral_discernment", "conscience formation versus excessive fear; corpus-risk query"),
    ("Jesus warns against vain repetition, so why do Catholics repeat prayers such as the Rosary?",
     "prayer_apologetic", "empty repetition versus persistence and meditation"),
    ("Is contemplative prayer only for monks and mystics, or is every Christian called to it?",
     "spirituality_practical", "contemplation across states of life"),
    ("If caring for other people is good, why would anyone withdraw from the world to live a monastic or contemplative life?",
     "spirituality_objection", "active versus contemplative life and differing vocations"),
    ("The Bible and Christian societies tolerated slavery. How can the Church claim moral authority after that?",
     "historical_selfcritical", "development, dignity, and historical complicity; corpus-risk query"),
    ("Did the Church change its teaching about religious freedom, or did Vatican II contradict earlier popes?",
     "development_contested", "development versus contradiction; councils-dependent corpus-risk query"),
    ("Why did Christians once condemn charging interest as usury when modern economies depend on lending?",
     "moral_development_historical", "object and circumstance across changed economic structures"),
    ("If Church leaders have sometimes been corrupt or disastrously wrong in practice, why trust the Church to teach reliably?",
     "ecclesiology_adversarial", "teaching reliability versus personal holiness and governance"),
]


# Failures no amount of retrying will clear. Everything else (timeouts, 429s, DNS)
# is transient and worth a retry.
_FATAL_MARKERS = (
    "credit balance is too low",
    "authentication_error",
    "invalid x-api-key",
    "permission_error",
    "account is not authorized",
)


def _abort_if_fatal(message: str, where: str) -> None:
    """Stop the whole suite on an error that retrying cannot fix.

    Skipping the query and continuing is right for a transient blip, but wrong for a
    dead API key: each subsequent query still pays Cohere and OpenAI in full to
    produce results that cannot be judged. Raises rather than returning so no caller
    can accidentally swallow it.
    """
    low = (message or "").lower()
    hit = next((m for m in _FATAL_MARKERS if m in low), None)
    if hit:
        raise SystemExit(
            f"\nFATAL at {where}: {hit!r}\n"
            f"  {message[:300]}\n"
            f"  Aborting the suite — retrying cannot fix this, and continuing would\n"
            f"  keep paying Cohere/OpenAI for queries the judge cannot score.\n"
            f"  Completed queries are already written; fix the credential and re-run\n"
            f"  the same command to resume."
        )


def _preflight(model: str) -> None:
    """One minimal Anthropic call before any billable work begins.

    The suite spends on Cohere and OpenAI before it ever reaches the judge, so a dead
    Anthropic key would otherwise be discovered only after a full query's worth of
    spend. This costs a few tokens and turns that into an immediate, clear failure.
    """
    import anthropic

    from app.config import settings

    try:
        anthropic.Anthropic(api_key=settings.anthropic_api_key).messages.create(
            model=model, max_tokens=4, messages=[{"role": "user", "content": "ok"}],
        )
    except Exception as exc:  # noqa: BLE001 - surfaced immediately below
        _abort_if_fatal(str(exc), "preflight")
        raise SystemExit(f"\nFATAL: preflight Anthropic call failed: {exc}") from exc
    print("preflight : Anthropic OK", flush=True)


async def _preflight_dependencies() -> None:
    """Verify every paid/data dependency before starting a resumable batch."""
    from app.db import get_pool
    from app.rag.qdrant_client import get_qdrant_client
    from app.rag.steps import embed, rerank_cohere
    from app.rag.steps.cost_tracker import CostTracker
    from app.rag.steps.llm_rerank.openai_provider import PROVIDER as luna
    from app.rag.steps.rerank_haiku import PROVIDER as haiku

    checks = {
        "Postgres": lambda: get_pool().fetchval("SELECT 1"),
        "Qdrant": lambda: get_qdrant_client().get_collections(),
        "OpenAI embedding": lambda: embed.run("evaluation preflight", CostTracker()),
        "Anthropic reranker": lambda: haiku.score(
            "Return only [].", "Return [].", 16,
        ),
        "OpenAI reranker": lambda: luna.score(
            "Return only [].", "Return [].", 16,
        ),
        "Cohere": lambda: rerank_cohere._client.rerank(
            model="rerank-v4.0-pro",
            query="evaluation preflight",
            documents=["evaluation preflight"],
            top_n=1,
        ),
    }
    for label, make_call in checks.items():
        try:
            await make_call()
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            _abort_if_fatal(message, f"preflight/{label}")
            raise SystemExit(
                f"\nFATAL: {label} preflight failed before batch spend: {message}"
            ) from exc
        print(f"preflight : {label} OK", flush=True)


def _hash_files(paths: list[Path]) -> str:
    return hashlib.sha256(b"".join(path.read_bytes() for path in paths)).hexdigest()


def _artifact_fingerprint(pipelines: list[str], quota: int) -> dict:
    """Identity of inputs that can change captured retrieval candidates."""
    from app.config import settings
    from app.rag.pipelines.registry import PIPELINES as REGISTRY

    root = Path(__file__).parents[1]
    capture_files = [
        root / "app/rag/compare/shared_runner.py",
        root / "app/rag/pipelines/runner.py",
        root / "app/rag/steps/embed.py",
        root / "app/rag/steps/hyde_s25.py",
        root / "app/rag/steps/retrieve_fts.py",
        root / "app/rag/steps/retrieve_vector.py",
        root / "app/rag/steps/rrf.py",
        root / "app/rag/steps/fetch_positions.py",
    ]
    query_hash = hashlib.sha256(
        json.dumps(QUERIES, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "collections": sorted(COLLECTIONS),
        "quota": quota,
        "query_manifest_sha256": query_hash,
        "capture_implementation_sha256": _hash_files(capture_files),
        "retrieval_configs": {
            name: dataclasses.asdict(REGISTRY[name].retrieval)
            for name in sorted(pipelines)
        },
        "models": {
            "hyde": settings.hyde_model,
            "embedding": "text-embedding-3-large",
        },
        "thresholds": {
            "candidate_multiplier": settings.candidate_multiplier,
            "cohere_max_pool": settings.cohere_max_pool,
            "retrieval_k_min": settings.retrieval_k_min,
            "retrieval_k_max": settings.retrieval_k_max,
        },
    }


def _fingerprint(pipelines: list[str], quota: int) -> dict:
    """Identity of the experiment, so a resumed run cannot silently mix configs.

    Resumability keys on query_idx alone, so without this, resuming after editing
    the pipeline list, quota, collections, judge model, or any scoring threshold
    would append new-shape records to the same file. Every aggregate would then
    average each pipeline over whichever query subset happened to include it.
    """
    from app.config import settings
    from app.rag.compare.judge import WEIGHTS, _JUDGE_MODEL
    from app.rag.pipelines.registry import PIPELINES as REGISTRY

    implementation_files = [
        Path(__file__),
        Path(__file__).parents[1] / "app/rag/pipelines/runner.py",
        Path(__file__).parents[1] / "app/rag/compare/shared_runner.py",
        Path(__file__).parents[1] / "app/rag/steps/rerank.py",
        Path(__file__).parents[1] / "app/rag/steps/retrieve_fts.py",
        Path(__file__).parents[1] / "app/rag/steps/retrieve_vector.py",
        Path(__file__).parents[1] / "app/rag/steps/llm_rerank/listwise.py",
        Path(__file__).parents[1] / "app/rag/steps/llm_rerank/pointwise.py",
        Path(__file__).parents[1] / "app/rag/compare/judge.py",
    ]
    implementation_hash = _hash_files(implementation_files)
    query_hash = hashlib.sha256(
        json.dumps(QUERIES, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()

    return {
        "pipelines": sorted(pipelines),
        "collections": sorted(COLLECTIONS),
        "quota": quota,
        "judge_model": _JUDGE_MODEL,
        "judge_weights": WEIGHTS,
        "query_manifest_sha256": query_hash,
        "implementation_sha256": implementation_hash,
        "artifact_fingerprint": _artifact_fingerprint(pipelines, quota),
        "pipeline_configs": {
            name: dataclasses.asdict(REGISTRY[name]) for name in sorted(pipelines)
        },
        "models": {
            "hyde": settings.hyde_model,
            "rerank_luna": settings.rerank_luna_model,
        },
        "thresholds": {
            "cohere_keep_score_floor": settings.cohere_keep_score_floor,
            "listwise_include_floor": settings.listwise_include_floor,
            "pointwise_score_cutoff": settings.pointwise_score_cutoff,
            "guarantee_min_score": settings.guarantee_min_score,
            "llm_pool_global_cap": settings.llm_pool_global_cap,
            "cohere_pool_safety": settings.cohere_pool_safety,
            "cohere_max_pool": settings.cohere_max_pool,
            "cohere_max_tokens_per_doc": settings.cohere_max_tokens_per_doc,
            "retrieval_k_min": settings.retrieval_k_min,
            "retrieval_k_max": settings.retrieval_k_max,
            "llm_rerank_max_tokens": settings.llm_rerank_max_tokens,
        },
    }


def _completed(path: Path, fingerprint: dict) -> set[int]:
    """Query indices already recorded, refusing to resume an incompatible file."""
    if not path.exists():
        return set()
    done: set[int] = set()
    for n, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            # A crash mid-write leaves a truncated line. Refuse rather than skip:
            # skipping silently drops the query AND the record it ran into.
            raise SystemExit(
                f"{path} line {n} is corrupt (truncated write?). Inspect and remove "
                f"the bad line before resuming."
            )
        if not rec.get("fingerprint"):
            raise SystemExit(
                f"{path} line {n} has no experiment fingerprint; resume into a new file."
            )
        if rec["fingerprint"] != fingerprint:
            raise SystemExit(
                f"{path} was produced with a different configuration.\n"
                f"  existing: {json.dumps(rec['fingerprint'], sort_keys=True)}\n"
                f"  current : {json.dumps(fingerprint, sort_keys=True)}\n"
                f"Scores are not comparable across configurations — write to a new "
                f"--out file."
            )
        if "query_idx" in rec:
            if rec["query_idx"] in done:
                raise SystemExit(
                    f"{path} contains duplicate query_idx={rec['query_idx']} at line {n}."
                )
            done.add(rec["query_idx"])
    return done


def _append_jsonl(path: Path, record: dict) -> None:
    """Durably append one complete record before advancing to the next query."""
    with path.open("a") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_json_atomic(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value))
    os.replace(tmp, path)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/eval.jsonl")
    ap.add_argument("--queries", nargs="+", type=int, default=None)
    ap.add_argument("--pipelines", nargs="+", default=PIPELINES)
    ap.add_argument("--quota", type=int, default=4)
    ap.add_argument("--artifacts-dir", default=None)
    ap.add_argument("--max-consecutive-ineligible", type=int, default=3)
    args = ap.parse_args()

    from app.db import close_pool, init_pool
    from app.llm import close_llm, init_llm
    from app.rag.api_keys import close_api_keys, init_api_keys
    from app.rag.compare import judge, overlap
    from app.rag.compare import shared_runner
    from app.rag.pipelines.registry import PIPELINES as REGISTRY
    from app.rag.qdrant_client import close_qdrant, init_qdrant
    from app.rag.steps.embed import close_embed, init_embed
    from app.rag.steps.llm_rerank.openai_provider import close as close_luna
    from app.rag.steps.llm_rerank.openai_provider import init as init_luna
    from app.rag.steps.rerank_cohere import close_cohere, init_cohere
    from app.rag.steps.rerank_haiku import close_rerank, init_rerank

    await init_pool()
    init_llm(); init_embed(); init_qdrant(); init_api_keys()
    init_rerank(); init_cohere(); init_luna(); judge.init_judge()

    out = Path(args.out)
    artifacts_dir = (
        Path(args.artifacts_dir)
        if args.artifacts_dir else out.with_suffix("").with_name(out.stem + "-artifacts")
    )
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    attempts_out = out.with_suffix(".attempts.jsonl")
    fingerprint = _fingerprint(args.pipelines, args.quota)
    artifact_fingerprint = fingerprint["artifact_fingerprint"]
    done = _completed(out, fingerprint)
    idxs = args.queries if args.queries is not None else list(range(len(QUERIES)))
    todo = [i for i in idxs if i not in done]
    configs = [REGISTRY[name] for name in args.pipelines]
    prior_attempts: dict[int, int] = {}
    if attempts_out.exists():
        for line in attempts_out.read_text().splitlines():
            if line.strip():
                attempt = json.loads(line)
                qi = attempt.get("query_idx")
                prior_attempts[qi] = prior_attempts.get(qi, 0) + 1

    def append_attempt(record: dict) -> None:
        _append_jsonl(attempts_out, record)

    print(f"pipelines : {len(args.pipelines)} -> {', '.join(args.pipelines)}")
    print(f"queries   : {len(todo)} to run ({len(done)} already complete)")
    print(f"cohere    : ~{sum(1 for p in args.pipelines if 'cohere' in p) * len(COLLECTIONS)}"
          f" calls/query = ~{sum(1 for p in args.pipelines if 'cohere' in p) * len(COLLECTIONS) * len(todo)} total")
    print(f"output    : {out}", flush=True)
    print(f"artifacts : {artifacts_dir}", flush=True)
    print(f"attempts  : {attempts_out}", flush=True)

    from app.rag.compare.judge import _JUDGE_MODEL  # noqa: PLC0415
    _preflight(_JUDGE_MODEL)
    await _preflight_dependencies()
    print(flush=True)

    t_suite = time.perf_counter()
    consecutive_ineligible = 0

    def note_ineligible(qi: int) -> None:
        nonlocal consecutive_ineligible
        consecutive_ineligible += 1
        if consecutive_ineligible >= args.max_consecutive_ineligible:
            raise SystemExit(
                f"\nCIRCUIT BREAKER: {consecutive_ineligible} consecutive queries "
                f"were ineligible (latest q{qi}). Stopping before more provider "
                f"spend. Inspect the attempts ledger, fix the systemic cause, and "
                f"resume the same query set."
            )

    try:
        for n, qi in enumerate(todo, 1):
            query, category, rationale = QUERIES[qi]
            print(f"\n{'='*80}\n[{n}/{len(todo)}] q{qi} ({category}): {query[:66]}...\n{'='*80}",
                  flush=True)
            t0 = time.perf_counter()
            attempt_number = prior_attempts.get(qi, 0) + 1
            try:
                artifact_path = artifacts_dir / f"q{qi:03d}.json"
                if artifact_path.exists():
                    stored = json.loads(artifact_path.read_text())
                    if stored.get("artifact_fingerprint") != artifact_fingerprint:
                        raise RuntimeError(f"{artifact_path} fingerprint mismatch")
                    artifacts = shared_runner.SharedArtifacts.from_dict(stored["shared"])
                    if artifacts.query != query:
                        raise RuntimeError(f"{artifact_path} query mismatch")
                    print("  shared retrieval: replaying cached artifact", flush=True)
                else:
                    artifacts = await shared_runner.capture(
                        query, COLLECTIONS, args.quota, configs,
                    )
                    if artifacts.quality_eligible:
                        _write_json_atomic(artifact_path, {
                            "artifact_fingerprint": artifact_fingerprint,
                            "query_idx": qi,
                            "shared": artifacts.to_dict(),
                        })

                if not artifacts.quality_eligible:
                    append_attempt({
                        "fingerprint": fingerprint,
                        "query_idx": qi,
                        "attempt": attempt_number,
                        "stage": "shared_capture",
                        "eligible": False,
                        "elapsed_s": round(time.perf_counter() - t0, 2),
                        "shared": artifacts.to_dict(),
                    })
                    print(
                        f"  QUARANTINED q{qi}: shared retrieval degraded "
                        f"{artifacts.degradations}; judge not called",
                        flush=True,
                    )
                    note_ineligible(qi)
                    continue

                results = await shared_runner.replay(artifacts, configs)

                by_pipe = {}
                for r in results:
                    # The stage reports its own degradation. Inferring it from the
                    # cost breakdown misses partial failures: cost is recorded per
                    # SUCCESSFUL Cohere collection, so 4-of-5 succeeding still leaves
                    # the step present, and listwise cost is recorded before parsing.
                    degraded = bool(r.degradations)
                    by_pipe[r.pipeline] = {
                        "wall_s": round(r.total_duration_s, 3),
                        "throttle_wait_s": round(r.throttle_wait_s, 3),
                        "wall_s_ex_throttle": round(
                            r.total_duration_s - r.throttle_wait_s, 3),
                        "degraded": degraded,
                        "degradations": r.degradations,
                        "degradation_events": r.degradation_events,
                        "quality_eligible": r.quality_eligible,
                        "latency_eligible": r.latency_eligible,
                        "total_cost": r.total_cost,
                        "cost_breakdown": r.cost_breakdown,
                        "n_results": len(r.chunks),
                        "collections": sorted({c.collection for c in r.chunks}),
                        "top": [
                            {"rank": i + 1, "collection": c.collection,
                             "reference": c.reference, "score": round(c.reranker_score, 4)}
                            for i, c in enumerate(r.chunks[:5])
                        ],
                    }

                ineligible = [p for p, value in by_pipe.items() if not value["quality_eligible"]]
                if ineligible:
                    append_attempt({
                        "fingerprint": fingerprint,
                        "query_idx": qi,
                        "attempt": attempt_number,
                        "stage": "pipeline_replay",
                        "eligible": False,
                        "elapsed_s": round(time.perf_counter() - t0, 2),
                        "shared": {
                            "cost_breakdown": artifacts.cost_breakdown,
                            "total_cost": artifacts.total_cost,
                            "duration_s": artifacts.duration_s,
                        },
                        "pipelines": by_pipe,
                    })
                    print(
                        f"  QUARANTINED q{qi}: ineligible pipelines={ineligible}; "
                        "judge not called",
                        flush=True,
                    )
                    note_ineligible(qi)
                    continue

                ov = overlap.run(results)
                jr = await judge.run(query, results, ov)
                _abort_if_fatal(jr.comparative_analysis, f"q{qi}")

                scored = {sc.pipeline for sc in jr.scores}
                if (
                    not jr.valid
                    or all(sc.weighted_total == 0.0 for sc in jr.scores)
                    or scored != set(args.pipelines)
                ):
                    append_attempt({
                        "fingerprint": fingerprint,
                        "query_idx": qi,
                        "attempt": attempt_number,
                        "stage": "judge",
                        "eligible": False,
                        "elapsed_s": round(time.perf_counter() - t0, 2),
                        "pipelines": by_pipe,
                        "judge": dataclasses.asdict(jr),
                    })
                    print(f"  QUARANTINED q{qi}: judge output invalid; re-run to retry")
                    note_ineligible(qi)
                    continue

                rec = {
                    "fingerprint": fingerprint,
                    "query_idx": qi, "query": query, "category": category,
                    "rationale": rationale,
                    "elapsed_s": round(time.perf_counter() - t0, 2),
                    "attempt": attempt_number,
                    "shared": {
                        "wall_s": round(artifacts.duration_s, 3),
                        "total_cost": artifacts.total_cost,
                        "cost_breakdown": artifacts.cost_breakdown,
                    },
                    "pipelines": by_pipe,
                    "judge": dataclasses.asdict(jr),
                    "overlap_shared": len(ov.shared),
                }
                _append_jsonl(out, rec)
                consecutive_ineligible = 0

                ranked = sorted(jr.scores, key=lambda s: s.weighted_total, reverse=True)
                degraded_n = sum(1 for v in by_pipe.values() if v["degraded"])
                print(f"  judge order: {' > '.join(f'{s.pipeline}={s.weighted_total:.3f}' for s in ranked)}")
                print(f"  presented  : {' , '.join(jr.presentation_order)}")
                print(f"  elapsed {rec['elapsed_s']}s | judge ${jr.cost:.4f}"
                      + (f" | {degraded_n} DEGRADED" if degraded_n else ""), flush=True)
            except Exception as exc:
                _abort_if_fatal(str(exc), f"q{qi}/pipeline")
                logging.exception("query %d failed", qi)
                append_attempt({
                    "fingerprint": fingerprint,
                    "query_idx": qi,
                    "attempt": attempt_number,
                    "stage": "unexpected_exception",
                    "eligible": False,
                    "elapsed_s": round(time.perf_counter() - t0, 2),
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                })
                print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
                note_ineligible(qi)
    finally:
        await judge.close_judge()
        await close_luna(); await close_cohere(); await close_rerank()
        await close_api_keys(); await close_embed(); await close_qdrant()
        await close_pool(); await close_llm()

    print(f"\nsuite done in {time.perf_counter() - t_suite:.0f}s -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
