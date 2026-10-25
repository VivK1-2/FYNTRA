import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError, app_error_handler
from app.core import runtime  # noqa: F401  (records process start time)
from app.core.ratelimit import RateLimitMiddleware
from app.db.session import get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.assert_production_safe()
    logger.info("Starting %s v%s (%s)", settings.PROJECT_NAME, settings.VERSION, settings.ENVIRONMENT)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    # Hide interactive docs in production; the API is consumed by the FYNTRA frontend only.
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None,
    description="FYNTRA: filing-to-insight backend.",
    lifespan=lifespan,
)

app.add_exception_handler(AppError, app_error_handler)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "X-Admin-Key", "Content-Type"],
)


@app.get("/health", tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """Unauthenticated liveness probe for Docker/Caddy/uptime monitors. Leaks nothing sensitive."""
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        db_ok = False
        logger.error("Healthcheck DB error: %s", e)
    return {
        "status": "healthy" if db_ok else "degraded",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database": "available" if db_ok else "unavailable",
    }


app.include_router(api_router, prefix=settings.API_V1_STR)
