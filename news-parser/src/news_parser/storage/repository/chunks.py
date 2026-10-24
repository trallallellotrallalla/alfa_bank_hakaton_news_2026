"""Векторный поиск по чанкам статей с фильтром по тегам событий (правила + вектор одним запросом)."""

from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from news_parser.storage.models import Article, ArticleChunk, Event
from news_parser.storage.repository.filters import EventFilters, _apply_filters


@dataclass
class ChunkHit:
    chunk: ArticleChunk
    event: Event
    article: Article
    similarity: float


_pgvector_version: tuple[int, ...] | None = None


def _vector_version(s: Session) -> tuple[int, ...]:
    global _pgvector_version
    if _pgvector_version is None:
        raw = s.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")) or "0"
        _pgvector_version = tuple(int(x) for x in raw.split(".") if x.isdigit())
    return _pgvector_version


def widen_vector_search(s: Session) -> None:
    """HNSW-индекс сначала берёт ближайших соседей, потом применяются фильтры —
    при жёстких фильтрах кандидатов может не хватить. Расширяем поиск;
    iterative_scan есть только в pgvector >= 0.8 (в старых версиях параметр — ошибка)."""
    s.execute(text("SET LOCAL hnsw.ef_search = 200"))
    if _vector_version(s) >= (0, 8):
        s.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))


def search_chunks(
    s: Session,
    *,
    query_embedding: list[float],
    filters: EventFilters | None,
    limit: int,
) -> list[ChunkHit]:
    """Ближайшие по смыслу чанки статей, у чьих событий совпадают метки (если фильтры заданы)."""
    widen_vector_search(s)
    distance = ArticleChunk.embedding.cosine_distance(query_embedding)
    q = (
        select(ArticleChunk, Event, Article, distance.label("d"))
        .join(Event, Event.id == ArticleChunk.event_id)
        .join(Article, Article.id == ArticleChunk.article_id)
        .where(ArticleChunk.embedding.is_not(None))
    )
    if filters is not None:
        q = _apply_filters(q, filters)
    rows = s.execute(q.order_by(distance).limit(limit)).all()
    return [ChunkHit(r[0], r[1], r[2], 1.0 - float(r[3])) for r in rows]
