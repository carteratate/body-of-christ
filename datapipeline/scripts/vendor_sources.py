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
    # Pope Benedict XIV (1740–1758)
    ("Ubi Primum",                "Pope Benedict XIV",  1740, "https://www.papalencyclicals.net/ben14/b14ubipr.htm"),
    ("Quanta Cura",               "Pope Benedict XIV",  1741, "https://www.papalencyclicals.net/ben14/b14quant.htm"),
    ("Nimiam Licentiam",          "Pope Benedict XIV",  1743, "https://www.papalencyclicals.net/ben14/b14nimia.htm"),
    ("Vix Pervenit",              "Pope Benedict XIV",  1745, "https://www.papalencyclicals.net/ben14/b14vixpe.htm"),
    ("Magnae Nobis",              "Pope Benedict XIV",  1748, "https://www.papalencyclicals.net/ben14/b14magna.htm"),
    ("Annus Qui Hunc",            "Pope Benedict XIV",  1749, "https://www.papalencyclicals.net/ben14/annus-qui-hunc.htm"),
    ("Apostolica Constitutio",    "Pope Benedict XIV",  1749, "https://www.papalencyclicals.net/ben14/b14apost.htm"),
    ("Peregrinantes",             "Pope Benedict XIV",  1749, "https://www.papalencyclicals.net/ben14/b14pereg.htm"),
    ("A Quo Primum",              "Pope Benedict XIV",  1751, "https://www.papalencyclicals.net/ben14/b14aquo.htm"),
    ("Cum Religiosi",             "Pope Benedict XIV",  1754, "https://www.papalencyclicals.net/ben14/b14cumre.htm"),
    ("Quod Provinciale",          "Pope Benedict XIV",  1754, "https://www.papalencyclicals.net/ben14/b14quod.htm"),
    ("Allatae Sunt",              "Pope Benedict XIV",  1755, "https://www.papalencyclicals.net/ben14/b14allat.htm"),
    ("Ex Omnibus",                "Pope Benedict XIV",  1756, "https://www.papalencyclicals.net/ben14/b14exomn.htm"),
    ("Ex Quo",                    "Pope Benedict XIV",  1756, "https://www.papalencyclicals.net/ben14/b14exquo.htm"),
    # Pope Clement XIII (1758–1769)
    ("A Quo Die",                 "Pope Clement XIII",  1758, "https://www.papalencyclicals.net/clem13/c13aquod.htm"),
    ("Cum Primum",                "Pope Clement XIII",  1759, "https://www.papalencyclicals.net/clem13/c13cumpr.htm"),
    ("Appetente Sacro",           "Pope Clement XIII",  1759, "https://www.papalencyclicals.net/clem13/c13appet.htm"),
    ("In Dominico Agro",          "Pope Clement XIII",  1761, "https://www.papalencyclicals.net/clem13/c13indom.htm"),
    ("Christianae Reipublicae",   "Pope Clement XIII",  1766, "https://www.papalencyclicals.net/clem13/c13chris.htm"),
    ("Summa Quae",                "Pope Clement XIII",  1768, "https://www.papalencyclicals.net/clem13/c13summa.htm"),
    # Pope Clement XIV (1769–1774)
    ("Cum Summi",                         "Pope Clement XIV",  1769, "https://www.papalencyclicals.net/clem14/c14cumsu.htm"),
    ("Decet Quam Maxime",                 "Pope Clement XIV",  1769, "https://www.papalencyclicals.net/clem14/c14decet.htm"),
    ("Inscrutabili Divinae Sapientiae",   "Pope Clement XIV",  1769, "https://www.papalencyclicals.net/clem14/c14inscr.htm"),
    ("Salutis Nostrae",                   "Pope Clement XIV",  1774, "https://www.papalencyclicals.net/clem14/c14salut.htm"),
    # Pope Pius VI (1775–1799)
    ("Inscrutabile",              "Pope Pius VI",       1775, "https://www.papalencyclicals.net/pius06/p6inscru.htm"),
    ("Charitas",                  "Pope Pius VI",       1791, "https://www.papalencyclicals.net/pius06/p6charit.htm"),
    ("Ubi Lutetiam",              "Pope Pius VI",       1792, "https://www.papalencyclicals.net/pius06/p6ubilu-i.htm"),
    # Pope Pius VII (1800–1823)
    ("Diu Satis",                 "Pope Pius VII",      1800, "https://www.papalencyclicals.net/pius07/p7diusat.htm"),
    # Pope Leo XII (1823–1829)
    ("Ubi Primum",                "Pope Leo XII",       1824, "https://www.papalencyclicals.net/leo12/l12ubipr.htm"),
    ("Quod Hoc Ineunte",          "Pope Leo XII",       1824, "https://www.papalencyclicals.net/leo12/l12quodh.htm"),
    ("Charitate Christi",         "Pope Leo XII",       1825, "https://www.papalencyclicals.net/leo12/l12chari.htm"),
    ("Quo Graviora",              "Pope Leo XII",       1826, "https://www.papalencyclicals.net/leo12/l12quogr.htm"),
    # Pope Pius VIII (1829–1830)
    ("Traditi Humilitati",        "Pope Pius VIII",     1829, "https://www.papalencyclicals.net/pius08/p8tradit.htm"),
    # Pope Gregory XVI (1831–1846)
    ("Mirari Vos",                "Pope Gregory XVI",   1832, "https://www.papalencyclicals.net/greg16/g16mirar.htm"),
    ("Cum Primum",                "Pope Gregory XVI",   1832, "https://www.papalencyclicals.net/greg16/g16cumpr.htm"),
    ("Summo Iugiter Studio",      "Pope Gregory XVI",   1832, "https://www.papalencyclicals.net/greg16/g16summo.htm"),
    ("Quo Graviora",              "Pope Gregory XVI",   1833, "https://www.papalencyclicals.net/greg16/g16quogr.htm"),
    ("Singulari Nos",             "Pope Gregory XVI",   1834, "https://www.papalencyclicals.net/greg16/g16singu.htm"),
    ("Commissum Divinitus",       "Pope Gregory XVI",   1835, "https://www.papalencyclicals.net/greg16/g16commi.htm"),
    ("In Supremo Apostolatus",    "Pope Gregory XVI",   1839, "https://www.papalencyclicals.net/greg16/g16sup.htm"),
    ("Probe Nostis",              "Pope Gregory XVI",   1840, "https://www.papalencyclicals.net/greg16/g16probe.htm"),
    ("Quas Vestro",               "Pope Gregory XVI",   1841, "https://www.papalencyclicals.net/greg16/g16quasv.htm"),
    ("Inter Praecipuas",          "Pope Gregory XVI",   1844, "https://www.papalencyclicals.net/greg16/g16inter.htm"),
    # Pope Pius IX (1846–1878)
    ("Qui Pluribus",              "Pope Pius IX",       1846, "https://www.papalencyclicals.net/pius09/p9quiplu.htm"),
    ("Praedecessores Nostros",    "Pope Pius IX",       1847, "https://www.papalencyclicals.net/pius09/p9praede.htm"),
    ("Ubi Primum",                "Pope Pius IX",       1847, "https://www.papalencyclicals.net/pius09/p9ubipr1.htm"),
    ("Nostis Et Nobiscum",        "Pope Pius IX",       1849, "https://www.papalencyclicals.net/pius09/p9nostis.htm"),
    ("Ubi Primum",                "Pope Pius IX",       1849, "https://www.papalencyclicals.net/pius09/p9ubipr2.htm"),
    ("Exultavit Cor Nostrum",     "Pope Pius IX",       1851, "https://www.papalencyclicals.net/pius09/p9exulta.htm"),
    ("Nemo Certe Ignorat",        "Pope Pius IX",       1852, "https://www.papalencyclicals.net/pius09/p9nemoce.htm"),
    ("Probe Noscitis Venerabiles","Pope Pius IX",       1852, "https://www.papalencyclicals.net/pius09/p9proben.htm"),
    ("Inter Multiplices",         "Pope Pius IX",       1853, "https://www.papalencyclicals.net/pius09/p9interm.htm"),
    ("Apostolicae Nostrae Caritatis","Pope Pius IX",    1854, "https://www.papalencyclicals.net/pius09/p9aposto.htm"),
    ("Ineffabilis Deus",          "Pope Pius IX",       1854, "https://www.papalencyclicals.net/pius09/p9ineff.htm"),
    ("Neminem Vestrum",           "Pope Pius IX",       1854, "https://www.papalencyclicals.net/pius09/p9nemini.htm"),
    ("Optime Noscitis",           "Pope Pius IX",       1854, "https://www.papalencyclicals.net/pius09/p9optim1.htm"),
    ("Optime Noscitis",           "Pope Pius IX",       1855, "https://www.papalencyclicals.net/pius09/p9optim2.htm"),
    ("Singulari Quidem",          "Pope Pius IX",       1856, "https://www.papalencyclicals.net/pius09/p9singul.htm"),
    ("Amantissimi Redemptoris",   "Pope Pius IX",       1858, "https://www.papalencyclicals.net/pius09/p9amant1.htm"),
    ("Cum Nuper",                 "Pope Pius IX",       1858, "https://www.papalencyclicals.net/pius09/p9cumnup.htm"),
    ("Cum Sancta Mater Ecclesia", "Pope Pius IX",       1858, "https://www.papalencyclicals.net/pius09/p9cumsan.htm"),
    ("Qui Nuper",                 "Pope Pius IX",       1859, "https://www.papalencyclicals.net/pius09/p9quinup.htm"),
    ("Nullis Certe Verbis",       "Pope Pius IX",       1860, "https://www.papalencyclicals.net/pius09/p9nullis.htm"),
    ("Amantissimus",              "Pope Pius IX",       1862, "https://www.papalencyclicals.net/pius09/p9amant2.htm"),
    ("Incredibili",               "Pope Pius IX",       1863, "https://www.papalencyclicals.net/pius09/p9incred.htm"),
    ("Quanto Conficiamur Moerore","Pope Pius IX",       1863, "https://www.papalencyclicals.net/pius09/p9quanto.htm"),
    ("Maximae Quidem",            "Pope Pius IX",       1864, "https://www.papalencyclicals.net/pius09/p9maxima.htm"),
    ("Quanta Cura",               "Pope Pius IX",       1864, "https://www.papalencyclicals.net/pius09/p9quanta.htm"),
    ("Syllabus of Errors",        "Pope Pius IX",       1864, "https://www.papalencyclicals.net/pius09/p9syll.htm"),
    ("Meridionali Americae",      "Pope Pius IX",       1865, "https://www.papalencyclicals.net/pius09/p9meridi.htm"),
    ("Levate",                    "Pope Pius IX",       1867, "https://www.papalencyclicals.net/pius09/p9levate.htm"),
    ("Respicientes",              "Pope Pius IX",       1870, "https://www.papalencyclicals.net/pius09/p9respic.htm"),
    ("Beneficia Dei",             "Pope Pius IX",       1871, "https://www.papalencyclicals.net/pius09/p9benefi.htm"),
    ("Saepe Venerabiles Fratres", "Pope Pius IX",       1871, "https://www.papalencyclicals.net/pius09/p9saepev.htm"),
    ("Ubi Nos",                   "Pope Pius IX",       1871, "https://www.papalencyclicals.net/pius09/p9ubinos.htm"),
    ("Quae In Patriarchatu",      "Pope Pius IX",       1872, "https://www.papalencyclicals.net/pius09/p9quaein.htm"),
    ("Etsi Multa",                "Pope Pius IX",       1873, "https://www.papalencyclicals.net/pius09/p9etsimu.htm"),
    ("Quartus Supra",             "Pope Pius IX",       1873, "https://www.papalencyclicals.net/pius09/p9quartu.htm"),
    ("Gravibus Ecclesiae",        "Pope Pius IX",       1874, "https://www.papalencyclicals.net/pius09/p9gravib.htm"),
    ("Omnem Sollicitudinem",      "Pope Pius IX",       1874, "https://www.papalencyclicals.net/pius09/p9omnems.htm"),
    ("Vix Dum A Nobis",           "Pope Pius IX",       1874, "https://www.papalencyclicals.net/pius09/p9vixdum.htm"),
    ("Graves Ac Diuturnae",       "Pope Pius IX",       1875, "https://www.papalencyclicals.net/pius09/p9graves.htm"),
    ("Quod Nunquam",              "Pope Pius IX",       1875, "https://www.papalencyclicals.net/pius09/p9quodnu.htm"),
    # Pope Leo XIII (1878–1903)
    ("Aeterni Patris",            "Pope Leo XIII",      1879, "https://www.vatican.va/content/leo-xiii/en/encyclicals/documents/hf_l-xiii_enc_04081879_aeterni-patris.html"),
    ("Immortale Dei",             "Pope Leo XIII",     1885, "https://www.papalencyclicals.net/leo13/l13sta.htm"),
    ("Libertas",                  "Pope Leo XIII",     1888, "https://www.papalencyclicals.net/leo13/l13liber.htm"),
    ("Rerum Novarum",             "Pope Leo XIII",     1891, "https://www.papalencyclicals.net/leo13/l13rerum.htm"),
    ("Providentissimus Deus",     "Pope Leo XIII",     1893, "https://www.papalencyclicals.net/leo13/l13provi.htm"),
    ("Divinum Illud Munus",       "Pope Leo XIII",     1897, "https://www.papalencyclicals.net/leo13/l13divin.htm"),
    ("Mirae Caritatis",           "Pope Leo XIII",     1902, "https://www.papalencyclicals.net/leo13/l13mirae.htm"),
    # Pope Pius X (1903–1914)
    ("Pascendi Dominici Gregis",  "Pope Pius X",       1907, "https://www.papalencyclicals.net/pius10/p10pasce.htm"),
    # Pope Benedict XV (1914–1922)
    ("Spiritus Paraclitus",       "Pope Benedict XV",  1920, "https://www.papalencyclicals.net/ben15/b15sp.htm"),
    # Pope Pius XI (1922–1939)
    ("Quas Primas",               "Pope Pius XI",      1925, "https://www.papalencyclicals.net/pius11/p11prima.htm"),
    ("Casti Connubii",            "Pope Pius XI",      1930, "https://www.papalencyclicals.net/pius11/p11casti.htm"),
    ("Quadragesimo Anno",         "Pope Pius XI",      1931, "https://www.papalencyclicals.net/pius11/p11quadr.htm"),
    ("Mit Brennender Sorge",      "Pope Pius XI",      1937, "https://www.papalencyclicals.net/pius11/p11brenn.htm"),
    ("Divini Redemptoris",        "Pope Pius XI",      1937, "https://www.papalencyclicals.net/pius11/p11divin.htm"),
    # Pope Pius XII (1939–1958)
    ("Mystici Corporis Christi",  "Pope Pius XII",     1943, "https://www.papalencyclicals.net/pius12/p12mysti.htm"),
    ("Divino Afflante Spiritu",   "Pope Pius XII",     1943, "https://www.papalencyclicals.net/pius12/p12divin.htm"),
    ("Mediator Dei",              "Pope Pius XII",     1947, "https://www.papalencyclicals.net/pius12/p12media.htm"),
    ("Humani Generis",            "Pope Pius XII",     1950, "https://www.papalencyclicals.net/pius12/p12human.htm"),
    ("Munificentissimus Deus",    "Pope Pius XII",     1950, "https://www.papalencyclicals.net/pius12/p12munif.htm"),
    # Pope John XXIII (1958–1963)
    ("Mater et Magistra",         "Pope John XXIII",   1961, "https://www.papalencyclicals.net/john23/j23mater.htm"),
    ("Pacem in Terris",           "Pope John XXIII",   1963, "https://www.papalencyclicals.net/john23/j23pacem.htm"),
    # Pope Paul VI (1963–1978)
    ("Ecclesiam Suam",            "Pope Paul VI",      1964, "https://www.papalencyclicals.net/paul06/p6eccles.htm"),
    ("Mysterium Fidei",           "Pope Paul VI",      1965, "https://www.papalencyclicals.net/paul06/p6myster.htm"),
    ("Populorum Progressio",      "Pope Paul VI",      1967, "https://www.vatican.va/content/paul-vi/en/encyclicals/documents/hf_p-vi_enc_26031967_populorum.html"),
    ("Humanae Vitae",             "Pope Paul VI",      1968, "https://www.papalencyclicals.net/paul06/p6humana.htm"),
    ("Evangelii Nuntiandi",       "Pope Paul VI",      1975, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19751208_evangelii-nuntiandi.html"),
    # Pope John Paul II (1978–2005)
    ("Redemptor Hominis",         "Pope John Paul II", 1979, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_04031979_redemptor-hominis.html"),
    ("Dives in Misericordia",     "Pope John Paul II", 1980, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_30111980_dives-in-misericordia.html"),
    ("Laborem Exercens",          "Pope John Paul II", 1981, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_14091981_laborem-exercens.html"),
    ("Dominum et Vivificantem",   "Pope John Paul II", 1986, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_18051986_dominum-et-vivificantem.html"),
    ("Redemptoris Mater",         "Pope John Paul II", 1987, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_25031987_redemptoris-mater.html"),
    ("Sollicitudo Rei Socialis",  "Pope John Paul II", 1987, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_30121987_sollicitudo-rei-socialis.html"),
    ("Redemptoris Missio",        "Pope John Paul II", 1990, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_07121990_redemptoris-missio.html"),
    ("Centesimus Annus",          "Pope John Paul II", 1991, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_01051991_centesimus-annus.html"),
    ("Veritatis Splendor",        "Pope John Paul II", 1993, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_06081993_veritatis-splendor.html"),
    ("Evangelium Vitae",          "Pope John Paul II", 1995, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_25031995_evangelium-vitae.html"),
    ("Ut Unum Sint",              "Pope John Paul II", 1995, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_25051995_ut-unum-sint.html"),
    ("Fides et Ratio",            "Pope John Paul II", 1998, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_14091998_fides-et-ratio.html"),
    ("Ecclesia de Eucharistia",   "Pope John Paul II", 2003, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_20030417_eccl-de-euch.html"),
    # Pope Benedict XVI (2005–2013)
    ("Deus Caritas Est",          "Pope Benedict XVI", 2005, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20051225_deus-caritas-est_en.html"),
    ("Spe Salvi",                 "Pope Benedict XVI", 2007, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20071130_spe-salvi_en.html"),
    ("Caritas in Veritate",       "Pope Benedict XVI", 2009, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20090629_caritas-in-veritate_en.html"),
    # Pope Francis (2013–2025)
    ("Lumen Fidei",               "Pope Francis",      2013, "https://www.vatican.va/content/francesco/en/encyclicals/documents/papa-francesco_20130629_enciclica-lumen-fidei.html"),
    ("Evangelii Gaudium",         "Pope Francis",      2013, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20131124_evangelii-gaudium.html"),
    ("Laudato Si",                "Pope Francis",      2015, "https://www.vatican.va/content/francesco/en/encyclicals/documents/papa-francesco_20150524_enciclica-laudato-si.html"),
    ("Fratelli Tutti",            "Pope Francis",      2020, "https://www.vatican.va/content/francesco/en/encyclicals/documents/papa-francesco_20201003_enciclica-fratelli-tutti.html"),
    ("Dilexit Nos",               "Pope Francis",      2024, "https://www.vatican.va/content/francesco/en/encyclicals/documents/20241024-enciclica-dilexit-nos.html"),
    # Pope Leo XIV (2025–present)
    ("Magnifica Humanitas",       "Pope Leo XIV",      2026, "https://www.vatican.va/content/leo-xiv/en/encyclicals/documents/20260515-magnifica-humanitas.html"),
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
    seen_slugs: set[str] = set()
    with _client() as client:
        for title, author, year, url in ENCYCLICALS:
            base_slug = _slug(title)
            slug = base_slug if base_slug not in seen_slugs else f"{base_slug}-{year}"
            seen_slugs.add(slug)
            fname = slug + ".html"
            if not (os.path.exists(os.path.join(d, fname)) and not force):
                data = _fetch(client, url)
                if data is None:
                    continue
                _save(d, fname, data, force)
                time.sleep(_DELAY)
            else:
                print(f"  skip (exists): {fname}")
            manifest.append({"title": title, "author": author, "year": year,
                             "url": url, "slug": slug, "file": fname})
    _write_manifest(d, manifest)


APOSTOLIC_EXHORTATIONS = [
    # Pope Pius X
    ("Haerent Animo",               "Pope Pius X",       1908, "https://www.papalencyclicals.net/pius10/p10haer.htm"),
    # Pope Pius XII
    ("Menti Nostrae",               "Pope Pius XII",     1950, "https://www.papalencyclicals.net/pius12/p12clerg.htm"),
    # Pope Paul VI
    ("Signum Magnum",               "Pope Paul VI",      1967, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19670513_signum-magnum.html"),
    ("Evangelica Testificatio",     "Pope Paul VI",      1971, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19710629_evangelica-testificatio.html"),
    ("Marialis Cultus",             "Pope Paul VI",      1974, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19740202_marialis-cultus.html"),
    ("Gaudete in Domino",           "Pope Paul VI",      1975, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19750509_gaudete-in-domino.html"),
    # Pope John Paul II
    ("Catechesi Tradendae",         "Pope John Paul II", 1979, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_16101979_catechesi-tradendae.html"),
    ("Familiaris Consortio",        "Pope John Paul II", 1981, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_19811122_familiaris-consortio.html"),
    ("Redemptionis Donum",          "Pope John Paul II", 1984, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_25031984_redemptionis-donum.html"),
    ("Reconciliatio et Paenitentia","Pope John Paul II", 1984, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_02121984_reconciliatio-et-paenitentia.html"),
    ("Christifideles Laici",        "Pope John Paul II", 1988, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_30121988_christifideles-laici.html"),
    ("Redemptoris Custos",          "Pope John Paul II", 1989, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_15081989_redemptoris-custos.html"),
    ("Pastores Dabo Vobis",         "Pope John Paul II", 1992, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_25031992_pastores-dabo-vobis.html"),
    ("Ecclesia in Africa",          "Pope John Paul II", 1995, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_14091995_ecclesia-in-africa.html"),
    ("Vita Consecrata",             "Pope John Paul II", 1996, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_25031996_vita-consecrata.html"),
    ("Ecclesia in America",         "Pope John Paul II", 1999, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_22011999_ecclesia-in-america.html"),
    ("Ecclesia in Asia",            "Pope John Paul II", 1999, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_06111999_ecclesia-in-asia.html"),
    ("Ecclesia in Oceania",         "Pope John Paul II", 2001, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_20011122_ecclesia-in-oceania.html"),
    ("Ecclesia in Europa",          "Pope John Paul II", 2003, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_20030628_ecclesia-in-europa.html"),
    ("Pastores Gregis",             "Pope John Paul II", 2003, "https://www.vatican.va/content/john-paul-ii/en/apost_exhortations/documents/hf_jp-ii_exh_20031016_pastores-gregis.html"),
    # Pope Benedict XVI
    ("Sacramentum Caritatis",       "Pope Benedict XVI", 2007, "https://www.vatican.va/content/benedict-xvi/en/apost_exhortations/documents/hf_ben-xvi_exh_20070222_sacramentum-caritatis.html"),
    ("Verbum Domini",               "Pope Benedict XVI", 2010, "https://www.vatican.va/content/benedict-xvi/en/apost_exhortations/documents/hf_ben-xvi_exh_20100930_verbum-domini.html"),
    ("Africae Munus",               "Pope Benedict XVI", 2011, "https://www.vatican.va/content/benedict-xvi/en/apost_exhortations/documents/hf_ben-xvi_exh_20111119_africae-munus.html"),
    ("Ecclesia in Medio Oriente",   "Pope Benedict XVI", 2012, "https://www.vatican.va/content/benedict-xvi/en/apost_exhortations/documents/hf_ben-xvi_exh_20120914_ecclesia-in-medio-oriente.html"),
    # Pope Francis
    ("Gaudete et Exsultate",        "Pope Francis",      2018, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20180319_gaudete-et-exsultate.html"),
    ("Christus Vivit",              "Pope Francis",      2019, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20190325_christus-vivit.html"),
    ("Querida Amazonia",            "Pope Francis",      2020, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20200202_querida-amazonia.html"),
    ("Laudate Deum",                "Pope Francis",      2023, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/20231004-laudate-deum.html"),
    ("C'est la confiance",          "Pope Francis",      2023, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/20231015-santateresa-delbambinogesu.html"),
    # Pope Leo XIV
    ("Dilexi te",                   "Pope Leo XIV",      2025, "https://www.vatican.va/content/leo-xiv/en/apost_exhortations/documents/20251004-dilexi-te.html"),
]


def vendor_apostolic_exhortations(force: bool) -> None:
    d = os.path.join(_SOURCES, "apostolic-exhortations")
    os.makedirs(d, exist_ok=True)
    manifest = []
    seen_slugs: set[str] = set()
    with _client() as client:
        for title, author, year, url in APOSTOLIC_EXHORTATIONS:
            base_slug = _slug(title)
            slug = base_slug if base_slug not in seen_slugs else f"{base_slug}-{year}"
            seen_slugs.add(slug)
            fname = slug + ".html"
            if not (os.path.exists(os.path.join(d, fname)) and not force):
                data = _fetch(client, url)
                if data is None:
                    continue
                _save(d, fname, data, force)
                time.sleep(_DELAY)
            else:
                print(f"  skip (exists): {fname}")
            manifest.append({"title": title, "author": author, "year": year,
                             "url": url, "slug": slug, "file": fname})
    _write_manifest(d, manifest)


PAPAL_DOCUMENTS = [
    # Historical Papal Bulls
    ("Unam Sanctam",               "Pope Boniface VIII",  1302, "https://www.papalencyclicals.net/bon08/b8unam.htm"),
    ("Exsurge Domine",             "Pope Leo X",          1520, "https://www.papalencyclicals.net/leo10/l10exdom.htm"),
    ("Sublimis Deus",              "Pope Paul III",       1537, "https://www.papalencyclicals.net/paul03/p3subli.htm"),
    # Apostolic Letters — John Paul II
    ("Salvifici Doloris",          "Pope John Paul II",   1984, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1984/documents/hf_jp-ii_apl_11021984_salvifici-doloris.html"),
    ("Mulieris Dignitatem",        "Pope John Paul II",   1988, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1988/documents/hf_jp-ii_apl_15081988_mulieris-dignitatem.html"),
    ("Ordinatio Sacerdotalis",     "Pope John Paul II",   1994, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1994/documents/hf_jp-ii_apl_19940522_ordinatio-sacerdotalis.html"),
    ("Tertio Millennio Adveniente","Pope John Paul II",   1994, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1994/documents/hf_jp-ii_apl_19941110_tertio-millennio-adveniente.html"),
    ("Orientale Lumen",            "Pope John Paul II",   1995, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1995/documents/hf_jp-ii_apl_19950502_orientale-lumen.html"),
    ("Dies Domini",                "Pope John Paul II",   1998, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/1998/documents/hf_jp-ii_apl_05071998_dies-domini.html"),
    ("Novo Millennio Ineunte",     "Pope John Paul II",   2001, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/2001/documents/hf_jp-ii_apl_20010106_novo-millennio-ineunte.html"),
    ("Rosarium Virginis Mariae",   "Pope John Paul II",   2002, "https://www.vatican.va/content/john-paul-ii/en/apost_letters/2002/documents/hf_jp-ii_apl_20021016_rosarium-virginis-mariae.html"),
    # Apostolic Letters — Benedict XVI
    ("Porta Fidei",                "Pope Benedict XVI",   2011, "https://www.vatican.va/content/benedict-xvi/en/motu_proprio/documents/hf_ben-xvi_motu-proprio_20111011_porta-fidei.html"),
    # Apostolic Letters — Francis
    ("Misericordia et Misera",     "Pope Francis",        2016, "https://www.vatican.va/content/francesco/en/apost_letters/documents/papa-francesco-lettera-ap_20161120_misericordia-et-misera.html"),
    ("Patris Corde",               "Pope Francis",        2020, "https://www.vatican.va/content/francesco/en/apost_letters/documents/papa-francesco-lettera-ap_20201208_patris-corde.html"),
]


def vendor_papal_documents(force: bool) -> None:
    d = os.path.join(_SOURCES, "papal-documents")
    os.makedirs(d, exist_ok=True)
    manifest = []
    seen_slugs: set[str] = set()
    with _client() as client:
        for title, author, year, url in PAPAL_DOCUMENTS:
            base_slug = _slug(title)
            slug = base_slug if base_slug not in seen_slugs else f"{base_slug}-{year}"
            seen_slugs.add(slug)
            fname = slug + ".html"
            if not (os.path.exists(os.path.join(d, fname)) and not force):
                data = _fetch(client, url)
                if data is None:
                    continue
                _save(d, fname, data, force)
                time.sleep(_DELAY)
            else:
                print(f"  skip (exists): {fname}")
            manifest.append({"title": title, "author": author, "year": year,
                             "url": url, "slug": slug, "file": fname})
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
    "apostolic-exhortations": vendor_apostolic_exhortations,
    "papal-documents": vendor_papal_documents,
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
