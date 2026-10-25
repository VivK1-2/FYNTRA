"""Stooq daily prices (fallback, US tickers only). Plain CSV, no key needed."""
import csv
import io
from datetime import date, timedelta
from typing import Any, Dict

import httpx

from app.providers.market.yahoo import MarketUnavailable

DAYS = {"1mo": 31, "3mo": 93, "6mo": 186, "1y": 366, "5y": 1830}


async def fetch(client: httpx.AsyncClient, symbol: str, rng: str) -> Dict[str, Any]:
    start = date.today() - timedelta(days=max(DAYS[rng], 380))
    try:
        r = await client.get(
            "https://stooq.com/q/d/l/",
            params={"s": f"{symbol.lower()}.us", "i": "d", "d1": start.strftime("%Y%m%d")},
        )
    except httpx.HTTPError as e:
        raise MarketUnavailable(f"stooq: {type(e).__name__}")
    if r.status_code != 200 or not r.text.lstrip().lower().startswith("date"):
        raise MarketUnavailable("stooq: no data")
    rows = []
    for row in csv.DictReader(io.StringIO(r.text)):
        try:
            rows.append((row["Date"], float(row["Close"]), float(row["High"]), float(row["Low"]), float(row.get("Volume") or 0)))
        except (KeyError, ValueError):
            continue
    if not rows:
        raise MarketUnavailable("stooq: empty")
    cutoff = (date.today() - timedelta(days=DAYS[rng])).isoformat()
    points = [{"t": d, "c": round(c, 4)} for d, c, *_ in rows if d >= cutoff]
    last = rows[-1]
    year = rows[-252:]
    return {
        "source": "stooq",
        "points": points or [{"t": last[0], "c": last[1]}],
        "quote": {
            "symbol": symbol, "name": None, "currency": "USD", "exchange": None,
            "price": last[1], "previous_close": rows[-2][1] if len(rows) > 1 else None,
            "day_high": last[2], "day_low": last[3],
            "year_high": max(r[2] for r in year), "year_low": min(r[3] for r in year),
            "volume": last[4], "as_of": last[0],
        },
    }
