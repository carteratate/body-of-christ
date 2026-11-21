"""Draft held-text entries for `registry/held_texts.json` (corpus-cleanup 4.3).

    cd datapipeline
    python3 scripts/held_texts.py --draft [--out PATH] [--today YYYY-MM-DD]

Proposes one entry per held text for every held removal (`registry.is_held_removal`) that
no entry of `held_texts.json` owns yet, and writes the proposals, never the file itself, to
`--out` (default `held_texts.draft.json` in the current folder). A person then edits each
heading into reader-facing words, checks each place, and moves the entries into
`held_texts.json` in the document's reading order. An existing entry is never rewritten.

Grouping. A council removal's `detail` names its text or texts: the "(gap Gn)" tag and
", a piece the 1.10c build cut" are dropped, and a detail that names two texts ("X; Y")
straddles them. The passage belongs to the first text it names; a text it alone holds gets
the passage in `shared_removal_ids`. A papal removal's detail opens "Paragraph N" or "The
address"; consecutive paragraphs make one run, the address joining the run that follows
it. Any other detail is its own draft group, labelled for review.

Placement. Each draft follows the last built passage before it: for a council, the last
passage of the last chapter whose session comes before the text's ("Basel" before
"Ferrara" before "Florence"); for a papal document, the last passage of a lower paragraph.
A text in the same session as a published chapter is drafted before that chapter; one
that follows it is moved by hand.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import registry  # noqa: E402

ITEM = "4.3"
_TAG = re.compile(r" \(gap G\d+\)")
_CUT = ", a piece the 1.10c build cut"
_SESSION = re.compile(r"^(?:(Basel|Ferrara|Florence), )?[Ss]ession (\d+), (.+)$")
_CHAPTER_SESSION = re.compile(r"^(?:(Basel|Ferrara|Florence), )?Session (\d+)\b")
_SERIES = {None: 0, "Basel": 0, "Ferrara": 1, "Florence": 2}
_PARAGRAPH = re.compile(r"^Paragraph (\d+) is not\b")
_ADDRESS = re.compile(r"^The address is not\b")


def texts_of(detail: str) -> list[str]:
    """The texts a council removal's detail names, in the order it names them."""
    plain = _TAG.sub("", detail).replace(_CUT, "")
    return [t.strip() for t in plain.split("; ") if t.strip()]


def session_of(text: str) -> tuple[int, int] | None:
    """(series, session) of "Florence, session 11, …" or "Session 8, …"; None otherwise."""
    m = _SESSION.match(text)
    return (_SERIES[m.group(1)], int(m.group(2))) if m else None


def paragraph_of(detail: str) -> int | None:
    """0 for the address, N for "Paragraph N", None for anything else."""
    if _ADDRESS.match(detail):
        return 0
    m = _PARAGRAPH.match(detail)
    return int(m.group(1)) if m else None


def _label_heading(text: str) -> tuple[str, str]:
    m = _SESSION.match(text)
    if not m:
        return "REVIEW", text
    label = f"{m.group(1)}, Session {m.group(2)}" if m.group(1) else f"Session {m.group(2)}"
    rest = m.group(3)
    return label, rest[0].upper() + rest[1:]


def _run_label(paragraphs: list[int]) -> str:
    numbers = [p for p in paragraphs if p]
    if not numbers:
        return "The address"
    span = (f"Paragraph {numbers[0]}" if len(numbers) == 1
            else f"Paragraphs {numbers[0]}–{numbers[-1]}")
    return f"The address and {span[0].lower()}{span[1:]}" if 0 in paragraphs else span


def council_groups(entries: list[dict]) -> list[dict]:
    """Draft groups of one council's held removals, by the text each detail names."""
    groups: dict[str, dict] = {}
    for e in sorted(entries, key=lambda e: e["id"]):
        names = texts_of(e.get("detail") or "")
        for i, text in enumerate(names or ["REVIEW: no detail"]):
            g = groups.setdefault(text, {"text": text, "removal_ids": [],
                                         "shared_removal_ids": []})
            (g["removal_ids"] if i == 0 else g["shared_removal_ids"]).append(e["id"])
    out = []
    for g in groups.values():
        if g["removal_ids"]:
            g["shared_removal_ids"] = []        # it holds passages of its own
        out.append(g)
    return out


def _council_place(text: str, chapters: list[tuple[str, str]]) -> str | None:
    """The last passage of the last chapter before the text's session; None when the
    text precedes every chapter or names no session. `chapters` is (label, last anchor)."""
    wanted = session_of(text)
    if wanted is None:
        return None
    after = None
    for label, last in chapters:
        m = _CHAPTER_SESSION.match(label)
        if m and (_SERIES[m.group(1)], int(m.group(2))) < wanted:
            after = last
    return after


def papal_groups(entries: list[dict]) -> list[dict]:
    """Runs of consecutive held paragraphs (the address joins the run after it); any
    other detail is a group of its own."""
    numbered, other = [], []
    for e in entries:
        n = paragraph_of(e.get("detail") or "")
        (numbered if n is not None else other).append((n, e))
    numbered.sort(key=lambda x: x[0])
    runs: list[list] = []
    for n, e in numbered:
        if runs and n == runs[-1][-1][0] + 1:
            runs[-1].append((n, e))
        else:
            runs.append([(n, e)])
    out = [{"paragraphs": [n for n, _ in run], "removal_ids": [e["id"] for _, e in run],
            "shared_removal_ids": []} for run in runs]
    for _, e in sorted(other, key=lambda x: x[1]["id"]):
        out.append({"paragraphs": None, "removal_ids": [e["id"]], "shared_removal_ids": [],
                    "text": f"REVIEW: {e.get('detail')}"})
    return out


def _paragraph_number(anchor: str) -> int | None:
    m = re.search(r"/(?:para-)?(\d+)(?:/|$)", anchor)
    return int(m.group(1)) if m else None


def _papal_place(first: int, document) -> str | None:
    """The last built passage of a lower paragraph (the address counts as 0)."""
    after = None
    for p in document.passages:
        n = 0 if p.anchor.split("/")[1:2] == ["preamble"] else _paragraph_number(p.anchor)
        if n is not None and n < first:
            after = p.anchor
    return after


def draft(reg: registry.WorkRegistry, documents: list, today: str) -> list[dict]:
    """Proposed entries for every held removal no entry owns, per document in build
    order, with IDs after the highest in use."""
    owned = {rid for h in reg.held_texts for rid in h.get("removal_ids") or []}
    pending: dict[str, list[dict]] = {}
    for e in reg.removals:
        if registry.is_held_removal(e) and e["id"] not in owned:
            pending.setdefault(e["document_id"], []).append(e)
    used = [int(h["id"][3:]) for h in reg.held_texts if str(h.get("id", "")).startswith("ht-")]
    next_id = max(used, default=0) + 1
    out = []
    for d in documents:
        entries = pending.get(d.id)
        if not entries:
            continue
        if d.collection == "councils":
            chapters: list[tuple[str, str]] = []
            for p in d.passages:
                if chapters and chapters[-1][0] == p.chapter_label:
                    chapters[-1] = (p.chapter_label, p.anchor)
                else:
                    chapters.append((p.chapter_label, p.anchor))
            drafts = []
            for g in council_groups(entries):
                label, heading = _label_heading(g["text"])
                drafts.append((g, label, heading, _council_place(g["text"], chapters)))
        else:
            drafts = []
            for g in papal_groups(entries):
                if g["paragraphs"] is None:
                    drafts.append((g, "REVIEW", g["text"], None))
                    continue
                drafts.append((g, _run_label(g["paragraphs"]), "Not in the public-domain printing",
                               _papal_place(g["paragraphs"][0], d)))
        order = {p.anchor: i for i, p in enumerate(d.passages)}
        drafts.sort(key=lambda x: -1 if x[3] is None else order[x[3]])
        for g, label, heading, after in drafts:
            entry = {"id": f"ht-{next_id:04d}", "document_id": d.id, "label": label,
                     "heading": heading, "after_anchor": after,
                     "removal_ids": g["removal_ids"]}
            if g["shared_removal_ids"]:
                entry["shared_removal_ids"] = g["shared_removal_ids"]
            entry.update({"url": None, "added_by": ITEM, "added_on": today})
            out.append(entry)
            next_id += 1
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--draft", action="store_true", required=True,
                        help="propose entries for held removals no entry owns")
    parser.add_argument("--out", default="held_texts.draft.json")
    parser.add_argument("--today", default=date.today().isoformat())
    args = parser.parse_args(argv)

    from publication import build

    reg = registry.current()
    collections = sorted({e["collection"] for e in reg.removals if registry.is_held_removal(e)})
    documents = [d for c in collections for d in build(c, registry=reg, held_coverage=False)]
    proposals = draft(reg, documents, args.today)
    try:
        f = open(args.out, "x", encoding="utf-8")
    except FileExistsError:
        parser.error(f"{args.out} exists; move it aside first (a draft never overwrites)")
    with f:
        json.dump(proposals, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{len(proposals)} draft entries for {len({p['document_id'] for p in proposals})} "
          f"documents written to {args.out}; edit the headings and places, then move them "
          f"into {registry.HELD_TEXTS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
