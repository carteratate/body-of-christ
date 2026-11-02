"""`gate.md` for one work: both gate results, the clean-up and correction counts, and the
person's check with its seed. It is pasted into the work's adapter PR."""
from __future__ import annotations

from collections import Counter

from ocr.correct import MAX_CHANGED_FRACTION
from ocr.gate import GateResult, evaluate
from ocr.work import WorkDir


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def render(workdir: WorkDir, result: GateResult) -> str:
    config = workdir.config
    passages = workdir.passages()
    cleanup = workdir.cleanup()
    runs = workdir.runs()
    check = workdir.check()
    status = Counter(p.correction.status for p in passages)
    removals = Counter(r["kind"] for r in cleanup.get("removals", []))
    hyphens = cleanup.get("hyphens", [])
    joined = sum(1 for h in hyphens if h["joined"])
    rate = result.rate
    words = sum(len(p.text.split()) for p in passages)

    out = [
        f"# OCR gate: {config.title}",
        "",
        f"**Result: {result.status.upper()}**" + (f" ({'; '.join(result.reasons)})" if result.reasons else ""),
        "",
        f"- Work `{config.work}`; scan [`{config.scan}`]({config.scan_url()}), "
        f"pp. {config.pages[0]}–{config.pages[1]} ({len(cleanup.get('pages', []))} pages); "
        f"layout `{config.layout}`.",
        f"- {len(passages)} passages, {words:,} words of body text; "
        f"{len(cleanup.get('notes', []))} note blocks kept apart.",
        "",
        "## 1. Unrecognized-word rate",
        "",
        "| | Words | Unrecognized | Rate |",
        "|---|---|---|---|",
        f"| This work (body text after correction) | {rate.words:,} | {rate.unknown:,} | {_pct(rate.rate)} |",
        f"| Baseline: `{config.baseline.path}` | {rate.baseline_words:,} | {rate.baseline_unknown:,} | {_pct(rate.baseline_rate)} |",
        "",
        f"Limit: baseline + 1 point = {_pct(rate.limit)}. "
        f"**{'Within the limit' if rate.ok else 'Above the limit'}.** "
        f"Word list `ocr/data/en_words.txt` plus {len(config.names)} names from the work's config.",
        "",
        "## 2. Clean-up",
        "",
        f"- Page numbers read in the furniture agree with the page map on "
        f"{cleanup.get('page_map', {}).get('agree', 0)} of {cleanup.get('page_map', {}).get('read', 0)} pages.",
        "- Furniture removed: " + (", ".join(f"{k.replace('_', ' ')} {n}" for k, n in sorted(removals.items())) or "none") + ".",
        f"- Words broken at a line end: {len(hyphens)}; joined {joined}, kept with the hyphen {len(hyphens) - joined}.",
        "",
        "## 3. Model correction",
        "",
    ]
    if runs:
        out += ["| Run | Model | Prompt | Calls | Tokens in / out | Cost | Stopped |",
                "|---|---|---|---|---|---|---|"]
        for r in runs:
            out.append(f"| `{r['run']}` | {r['model']} | {r['prompt_version']} | {r['calls']} | "
                       f"{r['input_tokens']:,} / {r['output_tokens']:,} | ${r['cost_usd']:.4f} | "
                       f"{r.get('stopped') or '—'} |")
        out += ["", f"Spent ${workdir.spent_usd():.4f} of the ${config.ceiling_usd:.2f} ceiling."]
    else:
        out.append("Not run.")
    out += ["",
            "Passages: " + ", ".join(f"{k} {status[k]}" for k in
                                     ("accepted", "unchanged", "rejected", "refused", "failed", "pending")
                                     if status[k]) + ".",
            f"**Rejected (over the {MAX_CHANGED_FRACTION:.0%} word-change limit or paragraphs changed): "
            f"{status['rejected']}**; their cleaned text is kept.", ""]
    for p in passages:
        if p.correction.status in ("rejected", "refused", "failed"):
            out.append(f"- `{p.id}` ({p.page_ref()}): {p.correction.reason}")
    out += ["", "## 4. Person's check against the page images", ""]
    if not check:
        out.append(f"Not drawn yet. Rule: {config.sample.fraction:.0%} of passages, at least "
                   f"{config.sample.minimum}, at most {config.sample.maximum}: {result.required} here.")
    else:
        rule = check["rule"]
        out += [f"Seed **{check['seed']}**, drawn {check['drawn_on']}: {len(check['sample'])} of "
                f"{check['passages_in_unit']} passages (rule: {rule['fraction']:.0%}, at least "
                f"{rule['minimum']}, at most {rule['maximum']}, per {rule['unit']}). "
                f"Any wording change fails the work.", "",
                "| Passage | Page | Scan | Result | Differences | Checked |",
                "|---|---|---|---|---|---|"]
        stale = set(result.stale)
        for e in check["sample"]:
            res = "check again (text changed)" if e["id"] in stale else e["result"]
            diff = (e["differences"] or "") + (" **(wording)**" if e.get("wording_changed") else "")
            who = f"{e['checked_by']}, {e['checked_on']}" if e.get("checked_by") else "—"
            out.append(f"| `{e['id']}` | {e['page_ref']} | [image]({e['link']}) | {res} | {diff or '—'} | {who} |")
    return "\n".join(out) + "\n"


def check_sheet(workdir: WorkDir) -> str:
    """The sampled passages' text, each with its page and a link to the page image, for
    the person comparing them."""
    check = workdir.check()
    if not check:
        return ""
    text = {p.id: p.text for p in workdir.passages()}
    out = [f"# Check sheet: {workdir.config.title}", "",
           f"Seed {check['seed']}. Compare each passage with its page image, word for word. "
           "Record the result with `python3 -m ocr check "
           f"{workdir.config.work} <passage> matches --by NAME`, or `differences --by NAME "
           '--what "..."`, adding `--wording` if the differences change any wording.', ""]
    for e in check["sample"]:
        out += [f"## Passage {e['id']}, {e['page_ref']}", "", f"[Page image]({e['link']})", "",
                text.get(e["id"], "(passage no longer exists: draw the sample again)"), ""]
    return "\n".join(out)


def write(workdir: WorkDir, baseline: list[str] | None = None) -> tuple[str, GateResult]:
    result = evaluate(workdir, baseline)
    text = render(workdir, result)
    workdir.path.mkdir(parents=True, exist_ok=True)
    workdir.file("gate.md").write_text(text, encoding="utf-8")
    sheet = check_sheet(workdir)
    if sheet:
        workdir.file("check.md").write_text(sheet, encoding="utf-8")
    return text, result
