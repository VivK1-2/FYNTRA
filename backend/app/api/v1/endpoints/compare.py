import asyncio
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.db.session import get_db
from app.services.company_service import get_or_resolve_company
from app.services.financials import build_financials, flatten

router = APIRouter()
TICKER = re.compile(r"^[A-Z0-9.\-]{1,12}$")


@router.get("")
async def compare(
    tickers: str = Query(..., description="2 to 4 tickers, comma separated"),
    fy: int = Query(2024, ge=2009, le=2100),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Same fiscal year, side by side. A company that fails does not fail the others."""
    ids = list(dict.fromkeys(t.strip().upper() for t in tickers.split(",") if t.strip()))
    if not 2 <= len(ids) <= 4 or not all(TICKER.match(t) for t in ids):
        raise AppError("BAD_TICKERS", "Enter 2 to 4 different tickers.", 422)

    entries: List[Dict[str, Any]] = []
    for t in ids:  # sequential: they share one DB session
        try:
            entries.append({"ticker": t, "company": await get_or_resolve_company(db, t), "error": None})
        except AppError as e:
            entries.append({"ticker": t, "company": None, "error": e.message})

    async def load(e: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if e["company"] is None:
            return None
        try:
            return flatten(await build_financials(e["company"], fy))
        except AppError as err:
            e["error"] = err.message
            return None

    metrics = await asyncio.gather(*(load(e) for e in entries))
    return {
        "fy": fy,
        "companies": [
            {
                "ticker": e["ticker"],
                "name": e["company"].name if e["company"] else None,
                "currency": (e["company"].currency if e["company"] else None) or "USD",
                "metrics": m,
                "error": e["error"],
            }
            for e, m in zip(entries, metrics)
        ],
    }
