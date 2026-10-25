"""Scoring for the question-set evaluation (see scripts/eval_qa.py). Pure functions, no network."""
import re
from typing import Any, Dict, List

ANSWER_TYPES = ("fact", "narrative", "comparison")


def norm(s: str) -> str:
    s = (s or "").lower().replace(",", "").replace("$", "")
    return re.sub(r"\s+", " ", s).strip()


def _hit(answer: str, groups: List[List[str]]) -> bool:
    """Every group needs at least one of its alternatives to appear in the answer."""
    a = norm(answer)
    return bool(groups) and all(any(norm(alt) in a for alt in g) for g in groups)


def _score_one(expect: List[List[str]], resp: Dict[str, Any], expect_pages: List[int] | None) -> Dict[str, Any]:
    status = resp.get("status")
    cites = resp.get("citations") or []
    out = {
        "status": status, "latency_ms": resp.get("latency_ms"), "has_citation": bool(cites),
        "citations": len(cites), "citations_with_page": sum(1 for c in cites if c.get("page_start") is not None),
    }
    if status != "answered":
        out.update(passed=False, note=f"no answer ({resp.get('reason') or status})")
        return out
    right = _hit(resp.get("answer") or "", expect)
    out["answer_correct"] = right
    cited_text = " ".join(c.get("passage", "") for c in cites)
    out["supported_by_cited_text"] = _hit(cited_text, expect)  # the expected figure really is on a cited page
    page_ok = True
    if expect_pages:
        page_ok = any(c.get("page_start") in expect_pages or c.get("page_end") in expect_pages for c in cites)
        out["page_correct"] = page_ok
    out["passed"] = bool(right and cites and page_ok)
    out["note"] = "" if out["passed"] else ("wrong or missing figure" if not right else "no citation" if not cites else "wrong page")
    return out


def score_item(item: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """payload: AskResponse json, or CompareAskResponse json for comparison items."""
    kind = item["type"]
    base = {"id": item["id"], "type": kind, "question": item["question"]}
    if kind == "unanswerable":
        refused = payload.get("status") == "insufficient_evidence"
        return {**base, "passed": refused, "status": payload.get("status"), "latency_ms": payload.get("latency_ms"),
                "note": "" if refused else "answered a question the reports cannot answer"}
    if kind == "comparison":
        parts = {}
        for c in payload.get("companies") or []:
            r = c.get("result")
            exp = (item.get("expect") or {}).get(c.get("ticker"))
            parts[c.get("ticker")] = _score_one(exp or [], r, None) if r else {"passed": False, "note": c.get("error") or "no result", "status": "error"}
        for t in (item.get("expect") or {}):
            parts.setdefault(t, {"passed": False, "note": "company missing from response", "status": "error"})
        lat = [p.get("latency_ms") or 0 for p in parts.values()]
        return {**base, "passed": all(p["passed"] for p in parts.values()) and bool(parts), "parts": parts,
                "latency_ms": max(lat) if lat else None,
                "note": "; ".join(f"{t}: {p['note']}" for t, p in parts.items() if not p["passed"])}
    return {**base, **_score_one(item.get("expect") or [], payload, item.get("expect_pages"))}


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    def rate(n: int, d: int):
        return round(100 * n / d, 1) if d else None
    ans = [r for r in results if r["type"] in ANSWER_TYPES]
    unans = [r for r in results if r["type"] == "unanswerable"]
    singles = []
    for r in ans:
        singles += list(r["parts"].values()) if r["type"] == "comparison" else [r]
    answered = [s for s in singles if s.get("status") == "answered"]
    cites = sum(s.get("citations", 0) for s in answered)
    lats = [r["latency_ms"] for r in results if r.get("latency_ms")]
    by_type = {}
    for t in ANSWER_TYPES + ("unanswerable",):
        rows = [r for r in results if r["type"] == t]
        if rows:
            by_type[t] = {"total": len(rows), "passed": sum(r["passed"] for r in rows), "pct": rate(sum(r["passed"] for r in rows), len(rows))}
    return {
        "total": len(results),
        "answer_accuracy_pct": rate(sum(r["passed"] for r in ans), len(ans)),
        "correct_refusal_pct": rate(sum(r["passed"] for r in unans), len(unans)),
        "false_answer_pct": rate(sum(not r["passed"] for r in unans), len(unans)),
        "answers_with_citation_pct": rate(sum(1 for s in answered if s.get("has_citation")), len(answered)),
        "citations_with_page_pct": rate(sum(s.get("citations_with_page", 0) for s in answered), cites),
        "answered_but_wrong": sum(1 for s in answered if s.get("answer_correct") is False),
        "avg_latency_s": round(sum(lats) / len(lats) / 1000, 1) if lats else None,
        "by_type": by_type,
    }
