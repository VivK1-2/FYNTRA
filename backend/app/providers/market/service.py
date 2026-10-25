"""Market data with fallback: Yahoo first, Stooq (US only) if Yahoo fails. Short in-memory cache."""
import re
import time
from typing import Any, Dict

import httpx

from app.models.company import Company
from app.providers.market import stooq, yahoo
from app.providers.market.yahoo import RANGES, MarketUnavailable

__all__ = ["RANGES", "MarketUnavailable", "get_market", "market_symbol"]

TTL = 90.0
_cache: Dict[tuple, tuple] = {}
SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.&\-]{0,19}$")


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=False,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"},
    )


def market_symbol(company: Company) -> str:
    t = (company.ticker or "").upper().strip()
    if not SYMBOL_RE.match(t):
        raise MarketUnavailable("invalid ticker")
    return f"{t}.NS" if (company.country or "").lower() == "india" else t


async def get_market(company: Company, rng: str) -> Dict[str, Any]:
    if rng not in RANGES:
        raise MarketUnavailable("unsupported range")
    symbol = market_symbol(company)
    key = (symbol, rng)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1]

    errors = []
    async with make_client() as client:
        providers = [yahoo.fetch]
        if not symbol.endswith(".NS"):
            providers.append(stooq.fetch)
        for fetch in providers:
            try:
                data = await fetch(client, symbol, rng)
                break
            except MarketUnavailable as e:
                errors.append(str(e))
        else:
            raise MarketUnavailable("; ".join(errors))

    q = data["quote"]
    q["change"] = round(q["price"] - q["previous_close"], 4) if q.get("previous_close") else None
    q["change_pct"] = round(q["change"] / q["previous_close"] * 100, 2) if q["change"] is not None else None
    data["range"] = rng
    if len(_cache) > 200:
        _cache.clear()
    _cache[key] = (time.monotonic(), data)
    return data
