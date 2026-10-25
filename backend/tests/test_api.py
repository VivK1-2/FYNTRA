from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.models.company import Company

SUBMISSIONS = {
    "name": "Apple Inc.",
    "tickers": ["AAPL"],
    "exchanges": ["Nasdaq"],
    "filings": {
        "recent": {
            "form": ["8-K", "10-K", "10-Q", "10-K"],
            "filingDate": ["2024-10-01", "2023-11-03", "2023-08-04", "2022-10-28"],
            "reportDate": ["", "2023-09-30", "2023-07-01", "2022-09-24"],
            "accessionNumber": ["0000320193-24-000001", "0000320193-23-000106", "0000320193-23-000077", "0000320193-22-000108"],
            "primaryDocument": ["a.htm", "aapl-20230930.htm", "q.htm", "aapl-20220924.htm"],
        }
    },
}


async def test_health(async_client):
    r = await async_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


async def test_auth_required_when_key_set(async_client):
    settings.API_KEY = "secret"
    r = await async_client.get("/api/v1/health")
    assert r.status_code == 403
    r = await async_client.get("/api/v1/health", headers={"X-API-Key": "secret"})
    assert r.status_code == 200


async def test_filings_endpoint_returns_only_10k_with_official_urls(async_client):
    async with async_client.session_factory() as s:
        s.add(Company(name="Apple Inc.", ticker="AAPL", country="USA", currency="USD", sec_cik="320193"))
        await s.commit()
    with patch(
        "app.providers.sec.client.SECClient.get_company_submissions",
        new_callable=AsyncMock,
        return_value=SUBMISSIONS,
    ):
        r = await async_client.get("/api/v1/company/AAPL/filings?limit=5")
    assert r.status_code == 200
    items = r.json()
    assert [i["form"] for i in items] == ["10-K", "10-K"]
    assert items[0]["document_url"] == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
    )
    assert items[0]["report_date"] == "2023-09-30"


async def test_unknown_company_404(async_client):
    with patch("app.providers.sec.provider.SECProvider.resolve_company", new_callable=AsyncMock, return_value=None), \
         patch("app.providers.india.nse.provider.NSEProvider.resolve_company", new_callable=AsyncMock, return_value=None):
        r = await async_client.get("/api/v1/company/ZZZZ")
    assert r.status_code == 404
