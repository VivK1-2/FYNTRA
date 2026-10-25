import logging
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_COOKIE_TTL = 600  # seconds


class NSEClient:
    """NSE's site only answers API calls that carry the cookies from its homepage, so one client (with a cookie jar) is reused."""

    def __init__(self) -> None:
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
        }
        self._client: Optional[httpx.AsyncClient] = None
        self._cookies_at = 0.0

    async def _session(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url="https://www.nseindia.com", headers=self._headers, timeout=20.0, follow_redirects=True)
        if time.monotonic() - self._cookies_at > _COOKIE_TTL:
            try:
                await self._client.get("/")
                await self._client.get("/companies-listing/corporate-filings-financial-results")  # sets the cookies the API checks
                self._cookies_at = time.monotonic()
            except httpx.HTTPError as e:
                logger.warning("Failed to fetch NSE cookies: %s", e)
        return self._client

    async def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        client = await self._session()
        for attempt in (1, 2):
            try:
                r = await client.get(path, params=params)
                if r.status_code in (401, 403) and attempt == 1:
                    self._cookies_at = 0.0  # cookies expired: refresh once and retry
                    client = await self._session()
                    continue
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as e:
                logger.error("NSE request %s failed: %s", path, e)
                return None
        return None

    async def search_company(self, query: str) -> Dict[str, Any]:
        """Search NSE for a company by ticker or name."""
        return (await self._get_json("/api/search/autocomplete", {"q": query})) or {}

    async def get_annual_reports(self, symbol: str) -> Any:
        """Annual reports NSE lists for a symbol."""
        return (await self._get_json("/api/annual-reports", {"index": "equities", "symbol": symbol})) or {}

    async def get_financial_results(self, symbol: str, period: str = "Annual") -> Any:
        """Results filings (quarterly/annual). Each row links an XBRL instance file on archives.nseindia.com."""
        return (await self._get_json("/api/corporates-financial-results", {"index": "equities", "symbol": symbol, "period": period})) or []
