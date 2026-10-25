"""
Simple in-memory sliding-window rate limiter (per client IP, per minute).

Two buckets: a general one, and a stricter one for routes that cost money or heavy work
(POST .../ask, POST .../ingest, POST /llm/ping). Single-process only, which matches this deployment
(one API container). Limits come from settings and 0 disables a bucket.
"""
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

WINDOW = 60.0
_hits: Dict[str, Deque[float]] = defaultdict(deque)


def _is_expensive(request: Request) -> bool:
    p = request.url.path
    return request.method == "POST" and (p.endswith("/ask") or p.endswith("/ingest") or p.endswith("/llm/ping"))


def _client_ip(request: Request) -> str:
    # Behind Caddy (production) the real client is in X-Forwarded-For; never trust it otherwise.
    if settings.ENVIRONMENT == "production":
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check(key: str, limit: int, now: float):
    """Returns None if allowed, else seconds to wait."""
    if limit <= 0:
        return None
    q = _hits[key]
    while q and now - q[0] >= WINDOW:
        q.popleft()
    if len(q) >= limit:
        return max(1, int(WINDOW - (now - q[0])) + 1)
    q.append(now)
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith(settings.API_V1_STR):
            return await call_next(request)

        now = time.monotonic()
        ip = _client_ip(request)
        if len(_hits) > 10_000:  # bound memory under a flood of distinct IPs
            for k in [k for k, q in _hits.items() if not q or now - q[-1] >= WINDOW]:
                _hits.pop(k, None)

        wait = _check(f"g:{ip}", settings.RATE_LIMIT_PER_MINUTE, now)
        if wait is None and _is_expensive(request):
            wait = _check(f"x:{ip}", settings.RATE_LIMIT_LLM_PER_MINUTE, now)
        if wait is not None:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(wait)},
                content={
                    "success": False,
                    "error": {"code": "RATE_LIMITED", "message": f"Too many requests. Try again in {wait} seconds."},
                    "meta": {},
                },
            )
        return await call_next(request)
