from datetime import date

import pytest

from app.core.config import settings
from app.models.company import Company
from app.models.filing import DocumentChunk, Filing
from app.services import xbrl

SAMPLE = """<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:xbrldi="http://xbrl.org/2006/xbrldi"><body>
<ix:header><ix:resources>
<xbrli:context id="d1"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:startDate>2023-10-01</xbrli:startDate><xbrli:endDate>2024-09-28</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="i1"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:instant>2024-09-28</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="seg"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier>
 <xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">aapl:IphoneMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
 <xbrli:period><xbrli:startDate>2023-10-01</xbrli:startDate><xbrli:endDate>2024-09-28</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
<xbrli:unit id="eps"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>
 <xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
</ix:resources></ix:header>
<ix:nonNumeric name="dei:EntityRegistrantName" contextRef="d1">Apple Inc.</ix:nonNumeric>
<p>Revenue <ix:nonFraction name="us-gaap:Revenues" contextRef="d1" unitRef="usd" decimals="-6" scale="6">391,035</ix:nonFraction></p>
<p>Revenue again <ix:nonFraction name="us-gaap:Revenues" contextRef="d1" unitRef="usd" decimals="-6" scale="6">391,035</ix:nonFraction></p>
<p>Loss <ix:nonFraction name="us-gaap:OtherNonoperatingIncomeExpense" contextRef="d1" unitRef="usd" decimals="-6" scale="6" sign="-">269</ix:nonFraction></p>
<p>Cash <ix:nonFraction name="us-gaap:Cash" contextRef="i1" unitRef="usd" decimals="-6" scale="6" format="ixt:fixed-zero">-</ix:nonFraction></p>
<p>EPS <ix:nonFraction name="us-gaap:EarningsPerShareBasic" contextRef="d1" unitRef="eps" decimals="2">6.11</ix:nonFraction></p>
<p>iPhone <ix:nonFraction name="us-gaap:Revenues" contextRef="seg" unitRef="usd" decimals="-6" scale="6">201,183</ix:nonFraction></p>
</body></html>"""


def test_parse_ixbrl(tmp_path):
    p = tmp_path / "a.htm"
    p.write_text(SAMPLE)
    xbrl.clear_cache()
    doc = xbrl.load_doc(p)
    rev = [f for f in doc.facts if f.concept == "us-gaap:Revenues" and not f.dimensions]
    assert len(rev) == 1 and rev[0].value == 391035e6 and rev[0].period_type == "duration"
    assert rev[0].end == "2024-09-28"
    loss = next(f for f in doc.facts if f.concept.endswith("OtherNonoperatingIncomeExpense"))
    assert loss.value == -269e6
    cash = next(f for f in doc.facts if f.concept.endswith(":Cash"))
    assert cash.value == 0 and cash.period_type == "instant"
    eps = next(f for f in doc.facts if "EarningsPerShareBasic" in f.concept)
    assert eps.value == 6.11 and "USD" in eps.unit and "shares" in eps.unit
    seg = [f for f in doc.facts if f.dimensions]
    assert len(seg) == 1 and "IphoneMember" in seg[0].dimensions[0]
    assert doc.document.get("EntityRegistrantName") == "Apple Inc." or "Apple Inc." in doc.document.values()
    assert len(xbrl.filter_facts(doc, None, False)) == len(doc.facts) - 1
    assert len(xbrl.filter_facts(doc, "revenue", True)) == 2


async def _seed(client, path=None, provider="sec"):
    async with client.session_factory() as s:
        c = Company(name="Apple Inc.", ticker="AAPL", country="USA", currency="USD", sec_cik="320193")
        s.add(c)
        await s.flush()
        f = Filing(company_id=c.id, provider=provider, filing_type="10-K", accession_number="ACC-1",
                   filing_date=date(2024, 11, 1), processing_status="processed",
                   local_storage_path=str(path) if path else None, document_url="https://www.sec.gov/x")
        s.add(f)
        await s.flush()
        s.add(DocumentChunk(filing_id=f.id, chunk_index=0, page_start=1, page_end=1, text="hello", char_count=5))
        await s.commit()
        return f.id


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    return tmp_path


async def test_xbrl_endpoint(async_client, storage):
    p = storage / "a.htm"
    p.write_text(SAMPLE)
    await _seed(async_client, p)
    r = await async_client.get("/api/v1/company/AAPL/filings/ACC-1/xbrl?q=revenue")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["has_xbrl"] and j["matched"] == 1 and j["facts"][0]["concept"] == "us-gaap:Revenues"
    r = await async_client.get("/api/v1/company/AAPL/filings/ACC-1/xbrl?dimensional=true&limit=2")
    assert len(r.json()["facts"]) == 2


async def test_xbrl_not_downloaded(async_client, storage, monkeypatch):
    from app.api.v1.endpoints import xbrl as xbrl_ep
    from app.services.documents.downloader import DownloadError

    async def boom(*a, **k):
        raise DownloadError("offline")
    monkeypatch.setattr(xbrl_ep, "download_document", boom)
    await _seed(async_client, None)
    r = await async_client.get("/api/v1/company/AAPL/filings/ACC-1/xbrl")
    assert r.status_code == 409


async def test_xbrl_missing_file_is_downloaded_again(async_client, storage, monkeypatch):
    """The database says the report exists but its file is gone: fetch it again instead of failing."""
    from app.api.v1.endpoints import xbrl as xbrl_ep
    from app.services.documents.downloader import Downloaded
    src = storage / "AAPL" / "again.html"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("<html><body>no tags</body></html>")

    async def fake(url, ticker, accession, headers=None, client=None):
        return Downloaded(path=src, sha256="x", mime="text/html", size=10)
    monkeypatch.setattr(xbrl_ep, "download_document", fake)
    await _seed(async_client, None)
    r = await async_client.get("/api/v1/company/AAPL/filings/ACC-1/xbrl")
    assert r.status_code == 200


async def test_bulk_status(async_client, storage):
    await _seed(async_client, None)
    r = await async_client.get("/api/v1/company/AAPL/filings/status")
    assert r.status_code == 200 and "ACC-1" in r.json()


H = {"X-Admin-Key": "k" * 20}


async def test_admin_disabled_and_auth(async_client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_KEY", "")
    assert (await async_client.get("/api/v1/admin/overview")).status_code == 503
    monkeypatch.setattr(settings, "ADMIN_KEY", "k" * 20)
    assert (await async_client.get("/api/v1/admin/overview")).status_code == 401
    assert (await async_client.get("/api/v1/admin/overview", headers={"X-Admin-Key": "nope"})).status_code == 401
    assert (await async_client.get("/api/v1/admin/overview", headers=H)).status_code == 200


async def test_admin_throttles_guessing(async_client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_KEY", "k" * 20)
    codes = [(await async_client.get("/api/v1/admin/overview", headers={"X-Admin-Key": f"x{i}"})).status_code for i in range(14)]
    assert 429 in codes
    # even the right key is not blocked by the failed-attempt counter
    assert (await async_client.get("/api/v1/admin/overview", headers=H)).status_code == 200


async def test_admin_overview_filings_delete(async_client, storage, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_KEY", "k" * 20)
    p = storage / "a.htm"
    p.write_text("<html></html>")
    fid = await _seed(async_client, p)
    o = (await async_client.get("/api/v1/admin/overview", headers=H)).json()
    assert o["counts"]["filings"] == 1 and o["counts"]["passages"] == 1 and o["database_ok"]
    rows = (await async_client.get("/api/v1/admin/filings", headers=H)).json()
    assert rows[0]["ticker"] == "AAPL" and rows[0]["passages"] == 1
    r = await async_client.delete(f"/api/v1/admin/filings/{fid}", headers=H)
    assert r.json() == {"deleted": fid, "file_removed": True} and not p.exists()
    assert (await async_client.delete(f"/api/v1/admin/filings/{fid}", headers=H)).status_code == 404


async def test_admin_never_deletes_outside_storage(async_client, storage, tmp_path_factory, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_KEY", "k" * 20)
    outside = tmp_path_factory.mktemp("elsewhere") / "keep.txt"
    outside.write_text("x")
    fid = await _seed(async_client, outside)
    r = await async_client.delete(f"/api/v1/admin/filings/{fid}", headers=H)
    assert r.json()["file_removed"] is False and outside.exists()


async def test_admin_asks_and_cache(async_client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_KEY", "k" * 20)
    await _seed(async_client, None)
    await async_client.post("/api/v1/company/AAPL/ask", json={"question": "zzzz qqqq nothing"})
    asks = (await async_client.get("/api/v1/admin/asks", headers=H)).json()
    assert asks and asks[0]["status"] == "insufficient_evidence"
    r = await async_client.post("/api/v1/admin/cache/clear", headers=H)
    assert set(r.json()) == {"market", "sec_facts", "xbrl_documents"}


# ---------- Indian (NSE) XBRL instance files ----------
NSE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin"
 xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:link="http://www.xbrl.org/2003/linkbase">
<link:schemaRef xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="x.xsd"/>
<xbrli:context id="OneD"><xbrli:entity><xbrli:identifier scheme="NSE">AHLWEST</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:startDate>2021-01-01</xbrli:startDate><xbrli:endDate>2021-03-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="OneI"><xbrli:entity><xbrli:identifier scheme="NSE">AHLWEST</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:instant>2021-03-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="Dim"><xbrli:entity><xbrli:identifier scheme="NSE">AHLWEST</xbrli:identifier>
 <xbrli:segment><xbrldi:explicitMember dimension="in-bse-fin:DetailsOfOtherExpensesAxis">in-bse-fin:OneOperatingExpenses01Member</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
 <xbrli:period><xbrli:startDate>2021-01-01</xbrli:startDate><xbrli:endDate>2021-03-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
<xbrli:unit id="INRPerShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unitNumerator>
 <xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<in-bse-fin:NameOfCompany contextRef="OneD">Asian Hotels (West) Limited</in-bse-fin:NameOfCompany>
<in-bse-fin:RevenueFromOperations contextRef="OneD" unitRef="INR" decimals="-5">499725000.00</in-bse-fin:RevenueFromOperations>
<in-bse-fin:RevenueFromOperations contextRef="OneD" unitRef="INR" decimals="-5">499725000.00</in-bse-fin:RevenueFromOperations>
<in-bse-fin:ProfitLossForPeriod contextRef="OneD" unitRef="INR" decimals="-5">-392075000.00</in-bse-fin:ProfitLossForPeriod>
<in-bse-fin:Assets contextRef="OneI" unitRef="INR" decimals="-5">10642723000.00</in-bse-fin:Assets>
<in-bse-fin:BasicEarningsLossPerShare contextRef="OneD" unitRef="INRPerShare" decimals="INF">-127.74</in-bse-fin:BasicEarningsLossPerShare>
<in-bse-fin:OtherExpenses contextRef="Dim" unitRef="INR" decimals="-5">1000000.00</in-bse-fin:OtherExpenses>
</xbrli:xbrl>"""


def test_parse_nse_instance(tmp_path):
    p = tmp_path / "n.xml"
    p.write_text(NSE_XML)
    xbrl.clear_cache()
    doc = xbrl.load_doc(p)
    names = [f.concept for f in doc.facts]
    assert names.count("in-bse-fin:RevenueFromOperations") == 1
    loss = next(f for f in doc.facts if f.concept.endswith("ProfitLossForPeriod"))
    assert loss.value == -392075000.0 and loss.unit == "INR" and loss.end == "2021-03-31"
    assets = next(f for f in doc.facts if f.concept.endswith(":Assets"))
    assert assets.period_type == "instant"
    eps = next(f for f in doc.facts if "EarningsLoss" in f.concept)
    assert eps.unit == "INR/shares" and eps.value == -127.74
    assert [f for f in doc.facts if f.dimensions] and doc.document.get("NameOfCompany") == "Asian Hotels (West) Limited"


async def test_india_endpoints(async_client, storage, monkeypatch):
    from app.api.v1.endpoints import xbrl as ep

    async with async_client.session_factory() as s:
        s.add(Company(name="Reliance", ticker="RELIANCE", country="India", currency="INR", exchange="NSE"))
        await s.commit()

    async def fake_results(self, symbol, period):
        if period != "Annual":
            return []
        return {"data": [{"toDate": "31-Mar-2024", "audited": "Audited", "consolidated": "Consolidated",
                          "xbrl": "https://archives.nseindia.com/corporate/xbrl/INDAS_1_2_3.xml"},
                         {"toDate": "x", "xbrl": "https://evil.example.com/a.xml"}]}
    monkeypatch.setattr("app.providers.india.nse.client.NSEClient.get_financial_results", fake_results)
    r = await async_client.get("/api/v1/company/RELIANCE/xbrl-filings")
    items = r.json()["filings"]
    assert len(items) == 1 and items[0]["period_end"] == "31-Mar-2024"  # off-allowlist host dropped

    async def fake_fetch(url):
        p = storage / "n.xml"
        p.write_text(NSE_XML)
        return p
    monkeypatch.setattr(ep, "_fetch_nse_xbrl", fake_fetch)
    r = await async_client.get("/api/v1/company/RELIANCE/xbrl-facts?url=https://archives.nseindia.com/corporate/xbrl/INDAS_1_2_3.xml&q=revenue")
    assert r.status_code == 200 and r.json()["matched"] == 1


async def test_nse_fetch_rejects_bad_hosts():
    from app.api.v1.endpoints.xbrl import _fetch_nse_xbrl
    from app.core.exceptions import AppError
    for bad in ["https://evil.example.com/a.xml", "http://archives.nseindia.com/a.xml", "https://archives.nseindia.com/a.pdf"]:
        with pytest.raises(AppError):
            await _fetch_nse_xbrl(bad)


async def test_india_resolution_falls_back_to_yahoo(monkeypatch):
    from app.providers.india.nse.provider import NSEProvider
    from app.providers.market import yahoo

    async def no_nse(self, q):
        return {}

    async def fake_fetch(client, symbol, rng):
        assert symbol == "RELIANCE.NS"
        return {"quote": {"name": "Reliance Industries Limited", "currency": "INR"}, "points": []}
    monkeypatch.setattr("app.providers.india.nse.client.NSEClient.search_company", no_nse)
    monkeypatch.setattr(yahoo, "fetch", fake_fetch)
    c = await NSEProvider().resolve_company("reliance")
    assert c.ticker == "RELIANCE" and c.country == "India" and c.name.startswith("Reliance")

    async def usd(client, symbol, rng):
        return {"quote": {"name": "x", "currency": "USD"}, "points": []}
    monkeypatch.setattr(yahoo, "fetch", usd)
    assert await NSEProvider().resolve_company("RELIANCE") is None
