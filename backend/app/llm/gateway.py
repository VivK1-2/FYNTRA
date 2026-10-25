"""
LLM gateway: the ONLY place in FYNTRA that talks to the language model.

The model name, endpoint and key come from the backend settings (LLM_MODEL, LLM_BASE_URL,
LLM_API_KEY). Nothing about the model is configured, shown or sent from the frontend.

- OpenAI-compatible chat completions endpoint ({LLM_BASE_URL}/chat/completions)
- one call goes to ONE model; the optional fallback is tried only if that model fails
- retries 429/5xx/timeouts with backoff
- JSON mode: parses and validates, asks once for a corrected reply
"""
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class LLMError(Exception):
    pass


class LLMUnavailableError(LLMError):
    """The model could not produce an answer."""


class _Fatal(Exception):
    """Non-retryable provider error (bad key, unknown model, spend cap). Moves to the fallback."""


@dataclass
class LLMResult:
    text: str
    model_name: str
    latency_ms: int
    usage: Dict[str, Any] = field(default_factory=dict)
    attempts: List[str] = field(default_factory=list)


def configured_models() -> List[str]:
    names = [settings.LLM_MODEL.strip(), settings.LLM_FALLBACK_MODEL.strip()]
    out: List[str] = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out


class LLMGateway:
    def __init__(self, client: Optional[httpx.AsyncClient] = None, max_retries: int = 2, backoff: float = 1.0):
        self._client = client
        self.max_retries = max_retries
        self.backoff = backoff

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS)
        return self._client

    @staticmethod
    def _parse_response(data: Dict[str, Any]) -> str:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("Malformed chat response from the model provider") from e
        if isinstance(content, list):  # some providers return content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return (content or "").strip()

    async def _call_one(self, model: str, messages, max_tokens, temperature) -> LLMResult:
        url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}", "Content-Type": "application/json"}
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            try:
                resp = await self._http().post(url, json=body, headers=headers)
                if resp.status_code in RETRYABLE_STATUS:
                    raise LLMError(f"HTTP {resp.status_code} from the model provider")
                if resp.status_code >= 400:
                    raise _Fatal(f"HTTP {resp.status_code} from the model provider: {resp.text[:300]}")
                data = resp.json()
                text = self._parse_response(data)
                if not text:
                    finish = ((data.get("choices") or [{}])[0] or {}).get("finish_reason")
                    raise LLMError(f"The model returned an empty reply (finish_reason={finish}); it may be using the token limit for thinking")
                return LLMResult(text=text, model_name=model, latency_ms=int((time.perf_counter() - started) * 1000),
                                 usage=data.get("usage", {}) or {})
            except _Fatal:
                raise
            except (httpx.TimeoutException, httpx.TransportError, LLMError, ValueError) as e:
                last_err = e
                logger.warning("LLM call attempt %d failed: %s", attempt + 1, e)
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff * (2**attempt))
        raise LLMError(f"Failed after retries: {last_err}")

    async def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 1500,
        temperature: float = 0.1,
        models: Optional[List[str]] = None,
    ) -> LLMResult:
        if not settings.LLM_API_KEY:
            raise LLMUnavailableError("The AI model is not configured: set LLM_API_KEY in the backend .env and restart.")
        chain = models or configured_models()
        if not chain:
            raise LLMUnavailableError("The AI model is not configured: set LLM_MODEL in the backend .env and restart.")
        attempts: List[str] = []
        errors: List[str] = []
        for model in chain:
            try:
                result = await self._call_one(model, messages, max_tokens, temperature)
                attempts.append(f"{model}:ok")
                result.attempts = attempts
                return result
            except (LLMError, _Fatal) as e:
                attempts.append(f"{model}:fail")
                errors.append(str(e)[:300])
                logger.error("LLM model %s failed. %s", model, e)
        raise LLMUnavailableError(f"The AI model failed ({', '.join(attempts)}): {' | '.join(errors)}")

    async def complete_json(
        self,
        messages: List[Dict[str, str]],
        *,
        required_keys: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> tuple[Dict[str, Any], LLMResult]:
        """Ask for a JSON object; validate; if invalid, ask once for a corrected version."""
        result = await self.complete(messages, **kwargs)
        parsed = _extract_json(result.text)
        if _valid(parsed, required_keys):
            return parsed, result
        repair = messages + [
            {"role": "assistant", "content": result.text},
            {
                "role": "user",
                "content": "Your reply was not valid JSON"
                + (f" with keys {required_keys}" if required_keys else "")
                + ". Reply again with ONLY the corrected JSON object, no prose, no code fences.",
            },
        ]
        kw = {k: v for k, v in kwargs.items() if k != "models"}
        result2 = await self.complete(repair, models=[result.model_name], **kw)
        parsed2 = _extract_json(result2.text)
        if _valid(parsed2, required_keys):
            return parsed2, result2
        raise LLMError("The model did not return valid JSON after one repair attempt")

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _valid(obj: Optional[Dict[str, Any]], keys: Optional[List[str]]) -> bool:
    return obj is not None and all(k in obj for k in (keys or []))


gateway = LLMGateway()
