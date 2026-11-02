"""OCR clean-up tool and gate (corpus-cleanup item 1.2f). The fixtures are synthetic
pages written for these tests; the model is stubbed, so nothing here calls a provider."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from model import Passage
from ocr import correct as correct_mod
from ocr.correct import ModelReply, allowed_words, changed_words, judge, run_correction
from ocr.furniture import clean_pages, clean_work
from ocr.gate import draw_sample, evaluate, rate_check, record, start_check
from ocr.label import is_scanned, label_passage, ocr_metadata, scanned_text
from ocr.layout import get_layout
from ocr.pages import Line, Page, load_pages
from ocr.report import write as write_report
from ocr.work import Baseline, OcrPassage, SampleRule, WorkConfig, WorkDir
from ocr.words import unrecognized_rate

FIXTURES = Path(__file__).parent / "fixtures" / "ocr"
XML = FIXTURES / "synthetic_djvu.xml"
NUMBERS = FIXTURES / "synthetic_page_numbers.json"


@pytest.fixture
def sources(tmp_path):
    src = tmp_path / "sources"
    src.mkdir()
    shutil.copy(XML, src / "synthetic_djvu.xml")
    shutil.copy(NUMBERS, src / "synthetic_page_numbers.json")
    (src / "baseline.html").write_text(
        "<html><body><p>Menu</p><p>START The bishops met in the spring.</p>"
        "<p>Note 1. A note.</p><p>Each abbot answers to the bishop.</p><p>END credits</p>"
        "</body></html>", encoding="utf-8")
    return src


def make_config(**over) -> WorkConfig:
    d = dict(work="synthetic", title="Synthetic book", scan="synthetic-scan",
             djvu_xml="synthetic_djvu.xml", page_numbers="synthetic_page_numbers.json",
             pages=("10", "12"),
             baseline=Baseline("baseline.html", "^START", "^END", "^Note", "START"))
    d.update(over)
    return WorkConfig(**d)


@pytest.fixture
def workdir(tmp_path, sources):
    w = WorkDir(make_config(), root=tmp_path / "work")
    # Small passages, so each fixture paragraph is one (the real size is 350 words).
    clean_work(w, sources=sources, passage_words=20)
    return w


class StubCorrector:
    """Applies `fixes` (old → new, plain replacement) to whatever it is sent."""
    model = "stub-model"
    prompt_version = "stub-v1"

    def __init__(self, fixes=None, cost=0.01, worst=0.02, stop_reason="end_turn"):
        self.fixes, self.cost, self.worst, self.stop_reason = fixes or {}, cost, worst, stop_reason
        self.calls = 0

    def worst_case_usd(self, text):
        return self.worst

    def correct(self, text):
        self.calls += 1
        for old, new in self.fixes.items():
            text = text.replace(old, new)
        return ModelReply(text, 100, 100, self.cost, self.stop_reason)


# --- furniture ---------------------------------------------------------------------

def test_furniture_removed_keeps_paragraphs():
    pages = load_pages(XML, NUMBERS)
    result = clean_pages(pages)
    removed = [(r.page, r.kind) for r in result.removals]
    assert removed == [("10", "running_head"), ("11", "running_head"), ("12", "page_number")]
    texts = [p.text for p in result.paragraphs]
    assert texts == [
        "The council met in tbe spring and its correspondence with the bishops shows that "
        "each of them was summoned in good time to the city. The blorf-zingle of the clerks "
        "is not recorded.",
        # Runs across the page break, with the running head of p. 11 out of it.
        "No bishop shail be absent without a lawful excuse, and whoever stays away without "
        "one is to be reproved by the metropolitan at the next meeting of the province.",
        "Text. The same rule binds abbots, who answer to the bishop of the place where "
        "their house stands.",
        "CANON 2",
        "Summary. Clerics may not hold two benefices at once, nor sell either of them.",
    ]
    body = " ".join(texts)
    assert "SYNTHETIC BOOK" not in body and not re.search(r"\b1[012]\b", body)
    # The note at the foot of p. 11 is kept, apart from the body.
    assert [(n.page, n.text.split("\n")[0]) for n in result.notes] == [
        ("11", "1 A note set in smaller type, which is kept apart from")]
    assert result.paragraphs[1].leaves == [0, 1]


def test_running_head_found_by_repetition_without_page_number():
    def page(leaf, head):
        lines = [Line(head, 600, 100, 1400, 150)] + [
            Line(f"Body line {k} of the page with ordinary words in it", 150, 300 + 75 * k, 1850, 360 + 75 * k)
            for k in range(5)]
        return Page(leaf, 2000, 3000, lines)
    # Garbled numbers, so only the repeated letters mark them; a one-off top line stays.
    heads = ["DECREES OF THE COUNCILS", "DECREES OF THE COUNCELS", "DECREES OF THE COUNCILS",
             "THE NINTH GENERAL COUNCIL"]
    result = clean_pages([page(i, h) for i, h in enumerate(heads)])
    assert [r.text for r in result.removals] == heads[:3]
    assert any("THE NINTH GENERAL COUNCIL" in p.text for p in result.paragraphs)


def test_specks_signatures_and_catchwords_removed():
    body = [Line(f"Ordinary words on line {k} of this page run on", 150, 300 + 75 * k, 1850, 360 + 75 * k)
            for k in range(4)]
    p1 = Page(0, 2000, 3000, body + [Line("|", 60, 900, 70, 950),
                                     Line("next", 1600, 2800, 1800, 2850)])
    p2 = Page(1, 2000, 3000, [Line("Next page opens here and goes on", 150, 300, 1850, 360)]
              + [Line("B2", 900, 2850, 1000, 2900)])
    result = clean_pages([p1, p2])
    assert sorted((r.leaf, r.kind, r.text) for r in result.removals) == [
        (0, "catchword", "next"), (0, "speck", "|"), (1, "signature", "B2")]


def test_note_found_on_a_short_last_page():
    # The text ends a third of the way down the image, its note just below.
    body = [Line(f"Body words on line {k} of the last page of the work", 150, 300 + 75 * k, 1850, 360 + 75 * k)
            for k in range(8)]
    note = [Line("20 These were the successors of the antipope in that see,", 150, 980, 1850, 1025),
            Line("and one of them was intruded into the see of Rome.", 150, 1035, 1500, 1080)]
    result = clean_pages([Page(0, 2000, 3000, body + note)])
    assert [n.text.split("\n")[0] for n in result.notes] == [note[0].text]
    assert "antipope" not in " ".join(p.text for p in result.paragraphs)


def test_hyphen_rejoined_only_for_known_words():
    result = clean_pages(load_pages(XML, NUMBERS))
    log = {h.broken: (h.result, h.reason) for h in result.hyphens}
    assert log == {"corre-|spondence": ("correspondence", "word list"),
                   "blorf-|zingle": ("blorf-zingle", "kept: unknown")}

    def lines(*texts):
        return Page(0, 2000, 3000, [Line(t, 150, 300 + 75 * k, 1850, 360 + 75 * k)
                                    for k, t in enumerate(texts)])
    # Not in the word list, but printed unbroken elsewhere in the work: joined.
    elsewhere = clean_pages([lines("the blorf-", "zingle was read", "and the blorfzingle again")])
    assert elsewhere.hyphens[0].reason == "elsewhere in the work"
    assert "blorfzingle was read" in elsewhere.paragraphs[0].text
    # A capital after the break is a compound name: the hyphen stays.
    capital = clean_pages([lines("the Anglo-", "Saxon church was old")])
    assert "Anglo-Saxon church" in capital.paragraphs[0].text


def test_unknown_layout_is_refused():
    assert get_layout("single-column").name == "single-column"
    with pytest.raises(ValueError, match="own PR"):
        get_layout("parallel-latin-english")


# --- correction --------------------------------------------------------------------

def test_correction_over_word_limit_is_rejected_and_cleaned_text_kept(tmp_path):
    words = " ".join(f"word{k}" for k in range(100))
    w = WorkDir(make_config(), root=tmp_path)
    w.save_passages([OcrPassage("0001", [0], ["10"], words, words)])
    assert allowed_words(words) == 2
    over = StubCorrector({f"word{k} ": f"changed{k} " for k in range(5)})
    run_correction(w, over, ceiling_usd=1.0)
    p = w.passages()[0]
    assert p.correction.status == "rejected"
    assert p.correction.changed_words == 5 and p.correction.allowed_words == 2
    assert p.text == words                      # the cleaned text goes on
    assert p.corrected.startswith("changed0")   # the model's text is kept for audit

    # Within the limit: accepted.
    w.save_passages([OcrPassage("0001", [0], ["10"], words, words)])
    run_correction(w, StubCorrector({"word7 ": "word 7 "}), ceiling_usd=1.0)
    p = w.passages()[0]
    assert p.correction.status == "accepted" and p.text.startswith("word0 word1")


def test_judge_rejects_dropped_paragraph_refusal_and_truncation():
    p = OcrPassage("0001", [0], ["1"], "a\n\nb", "Alpha one.\n\nBeta two.")
    judge(p, ModelReply("Alpha one. Beta two.", 1, 1, 0.0, "end_turn"))
    assert (p.correction.status, p.correction.reason) == ("rejected", "paragraph count changed")
    for reply, status in [(ModelReply(None, 1, 0, 0.0, "refusal"), "refused"),
                          (ModelReply(None, 1, 1, 0.0, "max_tokens"), "failed")]:
        p = OcrPassage("0001", [0], ["1"], "a", "Alpha one.")
        judge(p, reply)
        assert p.correction.status == status and p.text == "Alpha one."


def test_changed_words_counts_replacements_insertions_and_deletions():
    assert changed_words("a b c d", "a b c d") == 0
    assert changed_words("tbe cat sat", "the cat sat") == 1
    assert changed_words("It It solemnly", "It solemnly") == 1
    assert changed_words("a b", "a x y b") == 2


def test_raw_ocr_kept_beside_corrected(workdir):
    run_correction(workdir, StubCorrector({"tbe": "the", "shail": "shall"}), ceiling_usd=1.0)
    stored = json.loads(workdir.file("passages.json").read_text())
    joined = {k: "\n".join(p[k] or "" for p in stored) for k in ("raw_ocr", "cleaned", "corrected")}
    # The OCR as read: line breaks and the broken word, no furniture.
    assert "corre-\nspondence" in joined["raw_ocr"] and "tbe" in joined["raw_ocr"]
    assert "SYNTHETIC BOOK" not in joined["raw_ocr"]
    assert "correspondence" in joined["cleaned"] and "tbe spring" in joined["cleaned"]
    assert "the spring" in joined["corrected"] and "shall be absent" in joined["corrected"]
    assert all(p["correction"]["status"] in ("accepted", "unchanged") for p in stored)
    run = workdir.runs()[0]
    assert run["model"] == "stub-model" and run["prompt_version"] == "stub-v1"
    assert run["cost_usd"] == pytest.approx(0.01 * run["calls"])


def test_spend_ceiling_stops_before_it_is_exceeded(tmp_path):
    w = WorkDir(make_config(), root=tmp_path)
    w.save_passages([OcrPassage(f"{k:04d}", [k], [str(k)], "x y", "x y") for k in range(6)])
    stub = StubCorrector(cost=0.30, worst=0.40)
    res = run_correction(w, stub, ceiling_usd=1.00)
    # 0 + .40, .30 + .40 and .60 + .40 fit; .90 + .40 would not.
    assert stub.calls == 3 and res.stopped_at_ceiling
    assert w.spent_usd() == pytest.approx(0.90) and w.spent_usd() <= 1.00
    assert "ceiling" in res.run["stopped"]
    assert [p.correction.status for p in w.passages()].count("pending") == 3
    # The ceiling is per work: a second run starts from what the first spent.
    again = run_correction(w, stub, ceiling_usd=1.00)
    assert stub.calls == 3 and again.stopped_at_ceiling


def test_failed_call_counts_its_worst_case(tmp_path):
    w = WorkDir(make_config(), root=tmp_path)
    w.save_passages(_passages(["x y", "x y"]))

    class Failing(StubCorrector):
        def correct(self, text):
            raise ConnectionError("lost")
    res = run_correction(w, Failing(worst=0.40), ceiling_usd=1.00)
    assert "lost" in res.run["stopped"] and w.spent_usd() == pytest.approx(0.40)


def test_anthropic_request_is_thinking_off_json_and_priced(monkeypatch):
    sent = {}

    class FakeMessages:
        def count_tokens(self, **kw):
            return SimpleNamespace(input_tokens=1000)

        def create(self, **kw):
            sent.update(kw)
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text=json.dumps({"corrected": "the cat"}))],
                usage=SimpleNamespace(input_tokens=1000, output_tokens=100))

    corrector = correct_mod.AnthropicCorrector.__new__(correct_mod.AnthropicCorrector)
    corrector.model = "claude-sonnet-5-5"
    corrector.client = SimpleNamespace(messages=FakeMessages())
    reply = corrector.correct("tbe cat")
    assert reply.text == "the cat"
    assert reply.cost_usd == pytest.approx((1000 * 2.00 + 100 * 10.00) / 1e6)
    assert sent["thinking"] == {"type": "between_tools"}
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in sent and "fallbacks" not in sent
    assert "<ocr_text>\ntbe cat\n</ocr_text>" == sent["messages"][0]["content"]
    worst = corrector.worst_case_usd("tbe cat")
    assert worst >= reply.cost_usd
    with pytest.raises(ValueError, match="no price"):
        correct_mod.AnthropicCorrector("some-unpriced-model", api_key="x")


# --- gate --------------------------------------------------------------------------

def _passages(texts):
    return [OcrPassage(f"{k:04d}", [k], [str(k)], t, t) for k, t in enumerate(texts)]


def test_unrecognized_rate_uses_word_list_and_names():
    assert unrecognized_rate(["The bishop met tbe abbot."]) == (0.2, 1, 5)
    assert unrecognized_rate(["Callistus met the abbot."], extra=["Callistus"])[0] == 0.0
    # Possessives, diacritics and hyphenated compounds.
    assert unrecognized_rate(["The council’s prince-bishops naïve"])[1] == 0


def test_gate_fails_above_baseline_plus_one_point():
    baseline = ["the " * 98 + "zzqx zzqy"]                       # 2 of 100: 2%
    ok = _passages(["the " * 97 + "zzqa zzqb zzqc"])               # 3%: within
    bad = _passages(["the " * 96 + "zzqa zzqb zzqc zzqd"])         # 4%: over
    r_ok, r_bad = rate_check(ok, baseline), rate_check(bad, baseline)
    assert r_ok.baseline_rate == pytest.approx(0.02) and r_ok.limit == pytest.approx(0.03)
    assert r_ok.ok and not r_bad.ok
    with_names = rate_check(bad, baseline, names=["zzqa", "zzqb"])
    assert with_names.ok


def test_sample_rule_sizes():
    rule = SampleRule()
    assert [rule.size(n) for n in (3, 5, 19, 20, 21, 40, 79, 80, 81, 400)] == [
        3, 5, 5, 5, 6, 10, 20, 20, 20, 20]


def test_gate_requires_every_sampled_passage_checked(tmp_path):
    w = WorkDir(make_config(), root=tmp_path)
    w.save_passages(_passages([f"the bishop {k}" for k in range(100)]))
    baseline = ["the bishop"]
    check = start_check(w, seed=7)
    ids = [e["id"] for e in check["sample"]]
    assert len(ids) == 20 and ids == draw_sample([f"{k:04d}" for k in range(100)], SampleRule(), 7)
    assert start_check(w)["seed"] == 7                       # drawn once, then kept

    for pid in ids[:19]:
        record(w, pid, "matches", by="Carter")
    result = evaluate(w, baseline)
    assert result.status == "pending" and result.checked == 19 and result.required == 20
    record(w, ids[19], "differences", by="Carter", differences="'tbe' left in")
    assert evaluate(w, baseline).status == "pass"            # a typo, not wording
    record(w, ids[19], "differences", by="Carter", differences="'not' dropped",
           wording_changed=True)
    result = evaluate(w, baseline)
    assert result.status == "fail" and result.wording_changes == [ids[19]]

    # A checked passage whose text changes afterwards must be checked again.
    record(w, ids[19], "matches", by="Carter")
    passages = w.passages()
    next(p for p in passages if p.id == ids[0]).cleaned = "the bishop changed"
    w.save_passages(passages)
    result = evaluate(w, baseline)
    assert result.status == "pending" and result.stale == [ids[0]]

    with pytest.raises(ValueError):
        record(w, "9999", "matches", by="Carter")

    # A passage added after the draw invalidates the sample.
    w.save_passages(w.passages() + [OcrPassage("0100", [100], ["100"], "the bishop", "the bishop")])
    result = evaluate(w, baseline)
    assert result.status == "pending" and "draw it again" in result.reasons[0]


def test_small_work_samples_at_least_five(tmp_path):
    w = WorkDir(make_config(), root=tmp_path)
    w.save_passages(_passages([f"the bishop {k}" for k in range(8)]))
    assert len(start_check(w, seed=1)["sample"]) == 5


def test_gate_report_on_the_fixture_says_pending_with_seed(workdir, sources, monkeypatch):
    run_correction(workdir, StubCorrector({"tbe": "the", "shail": "shall"}), ceiling_usd=1.0)
    start_check(workdir, seed=42)
    monkeypatch.setattr("ocr.work.SOURCES", sources)
    from ocr.work import baseline_text
    baseline = baseline_text(workdir.config.baseline, sources=sources)
    assert baseline == ["The bishops met in the spring.", "Each abbot answers to the bishop."]
    text, result = write_report(workdir, baseline)
    assert result.status in ("pending", "fail")
    assert "Seed **42**" in text and "| pending |" in text
    assert "running head 2" in text and "page number 1" in text
    assert "joined 1, kept with the hyphen 1" in text
    assert workdir.file("gate.md").read_text() == text
    assert "agree with the page map on 3 of 3 pages" in text
    sheet = workdir.file("check.md").read_text()
    assert "Seed 42" in sheet and all(f"## Passage {e['id']}" in sheet
                                      for e in workdir.check()["sample"])


def test_clean_refuses_a_page_map_out_of_step(tmp_path, sources):
    numbers = json.loads((sources / "synthetic_page_numbers.json").read_text())
    for p in numbers["pages"]:
        p["pageNumber"] = str(int(p["pageNumber"]) + 1)     # every page one off
    (sources / "synthetic_page_numbers.json").write_text(json.dumps(numbers))
    w = WorkDir(make_config(pages=("11", "13")), root=tmp_path / "work")
    with pytest.raises(RuntimeError, match="out of step"):
        clean_work(w, sources=sources)


def test_clean_again_refuses_once_corrected(workdir, sources):
    run_correction(workdir, StubCorrector({"tbe": "the"}), ceiling_usd=1.0)
    with pytest.raises(RuntimeError, match="already corrected"):
        clean_work(workdir, sources=sources)
    clean_work(workdir, sources=sources, force=True)
    assert all(p.correction.status == "pending" for p in workdir.passages())


# --- source label ------------------------------------------------------------------

def test_scanned_passages_carry_source_label(workdir):
    handed = scanned_text(workdir)
    assert handed and all(p["metadata"] == {"text_source": "ocr", "scan_id": "synthetic-scan"}
                          for p in handed)
    passage = Passage(content=handed[0]["text"], reference="Synthetic 1", anchor="canon/1",
                      chapter_key="c", chapter_label="C", position=0, metadata={"x": 1})
    label_passage(passage, workdir.config.scan)
    assert passage.metadata == {"x": 1, "text_source": "ocr", "scan_id": "synthetic-scan"}
    assert is_scanned(passage)
    typed = Passage(content="x", reference="r", anchor="a", chapter_key="c",
                    chapter_label="C", position=0)
    assert not is_scanned(typed)
    with pytest.raises(ValueError):
        ocr_metadata("")


def test_demo_work_config_loads():
    config = WorkConfig.load("schroeder-lateran-1")
    assert config.scan == "DisciplinaryCouncils" and config.pages == ("177", "194")
    assert config.model == "claude-sonnet-5-5" and config.ceiling_usd == 2.0
    assert config.sample == SampleRule(0.25, 5, 20, "work")
    assert config.model in correct_mod.PRICES
