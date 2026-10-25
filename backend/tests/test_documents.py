import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fitz
import httpx
import pytest

from app.core.config import settings
from app.models.company import Company
from app.services.documents import downloader
from app.services.documents.chunker import chunk_pages
from app.services.documents.downloader import DownloadError, download_document, validate_url
from app.services.documents.extractor import Page, extract_html, extract_pdf

RISK_TEXT = (
    "Item 1A. Risk Factors\n"
    "The Company's business depends on global supply chains. Component shortages could reduce margins.\n"
    "Currency fluctuations may adversely affect results. " * 4
)
MDNA_TEXT = "Item 7. Management's Discussion and Analysis\nNet sales increased due to services growth. " * 6


def make_pdf(path: Path, pages):
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(40, 40, 550, 800), text, fontsize=9)
    doc.save(path)
    doc.close()


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "filings"))
    return tmp_path


# ---------- downloader safety ----------
@pytest.mark.parametrize(
    "url",
    ["http://www.sec.gov/a.pdf", "https://evil.com/a.pdf", "https://sec.gov.evil.com/a.pdf",
     "https://127.0.0.1/a.pdf", "file:///etc/passwd"],
)
def test_url_validation_blocks_unsafe(url):
    with pytest.raises(DownloadError):
        validate_url(url)


def test_url_validation_allows_official_hosts():
    validate_url("https://www.sec.gov/Archives/edgar/data/1/2/a.htm")
    validate_url("https://nsearchives.nseindia.com/annual_reports/x.pdf")


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_download_pdf_ok_and_hashed(storage):
    src = storage / "s.pdf"
    make_pdf(src, ["hello world " * 20])
    data = src.read_bytes()
    r = await download_document("https://www.sec.gov/x.pdf", "AAPL", "0001-23-000001",
                                client=_client(lambda req: httpx.Response(200, content=data)))
    assert r.mime == "application/pdf" and r.path.exists() and len(r.sha256) == 64
    assert not list(r.path.parent.glob("*.part"))


async def test_download_rejects_non_document(storage):
    with pytest.raises(DownloadError):
        await download_document("https://www.sec.gov/x", "AAPL", "a",
                                client=_client(lambda req: httpx.Response(200, content=b"MZ\x90\x00 binary")))


async def test_download_rejects_redirect_to_other_host(storage):
    def handler(req):
        return httpx.Response(302, headers={"location": "https://internal.example.net/secret"})
    with pytest.raises(DownloadError):
        await download_document("https://www.sec.gov/x", "AAPL", "a", client=_client(handler))


async def test_download_enforces_size_cap(storage, monkeypatch):
    monkeypatch.setattr(downloader, "MAX_BYTES", 1000)
    body = b"%PDF-1.4 " + b"a" * 5000
    with pytest.raises(DownloadError):
        await download_document("https://www.sec.gov/x.pdf", "AAPL", "a",
                                client=_client(lambda req: httpx.Response(200, content=body)))
    assert not list((Path(settings.STORAGE_DIR)).rglob("*.part"))


# ---------- extraction ----------
def test_pdf_pages_and_numbers(storage):
    p = storage / "a.pdf"
    make_pdf(p, [RISK_TEXT, MDNA_TEXT])
    ex = extract_pdf(p)
    assert ex.page_count == 2 and ex.has_page_numbers and not ex.needs_ocr
    assert "supply chains" in ex.pages[0].text and ex.pages[1].number == 2


def test_scanned_pdf_flagged_needs_ocr(storage):
    p = storage / "scan.pdf"
    doc = fitz.open()
    for _ in range(3):
        doc.new_page()  # no text layer
    doc.save(p)
    assert extract_pdf(p).needs_ocr is True


def test_html_with_page_breaks_gets_pages(storage):
    p = storage / "f.html"
    p.write_text(
        "<html><body><div>Item 1A. Risk Factors</div><p>Supply risk text here.</p>"
        "<div style='page-break-after:always'></div><p>Second page about liquidity.</p></body></html>"
    )
    ex = extract_html(p)
    assert ex.has_page_numbers and ex.page_count == 2
    assert "liquidity" in ex.pages[1].text


def test_html_without_breaks_has_no_fake_page_numbers(storage):
    p = storage / "f.html"
    p.write_text("<html><body><p>Only one blob of text about revenue.</p></body></html>")
    ex = extract_html(p)
    assert ex.has_page_numbers is False and ex.pages[0].number is None


# ---------- chunking ----------
def test_chunks_keep_sections_and_pages():
    pages = [Page(1, RISK_TEXT), Page(2, MDNA_TEXT)]
    chunks = chunk_pages(pages)
    sections = {c.section for c in chunks}
    assert any(s and s.startswith("Item 1A") for s in sections)
    assert any(s and s.startswith("Item 7") for s in sections)
    risk = next(c for c in chunks if c.section and c.section.startswith("Item 1A"))
    assert risk.page_start == 1
    mdna = next(c for c in chunks if c.section and c.section.startswith("Item 7"))
    assert mdna.page_start == 2


def test_long_text_splits_with_bounded_size():
    long_page = Page(1, "\n".join(f"Sentence number {i} about operations and costs." for i in range(400)))
    chunks = chunk_pages([long_page])
    assert len(chunks) > 3
    assert all(len(c.text) < 4200 for c in chunks)


# ---------- end to end through the API ----------
SUBMISSIONS = {
    "name": "Apple Inc.", "tickers": ["AAPL"], "exchanges": ["Nasdaq"],
    "filings": {"recent": {
        "form": ["10-K"], "filingDate": ["2023-11-03"], "reportDate": ["2023-09-30"],
        "accessionNumber": ["0000320193-23-000106"], "primaryDocument": ["aapl.pdf"],
    }},
}
ACC = "0000320193-23-000106"


async def _add_company(client):
    async with client.session_factory() as s:
        s.add(Company(name="Apple Inc.", ticker="AAPL", country="USA", currency="USD", sec_cik="320193"))
        await s.commit()


async def _wait_processed(client, tries=50):
    for _ in range(tries):
        r = await client.get(f"/api/v1/company/AAPL/filings/{ACC}/status")
        if r.json()["status"] in ("processed", "failed", "needs_ocr"):
            return r.json()
        await asyncio.sleep(0.05)
    raise AssertionError("ingest did not finish")


async def test_ingest_search_end_to_end_and_idempotent(async_client, storage):
    from app.api.v1.endpoints.documents import get_session_factory
    from app.main import app

    app.dependency_overrides[get_session_factory] = lambda: async_client.session_factory
    await _add_company(async_client)
    pdf = storage / "src.pdf"
    make_pdf(pdf, [RISK_TEXT, MDNA_TEXT])
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, content=pdf.read_bytes())

    real = httpx.AsyncClient
    with patch("app.providers.sec.client.SECClient.get_company_submissions", new_callable=AsyncMock,
               return_value=SUBMISSIONS), \
         patch("app.services.documents.downloader.httpx.AsyncClient",
               lambda **kw: real(transport=httpx.MockTransport(handler))):
        r = await async_client.post(f"/api/v1/company/AAPL/filings/{ACC}/ingest")
        assert r.status_code == 202
        status = await _wait_processed(async_client)
        assert status["status"] == "processed" and status["page_count"] == 2 and status["chunk_count"] >= 2

        # second request must not download again
        r2 = await async_client.post(f"/api/v1/company/AAPL/filings/{ACC}/ingest")
        assert r2.status_code == 200 and r2.json()["status"] == "processed"
        assert calls["n"] == 1

    hits = (await async_client.get("/api/v1/company/AAPL/search", params={"q": "supply chains risk"})).json()
    assert hits and hits[0]["page_start"] == 1 and "supply chains" in hits[0]["text"]
    assert hits[0]["section"].startswith("Item 1A")
    assert hits[0]["document_url"].startswith("https://www.sec.gov/Archives/")
    app.dependency_overrides.pop(get_session_factory, None)


async def test_ingest_unknown_accession_404(async_client):
    await _add_company(async_client)
    with patch("app.providers.sec.client.SECClient.get_company_submissions", new_callable=AsyncMock,
               return_value=SUBMISSIONS):
        r = await async_client.post("/api/v1/company/AAPL/filings/0000000000-00-000000/ingest")
    assert r.status_code == 404 and r.json()["error"]["code"] == "FILING_NOT_FOUND"


async def test_failed_download_marks_failed_not_crash(async_client):
    from app.api.v1.endpoints.documents import get_session_factory
    from app.main import app

    app.dependency_overrides[get_session_factory] = lambda: async_client.session_factory
    await _add_company(async_client)
    real = httpx.AsyncClient
    with patch("app.providers.sec.client.SECClient.get_company_submissions", new_callable=AsyncMock,
               return_value=SUBMISSIONS), \
         patch("app.services.documents.downloader.httpx.AsyncClient",
               lambda **kw: real(transport=httpx.MockTransport(lambda req: httpx.Response(500)))):
        await async_client.post(f"/api/v1/company/AAPL/filings/{ACC}/ingest")
        status = await _wait_processed(async_client)
    assert status["status"] == "failed" and "500" in status["error"]
    app.dependency_overrides.pop(get_session_factory, None)


# ---------- real Postgres (skipped unless TEST_PG_URL is set) ----------
@pytest.mark.skipif(not __import__("os").environ.get("TEST_PG_URL"), reason="set TEST_PG_URL to run")
async def test_postgres_full_text_search():
    import os
    from datetime import date as d

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.filing import DocumentChunk, Filing
    from app.services.documents.search import search_chunks

    eng = create_async_engine(os.environ["TEST_PG_URL"])  # DB must already be migrated (alembic upgrade head)
    async with async_sessionmaker(eng, expire_on_commit=False)() as db:
        c = Company(name="PGTest", ticker="PGT", country="USA")
        db.add(c)
        await db.flush()
        f = Filing(company_id=c.id, provider="sec", filing_type="10-K", accession_number="PG-1",
                   filing_date=d(2023, 1, 1), processing_status="processed")
        db.add(f)
        await db.flush()
        db.add(DocumentChunk(filing_id=f.id, chunk_index=0, page_start=12, page_end=12, section="Item 1A",
                             text="Component shortages and supply chain disruption could reduce margins.",
                             char_count=70))
        await db.commit()
        hits = await search_chunks(db, c.id, "What supply chain risks does it face?")
        assert hits and hits[0].page_start == 12
        assert await search_chunks(db, c.id, "zzzunrelated") == []
    await eng.dispose()
