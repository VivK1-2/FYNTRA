import httpx
from typing import Any, Dict, Optional
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

class HTTPClientError(Exception):
    pass

class RateLimitError(HTTPClientError):
    pass

class BaseHTTPClient:
    def __init__(self, base_url: str = "", headers: Optional[Dict[str, str]] = None, timeout: float = 15.0):
        self.base_url = base_url
        self.headers = headers or {}
        self.timeout = timeout

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError, RateLimitError)),
        reraise=True
    )
    async def request(self, method: str, endpoint: str, **kwargs: Any) -> httpx.Response:
        url = f"{self.base_url}{endpoint}" if self.base_url else endpoint
        
        # Merge headers
        request_headers = {**self.headers, **kwargs.pop("headers", {})}
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            logger.info(f"[{method}] {url}")
            try:
                response = await client.request(method, url, headers=request_headers, **kwargs)
                
                # Check for rate limits (e.g., SEC 429 Too Many Requests)
                if response.status_code == 429:
                    logger.warning(f"Rate limited by {url}")
                    raise RateLimitError(f"Rate limited: {response.text}")
                    
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP Status Error: {e.response.status_code} for {url}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request Error: {str(e)} for {url}")
                raise
