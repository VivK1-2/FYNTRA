import json
from pathlib import Path

from app.services.evalkit import score_item, summarize


def ans(text, cites=1, page=5, passage=""):
    return {"status": "answered", "answer": text, "latency_ms": 1000,
            "citations": [{"n": 1, "page_start": page, "page_end": page, "passage": passage or text}] * cites}


FACT = {"id": "f", "type": "fact", "question": "q", "expect": [["391,035", "391035"]]}


def test_fact_pass_normalises_commas_and_dollars():
    assert score_item(FACT, ans("Net sales were $391035 million [1]."))["passed"]


def test_fact_wrong_number_fails_and_is_counted_as_wrong():
    r = score_item(FACT, ans("Net sales were $390,000 million [1]."))
    assert not r["passed"] and r["answer_correct"] is False


def test_correct_number_without_citation_fails():
    r = score_item(FACT, ans("391,035", cites=0))
    assert not r["passed"] and r["note"] == "no citation"


def test_page_check_when_expected_pages_given():
    item = {**FACT, "expect_pages": [28]}
    assert not score_item(item, ans("391,035", page=5))["passed"]
    assert score_item(item, ans("391,035", page=28))["passed"]


def test_unanswerable_must_refuse():
    u = {"id": "u", "type": "unanswerable", "question": "q"}
    assert score_item(u, {"status": "insufficient_evidence"})["passed"]
    assert not score_item(u, ans("made up"))["passed"]


def test_comparison_needs_every_company_right():
    item = {"id": "c", "type": "comparison", "question": "q", "expect": {"AAPL": [["164,000"]], "MSFT": [["228,000"]]}}
    ok = {"companies": [{"ticker": "AAPL", "result": ans("164,000")}, {"ticker": "MSFT", "result": ans("228,000")}]}
    bad = {"companies": [{"ticker": "AAPL", "result": ans("164,000")}, {"ticker": "MSFT", "result": ans("100")}]}
    assert score_item(item, ok)["passed"] and not score_item(item, bad)["passed"]


def test_summary_rates():
    rs = [score_item(FACT, ans("391,035")), score_item(FACT, ans("nope")),
          score_item({"id": "u", "type": "unanswerable", "question": "q"}, {"status": "insufficient_evidence"})]
    s = summarize(rs)
    assert s["answer_accuracy_pct"] == 50.0 and s["correct_refusal_pct"] == 100.0 and s["answered_but_wrong"] == 1


def test_question_file_is_well_formed():
    doc = json.loads((Path(__file__).parents[1] / "eval" / "questions.json").read_text())
    qs = doc["questions"]
    assert len(qs) >= 25 and len({q["id"] for q in qs}) == len(qs)
    for q in qs:
        assert q["type"] in {"fact", "narrative", "unanswerable", "comparison"}
        assert q["type"] == "unanswerable" or q.get("expect")
        for t in q.get("tickers") or [q.get("ticker")]:
            assert t in doc["reports"]
