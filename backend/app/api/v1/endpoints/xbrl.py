import asyncio
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.documents import _find_filing
from app.core.config import settings
from app.core.exceptions import AppError, FilingNotFoundError
from app.db.session import get_db
from app.providers.india.nse.provider import NSEProvider
from app.services.documents.downloader import DownloadError, download_document, validate_url
from app.services.company_service import get_or_resolve_company
from app.services.xbrl import fact_to_dict, filter_facts, load_doc

router = APIRouter()


@router.get("/{identifier}/filings/{accession}/xbrl")
async def filing_xbrl(
    identifier: str,
    accession: str,
    q: Optional[str] = Query(None, max_length=100, description="Filter by concept name"),
    dimensional: bool = Query(False, description="Include facts broken down by segment, product, etc."),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Every number the filer tagged in the filing (inline XBRL), with period, unit and dimensions."""
    company = await get_or_resolve_company(db, identifier)
    filing = await _find_filing(db, company.id, accession)
    if filing is None:
        raise FilingNotFoundError(accession)
    if filing.provider != "sec":
        raise AppError("NO_XBRL", "XBRL tags are only available in SEC HTML filings.", 422)
    if "pdf" in (filing.mime_type or ""):
        raise AppError("NO_XBRL", "This filing is a PDF, so it has no XBRL tags.", 422)

    path = Path(filing.local_storage_path) if filing.local_storage_path else None
    root = Path(settings.STORAGE_DIR).resolve()
    if path is None or not path.exists() or not path.resolve().is_relative_to(root):
        # The database remembers the report, but its file is not in the current storage folder
        # (moved, deleted or saved under an older setting). Fetch it again from the official source.
        if not filing.document_url:
            raise AppError("NOT_DOWNLOADED", "The original file is missing and has no source address.", 409)
        try:
            dl = await download_document(filing.document_url, company.ticker, filing.accession_number or str(filing.id),
                                         headers={"User-Agent": settings.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"})
        except DownloadError as e:
            raise AppError("NOT_DOWNLOADED", f"The saved file was missing and could not be downloaded again: {e}", 409)
        filing.local_storage_path = str(dl.path)
        filing.document_hash = dl.sha256
        filing.mime_type = dl.mime
        await db.commit()
        path = dl.path

    doc = await asyncio.to_thread(load_doc, path)
    matched = filter_facts(doc, q, dimensional)
    return {
        "accession_number": accession,
        "has_xbrl": bool(doc.facts),
        "document": doc.document,
        "total_facts": len(doc.facts),
        "matched": len(matched),
        "offset": offset,
        "facts": [fact_to_dict(f) for f in matched[offset: offset + limit]],
    }


NSE_XBRL_MAX = 30 * 1024 * 1024


@router.get("/{identifier}/xbrl-filings")
async def india_xbrl_filings(identifier: str, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Indian companies: results filings (annual and quarterly) that have an XBRL file on NSE."""
    company = await get_or_resolve_company(db, identifier)
    if company.country != "India":
        raise AppError("NOT_INDIA", "This list is for NSE-listed companies. US filings use the filings tab.", 422)
    items = await NSEProvider().find_xbrl_filings(company)
    return {"ticker": company.ticker, "filings": items}


async def _fetch_nse_xbrl(url: str) -> Path:
    try:
        validate_url(url)
    except DownloadError as e:
        raise AppError("BAD_URL", str(e), 422)
    if not url.lower().endswith(".xml"):
        raise AppError("BAD_URL", "Expected an NSE XBRL (.xml) link.", 422)
    root = Path(settings.STORAGE_DIR).resolve() / "_nse_xbrl"
    target = root / (hashlib.sha1(url.encode()).hexdigest() + ".xml")
    if target.exists():
        return target
    root.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
               "Referer": "https://www.nseindia.com/"}
    current = url
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=False) as client:
            for _ in range(4):
                validate_url(current)
                resp = await client.get(current, headers=headers)
                if resp.status_code in (301, 302, 303, 307, 308):
                    current = str(httpx.URL(current).join(resp.headers.get("location", "")))
                    continue
                if resp.status_code != 200:
                    raise AppError("DOWNLOAD_FAILED", f"NSE returned HTTP {resp.status_code} for this file.", 502)
                if len(resp.content) > NSE_XBRL_MAX:
                    raise AppError("TOO_LARGE", "The XBRL file is unexpectedly large.", 422)
                if b"xbrl" not in resp.content[:4096].lower():
                    raise AppError("NO_XBRL", "That link did not return an XBRL file.", 422)
                tmp = target.with_suffix(".part")
                tmp.write_bytes(resp.content)
                tmp.replace(target)
                return target
    except DownloadError as e:
        raise AppError("BAD_URL", str(e), 422)
    except httpx.RequestError:
        raise AppError("DOWNLOAD_FAILED", "Could not reach NSE to download the XBRL file.", 502)
    raise AppError("DOWNLOAD_FAILED", "Too many redirects.", 502)


@router.get("/{identifier}/xbrl-facts")
async def india_xbrl_facts(
    identifier: str,
    url: str = Query(..., max_length=500),
    q: Optional[str] = Query(None, max_length=100),
    dimensional: bool = Query(False),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Downloads one NSE XBRL file (host-restricted) and returns its facts in the same shape as the SEC endpoint."""
    await get_or_resolve_company(db, identifier)
    path = await _fetch_nse_xbrl(url)
    doc = await asyncio.to_thread(load_doc, path)
    matched = filter_facts(doc, q, dimensional)
    return {
        "accession_number": url.rsplit("/", 1)[-1], "has_xbrl": bool(doc.facts), "document": doc.document,
        "total_facts": len(doc.facts), "matched": len(matched), "offset": offset,
        "facts": [fact_to_dict(f) for f in matched[offset: offset + limit]],
    }
