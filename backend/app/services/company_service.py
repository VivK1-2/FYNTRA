from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.exceptions import CompanyNotFoundError
from app.models.company import Company
from app.providers.india.nse.provider import NSEProvider
from app.providers.sec.provider import SECProvider


async def get_or_resolve_company(db: AsyncSession, identifier: str) -> Company:
    """DB first, then SEC (US), then NSE (India). Resolved companies are saved for reuse."""
    identifier = identifier.upper().strip()
    result = await db.execute(
        select(Company).where((Company.ticker == identifier) | (Company.sec_cik == identifier))
    )
    company = result.scalars().first()
    if company:
        return company

    resolved = await SECProvider().resolve_company(identifier)
    if not resolved:
        resolved = await NSEProvider().resolve_company(identifier)
    if not resolved:
        raise CompanyNotFoundError(identifier=identifier)

    db.add(resolved)
    await db.commit()
    await db.refresh(resolved)
    return resolved
