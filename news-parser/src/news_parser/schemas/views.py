"""Форматы параметров и результатов функций интерфейса (interface.py) для событий, статей,
аналитики и ручного добавления новостей. Функции возвращают их как обычный JSON (dict)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class IngestRequest(BaseModel):
    """Ручное добавление новости: либо url (текст скачаем), либо title + text."""

    url: str | None = None
    title: str | None = None
    text: str | None = None
    published_at: datetime | None = None
    source_name: str = "Ручной ввод"

    @model_validator(mode="after")
    def _need_url_or_text(self) -> "IngestRequest":
        if not self.url and not self.text:
            raise ValueError("нужен url или text")
        return self


class IngestResponse(BaseModel):
    status: str
    article_id: int | None
    event_id: int | None
    reason: str | None = None


class EventSearchRequest(BaseModel):
    """Поиск событий. Измерения (факторы, отрасли, ОКВЭД, регионы, страны)
    объединяются через ИЛИ (match=any) или И (match=all)."""

    query: str | None = Field(None, description="Текстовый запрос для семантического поиска")
    macro_factors: list[str] | None = None
    industries: list[str] | None = None
    okved: list[str] | None = Field(None, description="Коды ОКВЭД клиента, напр. ['41.20']")
    regions: list[str] | None = None
    countries: list[str] | None = None
    event_types: list[str] | None = None
    match: Literal["any", "all"] = "any"
    include_federal: bool = True
    include_structured: bool = True
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_sources: int = 1
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class SourceRef(BaseModel):
    article_id: int
    source_id: str
    source_name: str
    title: str
    url: str | None
    published_at: datetime | None
    trust: float
    status: str


class EventOut(BaseModel):
    id: int
    title: str
    summary: str
    event_type: str
    direction: str
    horizon: str
    macro_factors: list[str]
    industries: list[str]
    okved: list[str]
    regions: list[str]
    countries: list[str]
    entities: list[dict]
    is_structured: bool
    first_seen_at: datetime
    last_seen_at: datetime
    n_articles: int
    n_sources: int
    max_trust: float
    main_article_id: int | None


class EventDetail(EventOut):
    # факты/цифры главной статьи — для «Что произошло?» с разделением confirmed
    main_extraction: dict | None = None
    sources: list[SourceRef]


class ScoreParts(BaseModel):
    score: float
    similarity: float | None
    recency: float
    source_weight: float
    matched: dict[str, list[str]]


class EventHit(BaseModel):
    event: EventOut
    ranking: ScoreParts


class ArticleDetail(BaseModel):
    id: int
    source_id: str
    source_name: str
    url: str | None
    title: str
    text: str
    published_at: datetime | None
    fetched_at: datetime
    status: str
    status_reason: str | None
    trust: float
    extraction: dict | None
    extraction_meta: dict | None
    event_id: int | None
    cluster_similarity: float | None


class AnalyticsSearchRequest(BaseModel):
    query: str | None = None
    macro_factors: list[str] | None = None
    industries: list[str] | None = None
    limit: int = Field(5, ge=1, le=50)


class AnalyticsHit(BaseModel):
    id: int
    origin: str  # всегда alfa_bank — позиция банка, не вывод модели
    doc_id: str
    doc_title: str
    file_name: str
    page_from: int | None
    page_to: int | None
    text: str
    macro_factors: list[str]
    industries: list[str]
    similarity: float | None
