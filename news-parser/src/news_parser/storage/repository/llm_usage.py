"""Журнал вызовов LLM и учёт дневного бюджета токенов (таблица llm_calls)."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from news_parser.storage.db import session_scope
from news_parser.storage.models import LlmCall


class DbUsageStore:
    """Пишет журнал вызовов LLM в отдельной транзакции: запись сохранится,
    даже если обработка статьи потом упадёт и откатится."""

    def tokens_used_today(self) -> int:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        with session_scope() as s:
            return int(
                s.scalar(select(func.coalesce(func.sum(LlmCall.total_tokens), 0)).where(LlmCall.created_at >= start))
                or 0
            )

    def log_call(self, *, model, purpose, article_id, prompt_tokens, completion_tokens, latency_ms, ok, error) -> int:
        with session_scope() as s:
            call = LlmCall(
                model=model,
                purpose=purpose,
                article_id=article_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_ms=latency_ms,
                ok=ok,
                error=error,
            )
            s.add(call)
            s.flush()
            return call.id
