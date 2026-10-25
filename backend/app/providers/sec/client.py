import time
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.http_client import BaseHTTPClient

# SEC asks for <= 10 requests/second and a descriptive User-Agent with contact info.
_TICKERS_TTL = 24 * 3600
_facts_cache: Dict[str, tuple] = {}
_FACTS_TTL = 900
_FACTS_MAX = 8
_tickers_cache: Optional[tuple[float, Dict[str, Any]]] = None


class SECClient:
    def __init__(self):
        headers = {"User-Agent": settings.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
        self.client = BaseHTTPClient(headers=headers)

    async def get_company_tickers(self) -> Dict[str, Any]:
        """SEC ticker->CIK map. Process-wide cache so we do not re-download ~1MB per request."""
        global _tickers_cache
        now = time.time()
        if _tickers_cache and now - _tickers_cache[0] < _TICKERS_TTL:
            return _tickers_cache[1]
        response = await self.client.request("GET", "https://www.sec.gov/files/company_tickers.json")
        data = response.json()
        _tickers_cache = (now, data)
        return data

    async def get_company_submissions(self, cik: str) -> Dict[str, Any]:
        url = f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"
        return (await self.client.request("GET", url)).json()

    async def get_company_facts(self, cik: str) -> Dict[str, Any]:
        """XBRL facts are large; keep a few in memory for 15 minutes so trend/compare reuse one download."""
        key = str(cik).zfill(10)
        now = time.time()
        hit = _facts_cache.get(key)
        if hit and now - hit[0] < _FACTS_TTL:
            return hit[1]
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{key}.json"
        data = (await self.client.request("GET", url)).json()
        if len(_facts_cache) >= _FACTS_MAX:
            _facts_cache.pop(min(_facts_cache, key=lambda k: _facts_cache[k][0]))
        _facts_cache[key] = (now, data)
        return data
