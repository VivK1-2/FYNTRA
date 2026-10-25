"""Yahoo Finance chart feed (primary market data). One call returns quote metadata + price history."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

RANGES = {"1mo": "1d", "3mo": "1d", "6mo": "1d", "1y": "1d", "5y": "1wk"}


class MarketUnavailable(Exception):
    pass


def _f(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) else None


async def fetch(client: httpx.AsyncClient, symbol: str, rng: str) -> Dict[str, Any]:
    interval = RANGES[rng]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
    try:
        r = await client.get(url, params={"range": rng, "interval": interval})
    except httpx.HTTPError as e:
        raise MarketUnavailable(f"yahoo: {type(e).__name__}")
    if r.status_code != 200:
        raise MarketUnavailable(f"yahoo: HTTP {r.status_code}")
    try:
        res = (r.json().get("chart") or {}).get("result") or []
        node = res[0]
        meta = node.get("meta") or {}
        stamps = node.get("timestamp") or []
        closes = ((node.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    except (ValueError, IndexError, AttributeError):
        raise MarketUnavailable("yahoo: unexpected response")

    points: List[Dict[str, Any]] = []
    for t, c in zip(stamps, closes):
        if isinstance(c, (int, float)):
            points.append({"t": datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat(), "c": round(float(c), 4)})
    if not points:
        raise MarketUnavailable("yahoo: no prices")

    price = _f(meta.get("regularMarketPrice")) or points[-1]["c"]
    prev = _f(meta.get("previousClose"))
    if prev is None and interval == "1d" and len(points) >= 2:
        prev = points[-2]["c"]
    as_of = meta.get("regularMarketTime")
    return {
        "source": "yahoo",
        "points": points,
        "quote": {
            "symbol": symbol,
            "name": meta.get("longName") or meta.get("shortName"),
            "currency": meta.get("currency"),
            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
            "price": price,
            "previous_close": prev,
            "day_high": _f(meta.get("regularMarketDayHigh")),
            "day_low": _f(meta.get("regularMarketDayLow")),
            "year_high": _f(meta.get("fiftyTwoWeekHigh")),
            "year_low": _f(meta.get("fiftyTwoWeekLow")),
            "volume": _f(meta.get("regularMarketVolume")),
            "as_of": datetime.fromtimestamp(as_of, tz=timezone.utc).isoformat() if isinstance(as_of, (int, float)) else None,
        },
    }
