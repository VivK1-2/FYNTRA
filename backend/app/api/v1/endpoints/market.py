from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MarketDataUnavailableError
from app.db.session import get_db
from app.providers.market.service import MarketUnavailable, get_market
from app.services.company_service import get_or_resolve_company

router = APIRouter()


class Quote(BaseModel):
    symbol: str
    name: Optional[str] = None
    currency: Optional[str] = None
    exchange: Optional[str] = None
    price: float
    previous_close: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    year_high: Optional[float] = None
    year_low: Optional[float] = None
    volume: Optional[float] = None
    as_of: Optional[str] = None


class Point(BaseModel):
    t: str
    c: float


class MarketResponse(BaseModel):
    source: str
    range: str
    quote: Quote
    points: List[Point]


@router.get("/{identifier}/market", response_model=MarketResponse)
async def market(
    identifier: str,
    range: str = Query("1y", pattern="^(1mo|3mo|6mo|1y|5y)$"),
    db: AsyncSession = Depends(get_db),
):
    """Latest price and history. Yahoo first, Stooq fallback (US). Indian tickers use the NSE (.NS) listing."""
    company = await get_or_resolve_company(db, identifier)
    try:
        return await get_market(company, range)
    except MarketUnavailable as e:
        raise MarketDataUnavailableError(f"Could not get market data ({e}).")
