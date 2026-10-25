import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.core import ratelimit
from app.main import app


@pytest_asyncio.fixture
async def async_client():
    """API client backed by an in-memory SQLite DB, auth disabled. No network."""
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with Session() as s:
            yield s

    ratelimit._hits.clear()
    app.dependency_overrides[get_db] = override_get_db
    original_key = settings.API_KEY
    settings.API_KEY = "disabled"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.session_factory = Session  # type: ignore[attr-defined]
        yield client
    settings.API_KEY = original_key
    app.dependency_overrides.clear()
    await engine.dispose()
