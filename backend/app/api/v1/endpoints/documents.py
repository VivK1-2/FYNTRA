from datetime import date
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import FilingNotFoundError, NotSupportedError
from app.db.session import AsyncSessionLocal, get_db
from app.models.filing import PROCESSING, DocumentChunk, Filing
from app.providers.india.nse.provider import NSEProvider
from app.providers.sec.provider import SECProvider
from app.services.company_service import get_or_resolve_company
from app.services.documents.ingest import needs_work, run_ingest
from app.services.documents.search import search_chunks

router = APIRouter()


def get_session_factory():
    """Overridable in tests; background jobs need their own DB sessions."""
    return AsyncSessionLocal


class IngestStatus(BaseModel):
    accession_number: str
    status: str
    page_count: Optional[int] = None
    chunk_count: int = 0
    has_page_numbers: bool = False
    needs_ocr: bool = False
    error: Optional[str] = None
    document_url: Optional[str] = None


class SearchHit(BaseModel):
    chunk_id: int
    accession_number: Optional[str]
    form: str
    filing_date: Optional[str]
    document_url: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    section: Optional[str]
    text: str
    score: float


async def _status(db: AsyncSession, filing: Filing) -> IngestStatus:
    count = (
        await db.execute(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.filing_id == filing.id))
    ).scalar_one()
    return IngestStatus(
        accession_number=filing.accession_number or "",
        status=filing.processing_status,
        page_count=filing.page_count,
        chunk_count=count,
        has_page_numbers=bool(filing.has_page_numbers),
        needs_ocr=bool(filing.needs_ocr),
        error=filing.error_message,
        document_url=filing.document_url,
    )


async def _find_filing(db: AsyncSession, company_id: int, accession: str) -> Optional[Filing]:
    return (
        await db.execute(
            select(Filing).where(
                Filing.company_id == company_id,
                Filing.accession_number == accession,
            )
        )
    ).scalars().first()


@router.post("/{identifier}/filings/{accession}/ingest", response_model=IngestStatus, status_code=202)
async def ingest_filing(
    identifier: str,
    accession: str,
    background: BackgroundTasks,
    response: Response,
    db: AsyncSession = Depends(get_db),
    session_factory=Depends(get_session_factory),
):
    """Start (or reuse) download + parse + indexing of one filing. Poll the /status endpoint."""
    company = await get_or_resolve_company(db, identifier)
    if company.country not in ("USA", "India"):
        raise NotSupportedError("Report ingestion is available for US and NSE-listed companies.")

    filing = await _find_filing(db, company.id, accession)
    if filing is None:
        # Only accept accessions that the SEC itself lists for this company.
        provider = NSEProvider() if company.country == "India" else SECProvider()
        found = await provider.find_filings(company, form="10-K", limit=40)
        meta = next((f for f in found if f["accession_number"] == accession), None)
        if meta is None:
            raise FilingNotFoundError(accession)
        report = meta.get("report_date")
        filed = meta.get("filing_date")
        filing = Filing(
            company_id=company.id,
            provider=meta["provider"],
            filing_type=meta["form"],
            accession_number=accession,
            fiscal_period="FY",
            filing_date=date.fromisoformat(filed) if filed else None,
            period_end=date.fromisoformat(report) if report else None,
            fiscal_year=meta.get("fiscal_year") or (int(report[:4]) if report else None),
            source_url=meta["index_url"],
            document_url=meta["document_url"],
        )
        db.add(filing)
        await db.commit()
        await db.refresh(filing)

    if needs_work(filing):
        filing.processing_status = PROCESSING  # claim it so duplicate requests do not start a second job
        await db.commit()
        background.add_task(run_ingest, filing.id, company.ticker or identifier, session_factory)
    else:
        response.status_code = 200
    return await _status(db, filing)


@router.get("/{identifier}/filings/status", response_model=dict[str, IngestStatus])
async def ingest_statuses(identifier: str, db: AsyncSession = Depends(get_db)):
    """Status of every filing already downloaded for this company, keyed by accession (empty if none)."""
    company = await get_or_resolve_company(db, identifier)
    filings = (await db.execute(select(Filing).where(Filing.company_id == company.id))).scalars().all()
    return {f.accession_number: await _status(db, f) for f in filings if f.accession_number}


@router.get("/{identifier}/filings/{accession}/status", response_model=IngestStatus)
async def ingest_status(identifier: str, accession: str, db: AsyncSession = Depends(get_db)):
    company = await get_or_resolve_company(db, identifier)
    filing = await _find_filing(db, company.id, accession)
    if filing is None:
        raise FilingNotFoundError(accession)
    return await _status(db, filing)


@router.get("/{identifier}/search", response_model=List[SearchHit])
async def search_company_documents(
    identifier: str,
    q: str = Query(..., min_length=2, max_length=300),
    accession: Optional[str] = None,
    limit: int = Query(8, ge=1, le=25),
    db: AsyncSession = Depends(get_db),
):
    """Passages (with page/section) from this company's ingested reports that match the query."""
    company = await get_or_resolve_company(db, identifier)
    filing_ids = None
    if accession:
        filing = await _find_filing(db, company.id, accession)
        if filing is None:
            raise FilingNotFoundError(accession)
        filing_ids = [filing.id]
    hits = await search_chunks(db, company.id, q, limit=limit, filing_ids=filing_ids)
    return [SearchHit(**{**h.__dict__, "text": h.text[:4000]}) for h in hits]
