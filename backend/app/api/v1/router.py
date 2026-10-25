import secrets

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.api.v1.endpoints import admin, ask, company, compare, documents, financials, health, market, xbrl
from app.core.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(provided: str = Security(api_key_header)):
    if settings.API_KEY == "disabled":
        return None
    # constant-time comparison to avoid timing attacks
    if not provided or not secrets.compare_digest(provided, settings.API_KEY):
        raise HTTPException(status_code=403, detail="Could not validate API key")
    return provided


api_router = APIRouter(dependencies=[Depends(get_api_key)])
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(company.router, prefix="/company", tags=["company"])
api_router.include_router(financials.router, prefix="/company", tags=["financials"])
api_router.include_router(documents.router, prefix="/company", tags=["documents"])
api_router.include_router(ask.router, prefix="/company", tags=["ask"])
api_router.include_router(market.router, prefix="/company", tags=["market"])
api_router.include_router(ask.compare_router, prefix="/compare", tags=["ask"])
api_router.include_router(compare.router, prefix="/compare", tags=["compare"])
api_router.include_router(xbrl.router, prefix="/company", tags=["xbrl"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
