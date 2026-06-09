from __future__ import annotations
import asyncio
import os
import re
import sys
import time

import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document

_DELAY = 1.0
_MIN_LENGTH = 50
_TARGET = 1200
_CEILING = 3500

_SCRIPTURE_RE = re.compile(
    r'\b(?:[1-3]\s*[A-Z][a-z]+|[A-Z][a-z]+)\s+\d+:\d+(?:[–\-]\d+)?'
)

ENCYCLICALS: list[tuple[str, str, int, str]] = [
    ("Rerum Novarum",       "Pope Leo XIII",       1891, "https://www.papalencyclicals.net/leo13/l13rerum.htm"),
    ("Quadragesimo Anno",   "Pope Pius XI",        1931, "https://www.papalencyclicals.net/pius11/p11quadr.htm"),
    ("Humani Generis",      "Pope Pius XII",       1950, "https://www.papalencyclicals.net/pius12/p12human.htm"),
    ("Mater et Magistra",   "Pope John XXIII",     1961, "https://www.papalencyclicals.net/john23/j23mater.htm"),
    ("Pacem in Terris",     "Pope John XXIII",     1963, "https://www.papalencyclicals.net/john23/j23pacem.htm"),
    ("Humanae Vitae",       "Pope Paul VI",        1968, "https://www.papalencyclicals.net/paul06/p6humana.htm"),
    ("Evangelii Nuntiandi", "Pope Paul VI",        1975, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19751208_evangelii-nuntiandi.html"),
    ("Redemptor Hominis",   "Pope John Paul II",   1979, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_04031979_redemptor-hominis.html"),
    ("Laborem Exercens",    "Pope John Paul II",   1981, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_14091981_laborem-exercens.html"),
    ("Veritatis Splendor",  "Pope John Paul II",   1993, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_06081993_veritatis-splendor.html"),
    ("Evangelium Vitae",    "Pope John Paul II",   1995, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_25031995_evangelium-vitae.html"),
    ("Fides et Ratio",      "Pope John Paul II",   1998, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_14091998_fides-et-ratio.html"),
    ("Deus Caritas Est",    "Pope Benedict XVI",   2005, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20051225_deus-caritas-est_en.html"),
    ("Spe Salvi",           "Pope Benedict XVI",   2007, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20071130_spe-salvi_en.html"),
    ("Caritas in Veritate", "Pope Benedict XVI",   2009, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20090629_caritas-in-veritate_en.html"),
    ("Evangelii Gaudium",   "Pope Francis",        2013, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20131124_evangelii-gaudium.html"),
    ("Laudato Si",          "Pope Francis",        2015, "https://www.vatican.va/content/francesco/en/encyclicals/documents/papa-francesco_20150524_enciclica-laudato-si.html"),
    ("Magnifica Humanitas", "Pope Leo XIV",        2026, "https://www.vatican.va/content/leo-xiv/en/encyclicals/documents/20260515-magnifica-humanitas.html"),
]


def _detect_section_header(p_tag) -> str | None:
    """Return the section label if the <p> element is a section header; else None."""
    text = p_tag.get_text(strip=True)
    if not text or len(text) < 3:
        return None
    # Roman numeral pattern: "I. Title text" or "IV. Something"
    if re.match(r'^[IVX]+\.\s+\w', text):
        return text
    # Entire content is a single <b> or <strong> child with no surrounding text
    real_children = [c for c in p_tag.children if hasattr(c, 'name') and c.name is not None]
    bare_text = "".join(str(c) for c in p_tag.children if not hasattr(c, 'name')).strip()
    if (len(real_children) == 1
            and real_children[0].name in ('b', 'strong')
            and not bare_text
            and len(text) >= 10
            and not text.endswith(":")):
        return text
    return None


def parse_encyclical(
    html: str,
    title: str,
    author: str,
    year: int,
) -> list[tuple[str, str, int, dict]]:
    """Parse an encyclical HTML page into chunks.

    Returns list of (content, reference, position, metadata).
    Position 0 is the intro/overview chunk when preamble or sections exist.
    """
    soup = BeautifulSoup(html, "lxml")

    # ── Pass 1: tokenise ─────────────────────────────────────────────────────
    tokens: list[dict] = []
    first_numbered = False
    all_sections: list[str] = []

    for p in soup.find_all("p"):
        section_label = _detect_section_header(p)
        if section_label:
            tokens.append({"kind": "section", "num": None, "text": section_label})
            all_sections.append(section_label)
            continue

        raw = p.get_text(separator=" ", strip=True)
        m = re.match(r"^(\d+)\.\s*(.+)", raw, re.DOTALL)
        if m:
            first_numbered = True
            num = int(m.group(1))
            body = m.group(2).strip()
            if len(body) >= _MIN_LENGTH:
                tokens.append({"kind": "para", "num": num, "text": body})
        elif not first_numbered and len(raw) >= _MIN_LENGTH:
            tokens.append({"kind": "preamble", "num": None, "text": raw})

    # ── Intro chunk ───────────────────────────────────────────────────────────
    chunks: list[tuple[str, str, int, dict]] = []
    position = 0

    preamble = "\n\n".join(t["text"] for t in tokens if t["kind"] == "preamble")[:600]
    sections_summary = ", ".join(all_sections)[:400]

    if preamble or sections_summary:
        lines = [f"{title} — {author}, {year}"]
        if preamble:
            lines.append(preamble)
        if sections_summary:
            lines.append(f"Sections: {sections_summary}")
        chunks.append((
            "\n\n".join(lines),
            f"{title} — Overview",
            0,
            {"section": None, "para_range": None, "scripture_refs": [], "year": year, "pope": author},
        ))
        position = 1

    # ── Pass 2: accumulate chunks ────────────────────────────────────────────
    prefix = f"In {title} ({author}, {year})"
    active_section: str | None = None
    acc: list[tuple[int, str]] = []   # (para_num, text); overlap uses num=-1
    acc_len = 0
    overlap_text: str | None = None

    def _build_chunk(section: str | None, paras: list[tuple[int, str]]) -> tuple[str, str, dict]:
        section_part = f", §{section}" if section else ""
        body = "\n\n".join(text for _, text in paras)
        content = f"{prefix}{section_part}:\n\n{body}"
        real = [(n, t) for n, t in paras if n != -1]
        first_num = real[0][0] if real else 0
        last_num = real[-1][0] if real else 0
        ref = (f"{title}, §§{first_num}–{last_num}"
               if first_num != last_num else f"{title}, §{first_num}")
        scripture_refs = list(dict.fromkeys(
            m for _, t in real for m in _SCRIPTURE_RE.findall(t)
        ))
        meta = {
            "section": section,
            "para_range": [first_num, last_num],
            "scripture_refs": scripture_refs,
            "year": year,
            "pope": author,
        }
        return content, ref, meta

    def flush() -> None:
        nonlocal position, overlap_text
        if not acc:
            return
        if all(n == -1 for n, _ in acc):
            return
        content, ref, meta = _build_chunk(active_section, acc)
        if len(content) <= _CEILING:
            chunks.append((content, ref, position, meta))
            position += 1
        else:
            real = [(n, t) for n, t in acc if n != -1]
            total_len = sum(len(t) for _, t in real)
            running = 0
            split_at = max(1, len(real) // 2)
            for i, (_, t) in enumerate(real):
                running += len(t)
                if running >= total_len // 2:
                    split_at = i + 1
                    break
            for half in [real[:split_at], real[split_at:]]:
                if half:
                    c, r, m = _build_chunk(active_section, half)
                    chunks.append((c, r, position, m))
                    position += 1
        real_paras = [(n, t) for n, t in acc if n != -1]
        overlap_text = real_paras[-1][1] if real_paras else None

    for token in tokens:
        if token["kind"] == "preamble":
            continue

        if token["kind"] == "section":
            flush()
            active_section = token["text"]
            acc = []
            acc_len = 0
            overlap_text = None   # no overlap across section boundaries
            continue

        # "para" kind
        num, text = token["num"], token["text"]

        if acc_len + len(text) > _TARGET and acc:
            flush()
            acc = []
            acc_len = 0
            if overlap_text is not None:
                acc.append((-1, overlap_text))
                acc_len = len(overlap_text)

        acc.append((num, text))
        acc_len += len(text)

    flush()
    return chunks


async def main(pool) -> None:
    skipped: list[str] = []
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
    ) as client:
        with tqdm(total=len(ENCYCLICALS), unit="doc", desc="Encyclicals") as pbar:
            for title, author, year, url in ENCYCLICALS:
                time.sleep(_DELAY)
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except Exception as exc:
                    print(f"\n  WARNING: Failed to fetch {title}: {exc}", file=sys.stderr)
                    skipped.append(title)
                    pbar.update(1)
                    continue

                chunks = parse_encyclical(resp.text, title, author, year)

                if not chunks:
                    print(f"\n  WARNING: No chunks extracted for {title}", file=sys.stderr)
                    skipped.append(title)
                    pbar.update(1)
                    continue

                doc_id = await upsert_document(
                    pool,
                    collection="encyclicals",
                    title=title,
                    translation="",
                    author=author,
                    year=year,
                    metadata={"url": url, "pope": author},
                )

                for content, reference, position, meta in chunks:
                    await upsert_chunk(
                        pool,
                        document_id=doc_id,
                        content=content,
                        position=position,
                        reference=reference,
                        metadata=meta,
                    )

                pbar.set_postfix({"doc": title, "chunks": len(chunks)})
                pbar.update(1)

    if skipped:
        print(f"\n  WARNING: {len(skipped)} documents failed: {skipped}", file=sys.stderr)
    print(f"  Done. {len(ENCYCLICALS) - len(skipped)} encyclicals written.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
