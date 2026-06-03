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
_CHUNK_SIZE = 3

# (title, author, year, url)
# papalencyclicals.net used where available; vatican.va for JP2+, Francis
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
    ("Amoris Laetitia",     "Pope Francis",        2016, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20160319_amoris-laetitia.html"),
]


def parse_encyclical_paragraphs(html: str) -> list[tuple[int, str]]:
    """
    Extract numbered paragraphs from encyclical HTML.
    Returns list of (para_num, text) — text has the number prefix stripped.
    """
    soup = BeautifulSoup(html, "lxml")
    result: list[tuple[int, str]] = []
    for p in soup.find_all("p"):
        text = p.get_text(separator=" ", strip=True)
        m = re.match(r"^(\d+)\.\s*(.+)", text, re.DOTALL)
        if m:
            num = int(m.group(1))
            body = m.group(2).strip()
            result.append((num, body))
    return result


def group_paragraphs(
    paras: list[tuple[int, str]],
    chunk_size: int = _CHUNK_SIZE,
    min_length: int = _MIN_LENGTH,
) -> list[tuple[str, str, int]]:
    """
    Group paragraphs into chunks of chunk_size.
    Returns list of (content, reference, position).
    """
    filtered = [(num, text) for num, text in paras if len(text) >= min_length]
    chunks: list[tuple[str, str, int]] = []
    for i in range(0, len(filtered), chunk_size):
        group = filtered[i : i + chunk_size]
        content = "\n\n".join(text for _, text in group)
        first_num = group[0][0]
        last_num = group[-1][0]
        ref = f"§{first_num}-{last_num}" if first_num != last_num else f"§{first_num}"
        chunks.append((content, ref, len(chunks)))
    return chunks


async def main(pool) -> None:
    skipped: list[str] = []
    with httpx.Client(timeout=30, follow_redirects=True) as client:
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

                paras = parse_encyclical_paragraphs(resp.text)
                chunks = group_paragraphs(paras)

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

                for content, reference, position in chunks:
                    await upsert_chunk(
                        pool,
                        document_id=doc_id,
                        content=content,
                        position=position,
                        reference=f"{title}, {reference}",
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
