"""Дешёвый фильтр до LLM: отсекает мусор и нерелевантное, размечает очевидное правилами.

Задача — чтобы в LLM уходила только малая доля потока (бюджет токенов ограничен).
"""

from dataclasses import dataclass, field

from news_parser.taxonomy import Taxonomy


@dataclass
class PrefilterResult:
    keep: bool
    reason: str | None = None
    factors: dict[str, int] = field(default_factory=dict)  # id -> число совпадений
    industries: dict[str, int] = field(default_factory=dict)
    business_hits: int = 0

    @property
    def signal(self) -> int:
        return sum(self.factors.values()) + sum(self.industries.values()) + self.business_hits


def prefilter(
    taxonomy: Taxonomy,
    *,
    title: str,
    text: str,
    url: str | None,
    min_chars: int,
    require_signal: bool,
) -> PrefilterResult:
    full = f"{title}\n{text}"

    if len(text) < min_chars:
        return PrefilterResult(keep=False, reason=f"too_short:{len(text)}")

    if url and any(part in url.lower() for part in taxonomy.stop_url_parts):
        return PrefilterResult(keep=False, reason="stop_url")

    result = PrefilterResult(
        keep=True,
        factors=taxonomy.match_factors(full),
        industries=taxonomy.match_industries(full),
        business_hits=taxonomy.business_hits(full),
    )

    # Стоп-слова в заголовке и ни одного бизнес-признака — это спорт/шоу-бизнес.
    if taxonomy.stop_hits(title) and not result.factors and result.business_hits < 2:
        return PrefilterResult(keep=False, reason="stop_topic")

    if require_signal and result.signal == 0:
        return PrefilterResult(keep=False, reason="no_business_signal")

    return result


def top_ids(hits: dict[str, int], limit: int = 5) -> list[str]:
    return [k for k, _ in sorted(hits.items(), key=lambda kv: -kv[1])[:limit]]
