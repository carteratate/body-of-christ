"""Vendor the web-fetched corpus sources to local files for reproducible ingest.

Downloads the medieval / encyclicals / councils / canon-law raw sources into
``sources/<collection>/`` and writes a ``manifest.json`` per collection capturing
(title, author, year, url, file) for each document. The dual-pipeline adapters
then read these local files instead of hitting the network at ingest time
(design 2026-06-13-dual-datapipeline §7: re-acquire first, record provenance).

    cd datapipeline && python3 scripts/vendor_sources.py --collection medieval
    cd datapipeline && python3 scripts/vendor_sources.py --collection all

Idempotent: skips a file that already exists unless --force is given.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import httpx
from bs4 import BeautifulSoup

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SOURCES = os.path.join(_ROOT, "sources")

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_DELAY = 0.7  # polite delay between requests (s)

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _NON_SLUG.sub("-", text.strip().lower()).strip("-")


# ── Manifests (copied from the legacy ingest scripts) ────────────────────────

MEDIEVAL = [
    {"url": "https://ccel.org/ccel/a/anselm/basic_works.xml",
     "title": "Proslogium, Monologium, and Cur Deus Homo",
     "author": "Anselm", "year": 1099, "fix_author": True, "merge_short": False},
    {"url": "https://ccel.org/ccel/b/boethius/consolation.xml",
     "title": "Consolation of Philosophy",
     "author": "Boethius", "year": 524, "fix_author": False, "merge_short": False},
    {"url": "https://ccel.org/ccel/b/bernard/loving_god.xml",
     "title": "On Loving God",
     "author": "Bernard of Clairvaux", "year": 1128, "fix_author": False, "merge_short": False},
    {"url": "https://ccel.org/ccel/k/kempis/imitation.xml",
     "title": "Imitation of Christ",
     "author": "Thomas à Kempis", "year": 1441, "fix_author": False, "merge_short": True},
]

ENCYCLICALS = [
    ("Rerum Novarum",       "Pope Leo XIII",     1891, "https://www.papalencyclicals.net/leo13/l13rerum.htm"),
    ("Quadragesimo Anno",   "Pope Pius XI",      1931, "https://www.papalencyclicals.net/pius11/p11quadr.htm"),
    ("Humani Generis",      "Pope Pius XII",     1950, "https://www.papalencyclicals.net/pius12/p12human.htm"),
    ("Mater et Magistra",   "Pope John XXIII",   1961, "https://www.papalencyclicals.net/john23/j23mater.htm"),
    ("Pacem in Terris",     "Pope John XXIII",   1963, "https://www.papalencyclicals.net/john23/j23pacem.htm"),
    ("Humanae Vitae",       "Pope Paul VI",      1968, "https://www.papalencyclicals.net/paul06/p6humana.htm"),
    ("Evangelii Nuntiandi", "Pope Paul VI",      1975, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19751208_evangelii-nuntiandi.html"),
    ("Redemptor Hominis",   "Pope John Paul II", 1979, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_04031979_redemptor-hominis.html"),
    ("Laborem Exercens",    "Pope John Paul II", 1981, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_14091981_laborem-exercens.html"),
    ("Veritatis Splendor",  "Pope John Paul II", 1993, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_06081993_veritatis-splendor.html"),
    ("Evangelium Vitae",    "Pope John Paul II", 1995, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_25031995_evangelium-vitae.html"),
    ("Fides et Ratio",      "Pope John Paul II", 1998, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_14091998_fides-et-ratio.html"),
    ("Deus Caritas Est",    "Pope Benedict XVI", 2005, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20051225_deus-caritas-est_en.html"),
    ("Spe Salvi",           "Pope Benedict XVI", 2007, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20071130_spe-salvi_en.html"),
    ("Caritas in Veritate", "Pope Benedict XVI", 2009, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20090629_caritas-in-veritate_en.html"),
    ("Evangelii Gaudium",   "Pope Francis",      2013, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20131124_evangelii-gaudium.html"),
    ("Laudato Si",          "Pope Francis",      2015, "https://www.vatican.va/content/francesco/en/encyclicals/documents/papa-francesco_20150524_enciclica-laudato-si.html"),
    ("Magnifica Humanitas", "Pope Leo XIV",      2026, "https://www.vatican.va/content/leo-xiv/en/encyclicals/documents/20260515-magnifica-humanitas.html"),
]

COUNCILS = [
    ("Council of Nicaea",                  325,  "https://www.papalencyclicals.net/councils/ecum01.htm"),
    ("First Council of Constantinople",    381,  "https://www.papalencyclicals.net/councils/ecum02.htm"),
    ("Council of Ephesus",                 431,  "https://www.papalencyclicals.net/councils/ecum03.htm"),
    ("Council of Chalcedon",               451,  "https://www.papalencyclicals.net/councils/ecum04.htm"),
    ("Second Council of Constantinople",   553,  "https://www.papalencyclicals.net/councils/ecum05.htm"),
    ("Third Council of Constantinople",    681,  "https://www.papalencyclicals.net/councils/ecum06.htm"),
    ("Second Council of Nicaea",           787,  "https://www.papalencyclicals.net/councils/ecum07.htm"),
    ("Fourth Council of Constantinople",   870,  "https://www.papalencyclicals.net/councils/ecum08.htm"),
    ("First Lateran Council",              1123, "https://www.papalencyclicals.net/councils/ecum09.htm"),
    ("Second Lateran Council",             1139, "https://www.papalencyclicals.net/councils/ecum10.htm"),
    ("Third Lateran Council",              1179, "https://www.papalencyclicals.net/councils/ecum11.htm"),
    ("Fourth Lateran Council",             1215, "https://www.papalencyclicals.net/councils/ecum12-2.htm"),
    ("First Council of Lyons",             1245, "https://www.papalencyclicals.net/councils/ecum13.htm"),
    ("Second Council of Lyons",            1274, "https://www.papalencyclicals.net/councils/ecum14.htm"),
    ("Council of Vienne",                  1311, "https://www.papalencyclicals.net/councils/ecum15.htm"),
    ("Council of Constance",               1418, "https://www.papalencyclicals.net/councils/ecum16.htm"),
    ("Council of Basel-Ferrara-Florence",  1445, "https://www.papalencyclicals.net/councils/ecum17.htm"),
    ("Fifth Lateran Council",              1517, "https://www.papalencyclicals.net/councils/ecum18.htm"),
    ("Council of Trent",                   1563, "https://www.papalencyclicals.net/councils/trent/the-complete-text.htm"),
    ("First Vatican Council",              1870, "https://www.papalencyclicals.net/councils/ecum20.htm"),
]

VATICAN_II = [
    ("Dei Verbum",              "constitution", 1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_const_19651118_dei-verbum_en.html"),
    ("Lumen Gentium",           "constitution", 1964, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_const_19641121_lumen-gentium_en.html"),
    ("Sacrosanctum Concilium",  "constitution", 1963, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_const_19631204_sacrosanctum-concilium_en.html"),
    ("Gaudium et Spes",         "constitution", 1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_const_19651207_gaudium-et-spes_en.html"),
    ("Ad Gentes",               "decree",       1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651207_ad-gentes_en.html"),
    ("Presbyterorum Ordinis",   "decree",       1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651207_presbyterorum-ordinis_en.html"),
    ("Apostolicam Actuositatem","decree",       1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651118_apostolicam-actuositatem_en.html"),
    ("Optatam Totius",          "decree",       1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651028_optatam-totius_en.html"),
    ("Perfectae Caritatis",     "decree",       1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651028_perfectae-caritatis_en.html"),
    ("Christus Dominus",        "decree",       1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19651028_christus-dominus_en.html"),
    ("Unitatis Redintegratio",  "decree",       1964, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19641121_unitatis-redintegratio_en.html"),
    ("Orientalium Ecclesiarum", "decree",       1964, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19641121_orientalium-ecclesiarum_en.html"),
    ("Inter Mirifica",          "decree",       1963, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decree_19631204_inter-mirifica_en.html"),
    ("Gravissimum Educationis", "declaration",  1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decl_19651028_gravissimum-educationis_en.html"),
    ("Nostra Aetate",           "declaration",  1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decl_19651028_nostra-aetate_en.html"),
    ("Dignitatis Humanae",      "declaration",  1965, "https://www.vatican.va/archive/hist_councils/ii_vatican_council/documents/vat-ii_decl_19651207_dignitatis-humanae_en.html"),
]

_CANON_INDEX = "http://www.vatican.va/archive/cod-iuris-canonici/cic_index_en.html"
_CANON_BASE = "http://www.vatican.va"


def _client() -> httpx.Client:
    return httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": _UA})


def _fetch(client: httpx.Client, url: str) -> bytes | None:
    try:
        r = client.get(url)
        r.raise_for_status()
        return r.content
    except httpx.HTTPError as exc:
        print(f"  WARNING: failed {url}: {exc}", file=sys.stderr)
        return None


def _save(coll_dir: str, filename: str, data: bytes, force: bool) -> bool:
    path = os.path.join(coll_dir, filename)
    if os.path.exists(path) and not force:
        print(f"  skip (exists): {filename}")
        return True
    with open(path, "wb") as f:
        f.write(data)
    print(f"  saved: {filename} ({len(data):,} bytes)")
    return True


def vendor_medieval(force: bool) -> None:
    d = os.path.join(_SOURCES, "medieval")
    os.makedirs(d, exist_ok=True)
    manifest = []
    with _client() as client:
        for w in MEDIEVAL:
            fname = _slug(w["title"]) + ".xml"
            if not (os.path.exists(os.path.join(d, fname)) and not force):
                data = _fetch(client, w["url"])
                if data is None:
                    continue
                _save(d, fname, data, force)
                time.sleep(_DELAY)
            else:
                print(f"  skip (exists): {fname}")
            manifest.append({**w, "file": fname})
    _write_manifest(d, manifest)


def vendor_encyclicals(force: bool) -> None:
    d = os.path.join(_SOURCES, "encyclicals")
    os.makedirs(d, exist_ok=True)
    manifest = []
    with _client() as client:
        for title, author, year, url in ENCYCLICALS:
            fname = _slug(title) + ".html"
            if not (os.path.exists(os.path.join(d, fname)) and not force):
                data = _fetch(client, url)
                if data is None:
                    continue
                _save(d, fname, data, force)
                time.sleep(_DELAY)
            else:
                print(f"  skip (exists): {fname}")
            manifest.append({"title": title, "author": author, "year": year,
                             "url": url, "slug": _slug(title), "file": fname})
    _write_manifest(d, manifest)


def vendor_councils(force: bool) -> None:
    d = os.path.join(_SOURCES, "councils")
    os.makedirs(d, exist_ok=True)
    manifest = []
    with _client() as client:
        for n, (title, year, url) in enumerate(COUNCILS, start=1):
            fname = f"ecum-{n:02d}-{_slug(title)}.html"
            if not (os.path.exists(os.path.join(d, fname)) and not force):
                data = _fetch(client, url)
                if data is None:
                    continue
                _save(d, fname, data, force)
                time.sleep(_DELAY)
            else:
                print(f"  skip (exists): {fname}")
            manifest.append({"council": title, "document": title, "year": year,
                             "council_number": n, "group": "ecumenical-1-20",
                             "url": url, "file": fname})
        for title, doctype, year, url in VATICAN_II:
            fname = f"vat2-{_slug(title)}.html"
            if not (os.path.exists(os.path.join(d, fname)) and not force):
                data = _fetch(client, url)
                if data is None:
                    continue
                _save(d, fname, data, force)
                time.sleep(_DELAY)
            else:
                print(f"  skip (exists): {fname}")
            manifest.append({"council": "Second Vatican Council", "document": title,
                             "document_type": doctype, "year": year,
                             "group": "vatican-ii", "url": url, "file": fname})
    _write_manifest(d, manifest)


def _discover_canon_pages(index_html: bytes) -> list[str]:
    soup = BeautifulSoup(index_html, "lxml")
    hrefs = [a["href"] for a in soup.find_all("a", href=True)
             if "cic_lib" in a["href"] and "_en.html" in a["href"]]
    seen, out = set(), []
    for href in hrefs:
        url = href.split("#")[0]
        abs_url = url if url.startswith("http") else _CANON_BASE + url
        if abs_url not in seen:
            seen.add(abs_url)
            out.append(abs_url)
    return out


def vendor_canon_law(force: bool) -> None:
    d = os.path.join(_SOURCES, "canon-law")
    os.makedirs(d, exist_ok=True)
    manifest = []
    with _client() as client:
        index = _fetch(client, _CANON_INDEX)
        if index is None:
            print("  ABORT: could not fetch canon-law index", file=sys.stderr)
            return
        _save(d, "cic_index_en.html", index, force)
        pages = _discover_canon_pages(index)
        print(f"  discovered {len(pages)} canon pages")
        time.sleep(_DELAY)
        for url in pages:
            fname = url.rsplit("/", 1)[-1]
            if not (os.path.exists(os.path.join(d, fname)) and not force):
                data = _fetch(client, url)
                if data is None:
                    continue
                _save(d, fname, data, force)
                time.sleep(_DELAY)
            else:
                print(f"  skip (exists): {fname}")
            manifest.append({"url": url, "file": fname})
    _write_manifest(d, manifest, name="pages.json")


def _write_manifest(coll_dir: str, manifest: list, name: str = "manifest.json") -> None:
    with open(os.path.join(coll_dir, name), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"  manifest: {name} ({len(manifest)} entries)")


VENDORS = {
    "medieval": vendor_medieval,
    "encyclicals": vendor_encyclicals,
    "councils": vendor_councils,
    "canon-law": vendor_canon_law,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True, choices=list(VENDORS) + ["all"])
    ap.add_argument("--force", action="store_true", help="re-download even if file exists")
    a = ap.parse_args()
    targets = list(VENDORS) if a.collection == "all" else [a.collection]
    for c in targets:
        print(f"== {c} ==")
        VENDORS[c](a.force)


if __name__ == "__main__":
    main()
