"""The quality gate a scanned work passes before its adapter PR can merge.

1. The unrecognized-word rate of the work's body text (notes excluded) is within 1
   percentage point of the rate on a clean typed baseline of the same period, measured
   with the same word list and the work's own names.
2. A person checks a random sample of passages against the page images. The sample is
   drawn once with a recorded seed; its size follows the work's `SampleRule` (Decision
   log "OCR clean-up: model, spend, sample and inputs": a quarter of the passages, at
   least 5 and at most 20). Each sampled passage is recorded as "matches" or with the
   differences found; any wording change fails the work. A passage whose text changed
   after it was checked must be checked again.

Status: `fail` if either test fails, `pending` until every sampled passage is checked,
`pass` otherwise.
"""
from __future__ import annotations

import hashlib
import random
import secrets
from dataclasses import asdict, dataclass, field
from datetime import date

from ocr.work import OcrPassage, SampleRule, WorkDir, baseline_text
from ocr.words import unrecognized_rate

# Percentage points the work's rate may sit above the baseline's.
RATE_MARGIN = 0.01

RESULTS = ("pending", "matches", "differences")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class RateResult:
    rate: float
    unknown: int
    words: int
    baseline_rate: float
    baseline_unknown: int
    baseline_words: int

    @property
    def limit(self) -> float:
        return self.baseline_rate + RATE_MARGIN

    @property
    def ok(self) -> bool:
        return self.rate <= self.limit


def rate_check(passages: list[OcrPassage], baseline: list[str], names=()) -> RateResult:
    rate, unknown, total = unrecognized_rate((p.text for p in passages), names)
    b_rate, b_unknown, b_total = unrecognized_rate(baseline, names)
    return RateResult(rate, unknown, total, b_rate, b_unknown, b_total)


def draw_sample(passage_ids: list[str], rule: SampleRule, seed: int) -> list[str]:
    """`rule.size(n)` passage IDs from the unit's passages, the same for the same seed.
    The pool can hold one work's passages or several works' (the rule's unit)."""
    pool = sorted(passage_ids)
    return sorted(random.Random(seed).sample(pool, rule.size(len(pool))))


def start_check(workdir: WorkDir, seed: int | None = None, redraw: bool = False) -> dict:
    """Draw the sample once and record it; an existing check is kept unless `redraw`."""
    existing = workdir.check()
    if existing and not redraw:
        return existing
    passages = {p.id: p for p in workdir.passages()}
    if not passages:
        raise RuntimeError(f"{workdir.config.work}: no passages; run the clean-up first")
    rule = workdir.config.sample
    seed = secrets.randbelow(2**32) if seed is None else seed
    chosen = draw_sample(list(passages), rule, seed)
    check = {
        "seed": seed,
        "rule": asdict(rule),
        "passages_in_unit": len(passages),
        "population": sorted(passages),
        "drawn_on": date.today().isoformat(),
        "sample": [{
            "id": pid,
            "page_ref": passages[pid].page_ref(),
            "link": workdir.config.scan_url(passages[pid].leaves[0]),
            "text_sha256": text_hash(passages[pid].text),
            "result": "pending",
            "differences": None,
            "wording_changed": None,
            "checked_by": None,
            "checked_on": None,
        } for pid in chosen],
    }
    workdir.save_check(check)
    return check


def record(workdir: WorkDir, passage_id: str, result: str, by: str,
           differences: str | None = None, wording_changed: bool = False,
           shown_sha256: str | None = None) -> dict:
    """Record a person's check of one sampled passage against the page image.
    `shown_sha256` is the hash of the text they were shown: a verdict on text that has
    since changed is refused."""
    if result not in ("matches", "differences"):
        raise ValueError("result is 'matches' or 'differences'")
    if result == "differences" and not differences:
        raise ValueError("say what differs")
    check = workdir.check()
    if not check:
        raise RuntimeError("no sample drawn yet")
    entry = next((e for e in check["sample"] if e["id"] == passage_id), None)
    if entry is None:
        raise ValueError(f"{passage_id} is not in the sample")
    text = next(p.text for p in workdir.passages() if p.id == passage_id)
    if shown_sha256 is not None and shown_sha256 != text_hash(text):
        raise ValueError(f"{passage_id} changed since this page was loaded: reload and "
                         "check it again")
    entry.update(result=result, differences=differences if result == "differences" else None,
                 wording_changed=bool(wording_changed) if result == "differences" else False,
                 checked_by=by, checked_on=date.today().isoformat(),
                 text_sha256=text_hash(text))
    workdir.save_check(check)
    return entry


@dataclass
class GateResult:
    status: str
    rate: RateResult
    required: int
    checked: int
    pending: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    wording_changes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def evaluate(workdir: WorkDir, baseline: list[str] | None = None) -> GateResult:
    config = workdir.config
    passages = workdir.passages()
    if baseline is None:
        baseline = baseline_text(config.baseline)
    rate = rate_check(passages, baseline, config.names)
    required = config.sample.size(len(passages))
    check = workdir.check() or {"sample": []}
    current = {p.id: text_hash(p.text) for p in passages}

    pending, stale, wording, checked = [], [], [], 0
    redraw = bool(check["sample"]) and check.get("population") != sorted(current)
    for e in check["sample"]:
        if redraw or e["id"] not in current:
            stale.append(e["id"])
        elif e["result"] == "pending":
            pending.append(e["id"])
        elif e["text_sha256"] != current[e["id"]]:
            stale.append(e["id"])
        else:
            checked += 1
            if e["result"] == "differences" and e.get("wording_changed"):
                wording.append(e["id"])

    reasons = []
    if not rate.ok:
        reasons.append(f"unrecognized-word rate {rate.rate:.2%} is above the limit "
                       f"{rate.limit:.2%} (baseline {rate.baseline_rate:.2%} + 1 point)")
    if wording:
        reasons.append("wording changed in " + ", ".join(wording))
    if reasons:
        status = "fail"
    elif redraw:
        status = "pending"
        reasons.append("the passages changed since the sample was drawn: draw it again")
    elif checked < required or pending or stale:
        status = "pending"
        reasons.append(f"{checked} of {required} sampled passages checked"
                       + (f"; {len(stale)} to check again after a text change" if stale else ""))
    else:
        status = "pass"
    return GateResult(status, rate, required, checked, pending, stale, wording, reasons)
