#!/usr/bin/env python3
"""R3: verse inventory of the vendored WEB-C Greek Esther (43-ESGeng-web-c.usfm).

Read-only. Usage:
    python3 docs/research/R3_esther_inventory.py [path/to/43-ESGeng-web-c.usfm]
    python3 docs/research/R3_esther_inventory.py --nv nova-vulgata_vt_esther_lt.html

The --nv mode lists the verse labels of a saved copy of the Nova Vulgata page
https://www.vatican.va/archive/bible/nova_vulgata/documents/nova-vulgata_vt_esther_lt.html
(save it with curl; it is not vendored).

Prints, per chapter: the verse markers in order with the USFM line of each,
gaps in numbering, verse markers that carry a range (e.g. "\\v 7-8"),
duplicates, and every bracketed span ("[" ... "]", WEB-C's marker for Greek
additions) with the verse and line where it opens and closes.
"""
import json
import re
import sys
from collections import OrderedDict

from pathlib import Path

SRC = str(Path(__file__).resolve().parents[2] / "datapipeline" / "sources" / "bible") + "/"
DEFAULT = SRC + "eng-web-c_usfm/43-ESGeng-web-c.usfm"
PERICOPES = SRC + "PericopeGroupedKJVVerses.json"
FOOT = re.compile(r"\\f .*?\\f\*")
MARK = re.compile(r"\\[a-zA-Z0-9*+]+\s*")


def plain(s):
    return re.sub(r"\s+", " ", MARK.sub(" ", FOOT.sub("", s))).strip()


def main(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    chap = 0
    cur = None  # (chapter, verse_label)
    chapters = OrderedDict()   # ch -> list of (label, line)
    text = OrderedDict()       # (ch,label) -> plain text
    brackets = []              # open/close events
    depth = 0
    open_at = None
    for i, raw in enumerate(lines, 1):
        m = re.match(r"^\\c\s+(\d+)", raw)
        if m:
            chap = int(m.group(1)); chapters[chap] = []; cur = None
            continue
        m = re.match(r"^\\v\s+(\d+(?:-\d+)?)\s*(.*)", raw)
        body = raw
        if m and chap:
            cur = (chap, m.group(1)); chapters[chap].append((m.group(1), i))
            body = m.group(2); text[cur] = ""
        if cur is None:
            continue
        t = plain(body)
        if t:
            text[cur] = (text[cur] + " " + t).strip()
        for ch in FOOT.sub("", body):
            if ch == "[":
                depth += 1
                if depth == 1:
                    open_at = (cur, i)
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    brackets.append((open_at, (cur, i)))

    total = 0
    print("== Per-chapter verse markers ==")
    for ch, vs in chapters.items():
        nums = []
        ranges = []
        for lab, ln in vs:
            if "-" in lab:
                a, b = map(int, lab.split("-")); ranges.append((lab, ln))
                nums.extend(range(a, b + 1))
            else:
                nums.append(int(lab))
        dups = sorted({n for n in nums if nums.count(n) > 1})
        missing = [n for n in range(1, max(nums) + 1) if n not in nums]
        total += len(vs)
        print(f"ch {ch:>2}: {len(vs):>2} markers, lines {vs[0][1]}-{vs[-1][1]}, "
              f"highest verse {max(nums)}, numbers covered {len(set(nums))}")
        if ranges:
            print("        range markers: " + ", ".join(f"\\v {l} (line {n})" for l, n in ranges))
        if missing:
            print(f"        numbers never marked: {missing}")
        if dups:
            print(f"        duplicated numbers: {dups}")
    print(f"total markers: {total}")

    print("\n== Marker -> USFM line (all verses) ==")
    for ch, vs in chapters.items():
        print(f"ch {ch}: " + " ".join(f"{l}@{n}" for l, n in vs))

    print("\n== Bracketed spans (Greek additions as WEB-C marks them) ==")
    for (o, ol), (c, cl) in brackets:
        print(f"opens {o[0]}:{o[1]} (line {ol})  closes {c[0]}:{c[1]} (line {cl})")
    if depth:
        print(f"UNBALANCED: depth {depth} at end, last open {open_at}")

    print("\n== Verse lengths over 1,500 characters (plain text) ==")
    for (ch, lab), t in text.items():
        if len(t) > 1500:
            print(f"{ch}:{lab}  {len(t)} chars")

    # Same inclusive (chapter, verse) range test as ingest/bible.py
    # collect_pericope_verses: a verse outside every KJV range is dropped.
    print("\n== WEB-C verses outside every KJV Esther pericope (dropped today) ==")
    try:
        peri = json.load(open(PERICOPES, encoding="utf-8"))
    except OSError:
        print(f"(pericope file not found: {PERICOPES})")
        return
    def ref(r):
        cv = r.rsplit(" ", 1)[1]; c, v = cv.split(":"); return int(c), int(v)
    ranges = [(ref(x["Reference Start"]), ref(x["Reference End"]))
              for x in peri if x["Reference Start"].startswith("Esther ")]
    print(f"KJV Esther pericopes: {len(ranges)}")
    dropped = []
    for ch, vs in chapters.items():
        for lab, ln in vs:
            v = int(lab.split("-")[0])
            if not any(a <= (ch, v) <= b for a, b in ranges):
                dropped.append((ch, v, ln))
    runs = []
    for ch, v, ln in dropped:
        if runs and runs[-1][0] == ch and runs[-1][2] == v - 1:
            runs[-1][2] = v; runs[-1][4] = ln
        else:
            runs.append([ch, v, v, ln, ln])
    for ch, a, b, l1, l2 in runs:
        print(f"{ch}:{a}-{b}  ({b - a + 1} verses, USFM lines {l1}-{l2})")
    print(f"total dropped: {len(dropped)}")


NV_LETTERS = "abcdefghiklmnopqrstuvxyz"  # the Nova Vulgata skips j and w


def nv_labels(path):
    import html as htmlmod
    raw = open(path, encoding="latin-1").read()
    raw = re.sub(r"<br\s*/?>|</p>", "\n", raw)
    t = htmlmod.unescape(re.sub(r"<[^>]+>", "", raw))
    start = t.find("1 2 3 4 5 6  7 8 9 10")
    if start == -1:
        sys.exit("Nova Vulgata page: chapter index line not found")
    t = t[start + 21:]

    def lkey(letters):
        if not letters:
            return -1
        if len(letters) == 2:
            return 100 + NV_LETTERS.index(letters[0])
        return NV_LETTERS.index(letters)

    tok = re.compile(r"(?<!\S)(\d{1,2})([a-z]{0,2})(?=\s)")
    chap, cur, out = 0, None, OrderedDict()
    for line in t.split("\n"):
        s = line.strip()
        if not s:
            continue
        if re.fullmatch(r"\d{1,2}", s):
            chap = int(s); out[chap] = []; cur = None
            continue
        for m in tok.finditer(s):
            n, let = int(m.group(1)), m.group(2)
            # Accept a number as a verse label only if it can follow the last one.
            if (cur is None
                    or (n == cur[0] and lkey(let) > lkey(cur[1]))
                    or (n in (cur[0] + 1, cur[0] + 2) and let in ("", "a"))
                    or (chap == 1 and cur == (1, "k") and (n, let) == (1, ""))):
                cur = (n, let); out[chap].append(f"{n}{let}")
    print("== Nova Vulgata Esther verse labels (vatican.va) ==")
    total = 0
    for chap, labs in out.items():
        total += len(labs)
        lettered = [l for l in labs if not l.isdigit()]
        plain_nums = [int(l) for l in labs if l.isdigit()]
        miss = [n for n in range(1, max(plain_nums) + 1) if n not in plain_nums]
        print(f"ch {chap:>2}: {len(labs):>2} labels, plain verses 1-{max(plain_nums)}"
              + (f" missing {miss}" if miss else "")
              + f", lettered {len(lettered)}")
        print("        " + " ".join(labs))
    print(f"total labels: {total}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--nv":
        nv_labels(sys.argv[2])
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
