"""Все запросы к БД модуля — остальной код не пишет SQL сам.

Разбито по сущностям; наружу всё доступно как `from news_parser.storage import repository as repo`.
"""

from news_parser.storage.repository.analytics import (
    analytics_doc_exists,
    chunks_in_documents,
    delete_all_analytics,
    list_analytics_docs,
    search_analytics,
    select_documents,
)
from news_parser.storage.repository.articles import (
    CHUNKABLE_STATUSES,
    articles_without_chunks,
    event_articles,
    find_article_by_url,
    find_original_by_hash,
    main_articles,
    pending_llm_articles,
)
from news_parser.storage.repository.chunks import ChunkHit, search_chunks, widen_vector_search
from news_parser.storage.repository.events import (
    ScoredEvent,
    count_event_sources,
    get_event,
    latest_events,
    nearest_event,
    search_events,
)
from news_parser.storage.repository.filters import EventFilters, matched_labels
from news_parser.storage.repository.llm_usage import DbUsageStore
from news_parser.storage.repository.stats import stats

__all__ = [
    "CHUNKABLE_STATUSES", "ChunkHit", "DbUsageStore", "EventFilters", "ScoredEvent",
    "analytics_doc_exists", "chunks_in_documents", "delete_all_analytics", "select_documents", "articles_without_chunks", "count_event_sources", "event_articles",
    "find_article_by_url", "find_original_by_hash", "get_event", "latest_events", "list_analytics_docs",
    "main_articles", "matched_labels", "nearest_event", "pending_llm_articles", "search_analytics",
    "search_chunks", "search_events", "stats", "widen_vector_search",
]
