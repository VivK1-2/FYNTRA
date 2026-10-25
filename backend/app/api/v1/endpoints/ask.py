import asyncio
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import logging

from app.core.exceptions import FilingNotFoundError
from app.models.ask_log import AskLog
from app.db.session import get_db
from app.llm.gateway import LLMError, LLMUnavailableError, gateway
from app.services.company_service import get_or_resolve_company
from app.services.documents.search import search_chunks
from app.services.qa import build_messages, passage_text, verify
from app.api.v1.endpoints.documents import _find_filing

router = APIRouter()
compare_router = APIRouter()
logger = logging.getLogger(__name__)


async def _log(db: AsyncSession, company, question: str, status: str, reason=None, model=None, latency=None, cites=0, dropped=0):
    """Best effort: logging must never break an answer."""
    try:
        db.add(AskLog(company_id=company.id, ticker=company.ticker, question=question[:500], status=status, reason=(reason or None) and str(reason)[:200],
                      model=model, latency_ms=latency, citation_count=cites, dropped_sentences=dropped))
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.warning("could not write ask log")

PASSAGES = 6


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    accession: Optional[str] = Field(None, description="Limit to one filing")


class Citation(BaseModel):
    n: int
    quote: str
    accession_number: Optional[str] = None
    form: str
    filing_date: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    section: Optional[str] = None
    document_url: Optional[str] = None
    passage: str


class AskResponse(BaseModel):
    question: str
    status: str  # answered | insufficient_evidence
    answer: Optional[str] = None
    reason: Optional[str] = None
    citations: List[Citation] = []
    dropped_sentences: int = 0
    passages_considered: int = 0
    latency_ms: Optional[int] = None


async def _hits(db: AsyncSession, company, req_q: str, accession: Optional[str]):
    filing_ids = None
    if accession:
        filing = await _find_filing(db, company.id, accession)
        if filing is None:
            raise FilingNotFoundError(accession)
        filing_ids = [filing.id]
    return await search_chunks(db, company.id, req_q, limit=PASSAGES, filing_ids=filing_ids)


async def _llm(question: str, hits):
    return await gateway.complete_json(
        build_messages(question, hits),
        required_keys=["answer", "enough_evidence"],
        max_tokens=2500,
    )


def _build(question: str, parsed: Dict[str, Any], res, hits):
    v = verify(parsed, hits)
    cites = []
    for c in v.citations:
        h = hits[c["n"] - 1]
        cites.append(Citation(
            n=c["n"], quote=c["quote"], accession_number=h.accession_number, form=h.form,
            filing_date=h.filing_date, page_start=h.page_start, page_end=h.page_end,
            section=h.section, document_url=h.document_url, passage=passage_text(h),
        ))
    resp = AskResponse(
        question=question, status=v.status, answer=v.answer, reason=v.reason, citations=cites,
        dropped_sentences=v.dropped_sentences, passages_considered=len(hits),
        latency_ms=res.latency_ms,
    )
    return resp, v


@router.post("/{identifier}/ask", response_model=AskResponse)
async def ask(identifier: str, req: AskRequest, db: AsyncSession = Depends(get_db)):
    """Answer from the company's ingested reports. Every sentence is checked against its cited passage."""
    company = await get_or_resolve_company(db, identifier)
    hits = await _hits(db, company, req.question, req.accession)
    if not hits:
        await _log(db, company, req.question, "insufficient_evidence", "no_matching_passages")
        return AskResponse(question=req.question, status="insufficient_evidence", reason="no_matching_passages")

    try:
        parsed, res = await _llm(req.question, hits)
    except LLMUnavailableError as e:
        await _log(db, company, req.question, "error", str(e))
        raise HTTPException(status_code=503, detail="The AI model is unavailable right now. Please try again shortly.")
    except LLMError as e:
        await _log(db, company, req.question, "error", str(e))
        raise HTTPException(status_code=502, detail="The AI model could not answer. Please try again.")

    resp, v = _build(req.question, parsed, res, hits)
    await _log(db, company, req.question, v.status, v.reason, res.model_name, res.latency_ms, len(resp.citations), v.dropped_sentences)
    return resp


class CompareAskRequest(BaseModel):
    tickers: List[str] = Field(..., min_length=2, max_length=3)
    question: str = Field(..., min_length=3, max_length=500)
    accessions: Optional[Dict[str, str]] = Field(None, description="Optional ticker -> accession to pin one report per company")


class CompareAskItem(BaseModel):
    ticker: str
    name: Optional[str] = None
    result: Optional[AskResponse] = None
    error: Optional[str] = None


class CompareAskResponse(BaseModel):
    question: str
    companies: List[CompareAskItem]


@compare_router.post("/ask", response_model=CompareAskResponse)
async def compare_ask(req: CompareAskRequest, db: AsyncSession = Depends(get_db)):
    """The same question put to each company's own reports. Each answer is verified and cited independently."""
    tickers = list(dict.fromkeys(t.upper().strip() for t in req.tickers if t.strip()))
    if len(tickers) < 2:
        raise HTTPException(status_code=422, detail="Give at least two different tickers.")
    items: List[CompareAskItem] = []
    pending: List[Tuple[int, Any, Any]] = []  # (index, company, hits)
    for t in tickers:
        try:
            company = await get_or_resolve_company(db, t)
        except Exception as e:  # noqa: BLE001 - one unknown ticker should not sink the others
            items.append(CompareAskItem(ticker=t, error=getattr(e, "message", None) or "Company could not be resolved."))
            continue
        item = CompareAskItem(ticker=company.ticker or t, name=company.name)
        items.append(item)
        hits = await _hits(db, company, req.question, (req.accessions or {}).get(t))
        if not hits:
            item.result = AskResponse(question=req.question, status="insufficient_evidence", reason="no_matching_passages")
            await _log(db, company, req.question, "insufficient_evidence", "no_matching_passages")
        else:
            pending.append((len(items) - 1, company, hits))

    outcomes = await asyncio.gather(*[_llm(req.question, h) for _, _, h in pending], return_exceptions=True)
    for (idx, company, hits), out in zip(pending, outcomes):
        if isinstance(out, Exception):
            items[idx].error = "The AI model is unavailable right now." if isinstance(out, LLMUnavailableError) else "The AI model failed to answer."
            await _log(db, company, req.question, "error", str(out))
            continue
        parsed, res = out
        resp, v = _build(req.question, parsed, res, hits)
        items[idx].result = resp
        await _log(db, company, req.question, v.status, v.reason, res.model_name, res.latency_ms, len(resp.citations), v.dropped_sentences)
    return CompareAskResponse(question=req.question, companies=items)
