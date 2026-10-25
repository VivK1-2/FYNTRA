from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def api_health() -> dict:
    """Authenticated liveness check (the public /health route lives in main.py)."""
    return {"status": "ok"}
