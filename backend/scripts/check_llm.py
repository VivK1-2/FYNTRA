"""Check the LLM settings from the backend folder (nothing here is shown in the web app).

    python scripts/check_llm.py

Prints which model is configured and makes one tiny call, so you see the real provider error
(wrong key, unknown model, spend limit) in your terminal instead of in the browser.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.llm.gateway import LLMUnavailableError, configured_models, gateway  # noqa: E402


async def main() -> int:
    print(f"Endpoint : {settings.LLM_BASE_URL}")
    print(f"Models   : {', '.join(configured_models()) or '(none set)'}")
    print(f"API key  : {'set' if settings.LLM_API_KEY else 'MISSING (set LLM_API_KEY in .env)'}")
    try:
        res = await gateway.complete([{"role": "user", "content": "Reply with the single word: pong"}], max_tokens=50)
        print(f"\nOK (tiny call): {res.model_name} answered in {res.latency_ms} ms: {res.text!r}")
        # A call shaped like a real Ask: long context, JSON answer, same token limit.
        context = " ".join(f"Passage {i}: the company lists supply chain, competition and currency risks in its annual report." for i in range(1, 60))
        msgs = [{"role": "user", "content": context + '\n\nReturn ONLY JSON: {"answer": "one sentence", "quotes": ["a short quote from the text"]}. Question: what risks are listed?'}]
        parsed, res = await gateway.complete_json(msgs, required_keys=["answer"], max_tokens=2500)
    except LLMUnavailableError as e:
        print(f"\nFAILED: {e}")
        return 1
    print(f"OK (ask-sized JSON call): {res.latency_ms} ms: {str(parsed)[:150]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
