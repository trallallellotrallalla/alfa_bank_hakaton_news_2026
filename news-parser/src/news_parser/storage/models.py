"""Таблицы модуля. Все лежат в отдельной схеме БД (по умолчанию `news`),
чтобы не пересекаться с таблицами других модулей в общей базе.

articles         — каждая скачанная статья (в т.ч. дубли и отфильтрованные — чтобы не качать повторно)
events           — событие = кластер статей об одном и том же; основная единица выдачи
article_chunks   — фрагменты статей с векторами (контекст для агента)
analytics_documents — документы аналитики Альфа-Банка: выжимка, позиция банка, теги, дата
analytics_chunks — фрагменты аналитики Альфа-Банка
llm_calls        — журнал обращений к LLM (аудит + учёт дневного бюджета токенов)
"""

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from news_parser.core.settings import get_settings

_settings = get_settings()
EMBEDDING_DIM = _settings.embedding_dim


class Base(DeclarativeBase):
    metadata = MetaData(schema=_settings.db_schema)


def _str_array() -> Mapped[list[str]]:
    return mapped_column(ARRAY(String), nullable=False, server_default="{}")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(64), default="other")
    direction: Mapped[str] = mapped_column(String(16), default="neutral")
    horizon: Mapped[str] = mapped_column(String(16), default="short_term")
    macro_factors: Mapped[list[str]] = _str_array()
    industries: Mapped[list[str]] = _str_array()
    okved: Mapped[list[str]] = _str_array()
    regions: Mapped[list[str]] = _str_array()
    countries: Mapped[list[str]] = _str_array()
    entities: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default="[]")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    # статья, чей заголовок/саммари показываются как лицо события (самый доверенный источник)
    main_article_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_structured: Mapped[bool] = mapped_column(Boolean, default=False)  # из ЦБ/биржи, не из СМИ
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    n_articles: Mapped[int] = mapped_column(Integer, default=1)
    n_sources: Mapped[int] = mapped_column(Integer, default=1)
    max_trust: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    articles: Mapped[list["Article"]] = relationship(back_populates="event")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    source_name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(32))
    trust: Mapped[float] = mapped_column(Float, default=0.5)
    url: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # new | extracted | rules_only | pending_llm | structured | duplicate | filtered | failed
    status: Mapped[str] = mapped_column(String(32), index=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # schemas.Extraction
    extraction_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # schemas.ExtractionMeta
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cluster_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)

    event: Mapped[Event | None] = relationship(back_populates="articles")


class ArticleChunk(Base):
    """Фрагмент статьи (2–4 предложения) со своим вектором. Именно чанки отдаются
    агенту как контекст: локальная LLM читает их вместо того, чтобы ходить по URL."""

    __tablename__ = "article_chunks"
    __table_args__ = (UniqueConstraint("article_id", "chunk_index"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalyticsDocument(Base):
    """Документ аналитики целиком: выжимка позиции банка, теги, дата — для подбора в два шага
    (сначала документ, потом фрагменты в нём). Профиль строит LLM, без неё — правила."""

    __tablename__ = "analytics_documents"

    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 исходного файла
    file_name: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    published_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # главные тезисы банка
    stance: Mapped[str | None] = mapped_column(String(16), nullable=True)  # hawkish|dovish|neutral|risk
    macro_factors: Mapped[list[str]] = _str_array()
    industries: Mapped[list[str]] = _str_array()
    text_method: Mapped[str] = mapped_column(String(32))  # text_layer | vision | ocr_txt | text
    profile_method: Mapped[str] = mapped_column(String(16))  # llm | rules
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalyticsChunk(Base):
    __tablename__ = "analytics_chunks"
    __table_args__ = (UniqueConstraint("doc_id", "chunk_index"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)  # sha256 файла
    doc_title: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    macro_factors: Mapped[list[str]] = _str_array()
    industries: Mapped[list[str]] = _str_array()
    origin: Mapped[str] = mapped_column(String(32), default="alfa_bank")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    model: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(64))
    article_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
