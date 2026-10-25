import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotSupportedError
from app.db.session import get_db
from app.schemas.financials import CompleteFinancialResponse
from app.services.company_service import get_or_resolve_company
from app.services.financials import build_financials, flatten

router = APIRouter()


@router.get("/{identifier}/financials/complete", response_model=CompleteFinancialResponse)
async def get_complete_financials(
    identifier: str,
    fy: int = Query(2023, ge=2009, le=2100),
    db: AsyncSession = Depends(get_db),
):
    company = await get_or_resolve_company(db, identifier)
    return await build_financials(company, fy)


@router.get("/{identifier}/financials/trend")
async def financial_trend(
    identifier: str,
    from_fy: int = Query(2020, ge=2009, le=2100),
    to_fy: int = Query(2024, ge=2009, le=2100),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Key numbers for each fiscal year in a range (years with no data are skipped)."""
    if to_fy < from_fy or to_fy - from_fy > 9:
        raise AppError("BAD_RANGE", "Choose a range of 1 to 10 fiscal years.", 422)
    company = await get_or_resolve_company(db, identifier)
    if company.country != "USA":
        raise NotSupportedError("Structured financials for Indian companies are not implemented yet.")
    years = list(range(from_fy, to_fy + 1))
    results = await asyncio.gather(*(build_financials(company, y) for y in years), return_exceptions=True)
    rows: List[Dict[str, Any]] = [
        {"fy": y, **flatten(r)} for y, r in zip(years, results) if not isinstance(r, BaseException)
    ]
    return {"ticker": company.ticker, "currency": company.currency or "USD", "years": rows}
