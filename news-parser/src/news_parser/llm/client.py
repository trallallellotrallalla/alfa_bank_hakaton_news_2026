"""Клиент к OpenAI-совместимому API разрешённых моделей.

Каждый вызов журналируется (таблица llm_calls), перед вызовом проверяется
дневной бюджет токенов — общий ключ организаторов ограничен по деньгам.
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


# Разрешённые в кейсе модели (Приложение 3 ТЗ) — ID как в API организаторов.
# Другие модели использовать нельзя: клиент с чужой моделью считается не настроенным.
ALLOWED_MODELS = frozenset({
    "google/gemma-4-26b-a4b-it",
    "z-ai/glm-5.3-flash",
    "qwen/qwen3.6-35b-a3b",
    "deepseek/deepseek-v4.1-flash",
    "qwen/qwen3-vl-30b-a3b-instruct",
    "moonshotai/kimi-k2.6",
})

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(content: str) -> str:
    """Qwen3 / GLM могут начинать ответ с рассуждений в <think>…</think> — убираем их."""
    content = _THINK.sub("", content)
    # незакрытый <think> (ответ обрезан по max_tokens посреди рассуждений)
    head, sep, _ = content.partition("<think>")
    return (head if sep else content).strip()


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
        json_mode: bool = False,
        max_tokens: int = 2000,
        extra_body: str = "",
        reasoning_effort: str = "none",
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.usage = usage
        self.daily_budget = daily_budget
        self.json_mode = json_mode
        self.max_tokens = max_tokens
        # Qwen3.6 через API организаторов по умолчанию «думает» перед ответом: тратит весь
        # лимит токенов на рассуждения и возвращает пустой content. reasoning_effort="none"
        # это отключает (проверено на API кейса; «/no_think» в тексте там не работает).
        self.reasoning_effort = reasoning_effort.strip()
        # доп. параметры запроса как есть (JSON), например отключение рассуждений у Qwen,
        # если API организаторов это поддерживает: {"chat_template_kwargs": {"enable_thinking": false}}
        self.extra_body: dict = json.loads(extra_body) if extra_body.strip() else {}
        self._http = httpx.Client(
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )
        if self.model not in ALLOWED_MODELS:
            log.error("LLM_MODEL=%r не из списка разрешённых моделей кейса — LLM отключена", self.model)

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.api_key and self.model in ALLOWED_MODELS)

    def why_not_configured(self) -> str:
        if not self.api_url:
            return "LLM_API_URL не задан"
        if not self.api_key:
            return "LLM_API_KEY не задан"
        return f"LLM_MODEL={self.model!r} не из списка разрешённых: {sorted(ALLOWED_MODELS)}"

    def chat(
        self,
        messages: list[dict],
        *,
        purpose: str,
        article_id: int | None = None,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        if not self.configured:
            raise LlmUnavailable(self.why_not_configured())
        used = self.usage.tokens_used_today()
        if used >= self.daily_budget:
            raise BudgetExceeded(f"дневной бюджет исчерпан: {used}/{self.daily_budget}")

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        payload.update(self.extra_body)
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        try:
            resp = self._http.post(f"{self.api_url}/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = strip_reasoning(data["choices"][0]["message"]["content"] or "")
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
