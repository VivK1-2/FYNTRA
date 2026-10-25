#!/usr/bin/env python3
"""Run the question set against a running FYNTRA backend and report accuracy.

    python scripts/eval_qa.py --prepare            # download + index the reports first (slow, once)
    python scripts/eval_qa.py                      # just run the questions
Needs the backend running. API key: --key, or FYNTRA_API_KEY / API_KEY in the environment ("disabled" if auth is off).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.evalkit import score_item, summarize  # noqa: E402


def pin_reports(c: httpx.Client, reports: dict, prepare: bool) -> dict:
    pinned = {}
    for ticker, spec in reports.items():
        rows = c.get(f"/api/v1/company/{ticker}/filings", params={"limit": 10}).json()
        match = next((r for r in rows if r.get("filing_date") == spec["filed"]), None)
        if not match:
            print(f"  ! {ticker}: no 10-K filed {spec['filed']} found. Questions for it will be skipped.")
            continue
        acc = match["accession_number"]
        st = c.get(f"/api/v1/company/{ticker}/filings/{acc}/status").json() if not prepare else None
        if prepare or (st and st["status"] != "processed"):
            print(f"  preparing {ticker} {acc} ...", flush=True)
            st = c.post(f"/api/v1/company/{ticker}/filings/{acc}/ingest").json()
            for _ in range(180):
                if st["status"] not in ("pending", "processing"):
                    break
                time.sleep(2)
                st = c.get(f"/api/v1/company/{ticker}/filings/{acc}/status").json()
        if st and st["status"] == "processed":
            pinned[ticker] = acc
        else:
            print(f"  ! {ticker}: report not searchable (status {st and st['status']}). Run with --prepare.")
    return pinned


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--questions", default=str(Path(__file__).resolve().parents[1] / "eval" / "questions.json"))
    ap.add_argument("--key", default=os.environ.get("FYNTRA_API_KEY") or os.environ.get("API_KEY") or "disabled")
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between questions (stay under the rate limit)")
    a = ap.parse_args()

    doc = json.loads(Path(a.questions).read_text())
    c = httpx.Client(base_url=a.base, headers={"X-API-Key": a.key}, timeout=120.0)
    try:
        c.get("/health").raise_for_status()
    except httpx.HTTPError:
        print("Backend is not reachable. Start it first.")
        return 2
    print("Checking reports")
    pinned = pin_reports(c, doc["reports"], a.prepare)

    results = []
    for item in doc["questions"]:
        tickers = item.get("tickers") or [item["ticker"]]
        if any(t not in pinned for t in tickers):
            print(f"  skip {item['id']} (report not ready)")
            continue
        try:
            if item["type"] == "comparison":
                r = c.post("/api/v1/compare/ask", json={"tickers": tickers, "question": item["question"],
                                                         "accessions": {t: pinned[t] for t in tickers}})
            else:
                r = c.post(f"/api/v1/company/{item['ticker']}/ask", json={"question": item["question"], "accession": pinned[item["ticker"]]})
            if r.status_code == 429:
                time.sleep(30)
                continue
            payload = r.json() if r.status_code == 200 else {"status": "error", "reason": f"HTTP {r.status_code}"}
        except httpx.HTTPError as e:
            payload = {"status": "error", "reason": type(e).__name__}
        res = score_item(item, payload)
        results.append(res)
        print(f"  {'PASS' if res['passed'] else 'FAIL'}  {item['id']:<4} {item['question'][:60]}  {res.get('note','')}", flush=True)
        time.sleep(a.pause)

    if not results:
        print("Nothing was run.")
        return 1
    s = summarize(results)
    out = Path(__file__).resolve().parents[1] / "eval" / "results"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / f"{stamp}.json").write_text(json.dumps({"summary": s, "results": results}, indent=1))
    lines = [f"# Evaluation {stamp}", "", f"Questions run: {s['total']}", "",
             "| Measure | Result |", "|---|---|",
             f"| Answer accuracy (right figure, cited) | {s['answer_accuracy_pct']}% |",
             f"| Correct 'not found' on unanswerable questions | {s['correct_refusal_pct']}% |",
             f"| Answers that invented something for an unanswerable question | {s['false_answer_pct']}% |",
             f"| Answers with at least one citation | {s['answers_with_citation_pct']}% |",
             f"| Citations that carry a page number | {s['citations_with_page_pct']}% |",
             f"| Answered but wrong | {s['answered_but_wrong']} |",
             f"| Average time per question | {s['avg_latency_s']} s |", "", "| Type | Passed | Total |", "|---|---|---|"]
    lines += [f"| {t} | {v['passed']} | {v['total']} |" for t, v in s["by_type"].items()]
    lines += ["", "## Failures", ""] + [f"- **{r['id']}** {r['question']} ({r.get('note','')})" for r in results if not r["passed"]]
    (out / f"{stamp}.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines[:16]))
    print(f"\nSaved to eval/results/{stamp}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
