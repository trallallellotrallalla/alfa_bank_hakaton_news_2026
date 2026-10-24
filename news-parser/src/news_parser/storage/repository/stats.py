"""Сводная статистика модуля для interface.stats()."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_parser.storage.models import AnalyticsChunk, Article, ArticleChunk, Event


def stats(s: Session) -> dict:
    by_status = dict(s.execute(select(Article.status, func.count()).group_by(Article.status)).all())
    by_source = dict(s.execute(select(Article.source_id, func.count()).group_by(Article.source_id)).all())
    return {
        "articles_by_status": by_status,
        "article_chunks": s.scalar(select(func.count()).select_from(ArticleChunk)),
        "articles_by_source": by_source,
        "events": s.scalar(select(func.count()).select_from(Event)),
        "analytics_chunks": s.scalar(select(func.count()).select_from(AnalyticsChunk)),
    }
