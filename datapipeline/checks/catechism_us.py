"""The Catechism's alignment and identity report (issue #279, B4).

    cd datapipeline
    python3 -m checks.catechism_us [--snapshot releases/snapshots/<date>] [--out <dir>]

`run_collection.py --collection catechism --dry-run` writes it too. It says what moving
the Catechism to the US edition's words changes, and whether anything users hold would
break:

- paragraphs, old text (`ccc.json`) against new: identical, spelling or hyphenation only
  (with the UK-to-US pairs), words restored (the old words are a subsequence of the new),
  or substantive. CCC 2267 is the one expected substantive change;
- headings: each matched heading's old and new text, matches made despite one misprinted
  word, US headings inserted because no source line had them, and source lines kept as
  printed because nothing matched them;
- footnotes per paragraph against the source's `ref` markers;
- exact reconstruction: the passages, in order, hold every US item exactly once and only
  the source lines listed above besides; and every US footnote is on the passage that
  shows its text;
- live identity: every live anchor must still exist and open with the same source unit.
  Live passages carry no metadata to say which unit they open with, so it is derived: the
  live passages, in position order, are walked against ccc.json's lines, forward only, and
  the build is walked the same way against its own units. A piece opening mid-paragraph is
  compared by its paragraph and its first words.

Writes report.json and report.md (no passage text beyond short openings) to <out>, by
default releases/local/catechism-us-<timestamp>/ (gitignored). Exits 1 when an anchor
would disappear or open differently, or when reconstruction fails; those stop for Carter.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

from ingest import catechism, catechism_us as cu  # noqa: E402
from normalize.text import clean_text  # noqa: E402

SNAPSHOT_INDEX = os.path.join(DATAPIPELINE, "releases", "snapshots.json")
_OPENING_WORDS = 10
_LOWER_START = re.compile(r"[.!?][\"'”’)\]]*\s+(the|and)\s")


# --------------------------------------------------------------------------- paragraphs

def classify(old: str, new: str) -> tuple[str, list[tuple[str, str]]]:
    """identical | spelling | restored | substantive, and the spelling pairs seen."""
    old_raw, new_raw = cu.raw_words(old), cu.raw_words(new)
    if old_raw == new_raw:
        return "identical", []
    old_w, new_w = cu.words(old), cu.words(new)
    pairs = []
    matcher = SequenceMatcher(None, old_raw, new_raw, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace" and i2 - i1 == j2 - j1:
            pairs.extend(zip(old_raw[i1:i2], new_raw[j1:j2]))
    if old_w == new_w:
        return "spelling", pairs
    ops = [op for op in SequenceMatcher(None, old_w, new_w, autojunk=False).get_opcodes()
           if op[0] != "equal"]
    if all(op[0] == "insert" for op in ops):
        return "restored", pairs
    if all(_misprint(op, old_w, new_w) for op in ops):
        return "misprint", pairs
    return "substantive", pairs


def _misprint(op, old_w: list[str], new_w: list[str]) -> bool:
    """A difference that is the old source's typing, not the text: a misspelt word
    ("bums" for "burns"), words split or joined ("oldtestament"), a roman numeral
    misread ("vl", "i" for "1"), or a stray footnote number, or words the old source
    dropped (an insertion)."""
    tag, i1, i2, j1, j2 = op
    old, new = old_w[i1:i2], new_w[j1:j2]
    if tag == "insert":
        return True
    if tag == "delete":
        return all(w.isdigit() for w in old)
    if "".join(old) == "".join(new):
        return True
    if len(old) == len(new):
        return all(SequenceMatcher(None, a, b).ratio() >= 0.6 or (a, b) in _NUMERALS
                   for a, b in zip(old, new))
    return False


_NUMERALS = {("i", "1"), ("l", "1"), ("vl", "vi"), ("il", "ii"), ("jn", "in"), ("in", "jn")}


def diff_words(old: str, new: str, limit: int = 4) -> list[str]:
    """The word-level differences, "old -> new", for the report."""
    old_w, new_w = cu.words(old), cu.words(new)
    old_r, new_r = cu.raw_words(old), cu.raw_words(new)     # the same tokens, unfolded

    def shown(ws: list[str]) -> str:
        return (" ".join(ws[:12]) + (" …" if len(ws) > 12 else "")) or "∅"

    out = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, old_w, new_w, autojunk=False).get_opcodes():
        if tag != "equal" and not _misprint((tag, i1, i2, j1, j2), old_w, new_w):
            out.append(f"{shown(old_r[i1:i2])} -> {shown(new_r[j1:j2])}")
    return out[:limit]


def _source_refs(source: dict) -> Counter:
    """Footnote markers per CCC number in ccc.json: those on the numbered line and on
    the lines after it, up to the next number."""
    counts: Counter = Counter()
    current = 0
    for node_id in cu.ordered_node_ids(source["page_nodes"]):
        for paragraph in source["page_nodes"][node_id].get("paragraphs", []):
            for el in paragraph.get("elements", []):
                if el.get("type") == "ref-ccc":
                    current = el["ref_number"]
                elif el.get("type") == "ref":
                    counts[current] += 1
    return counts


# --------------------------------------------------------------------------- openings

def _identity_maps(alignment: cu.Alignment) -> tuple[dict, dict]:
    """(item key -> unit identity, continuation line -> its paragraph) so the live and
    the build walks name units the same way: ("p", N) for paragraph N, a source line's
    (node_id, index) for a heading or a line kept as printed, ("inserted", key) else."""
    key_to_ident: dict[str, tuple] = {}
    for key, item in alignment.items.items():
        if item["kind"] == "paragraph":
            key_to_ident[key] = ("p", item["n"])
        elif item.get("source_line"):
            key_to_ident[key] = tuple(item["source_line"])
        else:
            key_to_ident[key] = ("inserted", key)
    line_to_para: dict[tuple, tuple] = {}
    for match in alignment.matches:
        for li in match.continuation:
            line = match.lines[li]
            line_to_para[(line.node_id, line.index)] = ("p", match.after)
    return key_to_ident, line_to_para


def _walk(passages: list[tuple[str, str]], units: list[tuple[object, str]]) -> dict:
    """anchor -> (unit identity, opening words) for passages in reading order, matched
    forward only against `units` [(identity, raw text)]."""
    cleaned = [(ident, clean_text(text)) for ident, text in units]
    out: dict[str, tuple] = {}
    p = 0
    for anchor, content in passages:
        head = content[:80]
        found = None
        for u in range(p, len(cleaned)):
            ident, text = cleaned[u]
            if text and (content.startswith(text[:len(content)]) or text.startswith(head)):
                found = (u, ident, True)
                break
            if head and head in text:
                found = (u, ident, False)
                break
        if found is None:
            out[anchor] = (None, None, None)
            continue
        u, ident, at_start = found
        # The paragraph it opens with: headings above it do not change what a saved
        # anchor shows (restored headings now open some passages).
        para = ident
        if at_start and ident[0] != "p":
            nxt = next((cleaned[k][0] for k in range(u, len(cleaned)) if cleaned[k][0][0] == "p"
                        and cleaned[k][1] and cleaned[k][1][:40] in content), None)
            para = nxt or ident
        out[anchor] = (para, tuple(cu.words(content)[:_OPENING_WORDS]) if not at_start else (), ident)
        p = u
    return out


def openings(build: "catechism.Build", source: dict, live: list[dict]) -> dict:
    key_to_line, line_to_para = _identity_maps(build.alignment)
    numbered_line = {}
    old_units = []
    for line in cu.source_lines(source["page_nodes"]):
        ident = ("p", line.number) if line.number is not None else \
            line_to_para.get((line.node_id, line.index), (line.node_id, line.index))
        if line.number is not None:
            numbered_line[line.number] = ident
        if line.text:
            old_units.append((ident, line.text))
    # A live passage opening on a continuation line opens inside that paragraph.
    live_open = _walk([(r["anchor"], r["content"]) for r in sorted(live, key=lambda r: r["position"])],
                      old_units)
    new_units = []
    for key, text in catechism._units(build.alignment.page_nodes):
        if key and key.startswith("src:"):
            _, node_id, index = key.split(":")
            ident = line_to_para.get((node_id, int(index)), (node_id, int(index)))
        else:
            ident = key_to_line.get(key, ("inserted", key))
        new_units.append((ident, text))
    build_open = _walk([(p.anchor, p.content) for p in build.document.passages], new_units)

    removed, changed, unresolved, headed = [], [], [], []
    for anchor, (ident, words, first) in live_open.items():
        if ident is None:
            unresolved.append(anchor)
            continue
        if anchor not in build_open:
            removed.append(anchor)
            continue
        b_ident, b_words, b_first = build_open[anchor]
        if (b_ident, b_words) != (ident, words):
            changed.append({"anchor": anchor, "live": _show(ident, words),
                            "build": _show(b_ident, b_words)})
        elif b_first != first:
            headed.append(anchor)       # same paragraph, now under a restored heading
    added = sorted(set(build_open) - set(live_open))
    return {"live": len(live_open), "build": len(build_open), "added": added,
            "removed": sorted(removed), "opens_differently": changed,
            "same_paragraph_new_heading": sorted(headed),
            "live_unresolved": sorted(unresolved)}


def _show(ident, words) -> str:
    if ident is None:
        return "no unit"
    name = f"CCC {ident[1]}" if ident[0] == "p" else (
        f"inserted {ident[1]}" if ident[0] == "inserted" else f"line {ident[0]}#{ident[1]}")
    return name + (f", mid-paragraph at '{' '.join(words)}'" if words else "")


# --------------------------------------------------------------------------- report

def report(build: "catechism.Build", source: dict, live: list[dict] | None) -> dict:
    alignment = build.alignment
    paragraphs: dict[str, list] = {"identical": [], "spelling": [], "restored": [], "misprint": [],
                                   "substantive": []}
    pairs: Counter = Counter()
    for n in sorted(alignment.old_paragraphs):
        kind, seen = classify(alignment.old_paragraphs[n], alignment.items[f"p{n}"]["text"])
        paragraphs[kind].append(n)
        pairs.update(f"{a} -> {b}" for a, b in seen)

    headings = {"matched": 0, "changed": [], "fuzzy": [], "inserted": [], "unmatched_lines": [], "moved": []}
    for match in alignment.matches:
        for h in match.headings:
            headings["matched"] += 1
            old = " ".join(match.lines[li].text for li in
                           range(match.toks[h.start].line, match.toks[h.end - 1].line + 1))
            if cu.raw_words(old) != cu.raw_words(h.item["text"]):
                headings["changed"].append({"after": match.after, "old": old, "new": h.item["text"]})
            if h.fuzzy:
                headings["fuzzy"].append({"after": match.after, "old": old, "new": h.item["text"]})
        for _, item in match.inserted:
            headings["inserted"].append({"after": match.after, "kind": item["kind"], "text": item["text"],
                                         "glued": bool(item.get("_glued"))})
        for li in match.unmatched:
            headings["unmatched_lines"].append({"after": match.after, "text": match.lines[li].text})
        for li, other in match.moved:
            headings["moved"].append({"source_after": match.after, "us_after": other,
                                      "text": match.lines[li].text})

    refs = _source_refs(source)
    footnote_diffs = [
        {"n": n, "source": refs.get(n, 0), "us": len(alignment.items[f"p{n}"]["footnotes"])}
        for n in sorted(alignment.old_paragraphs)
        if refs.get(n, 0) != len(alignment.items[f"p{n}"]["footnotes"])
    ]

    # Reconstruction: the passages hold every unit in reading order, each once.
    held: list[str] = []
    for passage in build.document.passages:
        for key in build.held[passage.anchor]:
            if not held or held[-1] != key:
                held.append(key)
    expected = [k for k in alignment.order if k not in {key for key, _ in build.dropped}]
    us_keys = [k for k in alignment.items]
    counts = Counter(held)
    reconstruction = {
        "in_order": held == expected,
        "missing_us_items": [k for k in us_keys if counts[k] == 0],
        "repeated": sorted(k for k, c in counts.items() if c > 1),
        "source_lines_kept": [k for k in held if k.startswith("src:")],
        "dropped_by_chunker": [k for k, _ in build.dropped],
    }
    want = Counter((key, note["n"]) for key, item in alignment.items.items() for note in item["footnotes"])
    have: Counter = Counter()
    for passage in build.document.passages:
        for note in passage.metadata["footnotes"]:
            have[note["n"]] += 1
    note_numbers = Counter(n for _, n in want.elements())
    footnotes = {
        "us_total": sum(want.values()),
        "placed_total": sum(have.values()),
        "mismatched_numbers": sorted(n for n in set(note_numbers) | set(have)
                                     if note_numbers[n] != have[n]),
    }
    lower = sum(len(_LOWER_START.findall(p.content)) for p in build.document.passages)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "passages": len(build.document.passages),
        "paragraphs": {k: len(v) for k, v in paragraphs.items()},
        "substantive": paragraphs["substantive"],
        "substantive_diffs": {n: diff_words(alignment.old_paragraphs[n], alignment.items[f"p{n}"]["text"])
                              for n in paragraphs["substantive"]},
        "spelling_pairs": dict(pairs.most_common()),
        "headings": headings,
        "footnote_count_diffs": footnote_diffs,
        "reconstruction": reconstruction,
        "footnotes": footnotes,
        "lowercase_sentence_starts": lower,
    }
    if live is not None:
        result["identity"] = openings(build, source, live)
    return result


def stops(result: dict) -> list[str]:
    """What must go to Carter before this build may publish."""
    out = []
    rec = result["reconstruction"]
    if not rec["in_order"] or rec["missing_us_items"] or rec["repeated"]:
        out.append("reconstruction failed")
    if result["footnotes"]["mismatched_numbers"]:
        out.append("footnotes not all placed once")
    identity = result.get("identity")
    if identity and (identity["removed"] or identity["opens_differently"] or identity["live_unresolved"]):
        out.append("live anchors removed or opening differently")
    return out


def markdown(result: dict) -> str:
    p = result["paragraphs"]
    h = result["headings"]
    rec = result["reconstruction"]
    lines = [
        "# Catechism: US-edition alignment report (#279)", "",
        f"Generated {result['generated_at']}. {result['passages']} passages.", "",
        "## Paragraphs (old `ccc.json` against the US edition)", "",
        "| Class | Count |", "|---|---|",
        *(f"| {k} | {v} |" for k, v in p.items()), "",
        "Classes: identical words; spelling or hyphenation only; words restored (the old "
        "source dropped them); the old source's misprints corrected; substantive (the "
        "wording differs, listed below with each word change).", "",
        "Substantive:", "",
        *(f"- CCC {n}: {'; '.join(d)}" for n, d in result["substantive_diffs"].items()), "",
        "Spelling pairs (UK -> US), most common first: "
        + (", ".join(f"{k} ({v})" for k, v in list(result["spelling_pairs"].items())[:40]) or "none") + ".", "",
        "## Headings", "",
        f"{h['matched']} matched, {len(h['changed'])} with changed words, {len(h['fuzzy'])} despite a "
        f"misprint, {len(h['inserted'])} inserted, {len(h['unmatched_lines'])} source lines kept as printed.", "",
    ]
    if h["fuzzy"]:
        lines += ["Matched despite a misprinted word:", ""]
        lines += [f"- after CCC {x['after']}: {x['old']!r} -> {x['new']!r}" for x in h["fuzzy"]] + [""]
    if h["inserted"]:
        lines += ["Inserted (no source line):", ""]
        lines += [f"- after CCC {x['after']} ({x['kind']}): {x['text']!r}"
                  + (" (the source glues it to the end of the paragraph's line)" if x["glued"] else "")
                  for x in h["inserted"]] + [""]
    if h["moved"]:
        lines += ["Printed one gap away from the source (the US placement is kept):", ""]
        lines += [f"- {x['text']!r}: source after CCC {x['source_after']}, US after CCC {x['us_after']}"
                  for x in h["moved"]] + [""]
    if h["unmatched_lines"]:
        lines += ["Source lines kept as printed (no US text matched):", ""]
        by_gap: dict[int, list[str]] = {}
        for x in h["unmatched_lines"]:
            by_gap.setdefault(x["after"], []).append(x["text"])
        for after, texts in by_gap.items():
            lines.append(f"- after CCC {after}: {len(texts)} line(s), first {texts[0][:70]!r}")
        lines.append("")
    lines += [
        "## Footnotes", "",
        f"{result['footnotes']['us_total']} US footnotes, {result['footnotes']['placed_total']} placed on "
        f"passages; numbers placed other than once: {result['footnotes']['mismatched_numbers'][:20] or 'none'}.", "",
        f"Paragraphs whose note count differs from ccc.json's markers: {len(result['footnote_count_diffs'])}"
        + (" (" + ", ".join(f"CCC {d['n']} {d['source']}->{d['us']}" for d in result['footnote_count_diffs'][:30]) + ")"
           if result['footnote_count_diffs'] else "") + ".", "",
        "## Reconstruction", "",
        f"In order: {rec['in_order']}. US items missing: {rec['missing_us_items'][:20] or 'none'}. "
        f"Repeated: {rec['repeated'][:20] or 'none'}. Source lines kept: {len(rec['source_lines_kept'])}. "
        f"Dropped by the chunker: {rec['dropped_by_chunker'] or 'none'}.", "",
        f"Lowercase 'the'/'and' sentence starts left: {result['lowercase_sentence_starts']}.", "",
    ]
    identity = result.get("identity")
    if identity:
        lines += [
            "## Live identity", "",
            f"Live {identity['live']} anchors, build {identity['build']}. Added {len(identity['added'])}, "
            f"removed {len(identity['removed'])}, opening differently {len(identity['opens_differently'])}, "
            f"live passages whose opening could not be found {len(identity['live_unresolved'])}. "
            f"Same opening paragraph under a restored heading (not a stop): "
            f"{len(identity['same_paragraph_new_heading'])}.", "",
        ]
        for label in ("added", "removed", "live_unresolved"):
            if identity[label]:
                lines.append(f"- {label}: {', '.join(identity[label][:40])}")
        for x in identity["opens_differently"][:60]:
            lines.append(f"- {x['anchor']}: live opens with {x['live']}; build with {x['build']}")
        lines.append("")
    blockers = stops(result)
    lines += ["## Stops for Carter", "", *(f"- {s}" for s in blockers)] if blockers else ["## Stops for Carter", "", "None."]
    return "\n".join(lines) + "\n"


def _live_rows(snapshot: str) -> list[dict]:
    with gzip.open(os.path.join(snapshot, "passages.jsonl.gz"), "rt", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    return [r for r in rows if r.get("collection") == "catechism"
            and r.get("title", "").startswith("Catechism of the Catholic Church")]


def latest_snapshot() -> str | None:
    try:
        with open(SNAPSHOT_INDEX, encoding="utf-8") as f:
            dates = sorted(s["date"] for s in json.load(f)["snapshots"])
    except (OSError, KeyError, ValueError):
        return None
    path = os.path.join(DATAPIPELINE, "releases", "snapshots", dates[-1]) if dates else None
    return path if path and os.path.isdir(path) else None


def write(out: str | None = None, snapshot: str | None = None,
          source_path: str | None = None, us_path: str | None = None) -> tuple[str, dict]:
    build = catechism.build(source_path, us_path)
    with open(source_path or catechism._DEFAULT_SRC, encoding="utf-8") as f:
        source = json.load(f)
    snapshot = snapshot or latest_snapshot()
    live = _live_rows(snapshot) if snapshot else None
    result = report(build, source, live)
    result["snapshot"] = snapshot
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = out or os.path.join(DATAPIPELINE, "releases", "local", f"catechism-us-{stamp}")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write(markdown(result))
    return out, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshot", help="live snapshot directory (default: the latest)")
    parser.add_argument("--out", help="output directory")
    args = parser.parse_args(argv)
    out, result = write(args.out, args.snapshot)
    blockers = stops(result)
    print(f"catechism US report: {out}; stops: {', '.join(blockers) or 'none'}")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
