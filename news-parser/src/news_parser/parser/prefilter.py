"""Префильтр — дешёвый отсев до LLM-классификатора, без LLM и без токенов.

Смотрит только на текст публикации (заголовок + тело). Мета (URL, источник, дата)
сюда не подаётся — как и в LLM-классификатор: она идёт сразу в БД.

Задача — не решать, подходит ли новость конкретному клиенту (это правила на этапе
запроса), а выкинуть то, что не нужно никому: спорт, светскую хронику, рекламу,
пустые и обрезанные тексты. Тогда в LLM уходит только поток про бизнес и экономику.

Проверки по порядку (первая сработавшая — причина отсева в articles.status_reason):
1. too_short          — текста почти нет (пустая страница, обрезано пейволлом);
2. advertising        — рекламная публикация (маркировка erid, «на правах рекламы», промокоды);
3. off_topic          — стоп-тема (спорт, шоу-бизнес, гороскопы…) и нет экономических признаков;
4. no_business_signal — ни одного экономического признака в тексте.

Попутно текст размечается правилами (макрофакторы, отрасли по ключевым словам):
эта разметка — запасной вариант, если LLM недоступна.
"""

import re
from dataclasses import dataclass, field

from news_parser.core.taxonomy import Taxonomy

HEAD_CHARS = 600  # стоп-темы ищем в заголовке и начале текста: там и видно, о чём новость
STOP_THRESHOLD = 2  # стоп-слово в заголовке весит 2, в начале текста — 1
ECONOMY_GUARD = 3  # столько «бизнес-слов» достаточно, чтобы стоп-тему не отсекать

_ADVERTISING = re.compile(
    r"(?<!\w)erid(?!\w)|на правах рекламы|(?<!\w)реклама\.\s|промокод\w*|рекламодател\w*",
    re.IGNORECASE,
)


@dataclass
class PrefilterResult:
    keep: bool
    reason: str | None = None
    factors: dict[str, int] = field(default_factory=dict)  # id -> число совпадений
    industries: dict[str, int] = field(default_factory=dict)
    business_hits: int = 0

    @property
    def labels(self) -> int:
        return sum(self.factors.values()) + sum(self.industries.values())

    @property
    def signal(self) -> int:
        return self.labels + self.business_hits


def prefilter(
    taxonomy: Taxonomy,
    *,
    title: str,
    text: str,
    min_chars: int,
    require_signal: bool,
) -> PrefilterResult:
    if len(text) < min_chars:
        return PrefilterResult(keep=False, reason=f"too_short:{len(text)}")

    full = f"{title}\n{text}"
    if _ADVERTISING.search(full):
        return PrefilterResult(keep=False, reason="advertising")

    result = PrefilterResult(
        keep=True,
        factors=taxonomy.match_factors(full),
        industries=taxonomy.match_industries(full),
        business_hits=taxonomy.business_hits(full),
    )

    stop = 2 * taxonomy.stop_hits(title) + taxonomy.stop_hits(text[:HEAD_CHARS])
    if stop >= STOP_THRESHOLD and result.labels == 0 and result.business_hits < ECONOMY_GUARD:
        return PrefilterResult(keep=False, reason="off_topic")

    if require_signal and result.signal == 0:
        return PrefilterResult(keep=False, reason="no_business_signal")

    return result


def top_ids(hits: dict[str, int], limit: int = 5) -> list[str]:
    return [k for k, _ in sorted(hits.items(), key=lambda kv: -kv[1])[:limit]]
