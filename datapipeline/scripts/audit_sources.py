"""Audit vendored corpus sources to inform per-collection passage design.

Read-only structural analysis of sources/<collection>/ (after vendor_sources.py).
Reports the facts that drive anchor/chapter_key/cleaning decisions:
section-header presence, numbered-paragraph counts, hierarchy depth, oversized
units, footnote-marker and ALL-CAPS density. Writes nothing; prints a report.

    cd datapipeline && python3 scripts/audit_sources.py --collection all
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from bs4 import BeautifulSoup

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SOURCES = os.path.join(_ROOT, "sources")

_FOOTNOTE = re.compile(r"(?<=\S)\s*\[\d+\]")
_CAPS_RUN = re.compile(r"\b(?:[A-Z][A-Z'’]+)(?:\s+[A-Z][A-Z'’]+){2,}\b")
_NUMBERED = re.compile(r"^(\d+)\.\s+(.+)", re.DOTALL)
_ROMAN_SECTION = re.compile(r"^[IVX]+\.\s+\w")
_CHAPTER = re.compile(r"^CHAPTER\s+[IVXLCDM]+", re.IGNORECASE)


def _load_manifest(d: str, name: str = "manifest.json") -> list:
    p = os.path.join(d, name)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _soup(path: str) -> BeautifulSoup:
    with open(path, "rb") as f:
        return BeautifulSoup(f.read(), "lxml")


def _is_bold_header(p) -> bool:
    children = [c for c in p.children if getattr(c, "name", None)]
    bare = "".join(str(c) for c in p.children if not getattr(c, "name", None)).strip()
    txt = p.get_text(strip=True)
    return (len(children) == 1 and children[0].name in ("b", "strong")
            and not bare and len(txt) >= 10 and not txt.endswith(":"))


def audit_encyclicals() -> None:
    d = os.path.join(_SOURCES, "encyclicals")
    print(f"\n{'title':28} {'paras':>5} {'sects':>5} {'foot':>5} {'caps':>5} {'maxP':>6}")
    for m in _load_manifest(d):
        soup = _soup(os.path.join(d, m["file"]))
        paras = sects = foot = caps = maxp = 0
        for p in soup.find_all("p"):
            txt = p.get_text(separator=" ", strip=True)
            if not txt:
                continue
            if _ROMAN_SECTION.match(txt) or _is_bold_header(p):
                sects += 1
                continue
            mm = _NUMBERED.match(txt)
            if mm:
                paras += 1
                maxp = max(maxp, len(mm.group(2)))
            foot += len(_FOOTNOTE.findall(txt))
            caps += len(_CAPS_RUN.findall(txt))
        print(f"{m['title'][:28]:28} {paras:>5} {sects:>5} {foot:>5} {caps:>5} {maxp:>6}")


def audit_councils() -> None:
    d = os.path.join(_SOURCES, "councils")
    print(f"\n{'document':28} {'group':14} {'p':>4} {'num':>4} {'h2/3/4':>7} "
          f"{'chap':>4} {'foot':>5} {'caps':>5}")
    for m in _load_manifest(d):
        soup = _soup(os.path.join(d, m["file"]))
        for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
            tag.decompose()
        p = num = head = chap = foot = caps = 0
        for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "strong"]):
            txt = el.get_text(separator=" ", strip=True)
            if not txt:
                continue
            if el.name in ("h2", "h3", "h4"):
                head += 1
            if _CHAPTER.match(txt):
                chap += 1
            if el.name == "p":
                p += 1
                if _NUMBERED.match(txt):
                    num += 1
                foot += len(_FOOTNOTE.findall(txt))
                caps += len(_CAPS_RUN.findall(txt))
        print(f"{m['document'][:28]:28} {m['group'][:14]:14} {p:>4} {num:>4} "
              f"{head:>7} {chap:>4} {foot:>5} {caps:>5}")


def audit_canon_law() -> None:
    d = os.path.join(_SOURCES, "canon-law")
    sys.path.insert(0, _ROOT)
    from ingest.canon_law import parse_canon_page, _context_key  # noqa: E402
    pages = _load_manifest(d, "pages.json")
    all_canons = []
    for m in pages:
        soup_path = os.path.join(d, m["file"])
        with open(soup_path, "rb") as f:
            html = f.read().decode("utf-8", "replace")
        all_canons.extend(parse_canon_page(html))
    # dedup by canon number
    seen, uniq = set(), []
    for num, text, ctx in sorted(all_canons, key=lambda x: x[0]):
        if num not in seen:
            seen.add(num)
            uniq.append((num, text, ctx))
    sizes = [len(t) for _, t, _ in uniq]
    over = [n for n, t, _ in uniq if len(t) > 3500]
    books = {ctx["book"] for _, _, ctx in uniq if ctx["book"]}
    titles = {(ctx["book"], ctx["title"]) for _, _, ctx in uniq if ctx["title"]}
    chapters = {_context_key(ctx) for _, _, ctx in uniq}
    print(f"\n  unique canons:   {len(uniq)}")
    print(f"  canon size:      min={min(sizes)} max={max(sizes)} "
          f"mean={sum(sizes)//len(sizes)}")
    print(f"  canons > 3500:   {len(over)}  {over[:10]}")
    print(f"  books:           {len(books)}")
    print(f"  (book,title):    {len(titles)} distinct")
    print(f"  full ctx groups: {len(chapters)} distinct")
    print(f"  sample books:    {sorted(books)[:8]}")


def audit_medieval() -> None:
    d = os.path.join(_SOURCES, "medieval")
    sys.path.insert(0, _ROOT)
    import defusedxml.ElementTree as ET  # noqa: E402
    for m in _load_manifest(d):
        with open(os.path.join(d, m["file"]), encoding="utf-8", errors="replace") as f:
            xml = f.read()
        xml = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)
        root = ET.fromstring(xml)
        div1 = len(list(root.iter("div1")))
        div2 = len(list(root.iter("div2")))
        div3 = len(list(root.iter("div3")))
        ps = len(list(root.iter("p")))
        print(f"  {m['title'][:38]:38} div1={div1:>3} div2={div2:>3} "
              f"div3={div3:>4} p={ps:>5} multiwork={m.get('fix_author')}")


AUDITS = {
    "encyclicals": audit_encyclicals,
    "councils": audit_councils,
    "canon-law": audit_canon_law,
    "medieval": audit_medieval,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True, choices=list(AUDITS) + ["all"])
    a = ap.parse_args()
    targets = list(AUDITS) if a.collection == "all" else [a.collection]
    for c in targets:
        print(f"\n===== {c} =====")
        AUDITS[c]()


if __name__ == "__main__":
    main()
