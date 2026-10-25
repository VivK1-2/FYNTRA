import json

import httpx
import pytest

from app.core.config import settings
from app.llm.gateway import LLMGateway, LLMUnavailableError, configured_models


@pytest.fixture(autouse=True)
def llm_settings(monkeypatch):
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://llm.test/v1")
    monkeypatch.setattr(settings, "LLM_API_KEY", "k")
    monkeypatch.setattr(settings, "LLM_MODEL", "main")
    monkeypatch.setattr(settings, "LLM_FALLBACK_MODEL", "backup")


def _gw(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LLMGateway(client=client, max_retries=1, backoff=0)


def _chat(text):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}], "usage": {"total_tokens": 5}})


async def test_model_success_uses_configured_endpoint_and_key():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"], seen["model"] = str(req.url), req.headers["authorization"], json.loads(req.content)["model"]
        return _chat("hello")

    res = await _gw(handler).complete([{"role": "user", "content": "hi"}])
    assert res.text == "hello" and res.model_name == "main" and res.attempts == ["main:ok"]
    assert seen == {"url": "https://llm.test/v1/chat/completions", "auth": "Bearer k", "model": "main"}


async def test_falls_back_when_model_keeps_failing():
    def handler(req):
        return httpx.Response(503) if json.loads(req.content)["model"] == "main" else _chat("from backup")

    res = await _gw(handler).complete([{"role": "user", "content": "hi"}])
    assert res.model_name == "backup" and res.attempts == ["main:fail", "backup:ok"]


async def test_bad_key_skips_retries_and_falls_back():
    calls = []

    def handler(req):
        m = json.loads(req.content)["model"]
        calls.append(m)
        return httpx.Response(401, text="bad key") if m == "main" else _chat("ok")

    res = await _gw(handler).complete([{"role": "user", "content": "hi"}])
    assert calls.count("main") == 1 and res.model_name == "backup"


async def test_all_fail_raises():
    with pytest.raises(LLMUnavailableError):
        await _gw(lambda req: httpx.Response(500)).complete([{"role": "user", "content": "hi"}])


async def test_missing_key_is_reported_without_calling_the_provider(monkeypatch):
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    with pytest.raises(LLMUnavailableError, match="LLM_API_KEY"):
        await _gw(lambda req: pytest.fail("must not call")).complete([{"role": "user", "content": "hi"}])


def test_fallback_is_optional_and_not_duplicated(monkeypatch):
    monkeypatch.setattr(settings, "LLM_FALLBACK_MODEL", "")
    assert configured_models() == ["main"]
    monkeypatch.setattr(settings, "LLM_FALLBACK_MODEL", "main")
    assert configured_models() == ["main"]


async def test_json_mode_repairs_once_on_the_same_model():
    replies = iter(["not json", '{"answer": "x", "enough_evidence": true}'])
    models = []

    def handler(req):
        models.append(json.loads(req.content)["model"])
        return _chat(next(replies))

    parsed, res = await _gw(handler).complete_json([{"role": "user", "content": "q"}], required_keys=["answer"])
    assert parsed["answer"] == "x" and models == ["main", "main"]


async def test_json_mode_accepts_fenced_json():
    parsed, _ = await _gw(lambda req: _chat('```json\n{"answer": "y"}\n```')).complete_json(
        [{"role": "user", "content": "q"}], required_keys=["answer"])
    assert parsed == {"answer": "y"}
