from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import settings
from app.models.company import Company
from app.providers.market import service as market
from app.schemas.financials import FinancialFact, SourceProvenance


def fact(metric, v):
    return FinancialFact(metric=metric, value=v, currency="USD", unit="USD", period="FY2024",
                         source=SourceProvenance(provider="sec", xbrl_tag=metric))


def structured(rev, ni, assets=1000.0, equity=500.0, ocf=300.0, capex=50.0):
    return {
        "income_statement": {"revenue": fact("Revenues", rev), "gross_profit": fact("GP", rev * 0.4),
                             "operating_income": fact("OI", rev * 0.3), "net_income": fact("NI", ni)},
        "balance_sheet": {"total_assets": fact("Assets", assets), "total_equity": fact("Eq", equity)},
        "cash_flow": {"operating_cash_flow": fact("OCF", ocf), "capital_expenditure": fact("Capex", capex)},
    }


async def add(client, ticker, country="USA", cik=None, name=None):
    async with client.session_factory() as s:
        s.add(Company(name=name or ticker, ticker=ticker, country=country,
                      currency="USD" if country == "USA" else "INR", sec_cik=cik))
        await s.commit()


# ---------- rate limiting ----------
async def test_rate_limit_general(async_client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 3)
    codes = [(await async_client.get("/api/v1/health")).status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3:] == [429, 429]
    r = await async_client.get("/api/v1/health")
    assert r.json()["error"]["code"] == "RATE_LIMITED" and int(r.headers["retry-after"]) >= 1


async def test_rate_limit_stricter_for_ask(async_client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_LLM_PER_MINUTE", 2)
    await add(async_client, "AAPL")
    codes = [(await async_client.post("/api/v1/company/AAPL/ask", json={"question": "zzz"})).status_code
             for _ in range(4)]
    assert 429 in codes[2:] and 429 not in codes[:2]


async def test_health_not_rate_limited(async_client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    assert [(await async_client.get("/health")).status_code for _ in range(3)] == [200] * 3


# ---------- market data ----------
def yahoo_payload(n=5, base=100.0):
    t0 = int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp())
    return {"chart": {"result": [{
        "meta": {"currency": "USD", "longName": "Apple Inc.", "fullExchangeName": "NasdaqGS",
                 "regularMarketPrice": base + n - 1, "fiftyTwoWeekHigh": 200.0, "fiftyTwoWeekLow": 90.0,
                 "regularMarketVolume": 1000, "regularMarketTime": t0 + 86400 * n},
        "timestamp": [t0 + 86400 * i for i in range(n)],
        "indicators": {"quote": [{"close": [base + i for i in range(n)]}]},
    }]}}


@pytest.fixture(autouse=True)
def _clear_market():
    market._cache.clear()


def _client_for(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_market_yahoo_quote_and_history(async_client):
    await add(async_client, "AAPL")
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(200, json=yahoo_payload())

    with patch.object(market, "make_client", _client_for(handler)):
        r = await async_client.get("/api/v1/company/AAPL/market?range=1y")
    b = r.json()
    assert r.status_code == 200 and b["source"] == "yahoo" and len(b["points"]) == 5
    assert b["quote"]["price"] == 104.0 and b["quote"]["previous_close"] == 103.0 and b["quote"]["change"] == 1.0
    assert "chart/AAPL" in seen[0]


async def test_market_indian_company_uses_ns_symbol(async_client):
    await add(async_client, "RELIANCE", country="India")
    seen = []

    def handler(req):
        seen.append(req.url.path)
        return httpx.Response(200, json=yahoo_payload())

    with patch.object(market, "make_client", _client_for(handler)):
        r = await async_client.get("/api/v1/company/RELIANCE/market")
    assert r.status_code == 200 and seen[0].endswith("/RELIANCE.NS")


async def test_market_falls_back_to_stooq_for_us(async_client):
    await add(async_client, "AAPL")
    today = datetime.now().date()
    csv_rows = "\n".join(f"{today.replace(day=1).isoformat()},1,{100+i},{90+i},{95+i},500" for i in range(3))

    def handler(req):
        if "yahoo" in req.url.host:
            return httpx.Response(429)
        return httpx.Response(200, text="Date,Open,High,Low,Close,Volume\n" + csv_rows)

    with patch.object(market, "make_client", _client_for(handler)):
        r = await async_client.get("/api/v1/company/AAPL/market?range=1mo")
    assert r.status_code == 200 and r.json()["source"] == "stooq" and r.json()["quote"]["price"] == 97.0


async def test_market_all_sources_down_is_503(async_client):
    await add(async_client, "AAPL")
    with patch.object(market, "make_client", _client_for(lambda req: httpx.Response(500))):
        r = await async_client.get("/api/v1/company/AAPL/market")
    assert r.status_code == 503 and r.json()["error"]["code"] == "MARKET_DATA_UNAVAILABLE"


async def test_market_rejects_unknown_range(async_client):
    await add(async_client, "AAPL")
    assert (await async_client.get("/api/v1/company/AAPL/market?range=10y")).status_code == 422


async def test_market_result_is_cached(async_client):
    await add(async_client, "AAPL")
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json=yahoo_payload())

    with patch.object(market, "make_client", _client_for(handler)):
        await async_client.get("/api/v1/company/AAPL/market")
        await async_client.get("/api/v1/company/AAPL/market")
    assert calls["n"] == 1


# ---------- trend + compare ----------
async def test_trend_skips_missing_years_and_computes_fcf(async_client):
    await add(async_client, "AAPL", cik="320193")

    async def fake(self, company, fy=2023):
        return structured(1000.0 + fy, 200.0) if fy != 2021 else {}

    with patch("app.providers.sec.provider.SECProvider.get_structured_data", fake):
        r = await async_client.get("/api/v1/company/AAPL/financials/trend?from_fy=2020&to_fy=2023")
    years = r.json()["years"]
    assert [y["fy"] for y in years] == [2020, 2022, 2023]
    assert years[0]["net_margin"] == pytest.approx(200 / 3020, rel=1e-3)
    assert years[0]["free_cash_flow"] == 250.0 and years[0]["net_income"] == 200.0


async def test_trend_rejects_bad_range(async_client):
    await add(async_client, "AAPL", cik="1")
    assert (await async_client.get("/api/v1/company/AAPL/financials/trend?from_fy=2024&to_fy=2020")).status_code == 422


async def test_compare_isolates_failures(async_client):
    await add(async_client, "AAPL", cik="1")
    await add(async_client, "MSFT", cik="2")
    await add(async_client, "RELIANCE", country="India")

    async def fake(self, company, fy=2023):
        return structured(500.0 if company.ticker == "AAPL" else 300.0, 100.0)

    with patch("app.providers.sec.provider.SECProvider.get_structured_data", fake):
        r = await async_client.get("/api/v1/compare?tickers=aapl,msft,reliance&fy=2024")
    comp = {c["ticker"]: c for c in r.json()["companies"]}
    assert comp["AAPL"]["metrics"]["revenue"] == 500.0 and comp["MSFT"]["metrics"]["revenue"] == 300.0
    assert comp["RELIANCE"]["metrics"] is None and "Indian" in comp["RELIANCE"]["error"]


async def test_compare_validates_ticker_count(async_client):
    assert (await async_client.get("/api/v1/compare?tickers=AAPL")).status_code == 422
    assert (await async_client.get("/api/v1/compare?tickers=A,B,C,D,E")).status_code == 422


# ---------- India annual reports ----------
NSE_ROWS = {"data": [
    {"companyName": "Reliance", "fromYr": "2022", "toYr": "2023", "fileName": "https://nsearchives.nseindia.com/annual_reports/AR_2023.pdf"},
    {"companyName": "Reliance", "fromYr": "2023", "toYr": "2024", "fileName": "https://nsearchives.nseindia.com/annual_reports/AR_2024.pdf"},
    {"fromYr": "2021", "toYr": "2022", "fileName": "https://evil.example.com/AR_2022.pdf"},
    {"fromYr": "2020", "toYr": "2021"},
]}


async def test_india_filings_listed_newest_first_and_unsafe_urls_dropped(async_client):
    await add(async_client, "RELIANCE", country="India")
    with patch("app.providers.india.nse.client.NSEClient.get_annual_reports", new_callable=AsyncMock,
               return_value=NSE_ROWS):
        r = await async_client.get("/api/v1/company/RELIANCE/filings")
    items = r.json()
    assert [i["fiscal_label"] for i in items] == ["FY 2023-24", "FY 2022-23"]
    assert items[0]["accession_number"] == "NSE-RELIANCE-2024" and items[0]["filing_date"] is None


async def test_india_ingest_end_to_end(async_client, tmp_path, monkeypatch):
    import asyncio
    import fitz
    from app.api.v1.endpoints.documents import get_session_factory
    from app.main import app

    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path / "f"))
    pdf = tmp_path / "ar.pdf"
    d = fitz.open()
    pg = d.new_page()
    pg.insert_textbox(fitz.Rect(40, 40, 550, 800), "Management discussion. Revenue grew strongly in retail. " * 30, fontsize=9)
    d.save(pdf)
    d.close()

    app.dependency_overrides[get_session_factory] = lambda: async_client.session_factory
    await add(async_client, "RELIANCE", country="India")
    real = httpx.AsyncClient
    with patch("app.providers.india.nse.client.NSEClient.get_annual_reports", new_callable=AsyncMock,
               return_value=NSE_ROWS), \
         patch("app.services.documents.downloader.httpx.AsyncClient",
               lambda **kw: real(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=pdf.read_bytes())))):
        r = await async_client.post("/api/v1/company/RELIANCE/filings/NSE-RELIANCE-2024/ingest")
        assert r.status_code == 202
        for _ in range(60):
            st = (await async_client.get("/api/v1/company/RELIANCE/filings/NSE-RELIANCE-2024/status")).json()
            if st["status"] in ("processed", "failed", "needs_ocr"):
                break
            await asyncio.sleep(0.05)
    app.dependency_overrides.pop(get_session_factory, None)
    assert st["status"] == "processed" and st["page_count"] == 1
    hits = (await async_client.get("/api/v1/company/RELIANCE/search", params={"q": "retail revenue"})).json()
    assert hits and hits[0]["form"] == "Annual report"


async def test_india_ingest_unknown_report_404(async_client):
    await add(async_client, "RELIANCE", country="India")
    with patch("app.providers.india.nse.client.NSEClient.get_annual_reports", new_callable=AsyncMock,
               return_value=NSE_ROWS):
        r = await async_client.post("/api/v1/company/RELIANCE/filings/NSE-RELIANCE-1999/ingest")
    assert r.status_code == 404
