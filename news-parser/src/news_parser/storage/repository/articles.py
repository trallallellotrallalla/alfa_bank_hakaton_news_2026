"""Статьи: поиск известных (по URL и хешу текста), очереди на дообработку, статьи событий."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_parser.storage.models import Article, ArticleChunk, Event


def find_article_by_url(s: Session, url: str) -> Article | None:
    return s.scalar(select(Article).where(Article.url == url).order_by(Article.id).limit(1))


def find_original_by_hash(s: Session, content_hash: str) -> Article | None:
    return s.scalar(
        select(Article)
        .where(Article.content_hash == content_hash, Article.status.not_in(["duplicate", "filtered"]))
        .order_by(Article.id)
        .limit(1)
    )


CHUNKABLE_STATUSES = ("extracted", "rules_only", "pending_llm", "structured")


def articles_without_chunks(s: Session, *, limit: int) -> list[Article]:
    has_chunks = select(ArticleChunk.id).where(ArticleChunk.article_id == Article.id).exists()
    return list(
        s.scalars(
            select(Article)
            .where(Article.status.in_(CHUNKABLE_STATUSES), Article.event_id.is_not(None), ~has_chunks)
            .order_by(Article.id)
            .limit(limit)
        )
    )


def pending_llm_articles(s: Session, *, max_age_hours: int = 48, limit: int = 50) -> list[Article]:
    since = datetime.now(UTC) - timedelta(hours=max_age_hours)
    return list(
        s.scalars(
            select(Article)
            .where(Article.status == "pending_llm", Article.fetched_at >= since)
            .order_by(Article.trust.desc(), Article.fetched_at.desc())
            .limit(limit)
        )
    )


def main_articles(s: Session, event_ids: list[int]) -> dict[int, Article]:
    """Главная статья каждого события (та, что даёт событию заголовок и саммари)."""
    if not event_ids:
        return {}
    rows = s.execute(
        select(Event.id, Article).join(Article, Article.id == Event.main_article_id).where(Event.id.in_(event_ids))
    ).all()
    return {event_id: article for event_id, article in rows}


def event_articles(s: Session, event_ids: list[int]) -> dict[int, list[Article]]:
    out: dict[int, list[Article]] = {i: [] for i in event_ids}
    if not event_ids:
        return out
    rows = s.scalars(
        select(Article).where(Article.event_id.in_(event_ids), Article.status != "filtered").order_by(Article.id)
    )
    for a in rows:
        out[a.event_id].append(a)
    return out
