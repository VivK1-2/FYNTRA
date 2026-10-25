import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.documents import get_session_factory
from app.core import ratelimit, runtime
from app.core.config import settings
from app.core.exceptions import AppError
from app.db.session import get_db
from app.models.ask_log import AskLog
from app.models.company import Company
from app.models.filing import PROCESSING, DocumentChunk, Filing
from app.providers.market import service as market_service
from app.providers.sec import client as sec_client
from app.services import xbrl as xbrl_service
from app.services.documents.ingest import run_ingest


async def require_admin(request: Request, x_admin_key: Optional[str] = Header(None)) -> None:
    """Separate key from the app's API key. Wrong guesses are throttled per IP."""
    if not settings.ADMIN_KEY:
        raise HTTPException(status_code=503, detail="Admin panel is disabled. Set ADMIN_KEY in the backend .env and restart.")
    ok = bool(x_admin_key) and secrets.compare_digest(x_admin_key.encode(), settings.ADMIN_KEY.encode())
    if not ok:
        wait = ratelimit._check(f"adminfail:{ratelimit._client_ip(request)}", 10, time.monotonic())
        if wait is not None:
            raise HTTPException(status_code=429, detail=f"Too many wrong attempts. Try again in {wait} seconds.")
        raise HTTPException(status_code=401, detail="Wrong admin key.")


router = APIRouter(dependencies=[Depends(require_admin)])


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False

    async def count(model) -> int:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()

    by_status = dict((await db.execute(select(Filing.processing_status, func.count()).group_by(Filing.processing_status))).all())
    asks_by_status = dict((await db.execute(select(AskLog.status, func.count()).group_by(AskLog.status))).all())
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    asks_24h = (await db.execute(select(func.count()).select_from(AskLog).where(AskLog.created_at >= day_ago))).scalar_one()

    return {
        "status": "healthy" if db_ok else "degraded",
        "database_ok": db_ok,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": int(time.time() - runtime.STARTED_AT),
        "counts": {
            "companies": await count(Company),
            "filings": await count(Filing),
            "filings_by_status": by_status,
            "passages": await count(DocumentChunk),
            "questions": await count(AskLog),
            "questions_24h": asks_24h,
            "questions_by_status": asks_by_status,
        },
        "storage_bytes": _dir_size(Path(settings.STORAGE_DIR)),
        "limits": {"per_minute": settings.RATE_LIMIT_PER_MINUTE, "llm_per_minute": settings.RATE_LIMIT_LLM_PER_MINUTE},
        "caches": {
            "market": len(market_service._cache),
            "sec_facts": len(sec_client._facts_cache),
            "xbrl_documents": xbrl_service.cache_size(),
        },
    }


@router.get("/filings")
async def list_filings(
    status: Optional[str] = Query(None, pattern="^(pending|processing|processed|failed|needs_ocr)$"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    chunk_counts = select(DocumentChunk.filing_id, func.count().label("n")).group_by(DocumentChunk.filing_id).subquery()
    stmt = (
        select(Filing, Company.ticker, Company.name, func.coalesce(chunk_counts.c.n, 0))
        .join(Company, Company.id == Filing.company_id)
        .outerjoin(chunk_counts, chunk_counts.c.filing_id == Filing.id)
        .order_by(Filing.id.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Filing.processing_status == status)
    rows = (await db.execute(stmt)).all()
    out = []
    for f, ticker, name, n in rows:
        p = Path(f.local_storage_path) if f.local_storage_path else None
        out.append({
            "id": f.id, "ticker": ticker, "company": name, "provider": f.provider, "form": f.filing_type,
            "accession_number": f.accession_number, "fiscal_year": f.fiscal_year,
            "filing_date": f.filing_date.isoformat() if f.filing_date else None,
            "status": f.processing_status, "error": f.error_message, "pages": f.page_count, "passages": n,
            "file_bytes": p.stat().st_size if p and p.exists() else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        })
    return out


@router.post("/filings/{filing_id}/reingest", status_code=202)
async def reingest(
    filing_id: int,
    background: BackgroundTasks,
    redownload: bool = Query(False, description="Also fetch the original file again"),
    db: AsyncSession = Depends(get_db),
    session_factory=Depends(get_session_factory),
) -> Dict[str, Any]:
    filing = await db.get(Filing, filing_id)
    if filing is None:
        raise AppError("FILING_NOT_FOUND", "No such filing.", 404)
    company = await db.get(Company, filing.company_id)
    if redownload:
        filing.local_storage_path = None
    filing.processing_status = PROCESSING
    filing.error_message = None
    await db.commit()
    background.add_task(run_ingest, filing.id, (company.ticker if company else None) or str(filing.id), session_factory)
    return {"id": filing.id, "status": filing.processing_status}


@router.delete("/filings/{filing_id}")
async def delete_filing(filing_id: int, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Removes the filing, its searchable passages and the stored original file."""
    filing = await db.get(Filing, filing_id)
    if filing is None:
        raise AppError("FILING_NOT_FOUND", "No such filing.", 404)
    removed_file = False
    if filing.local_storage_path:
        p = Path(filing.local_storage_path).resolve()
        root = Path(settings.STORAGE_DIR).resolve()
        if p.is_relative_to(root) and p.is_file():
            p.unlink()
            removed_file = True
    await db.execute(delete(DocumentChunk).where(DocumentChunk.filing_id == filing.id))
    await db.delete(filing)
    await db.commit()
    return {"deleted": filing_id, "file_removed": removed_file}


@router.get("/asks")
async def recent_asks(limit: int = Query(50, ge=1, le=300), db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(AskLog).order_by(AskLog.id.desc()).limit(limit))).scalars().all()
    return [{
        "id": r.id, "ticker": r.ticker, "question": r.question, "status": r.status, "reason": r.reason,
        "latency_ms": r.latency_ms, "citations": r.citation_count,
        "dropped_sentences": r.dropped_sentences, "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.post("/cache/clear")
async def clear_caches() -> Dict[str, int]:
    market = len(market_service._cache)
    market_service._cache.clear()
    facts = len(sec_client._facts_cache)
    sec_client._facts_cache.clear()
    return {"market": market, "sec_facts": facts, "xbrl_documents": xbrl_service.clear_cache()}
