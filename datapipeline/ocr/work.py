"""A scanned work: its tracked config, and its gitignored work directory.

The config (`ocr/works/<work>.json`) names the scan, the vendored files, the printed page
range, the layout, the clean baseline, the per-work names, the correction model and
spend ceiling, and the sample rule. The work directory (`ocr_work/<work>/`, gitignored)
holds everything derived from the scan:

- `passages.json`: per passage, `raw_ocr`, `cleaned`, `corrected` and `fixed` side by
  side, with its pages and the outcome of correction;
- `cleanup.json`: the per-page removal log, the line-end breaks and the notes;
- `runs.json`: each correction run's model, prompt version, tokens and cost;
- `check.json`: the person's check, with its seed, sample and results;
- `gate.md`: the report.

Two tracked files sit beside the config: `ocr/works/<work>.fixes.json`, the edits a person
made against the page images, and `ocr/texts/<work>.json`, the final text an adapter reads,
frozen because a correction run cannot be repeated word for word.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

DATAPIPELINE = Path(__file__).resolve().parents[1]
WORKS_DIR = Path(__file__).resolve().parent / "works"
TEXTS_DIR = Path(__file__).resolve().parent / "texts"
WORK_ROOT = DATAPIPELINE / "ocr_work"
SOURCES = DATAPIPELINE / "sources"

# Words per passage sent to the model, and per passage in the person's sample. Whole
# paragraphs are grouped up to this; a longer paragraph is a passage on its own.
PASSAGE_WORDS = 350


@dataclass(frozen=True)
class SampleRule:
    """How many passages a person checks: `fraction` of the unit's passages, at least
    `minimum` and at most `maximum`, and never more than there are. The unit is the set
    of passages the sample is drawn from: one work, or several printed in one scan
    (Decision log "OCR clean-up: model, spend, sample and inputs")."""
    fraction: float = 0.25
    minimum: int = 5
    maximum: int = 20
    unit: str = "work"

    def size(self, passages: int) -> int:
        return min(passages, max(self.minimum, min(self.maximum, math.ceil(self.fraction * passages))))


@dataclass(frozen=True)
class Baseline:
    """A clean typed text of the same period: HTML paragraphs from the one matching
    `start` up to (not including) the one matching `end`, minus paragraphs matching
    `drop`, with `strip` removed from the rest. With `opens` and `closes`, only the runs
    from a paragraph matching `opens` to one matching `closes`, so a work measured on its
    units is compared with the same kind of text."""
    path: str
    start: str
    end: str
    drop: str | None = None
    strip: str | None = None
    opens: str | None = None
    closes: str | None = None


@dataclass(frozen=True)
class WorkConfig:
    work: str
    title: str
    scan: str                    # the Internet Archive identifier, or the PDF scan's name
    pages: tuple[str, str]       # first and last printed page
    baseline: Baseline
    djvu_xml: str = ""           # paths relative to datapipeline/sources/
    page_numbers: str = ""
    pdf: str = ""                # a PDF with a text layer, read instead (`pdf.py`)
    pdf_page_offset: int = 0     # PDF page index (from 0) minus the printed page number
    margin_numbers: bool = False   # numbers printed in the margins are furniture
    layout: str = "single-column"
    leaf_offset: int = 0         # scan leaves the XML leaves out before its first page
    broken_words_continue: bool = False   # a broken word's rest never opens a paragraph
    max_paragraph_words: int | None = None   # cut longer paragraphs at a sentence end
    units: str | None = None     # ocr/units.py; None groups paragraphs into passages
    unit_count: int | None = None   # how many units the work prints
    unit_series: tuple[int, ...] | None = None   # units per series, where it prints several
    unit_closes: tuple[str, ...] = ()   # the editor's unlabelled paragraphs that close a unit
    unit_bounds: tuple[dict, ...] = ()  # bounded units: each text's first and last paragraph
    names: tuple[str, ...] = ()
    model: str = "claude-sonnet-5-5"
    ceiling_usd: float = 2.00
    sample: SampleRule = field(default_factory=SampleRule)

    @classmethod
    def from_dict(cls, d: dict) -> "WorkConfig":
        d = dict(d)
        d["pages"] = tuple(d["pages"])
        d["names"] = tuple(d.get("names", ()))
        d["unit_closes"] = tuple(d.get("unit_closes", ()))
        d["unit_bounds"] = tuple(d.get("unit_bounds", ()))
        if d.get("unit_series") is not None:
            d["unit_series"] = tuple(d["unit_series"])
        d["baseline"] = Baseline(**d["baseline"])
        d["sample"] = SampleRule(**d.get("sample", {}))
        return cls(**d)

    @classmethod
    def load(cls, work: str, works_dir: Path = WORKS_DIR) -> "WorkConfig":
        return cls.from_dict(json.loads((works_dir / f"{work}.json").read_text(encoding="utf-8")))

    def source(self, rel: str, sources: Path = SOURCES) -> Path:
        return sources / rel

    def scan_url(self, leaf: int | None = None) -> str:
        if self.pdf:
            # Not online: the vendored file, at the PDF's page (counted from 1).
            return f"sources/{self.pdf}" + (f"#page={leaf + 1}" if leaf is not None else "")
        url = f"https://archive.org/details/{self.scan}"
        return f"{url}/page/n{leaf}/mode/1up" if leaf is not None else url


@dataclass
class Correction:
    status: str = "pending"      # pending | accepted | unchanged | rejected | refused | failed
    reason: str | None = None
    changed_words: int | None = None
    allowed_words: int | None = None
    run: str | None = None


@dataclass
class OcrPassage:
    id: str
    leaves: list[int]
    pages: list[str | None]
    raw_ocr: str
    cleaned: str
    corrected: str | None = None
    correction: Correction = field(default_factory=Correction)
    fixed: str | None = None     # `base` with the work's tracked fixes applied
    continues: bool = False      # opens inside the paragraph the passage before it ends

    @property
    def base(self) -> str:
        """The model's correction where it was accepted, else the script-cleaned text."""
        return self.corrected if self.correction.status == "accepted" and self.corrected else self.cleaned

    @property
    def text(self) -> str:
        """The text that goes on: `base`, with any fixes a person made."""
        return self.fixed if self.fixed is not None else self.base

    def page_ref(self) -> str:
        nums = [p for p in self.pages if p]
        if not nums:
            return "scan images " + "–".join(str(x) for x in sorted({self.leaves[0], self.leaves[-1]}))
        return f"p. {nums[0]}" if nums[0] == nums[-1] else f"pp. {nums[0]}–{nums[-1]}"

    @classmethod
    def from_dict(cls, d: dict) -> "OcrPassage":
        d = dict(d)
        d["correction"] = Correction(**d.get("correction", {}))
        return cls(**d)


class WorkDir:
    def __init__(self, config: WorkConfig, root: Path = WORK_ROOT):
        self.config = config
        self.path = root / config.work

    def file(self, name: str) -> Path:
        return self.path / name

    def _read(self, name: str, default):
        p = self.file(name)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    def _write(self, name: str, data) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        tmp = self.file(name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(self.file(name))

    def passages(self) -> list[OcrPassage]:
        return [OcrPassage.from_dict(d) for d in self._read("passages.json", [])]

    def save_passages(self, passages: list[OcrPassage]) -> None:
        self._write("passages.json", [asdict(p) for p in passages])

    def cleanup(self) -> dict:
        return self._read("cleanup.json", {})

    def save_cleanup(self, data: dict) -> None:
        self._write("cleanup.json", data)

    def runs(self) -> list[dict]:
        return self._read("runs.json", [])

    def save_runs(self, runs: list[dict]) -> None:
        self._write("runs.json", runs)

    def check(self) -> dict | None:
        return self._read("check.json", None)

    def save_check(self, data: dict) -> None:
        self._write("check.json", data)

    def spent_usd(self) -> float:
        return sum(r.get("cost_usd", 0.0) for r in self.runs())


def group_passages(paragraphs: list, target_words: int = PASSAGE_WORDS) -> list[list]:
    """Consecutive paragraphs grouped into passages of about `target_words`, never
    splitting a paragraph."""
    groups: list[list] = []
    current: list = []
    count = 0
    for para in paragraphs:
        n = len(para.text.split())
        if current and count + n > target_words:
            groups.append(current)
            current, count = [], 0
        current.append(para)
        count += n
    if current:
        groups.append(current)
    return groups


def baseline_text(baseline: Baseline, sources: Path = SOURCES) -> list[str]:
    """The baseline's paragraphs as plain text."""
    from bs4 import BeautifulSoup

    html = (sources / baseline.path).read_bytes()
    paras = [re.sub(r"\s+", " ", p.get_text(" ")).strip()
             for p in BeautifulSoup(html, "lxml").find_all("p")]
    start = next(i for i, p in enumerate(paras) if re.search(baseline.start, p))
    end = next(i for i, p in enumerate(paras) if i > start and re.search(baseline.end, p))
    out = []
    inside = baseline.opens is None
    for p in paras[start:end]:
        if baseline.opens:
            if re.search(baseline.opens, p):
                inside = True
            elif re.search(baseline.closes, p):
                inside = False
            if not inside:
                continue
        if baseline.drop and re.search(baseline.drop, p):
            continue
        if baseline.strip:
            p = re.sub(baseline.strip, " ", p)
        if p.strip():
            out.append(p.strip())
    return out
