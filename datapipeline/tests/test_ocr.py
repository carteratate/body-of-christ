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
from ocr.gate import draw_sample, evaluate, rate_check, record, start_check, text_hash
from ocr.label import is_scanned, label_passage, ocr_metadata, scanned_text
from ocr.layout import get_layout
from ocr.pages import Line, Page, load_pages
from ocr.report import write as write_report
from ocr.work import (SOURCES, Baseline, OcrPassage, SampleRule, WorkConfig, WorkDir,
                      baseline_text)
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


# --- units, fixes and the frozen text (1.2e) ------------------------------------------

from ocr.fixes import apply_fixes, freeze, read_text  # noqa: E402
from ocr.furniture import Paragraph  # noqa: E402
from ocr.units import SchroederCanons, get_units, strip_note_calls, strip_stray_quotes  # noqa: E402


def _paras(*texts):
    return [Paragraph(t, t, [1]) for t in texts]


def test_schroeder_units_keep_only_the_text_of_each_canon():
    units = SchroederCanons().split(_paras(
        "History. The council met.", "CANON I", "Summary. A digest.",
        "Text. The first canon.", "It goes on here.", "Comment. His remarks.",
        "More remarks.", "CANON 2", "Summary. Another.", "Text, The second canon."))
    assert [u.id for u in units] == ["canon-1", "canon-2"]
    assert [[p.text for p in u.paragraphs] for u in units] == [
        ["The first canon.", "It goes on here."], ["The second canon."]]


def test_a_lost_heading_is_numbered_by_counting_texts():
    units = SchroederCanons().split(_paras(
        "CANON 1", "Text. One.", "Summary. Lost heading.", "Text. Two.", "CANON 3", "Text. Three."))
    assert [u.id for u in units] == ["canon-1", "canon-2", "canon-3"]


def test_a_heading_sharing_a_paragraph_with_its_summary_closes_the_canon():
    units = SchroederCanons().split(_paras(
        "Text. One.", "CANON 2 Summary. The digest.", "Text. Two."))
    assert [[p.text for p in u.paragraphs] for u in units] == [["One."], ["Two."]]


def test_a_heading_that_disagrees_with_the_count_stops_the_split():
    with pytest.raises(ValueError, match="canon heading 5"):
        SchroederCanons().split(_paras("CANON 1", "Text. One.", "CANON 5", "Text. Two."))


def test_unknown_units_are_refused():
    with pytest.raises(ValueError, match="no OCR units"):
        get_units("nonsense")


@pytest.mark.parametrize("before,after", [
    ("could arise.°", "could arise."),
    ("the Church.’®", "the Church."),
    ("null and void.*?", "null and void."),
    ("of all dignity.” Next.", "of all dignity. Next."),
    ("He said, “Go in peace.” Next.", "He said, “Go in peace.” Next."),
    ("Who is he? Next.", "Who is he? Next."),
    ("in * the text", "in the text"),
])
def test_note_calls_go_and_quotations_stay(before, after):
    assert strip_note_calls(before) == after


def _fixed_work(tmp_path, fixes):
    works = tmp_path / "works"
    works.mkdir()
    (works / "w.fixes.json").write_text(json.dumps(fixes), encoding="utf-8")
    config = SimpleNamespace(work="w")
    wd = SimpleNamespace(config=config, _p=[OcrPassage("canon-1", [1], ["1"], "raw", "the shail be")])
    wd.passages = lambda: wd._p
    wd.save_passages = lambda ps: None
    return wd, works


def test_fixes_apply_on_the_final_text_and_keep_the_rest(tmp_path):
    wd, works = _fixed_work(tmp_path, [
        {"passage": "canon-1", "find": "shail", "replace": "shall", "why": "print"}])
    assert apply_fixes(wd, works) == 1
    assert wd._p[0].text == "the shall be"
    assert wd._p[0].cleaned == "the shail be"


@pytest.mark.parametrize("fix,message", [
    ({"passage": "canon-1", "find": "absent", "replace": "x", "why": "print"}, "0 times"),
    ({"passage": "canon-9", "find": "the", "replace": "x", "why": "print"}, "no passage"),
    ({"passage": "canon-1", "find": "the", "replace": "x", "why": ""}, "says why"),
])
def test_a_fix_that_does_not_fit_stops_the_run(tmp_path, fix, message):
    wd, works = _fixed_work(tmp_path, [fix])
    with pytest.raises(ValueError, match=message):
        apply_fixes(wd, works)


def test_the_check_hashes_the_fixed_text():
    # The sampled text is hashed through `text`, so a later fix makes the check stale.
    p = OcrPassage("canon-1", [1], ["1"], "raw", "the shail be")
    before = p.text
    p.fixed = "the shall be"
    assert p.text != before and p.base == before


def test_freeze_writes_the_text_the_adapter_reads(tmp_path, monkeypatch):
    config = WorkConfig.from_dict({
        "work": "w", "title": "T", "scan": "scan-id", "djvu_xml": "synthetic_djvu.xml",
        "page_numbers": "synthetic_page_numbers.json", "pages": ["1", "3"],
        "baseline": {"path": "baseline.html", "start": "^START", "end": "^END"}})
    wd = WorkDir(config, tmp_path / "work")
    wd.save_passages([OcrPassage("canon-1", [1], ["1"], "raw", "cleaned", fixed="final")])
    monkeypatch.setattr("ocr.fixes.evaluate", lambda w: SimpleNamespace(status="pending"))
    freeze(wd, tmp_path / "texts")
    data = read_text("w", tmp_path / "texts")
    assert data["gate"] == "pending"
    assert data["metadata"] == {"text_source": "ocr", "scan_id": "scan-id"}
    assert data["passages"][0]["text"] == "final"


def test_a_verdict_on_text_that_has_changed_is_refused(tmp_path):
    config = WorkConfig.from_dict({
        "work": "w", "title": "T", "scan": "s", "djvu_xml": "x", "page_numbers": "n",
        "pages": ["1", "3"], "baseline": {"path": "b", "start": "s", "end": "e"},
        "sample": {"fraction": 1.0, "minimum": 1, "maximum": 1}})
    wd = WorkDir(config, tmp_path)
    wd.save_passages([OcrPassage("canon-1", [1], ["1"], "raw", "the text shown")])
    start_check(wd, seed=1)
    shown = text_hash("the text shown")
    wd.save_passages([OcrPassage("canon-1", [1], ["1"], "raw", "a revised text")])
    with pytest.raises(ValueError, match="changed since"):
        record(wd, "canon-1", "matches", "P", shown_sha256=shown)
    assert wd.check()["sample"][0]["result"] == "pending"
    record(wd, "canon-1", "matches", "P", shown_sha256=text_hash("a revised text"))
    assert wd.check()["sample"][0]["result"] == "matches"


def test_a_baseline_can_take_only_the_units_text(tmp_path):
    (tmp_path / "b.html").write_text(
        "<p>START History.</p><p>Text. A canon.</p><p>It goes on.</p><p>Comment. His view.</p>"
        "<p>More of his view.</p><p>Text. Another.</p><p>END</p>", encoding="utf-8")
    baseline = Baseline("b.html", "^START", "^END", opens="^Text", closes="^Comment")
    assert baseline_text(baseline, tmp_path) == ["Text. A canon.", "It goes on.", "Text. Another."]


@pytest.mark.skipif(not (SOURCES / "councils" / "fordham-lateran1.html").exists(),
                    reason="needs the gitignored datapipeline/sources/")
@pytest.mark.parametrize("work,canons", [("schroeder-lateran-1", 22), ("schroeder-lateran-2", 30),
                                         ("schroeder-lateran-4", 71)])
def test_council_baselines_hold_every_canon_and_no_editor_text(work, canons):
    paragraphs = baseline_text(WorkConfig.load(work).baseline)
    assert sum(p.startswith("Text") for p in paragraphs) == canons
    assert not [p[:40] for p in paragraphs
                if re.match(r"(?i)(?:summary|comment|canon\s+\d|note\s*\d|\[note)", p)]


# --- running heads set low, two series, misread labels (1.2e-2) ------------------------

def _low_page(leaf, number, top_lines, first_top=360):
    lines = [Line(t, 300, first_top + 80 * k, 1700, first_top + 60 + 80 * k)
             for k, t in enumerate(top_lines)]
    body_top = first_top + 80 * len(top_lines) + 40
    lines += [Line(f"Body line {k} of the page with ordinary words in it", 150,
                   body_top + 75 * k, 1850, body_top + 60 + 75 * k) for k in range(5)]
    return Page(leaf, 2000, 4000, lines, number=number)


def test_a_running_head_set_low_on_the_page_goes_with_marks_above_it():
    # Below the 7% band (Schroeder pp. 301-442 sit up to 14% down), the page's number
    # marks the head; a pen mark above it goes too, and a title page keeps its title.
    pages = [_low_page(0, "301", ["FIRST COUNCIL OF LYONS 301"]),
             _low_page(1, "306", ["i re tne pee", "306 DECREES OF THE COUNCILS"], first_top=180),
             _low_page(2, "371", ["COUNCIL OF VIENNE", "371"]),
             _low_page(3, "373", ["COUNCIL OF VIENNE 373"]),
             _low_page(4, "375", ["COUNCIL OF VIENNE 375"]),
             _low_page(5, "324", ["THE FOURTEENTH GENERAL COUNCIL (1274)", "Second Council of Lyons"])]
    result = clean_pages(pages)
    assert [(r.page, r.kind, r.text) for r in result.removals] == [
        ("301", "running_head", "FIRST COUNCIL OF LYONS 301"),
        ("306", "speck", "i re tne pee"), ("306", "running_head", "306 DECREES OF THE COUNCILS"),
        ("371", "running_head", "COUNCIL OF VIENNE"), ("371", "page_number", "371"),
        ("373", "running_head", "COUNCIL OF VIENNE 373"),
        ("375", "running_head", "COUNCIL OF VIENNE 375")]
    body = " ".join(p.text for p in result.paragraphs)
    assert "THE FOURTEENTH GENERAL COUNCIL" in body and "Second Council of Lyons" in body


def test_two_series_restart_the_count_and_name_their_units():
    units = SchroederCanons().split(_paras(
        "CANON 1", "Text. One.", "CANON 2", "Text. Two.", "An editor's bridge.",
        "SECOND SERIES", "CANON I", "Text. Again one."), series=(2, 1),
        closes=("^An editor's bridge",))
    assert [(u.id, [p.text for p in u.paragraphs]) for u in units] == [
        ("series-1-canon-1", ["One."]), ("series-1-canon-2", ["Two."]),
        ("series-2-canon-1", ["Again one."])]


def test_a_series_count_that_the_text_does_not_fill_stops_the_split():
    with pytest.raises(ValueError, match="series"):
        SchroederCanons().split(_paras("CANON 1", "Text. One."), series=(2, 1))


def test_a_text_label_inside_a_summary_paragraph_opens_the_canon():
    units = SchroederCanons().split(_paras(
        "CANON 1", "Summary. Votes are void. Text. In elections we condemn.",
        "CANON 2", "Sey. Roads must be watched.: Text, Desiring above all things."))
    assert [[p.text for p in u.paragraphs] for u in units] == [
        ["In elections we condemn."], ["Desiring above all things."]]


def test_a_paragraph_opening_with_a_misread_label_never_joins_the_text():
    units = SchroederCanons().split(_paras(
        "CANON 1", "Text. One.", "Conrment. His remarks.", "More of his remarks."))
    assert [[p.text for p in u.paragraphs] for u in units] == [["One."]]
    with pytest.raises(ValueError, match="unknown word"):
        SchroederCanons().split(_paras("CANON 1", "Text. One.", "Zqxw. Not a word."))


def test_a_latin_clause_after_a_comma_stays_in_the_text():
    units = SchroederCanons().split(_paras("CANON 1", "Text. One.", "Quoniam, ut ait Apostolus."))
    assert [p.text for p in units[0].paragraphs] == ["One.", "Quoniam, ut ait Apostolus."]


def test_a_heading_with_a_misread_digit_does_not_overrule_the_count():
    # "CANON I10" is a printed 10 with a mark read as "I"; "CANON §" a printed 5.
    units = SchroederCanons().split(_paras(
        "CANON 1", "Text. One.", "CANON I10", "Text. Two.", "CANON §", "Text. Three."))
    assert [u.id for u in units] == ["canon-1", "canon-2", "canon-3"]
    with pytest.raises(ValueError, match="canon heading 110"):
        SchroederCanons().split(_paras("CANON 1", "Text. One.", "CANON 110", "Text. Two."))


def test_his_citation_of_the_clementines_is_dropped():
    units = SchroederCanons().split(_paras(
        "CANON 1", "Text. The decree ends here. (C. un., in Clem., De foro competenti, II, 2.)"))
    assert units[0].paragraphs[0].text == "The decree ends here."


@pytest.mark.parametrize("before,after", [
    ("clear ‘proof in regard", "clear proof in regard"),
    ("shall ‘ permit strangers", "shall permit strangers"),
    ("He said ‘go’, and God’s word.", "He said ‘go’, and God’s word."),
])
def test_an_opening_single_quote_that_nothing_closes_goes(before, after):
    assert strip_stray_quotes(before) == after


# --- Giles's Matthew Paris (1.2e) ------------------------------------------------------

from ocr.furniture import _joined  # noqa: E402
from ocr.pages import read_page_numbers  # noqa: E402
from ocr.units import Bounded  # noqa: E402


def _body(texts, indent_first=()):
    """A page whose lines are `texts`; a line in `indent_first` is drawn indented."""
    return Page(0, 2000, 3000, [Line(t, 400 if k in indent_first else 150, 300 + 75 * k,
                                     1850, 360 + 75 * k) for k, t in enumerate(texts)])


def test_page_numbers_follow_a_leaf_left_out_of_the_images(tmp_path):
    path = tmp_path / "n.json"
    path.write_text(json.dumps({"pages": [{"leafNum": 5, "pageNumber": "3"}]}))
    assert read_page_numbers(path) == {5: "3"}
    assert read_page_numbers(path, leaf_offset=1) == {4: "3"}
    assert make_config().leaf_offset == 0


def test_a_broken_words_rest_opens_no_paragraph_where_the_work_says_so():
    # Giles's OCR misplaces the box of "ration" after "delibe-", so it reads as indented.
    page = _body(["It needed long delibe-", "ration of the matter at hand,",
                  "and nothing more was said."], indent_first={1})
    assert len(clean_pages([page]).paragraphs) == 2
    joined = clean_pages([page], broken_words_continue=True).paragraphs
    assert [p.text for p in joined] == [
        "It needed long deliberation of the matter at hand, and nothing more was said."]


def test_bohns_signature_marks_are_furniture():
    for mark in ("VOL. II. G", "g2"):
        page = _body([f"Ordinary words on line {k} of this page run on" for k in range(5)])
        page.lines.append(Line(mark, 150, 2700, 600, 2760))
        result = clean_pages([page])
        assert [r.kind for r in result.removals] == ["signature"], mark


def test_a_long_paragraph_is_cut_at_a_clause_end_and_joined_back():
    lines = ["one two three four five six,", "seven eight nine ten", "eleven twelve thirteen.",
             "fourteen fifteen sixteen"]
    paras = clean_pages([_body(lines)], max_paragraph_words=6).paragraphs
    assert [(p.text, p.continues) for p in paras] == [
        ("one two three four five six,", False),
        ("seven eight nine ten eleven twelve thirteen.", True),
        ("fourteen fifteen sixteen", True)]
    assert _joined([(p.text, p.continues) for p in paras]) == " ".join(lines)
    assert _joined([("A.", False), ("B.", False)]) == "A.\n\nB."


def test_bounded_units_take_each_text_and_drop_its_double_quotes():
    paras = _paras("The chronicle.", "“ Innocent, bishop, &c.", "“ He said ‘go’. ”",
                   "More chronicle.", "“ Of the legate. ”", "After.")
    units = Bounded().split(paras, bounds=(
        {"id": "bull", "first": "Innocent", "last": "said"},
        {"id": "legate", "first": "Of the legate", "last": "legate"}))
    assert [(u.id, [p.text for p in u.paragraphs]) for u in units] == [
        ("bull", ["Innocent, bishop, &c.", "He said ‘go’."]), ("legate", ["Of the legate."])]


def test_a_bounded_text_longer_than_a_passage_is_numbered_in_parts():
    words = " ".join(["word"] * 300)
    units = Bounded().split(_paras(f"Start {words}.", f"{words} end."),
                            bounds=({"id": "bull", "first": "^Start", "last": "end\\.$"},))
    assert [u.id for u in units] == ["bull-01", "bull-02"]


def test_bounded_units_refuse_a_missing_bound_or_a_start_inside_a_paragraph():
    with pytest.raises(ValueError, match="no paragraph"):
        Bounded().split(_paras("Text."), bounds=({"id": "x", "first": "Nowhere", "last": "."},))
    cut = [Paragraph("Earlier,", "", [1]), Paragraph("Start here.", "", [1], continues=True)]
    with pytest.raises(ValueError, match="inside a paragraph"):
        Bounded().split(cut, bounds=({"id": "x", "first": "Start", "last": "here"},))
    with pytest.raises(ValueError, match="by bounds"):
        SchroederCanons().split(_paras("Text. One."), bounds=({"id": "x"},))


def test_a_run_without_recorded_cuts_finds_them_again(tmp_path, sources):
    """A run cleaned before `cut` was recorded: a join its fixes no longer make goes."""
    w = WorkDir(make_config(work="w"), root=tmp_path / "work")
    clean_work(w, sources=sources, passage_words=20)
    data = json.loads(w.file("passages.json").read_text())
    assert not data[1]["continues"]
    for d in data:
        d.pop("cut")
    data[1]["continues"] = True          # joined by a fix since taken out
    w.file("passages.json").write_text(json.dumps(data))
    (tmp_path / "w.fixes.json").write_text("[]")
    apply_fixes(w, tmp_path, sources=sources, passage_words=20)
    assert [p.continues for p in w.passages()] == [p["cut"] for p in json.loads(
        w.file("passages.json").read_text())]
    assert not w.passages()[1].continues


def test_a_fix_can_join_a_passage_to_the_paragraph_before_it(tmp_path):
    config = make_config(work="w")
    wd = WorkDir(config, tmp_path / "work")
    wd.save_passages([OcrPassage("a-01", [1], ["1"], "raw", "That"),
                      OcrPassage("a-02", [1], ["1"], "raw", "the Church")])
    (tmp_path / "w.fixes.json").write_text(json.dumps(
        [{"passage": "a-02", "continues": True, "why": "one sentence over the page"}]))
    apply_fixes(wd, tmp_path)
    assert [p.continues for p in wd.passages()] == [False, True]
    (tmp_path / "w.fixes.json").write_text("[]")   # the join taken out again no longer holds
    apply_fixes(wd, tmp_path)
    assert [p.continues for p in wd.passages()] == [False, False]
    (tmp_path / "w.fixes.json").write_text(json.dumps(
        [{"passage": "a-02", "why": "no find and no join"}]))
    with pytest.raises(ValueError, match="continues"):
        apply_fixes(wd, tmp_path)


# --- 1.2e-4: Deferrari's PDF, parallel columns, headed units ---------------------------

from ocr.furniture import _strip_margin_numbers  # noqa: E402
from ocr.layout import ParallelLeft  # noqa: E402
from ocr.pdf import mended as _mended  # noqa: E402
from ocr.units import DeferrariExtracts, Headed  # noqa: E402


@pytest.mark.parametrize("read, mended", [
    ("con1mand", "command"), ("trans111it", "transmit"), ("\\vhich,", "which,"), ("£ro111", "from"),
    ("sonletimes", "sometimes"), ("eculnenical", "ecumenical"), ("n10ve", "move"),
    ("only", "only"), ("1415", "1415"), ("Isaias", "Isaias"), ("Annenians", "Annenians"),
])
def test_text_layer_misreadings_are_mended_only_into_known_words(read, mended):
    assert _mended(read) == mended


def _wline(top, *words):
    """A line of (text, x0, x1) words, as `pdf.py` gives it."""
    return Line(" ".join(w[0] for w in words), words[0][1], top, words[-1][2], top + 25,
                words=tuple(words))


def _row(top, left, right=None):
    """A line of six words across the left column, and optionally the right one."""
    words = [(w, 120 + 100 * k, 190 + 100 * k) for k, w in enumerate(left.split())]
    if right:
        words += [(w, 760 + 100 * k, 830 + 100 * k) for k, w in enumerate(right.split())]
    return _wline(top, *words)


def test_parallel_left_keeps_the_left_column_and_lines_across_the_page():
    full = _wline(300, *[(f"w{k}", 120 + 100 * k, 190 + 100 * k) for k in range(12)])
    page = Page(0, 1400, 2200, [
        _row(100, "one two three four five six", "Greek alpha beta gamma delta epsilon"),
        _row(150, "seven eight nine ten eleven twelve", "Greek zeta eta theta iota kappa"),
        _row(200, "thirteen fourteen fifteen sixteen seventeen eighteen", "Greek lambda mu nu xi omicron"),
        _wline(250, ("anathema.", 760, 900)),           # the right column alone
        full])
    kept = ParallelLeft().reading_order(page)
    assert [ln.text for ln in kept] == [
        "one two three four five six", "seven eight nine ten eleven twelve",
        "thirteen fourteen fifteen sixteen seventeen eighteen", full.text]


def test_parallel_left_leaves_a_page_without_columns_whole():
    # One wide space near the middle of running text is not a gutter.
    wide = _wline(100, *[(f"a{k}", 120 + 100 * k, 190 + 100 * k) for k in range(6)],
                  *[(f"b{k}", 760 + 100 * k, 830 + 100 * k) for k in range(6)])
    page = Page(0, 1400, 2200, [wide, _row(150, "one two three four five six seven")])
    assert ParallelLeft().reading_order(page) == sorted(page.lines, key=lambda ln: (ln.top, ln.x0))


def test_parallel_left_needs_each_lines_words():
    with pytest.raises(ValueError, match="needs each line's words"):
        ParallelLeft().reading_order(Page(0, 1400, 2200, [Line("text", 100, 100, 900, 125)]))


def test_margin_numbers_go_and_an_articles_own_number_stays():
    body = [(w, 200 + 90 * k, 270 + 90 * k) for k, w in enumerate("a b c d e f g h i j".split())]
    lines = [_wline(100, ("6.", 200, 230), *body[1:]),
             _wline(150, *body, ("586", 1250, 1310)),          # right margin
             _wline(200, ("337", 100, 160), *body),            # left margin
             _wline(250, ("1415", 1250, 1330))]                # a margin number alone
    kept, removed = _strip_margin_numbers(lines, Page(0, 1400, 2200, lines))
    assert [ln.words[0][0] for ln in kept] == ["6.", "a", "a"]
    assert all("586" not in ln.text and "337" not in ln.text for ln in kept)
    assert sorted(r.text for r in removed) == ["1415", "337", "586"]


def test_headed_units_run_from_each_opening_to_the_next_and_take_the_heading_off():
    paras = _paras("History of the council.", "From the bull Alpha (session I, 1513): First text.",
                   "More of the first.", "2", "Second text.", "End of the second.", "Index.")
    bounds = ({"id": "session-1/alpha", "first": "^From the bull Alpha",
               "heading": "^From the bull [^:]*:\\s*"},
              {"id": "session-1/beta", "first": "^Second text", "last": "^End of"})
    units = Headed().split(paras, bounds=bounds)
    assert [(u.id, [p.text for p in u.paragraphs]) for u in units] == [
        ("session-1/alpha", ["First text.", "More of the first."]),
        ("session-1/beta", ["Second text.", "End of the second."])]


@pytest.mark.parametrize("paras, bounds, message", [
    (("Alpha.", "3", "More."), ({"id": "a", "first": "^Alpha", "last": "^More"},), "heading inside"),
    (("Alpha.", "From the bull Gamma: text."), ({"id": "a", "first": "^Alpha", "last": "Gamma"},),
     "heading inside"),
    (("Alpha.",), ({"id": "a", "first": "^Beta", "last": "x"},), "no paragraph"),
    (("Alpha.", "Beta."), ({"id": "a", "first": "^Alpha"},), "needs `last`"),
])
def test_headed_units_raise_on_doubt(paras, bounds, message):
    with pytest.raises(ValueError, match=message):
        Headed().split(_paras(*paras), closes=("^From the bull",), bounds=bounds)


def test_deferrari_units_drop_his_labels_and_references_and_keep_the_translators_words():
    paras = _paras('We say: "Thy light [law] is a lamp" [Ps. 118:105], and so [see n. 595] on.',
                   "[The procession of the Holy Spirit]",
                   "(The decrees for Greeks and Armenians ... follow.)",
                   "Christ spoke [Luke 3: 17J this; the sanction [pragmatic] itself.")
    unit, = DeferrariExtracts().split(paras, bounds=({"id": "x", "first": "^We say", "last": "itself"},))
    assert [p.text for p in unit.paragraphs] == [
        'We say: "Thy light [law] is a lamp", and so on.',
        "Christ spoke this; the sanction [pragmatic] itself."]


def test_a_comment_inside_a_canons_paragraph_closes_it():
    units = SchroederCanons().split(_paras(
        "CANON 1", "Text. The canon reads so. Comment. Schroeder explains it.",
        "CANON 2", "Text. Another canon.", "More of it. Comment. His view."))
    assert [[p.text for p in u.paragraphs] for u in units] == [
        ["The canon reads so."], ["Another canon.", "More of it."]]


def test_a_heading_at_the_foot_of_a_page_is_not_a_note():
    body = [Line(f"line {k} of the body text runs across the page", 100, 200 + 40 * k, 900,
                 225 + 40 * k) for k in range(20)]
    heading = Line("‘CANON 10", 400, 1060, 560, 1085)
    summary = [Line("Summary. A short summary set tight under it.", 100, 1092 + 30 * k, 900,
                    1112 + 30 * k) for k in range(3)]
    result = clean_pages([Page(0, 1000, 1400, body + [heading] + summary, number="166")])
    assert not result.notes
    assert any("CANON 10" in p.text for p in result.paragraphs)


DEFERRARI_PDF = SOURCES / "councils/sources-of-catholic-dogma/the-sources-of-catholic-dogma-loreto-reprint.pdf"


@pytest.mark.skipif(not DEFERRARI_PDF.exists(), reason="the vendored PDF is not in this checkout")
def test_the_pdf_reader_gives_lines_with_words_and_the_printed_page():
    from ocr.pdf import read_pdf
    calls = []
    page, = read_pdf(DEFERRARI_PDF, range(166, 167), 31, calls)
    assert page.number == "135"
    assert all(ln.words for ln in page.lines)
    first = next(ln for ln in page.lines if ln.text.startswith("(Text of Anastasius"))
    assert first.words[-1][0] == "336"                  # the margin number, as a word
    assert any(c.text == "3" for c in calls)            # "Dionysius,³"


def test_a_passage_the_fixes_emptied_is_not_drawn_or_counted(workdir):
    passages = workdir.passages()
    passages[0].fixed = ""            # wholly a note read into the text, taken out
    workdir.save_passages(passages)
    check = start_check(workdir, seed=7)
    assert passages[0].id not in check["population"]
    assert passages[0].id not in [e["id"] for e in check["sample"]]
    assert not evaluate(workdir, ["A clean baseline sentence."]).stale


def test_raw_ocr_keeps_the_text_layers_reading_of_a_mended_word():
    words = (("the", 100, 150, "the"), ("command", 160, 300, "con1mand"), ("of", 310, 340, "of"))
    line = Line("the command of", 100, 100, 340, 125, words=words)
    para, = clean_pages([Page(0, 1000, 1400, [line], number="1")]).paragraphs
    assert para.text == "the command of" and para.raw == "the con1mand of"


# --- 1.2e-5: Deferrari's numbered lists, lost decree headings ---------------------------------


def _article(top, number, words, margin=None, indent=230):
    """A line of an article in Deferrari's lists: its own number, then words; his margin
    number, where given, stands left of the text block."""
    out = [(margin, 100, 160)] if margin else []
    out.append((f"{number}.", indent, indent + 40))
    out += [(w, indent + 60 + 90 * k, indent + 130 + 90 * k) for k, w in enumerate(words.split())]
    return _wline(top, *out)


def test_margin_numbers_go_on_a_page_where_most_lines_open_with_one():
    # Wyclif's articles, p. 210: nearly every full line opens with a margin number, so the
    # text block is measured without them.
    lines = [_article(100 + 50 * k, k + 1, "a b c d e f g h", margin=str(602 + k)) for k in range(6)]
    lines.append(_wline(400, *[(w, 200 + 90 * k, 270 + 90 * k) for k, w in enumerate("x y z q r s".split())]))
    kept, removed = _strip_margin_numbers(lines, Page(0, 1400, 2200, lines))
    assert sorted(r.text for r in removed) == [str(602 + k) for k in range(6)]
    assert [ln.words[0][0] for ln in kept[:6]] == [f"{k + 1}." for k in range(6)]
    assert all(ln.numbered for ln in kept[:6]) and not kept[6].numbered


def test_a_line_that_carried_a_margin_number_opens_a_paragraph():
    # One-line articles under each other, none indented against its neighbours: each still
    # opens a paragraph, since Denzinger numbers each.
    lines = [_article(100 + 40 * k, k + 26, "the prayer avails no one", margin=str(606 + k)) for k in range(3)]
    result = clean_pages([Page(0, 1400, 2200, lines, "210")], margin_numbers=True)
    assert [p.text for p in result.paragraphs] == [f"{k + 26}. the prayer avails no one" for k in range(3)]


def test_paragraph_opens_starts_a_paragraph_where_a_lost_heading_left_none():
    lines = [Line(f"line {k} of the decree runs right across the page", 100, 100 + 40 * k, 900, 125 + 40 * k)
             for k in range(4)]
    lines[2] = Line("Since from the indiscreet imposition of interdicts the", 100, 180, 900, 205)
    page = Page(0, 1000, 2000, lines, "475")
    assert len(clean_pages([page]).paragraphs) == 1
    paras = clean_pages([page], paragraph_opens=("^Since from the indiscreet",)).paragraphs
    assert [p.text.split()[0] for p in paras] == ["line", "Since"]
    with pytest.raises(ValueError, match="matches 0 lines"):
        clean_pages([page], paragraph_opens=("^No such line",))


def test_deferrari_units_drop_a_label_opening_a_paragraph_and_a_remark_set_over_two():
    paras = _paras("[The procession of the Holy Spirit] In the name of the Trinity we define.",
                   "[De novissimisJ 2 It has likewise defined.",
                   "(The decrees for Greeks and Armenians of the ecumenical",
                   "Synod accepted by the Roman Church follow.)",
                   "But since the form of the words is fixed, it is so.")
    unit, = DeferrariExtracts().split(paras, bounds=({"id": "x", "first": "^\\[The procession",
                                                      "last": "it is so"},))
    assert [p.text for p in unit.paragraphs] == [
        "In the name of the Trinity we define.", "It has likewise defined.",
        "But since the form of the words is fixed, it is so."]


# --- 1.2c: Hefele's anathemas, Chrystal's Nestorius ------------------------------------------

from ocr.units import ChrystalLetter  # noqa: E402


def _body_and_notes(top, words="the letter runs on across the whole width of the page"):
    return Line(words, 100, top, 900, top + 25)


def test_rule_lines_go_as_furniture_and_each_names_one_line():
    lines = [_body_and_notes(100 + 40 * k) for k in range(3)]
    lines.insert(1, Line("ee SS ---ς-ς---ο--- --ο------", 100, 130, 900, 150))
    page = Page(0, 1000, 2000, lines, "157")
    result = clean_pages([page], rule_lines=("^ee SS ---",))
    assert [r.kind for r in result.removals] == ["rule"]
    assert "SS" not in result.paragraphs[0].text
    with pytest.raises(ValueError, match="matches 3 lines"):
        clean_pages([page], rule_lines=("^the letter",))


def test_note_opens_starts_the_pages_notes_where_the_measure_sees_none():
    # Chrystal's notes are set almost the size of his text, with no extra space, and a note
    # carried over from the page before opens with no marker.
    body = [_body_and_notes(100 + 40 * k) for k in range(3)]
    notes = [Line("Surely after such language as this, both Cyril and the Church", 100, 220, 900, 245),
             Line("(309). The Greek is as follows", 140, 260, 900, 285)]
    page = Page(0, 1000, 2000, body + notes, "158")
    assert len(clean_pages([page]).notes) == 0
    result = clean_pages([page], note_opens=("^Surely after such language",))
    assert [n.text.split("\n")[0][:6] for n in result.notes] == ["Surely"]
    assert "Surely" not in " ".join(p.text for p in result.paragraphs)


def test_a_bounded_text_can_open_and_close_inside_a_paragraph():
    paras = _paras("Anathema to John! If anyone does not confess that Christ, let him be anathema! "
                   "If anyone rejects the tradition, let him be anathema! Eternal remembrance.")
    unit, = Bounded().split(paras, bounds=({"id": "anathemas", "first": "If anyone",
                                            "last": "rejects", "start": "If anyone does not",
                                            "end": "rejects the tradition, let him be anathema!"},))
    assert unit.paragraphs[0].text == ("If anyone does not confess that Christ, let him be "
                                       "anathema! If anyone rejects the tradition, let him be anathema!")
    with pytest.raises(ValueError, match="holds no"):
        Bounded().split(paras, bounds=({"id": "x", "first": "If", "last": "If", "end": "Nowhere"},))


def test_chrystal_units_drop_his_summaries_and_note_calls_and_keep_quotes():
    paras = _paras("“To the most religious Cyril, Nestorius wishes joy in the Lord” (290).",
                   "[Section I. Nestorius brands St. Cyril's Epistle as insulting to him",
                   "and of course His Inman also. |",
                   "The insults directed against us in thy admirable (291) Letter, I dismiss as "
                   "worthy of a physicians’ long suffering, (292), and the words “Lord,” (299), and "
                   "“Son” the names [that is] common to both.",
                   "[SEcTION IV. Nestorius thanks Cyril.]",
                   "May you continue strong, O brother, and to God most dear” (346).")
    unit, = ChrystalLetter().split(paras, bounds=({"id": "letter", "first": "^“To the",
                                                   "last": "most dear"},))
    assert [p.text for p in unit.paragraphs] == [
        "“To the most religious Cyril, Nestorius wishes joy in the Lord”.",
        "The insults directed against us in thy admirable Letter, I dismiss as worthy of a "
        "physicians’ long suffering, and the words “Lord,” and “Son” the names [that is] "
        "common to both.",
        "May you continue strong, O brother, and to God most dear”."]
    with pytest.raises(ValueError, match="does not close"):
        ChrystalLetter().split(paras[:2], bounds=({"id": "x", "first": "^“To", "last": "Section"},))


# ------------------------------------------------- 1.3d: papal printings' scans

def test_only_pages_reads_the_pages_named(tmp_path, sources):
    """A printing that faces its Latin with the English reads only the English pages."""
    w = WorkDir(make_config(only_pages=("10", "12")), root=tmp_path / "w")
    clean_work(w, sources=sources, passage_words=20)
    assert {p for passage in w.passages() for p in passage.pages} <= {"10", "12"}
    with pytest.raises(ValueError, match="only_pages"):
        clean_work(WorkDir(make_config(only_pages=("10", "99")), root=tmp_path / "x"),
                   sources=sources, passage_words=20)


def test_leaf_pages_name_the_pages_without_a_page_map(tmp_path, sources):
    """A work that names each leaf's printed page reads them without the scan's map."""
    w = WorkDir(make_config(page_numbers="", leaf_pages={"0": "10", "1": "11", "2": "12"}),
                root=tmp_path / "w")
    clean_work(w, sources=sources, passage_words=20)
    assert {p for passage in w.passages() for p in passage.pages} <= {"10", "11", "12"}
    assert w.passages()


def test_edge_strip_drops_the_previous_pages_cut_off_lines(tmp_path, sources):
    """A microfilm frame that also caught the page before's edge reads only its own
    page: lines starting within the strip go, logged as `edge_strip`."""
    w = WorkDir(make_config(edge_strip=0.09), root=tmp_path / "w")   # 180 of 2000 pixels
    clean_work(w, sources=sources, passage_words=20)
    dropped = [r for r in w.cleanup()["removals"] if r["kind"] == "edge_strip"]
    assert dropped
    kept = " ".join(p.cleaned for p in w.passages())
    assert all(r["text"] not in kept for r in dropped)


def test_parallel_right_keeps_the_right_column_and_lines_across_the_page():
    from ocr.layout import ParallelRight

    lines = [Line("The text of the Bull runs thus:", 460, 100, 2150, 140)]
    for k in range(8):
        lines.append(Line(f"Latin line {k}", 460, 200 + 60 * k, 1270, 240 + 60 * k))
        lines.append(Line(f"English line {k}", 1335, 200 + 60 * k, 2145, 240 + 60 * k))
    kept = [ln.text for ln in ParallelRight().reading_order(Page(0, 2500, 3800, lines))]
    assert kept == ["The text of the Bull runs thus:"] + [f"English line {k}" for k in range(8)]
    assert get_layout("parallel-right").name == "parallel-right"


def test_long_s_is_written_out():
    body = [Line(f"Ordinary words on line {k} of this page run on", 150, 300 + 75 * k, 1850, 360 + 75 * k)
            for k in range(6)] + [Line("moſt ſolicitude, which theſe times require.", 150, 760, 1850, 820)]
    text = "\n".join(p.text for p in clean_pages([Page(0, 2000, 3000, body)]).paragraphs)
    assert "most solicitude, which these times require." in text and "ſ" not in text


def test_watermark_is_taken_out_of_the_line_it_was_read_into():
    body = [Line(f"Ordinary words on line {k} of this page run on", 150, 300 + 75 * k, 1850, 360 + 75 * k)
            for k in range(6)]
    page = Page(0, 2000, 3000, body + [
        Line("Digitized by LjOOQle", 1200, 2700, 1800, 2750),
        Line("Digitized by CjOOQle principles, to attain the truth.", 150, 760, 1850, 820)])
    result = clean_pages([page], watermark=r"Digitized by \S+")
    text = "\n".join(p.text for p in result.paragraphs)
    assert "Digitized" not in text and "principles, to attain the truth." in text
    assert [r.kind for r in result.removals].count("watermark") == 2


def test_bounded_text_keeps_its_quotes_when_asked():
    from ocr.furniture import Paragraph
    from ocr.units import Bounded

    paras = [Paragraph('He wrote: "Mirari vos" is cited.', "", [0]),
             Paragraph("Given at Rome, 1864.", "", [0])]
    bound = {"id": "t", "first": "^He wrote", "last": "^Given"}
    dropped = Bounded().split(paras, bounds=(bound,))[0].paragraphs[0].text
    kept = Bounded().split(paras, bounds=({**bound, "keep_quotes": True},))[0].paragraphs[0].text
    assert '"' not in dropped and kept == 'He wrote: "Mirari vos" is cited.'


def test_two_column_reads_the_head_then_left_then_right_by_row():
    from ocr.layout import TwoColumn

    lines = [Line("ROMAN CATHOLIC CHURCH.", 1035, 302, 1925, 340), Line("689", 2586, 314, 2679, 350)]
    for k in range(6):
        lines.append(Line(f"left column line {k} of running text here", 240, 440 + 48 * k, 1430, 480 + 48 * k))
        lines.append(Line(f"right column line {k} of running text here", 1490, 440 + 48 * k, 2680, 480 + 48 * k))
    # A stray mark before a right-column line does not make it run across the page.
    lines.append(Line("- anew right column line 6 of text", 1440, 440 + 48 * 6, 2655, 480 + 48 * 6))
    # One printed line the OCR cut in two, the second piece a few pixels higher.
    lines.append(Line("left line 6 first half", 240, 440 + 48 * 6 + 4, 800, 480 + 48 * 6))
    lines.append(Line("and its second half", 820, 440 + 48 * 6 - 3, 1430, 480 + 48 * 6))
    kept = [ln.text for ln in TwoColumn().reading_order(Page(0, 2900, 4400, lines))]
    assert kept[:2] == ["ROMAN CATHOLIC CHURCH.", "689"]
    assert kept[2:10] == [f"left column line {k} of running text here" for k in range(6)] \
        + ["left line 6 first half", "and its second half"]
    assert kept[10:] == [f"right column line {k} of running text here" for k in range(6)] \
        + ["- anew right column line 6 of text"]
