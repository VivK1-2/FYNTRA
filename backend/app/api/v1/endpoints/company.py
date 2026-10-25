from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotSupportedError
from app.db.session import get_db
from app.schemas.company import CompanyResponse
from app.providers.india.nse.provider import NSEProvider
from app.providers.sec.provider import SECProvider
from app.services.company_service import get_or_resolve_company

router = APIRouter()


class FilingItem(BaseModel):
    provider: str
    form: str
    filing_date: str | None = None
    report_date: str | None = None
    fiscal_label: str | None = None
    accession_number: str
    primary_document: str
    document_url: str
    index_url: str


@router.get("/{identifier}", response_model=CompanyResponse)
async def get_company(identifier: str, db: AsyncSession = Depends(get_db)):
    return await get_or_resolve_company(db, identifier)


@router.get("/{identifier}/filings", response_model=List[FilingItem])
async def list_filings(
    identifier: str,
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Latest annual reports: 10-K from the SEC (US) or annual reports listed on NSE (India)."""
    company = await get_or_resolve_company(db, identifier)
    if company.country == "India":
        return await NSEProvider().find_filings(company, limit=limit)
    if company.country != "USA":
        raise NotSupportedError("Annual-report discovery is available for US and NSE-listed companies.")
    return await SECProvider().find_filings(company, form="10-K", limit=limit)
