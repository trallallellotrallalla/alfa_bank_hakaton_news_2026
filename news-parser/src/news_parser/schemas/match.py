"""Контракт match_profile / match_client: профиль клиента -> готовый контекст для локального агента.

Агент не ходит по URL: всё, что нужно LLM, лежит в ответе — саммари, факты
с пометкой confirmed, чанки текста статей и чанки аналитики Альфа-Банка.
URL оставлены только для пользователя («перейти к первоисточнику»).
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class MatchOptions(BaseModel):
    window_days: int | None = Field(None, ge=1, le=365, description="По умолчанию MATCH_WINDOW_DAYS")
    limit_news: int = Field(8, ge=1, le=30)
    chunks_per_news: int = Field(2, ge=1, le=6)
    analytics_per_news: int = Field(3, ge=0, le=5, description="фрагментов аналитики к каждой новости")
    min_similarity: float | None = Field(None, ge=0, le=1, description="По умолчанию MATCH_MIN_SIMILARITY")
    include_structured: bool = True  # события из ЦБ/биржи (курсы, индексы)
    render_context: bool = True  # собрать готовый текст для промпта
    max_context_chars: int = Field(12000, ge=1000, le=100000)


class AspectOut(BaseModel):
    id: str
    title: str
    query: str
    weight: float
    filters: dict[str, list[str]]
    reason: str


class AspectMatch(BaseModel):
    aspect_id: str
    aspect_title: str
    similarity: float
    matched_labels: dict[str, list[str]]  # какие метки события совпали с фильтрами аспекта


class NewsChunk(BaseModel):
    chunk_id: int
    article_id: int
    source_name: str
    published_at: datetime | None
    text: str
    similarity: float
    aspect_id: str


class NewsSource(BaseModel):
    article_id: int
    source_name: str
    url: str | None  # только для пользователя; агенту не нужен
    published_at: datetime | None


class NewsItem(BaseModel):
    ref: str  # N1, N2… — на них LLM ссылается в ответе
    event_id: int
    title: str
    summary: str
    event_type: str
    direction: str
    horizon: str
    first_seen_at: datetime
    last_seen_at: datetime
    macro_factors: list[str]
    industries: list[str]
    regions: list[str]
    countries: list[str]
    facts: list[dict]  # [{"text", "confirmed"}] из разметки главной статьи
    extraction_method: str | None  # llm | rules | structured
    n_sources: int
    # Ранжирования пока нет: порядок новостей = сходство из векторного поиска.
    similarity: float  # лучшее сходство чанков новости с аспектами клиента
    passed_rules: bool  # false — новость из запасного поиска (правила пропустили слишком мало)
    matched_aspects: list[AspectMatch]
    chunks: list[NewsChunk]
    sources: list[NewsSource]
    related_analytics: list[str]  # ref'ы A1… из bank_analytics


class AnalyticsItem(BaseModel):
    ref: str  # A1, A2…
    chunk_id: int
    origin: str  # alfa_bank — позиция банка, а не вывод модели
    doc_title: str
    file_name: str
    chunk_index: int
    page_from: int | None
    page_to: int | None
    text: str
    similarity: float  # сходство с новостью, к которой фрагмент подобран
    related_news: list[str]
    # документ целиком (профиль через LLM; без LLM — None)
    doc_summary: str | None = None  # главные тезисы банка в документе
    doc_stance: str | None = None  # hawkish | dovish | neutral | risk
    doc_date: date | None = None


class ProfileMatchResponse(BaseModel):
    profile_uid: str | None
    profile_summary: str
    aspects: list[AspectOut]
    news: list[NewsItem]
    bank_analytics: list[AnalyticsItem]
    context: str | None  # готовый текст для промпта локальной LLM
    meta: dict


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=256)
    kind: str = Field("query", pattern="^(query|passage)$")
