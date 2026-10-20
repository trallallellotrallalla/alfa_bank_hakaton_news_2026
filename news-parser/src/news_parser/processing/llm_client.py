"""Клиент к OpenAI-совместимому API разрешённых моделей.

Каждый вызов журналируется (таблица llm_calls), перед вызовом проверяется
дневной бюджет токенов — общий ключ организаторов ограничен по деньгам.
"""

import logging
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


class LlmUnavailable(Exception):
    """LLM не настроена, недоступна или исчерпан бюджет — вызывающий код
    должен деградировать до правил, а не падать."""


class BudgetExceeded(LlmUnavailable):
    pass


class UsageStore(Protocol):
    def tokens_used_today(self) -> int: ...

    def log_call(
        self,
        *,
        model: str,
        purpose: str,
        article_id: int | None,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        ok: bool,
        error: str | None,
    ) -> int: ...


@dataclass
class LlmResponse:
    content: str
    call_id: int
    total_tokens: int


class LlmClient:
    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        model: str,
        usage: UsageStore,
        daily_budget: int,
        timeout_s: float = 90.0,
        json_mode: bool = True,
    ):
        self.api_url = api_url.rstrip("/")
        self.model = model
        self.usage = usage
        self.daily_budget = daily_budget
        self.json_mode = json_mode
        self._http = httpx.Client(
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_url)

    def chat(
        self,
        messages: list[dict],
        *,
        purpose: str,
        article_id: int | None = None,
        max_tokens: int = 1200,
    ) -> LlmResponse:
        if not self.configured:
            raise LlmUnavailable("LLM_API_URL не задан")
        used = self.usage.tokens_used_today()
        if used >= self.daily_budget:
            raise BudgetExceeded(f"дневной бюджет исчерпан: {used}/{self.daily_budget}")

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        try:
            resp = self._http.post(f"{self.api_url}/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage") or {}
        except Exception as exc:  # сеть, 4xx/5xx, неожиданный формат ответа
            latency = int((time.monotonic() - started) * 1000)
            self.usage.log_call(
                model=self.model, purpose=purpose, article_id=article_id,
                prompt_tokens=0, completion_tokens=0, latency_ms=latency,
                ok=False, error=repr(exc)[:2000],
            )
            log.warning("LLM call failed (%s): %r", purpose, exc)
            raise LlmUnavailable(str(exc)) from exc

        latency = int((time.monotonic() - started) * 1000)
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        call_id = self.usage.log_call(
            model=self.model, purpose=purpose, article_id=article_id,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            latency_ms=latency, ok=True, error=None,
        )
        return LlmResponse(content=content, call_id=call_id, total_tokens=prompt_tokens + completion_tokens)
