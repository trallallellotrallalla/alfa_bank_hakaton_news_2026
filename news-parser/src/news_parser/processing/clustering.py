"""Склейка статей в события.

Одну новость перепечатывают десятки СМИ разными словами — хеш это не ловит.
Поэтому новая статья сравнивается по эмбеддингу с недавними событиями: если
близость выше порога, статья становится ещё одним источником события,
иначе создаётся новое событие.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from news_parser.schemas.extraction import Extraction
from news_parser.storage import repository as repo
from news_parser.storage.models import Article, Event
from news_parser.taxonomy import Taxonomy

MAX_ENTITIES = 30


def _union(a: list[str], b: list[str]) -> list[str]:
    return list(dict.fromkeys([*a, *b]))


def _merge_entities(a: list[dict], b: list[dict]) -> list[dict]:
    seen = {e["name"].lower(): e for e in a}
    for e in b:
        seen.setdefault(e["name"].lower(), e)
    return list(seen.values())[:MAX_ENTITIES]


def _new_event(article: Article, ex: Extraction, taxonomy: Taxonomy, *, structured: bool) -> Event:
    seen_at = article.published_at or datetime.now(UTC)
    return Event(
        title=article.title,
        summary=ex.summary,
        event_type=ex.event_type,
        direction=ex.direction,
        horizon=ex.horizon,
        macro_factors=list(ex.macro_factors),
        industries=list(ex.industries),
        okved=taxonomy.okved_for(ex.industries),
        regions=list(ex.regions),
        countries=list(ex.countries),
        entities=[e.model_dump() for e in ex.entities][:MAX_ENTITIES],
        embedding=article.embedding,
        main_article_id=article.id,
        is_structured=structured,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        n_articles=1,
        n_sources=1,
        max_trust=article.trust,
    )


def assign_event(
    s: Session,
    article: Article,
    ex: Extraction,
    taxonomy: Taxonomy,
    *,
    threshold: float,
    window_hours: int,
    structured: bool = False,
    prefer_as_main: bool = True,
) -> Event:
    """Привязывает статью к существующему событию или создаёт новое.

    prefer_as_main=False для статей без LLM-разметки: их саммари хуже, поэтому
    они не перехватывают «лицо» события у статьи, размеченной моделью.
    """
    if not structured and article.embedding is not None:
        since = datetime.now(UTC) - timedelta(hours=window_hours)
        found = repo.nearest_event(s, article.embedding, since=since)
        if found and found[1] >= threshold:
            event, similarity = found
            article.event_id = event.id
            article.cluster_similarity = round(similarity, 4)
            _merge_into(s, event, article, ex, taxonomy, prefer_as_main)
            return event

    event = _new_event(article, ex, taxonomy, structured=structured)
    s.add(event)
    s.flush()
    article.event_id = event.id
    article.cluster_similarity = 1.0
    return event


def _merge_into(
    s: Session, event: Event, article: Article, ex: Extraction, taxonomy: Taxonomy, prefer_as_main: bool
) -> None:
    seen_at = article.published_at or datetime.now(UTC)
    event.first_seen_at = min(event.first_seen_at, seen_at)
    event.last_seen_at = max(event.last_seen_at, seen_at)
    event.n_articles += 1
    s.flush()
    event.n_sources = repo.count_event_sources(s, event.id)

    event.macro_factors = _union(event.macro_factors, ex.macro_factors)
    event.industries = _union(event.industries, ex.industries)
    event.okved = taxonomy.okved_for(event.industries)
    event.regions = _union(event.regions, ex.regions)
    event.countries = _union(event.countries, ex.countries)
    event.entities = _merge_entities(event.entities, [e.model_dump() for e in ex.entities])

    # «Лицо» события — статья самого доверенного источника.
    if prefer_as_main and article.trust > event.max_trust:
        event.title = article.title
        event.summary = ex.summary
        event.event_type = ex.event_type
        event.direction = ex.direction
        event.horizon = ex.horizon
        event.main_article_id = article.id
    event.max_trust = max(event.max_trust, article.trust)


def refresh_event_after_llm(s: Session, article: Article, ex: Extraction, taxonomy: Taxonomy) -> None:
    """Статья была размечена правилами (LLM была недоступна), теперь пришла
    LLM-разметка: дополняем метки события и, если статья — его «лицо», саммари."""
    if article.event_id is None:
        return
    event = s.get(Event, article.event_id)
    if event is None:
        return
    event.macro_factors = _union(event.macro_factors, ex.macro_factors)
    event.industries = _union(event.industries, ex.industries)
    event.okved = taxonomy.okved_for(event.industries)
    event.regions = _union(event.regions, ex.regions)
    event.countries = _union(event.countries, ex.countries)
    event.entities = _merge_entities(event.entities, [e.model_dump() for e in ex.entities])
    if event.main_article_id == article.id:
        event.summary = ex.summary
        event.event_type = ex.event_type
        event.direction = ex.direction
        event.horizon = ex.horizon


def attach_duplicate(s: Session, article: Article, original: Article) -> None:
    """Точный дубль (тот же текст у другого источника) — просто ещё один источник события."""
    article.event_id = original.event_id
    article.cluster_similarity = 1.0
    if original.event_id is None:
        return
    event = s.get(Event, original.event_id)
    if event is None:
        return
    event.n_articles += 1
    s.flush()
    event.n_sources = repo.count_event_sources(s, event.id)
    event.max_trust = max(event.max_trust, article.trust)
