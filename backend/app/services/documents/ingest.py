"""
Ingest one filing: download -> extract -> chunk -> store. Idempotent and crash-safe.

- A filing already "processed" with the same extraction version is left alone.
- A filing stuck in "processing" longer than STALE_AFTER is treated as crashed and can be retried.
- Original files are never re-downloaded when the stored copy still exists.
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.filing import (
    FAILED,
    NEEDS_OCR,
    PENDING,
    PROCESSED,
    PROCESSING,
    DocumentChunk,
    Filing,
)
from app.services.documents.chunker import chunk_pages
from app.services.documents.downloader import DownloadError, download_document, sniff_mime
from app.services.documents.extractor import EXTRACTION_VERSION, ExtractionError, extract

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=15)

SessionFactory = Callable[[], AsyncSession]


def needs_work(filing: Filing) -> bool:
    """Should an ingest request start a new job for this filing?"""
    if filing.processing_status in (PENDING, FAILED):
        return True
    if filing.processing_status == PROCESSING:
        updated = filing.updated_at
        if updated is None:
            return True
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - updated > STALE_AFTER
    if filing.processing_status in (PROCESSED, NEEDS_OCR):
        return filing.extraction_version != EXTRACTION_VERSION
    return True


def _browser_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Referer": "https://www.nseindia.com/",
    }


def _sec_headers() -> dict:
    return {"User-Agent": settings.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}


async def run_ingest(filing_id: int, ticker: str, session_factory: Optional[SessionFactory] = None) -> None:
    """Background job entry point. Opens its own DB session (the request session is long gone)."""
    factory = session_factory or AsyncSessionLocal
    async with factory() as db:
        filing = await db.get(Filing, filing_id)
        if filing is None:
            logger.error("ingest: filing %s vanished", filing_id)
            return
        try:
            await _ingest(db, filing, ticker)
        except (DownloadError, ExtractionError) as e:
            await _fail(db, filing, str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("ingest crashed for filing %s", filing_id)
            detail = f"{type(e).__name__}: {e}"[:300] if isinstance(e, OSError) else type(e).__name__
            await _fail(db, filing, f"Unexpected error: {detail}")


async def _fail(db: AsyncSession, filing: Filing, message: str) -> None:
    await db.rollback()
    filing = await db.get(Filing, filing.id)
    filing.processing_status = FAILED
    filing.error_message = message[:500]
    await db.commit()
    logger.warning("ingest failed for filing %s: %s", filing.id, message)


async def _ingest(db: AsyncSession, filing: Filing, ticker: str) -> None:
    filing.processing_status = PROCESSING
    filing.error_message = None
    await db.commit()

    # 1. Original file: reuse the stored copy if it is still on disk
    path: Optional[Path] = Path(filing.local_storage_path) if filing.local_storage_path else None
    if path and path.exists():
        mime = filing.mime_type or sniff_mime(path.read_bytes()[:4096]) or "text/html"
    else:
        if not filing.document_url:
            raise DownloadError("Filing has no document URL")
        headers = _sec_headers() if filing.provider == "sec" else _browser_headers()
        dl = await download_document(
            filing.document_url, ticker, filing.accession_number or str(filing.id), headers=headers
        )
        path, mime = dl.path, dl.mime
        filing.local_storage_path = str(dl.path)
        filing.document_hash = dl.sha256
        filing.mime_type = dl.mime
        await db.commit()

    # 2. Extract text with page info (CPU-bound: keep it off the event loop)
    import asyncio

    extracted = await asyncio.to_thread(extract, path, mime)
    filing.page_count = extracted.page_count
    filing.has_page_numbers = extracted.has_page_numbers
    filing.needs_ocr = extracted.needs_ocr
    filing.extraction_version = EXTRACTION_VERSION

    if extracted.needs_ocr:
        # Scanned PDF: do not index garbage. Surface it so the UI/answers can say so.
        await db.execute(delete(DocumentChunk).where(DocumentChunk.filing_id == filing.id))
        filing.processing_status = NEEDS_OCR
        filing.error_message = "Scanned PDF without a text layer; OCR is required."
        await db.commit()
        return

    # 3. Chunk and replace any previous chunks atomically
    chunks = chunk_pages(extracted.pages)
    if not chunks:
        raise ExtractionError("No searchable text found")
    await db.execute(delete(DocumentChunk).where(DocumentChunk.filing_id == filing.id))
    db.add_all(
        DocumentChunk(
            filing_id=filing.id,
            chunk_index=c.index,
            text=c.text,
            page_start=c.page_start,
            page_end=c.page_end,
            section=c.section,
            char_count=len(c.text),
        )
        for c in chunks
    )
    filing.processing_status = PROCESSED
    await db.commit()
    logger.info("ingested filing %s: %d pages, %d chunks", filing.id, extracted.page_count, len(chunks))
