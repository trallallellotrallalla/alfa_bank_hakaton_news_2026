"""События: склейка (ближайшее событие), карточка события, поиск и лента для search_events / latest_events."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from news_parser.storage.models import Article, Event
from news_parser.storage.repository.filters import EventFilters, _apply_filters, matched_labels


def nearest_event(s: Session, embedding: list[float], *, since: datetime) -> tuple[Event, float] | None:
    """Ближайшее по смыслу «живое» событие из СМИ (структурированные не склеиваем)."""
    distance = Event.embedding.cosine_distance(embedding)
    row = s.execute(
        select(Event, distance.label("d"))
        .where(Event.last_seen_at >= since, Event.is_structured.is_(False), Event.embedding.is_not(None))
        .order_by(distance)
        .limit(1)
    ).first()
    if row is None:
        return None
    return row[0], 1.0 - float(row[1])


def count_event_sources(s: Session, event_id: int) -> int:
    return int(s.scalar(select(func.count(func.distinct(Article.source_id))).where(Article.event_id == event_id)) or 0)


def get_event(s: Session, event_id: int) -> Event | None:
    return s.scalar(select(Event).options(selectinload(Event.articles)).where(Event.id == event_id))


@dataclass
class ScoredEvent:
    event: Event
    score: float
    similarity: float | None
    recency: float
    source_weight: float
    matched: dict[str, list[str]]  # по каким меткам совпало — для объяснимости


def search_events(
    s: Session,
    f: EventFilters,
    *,
    query_embedding: list[float] | None = None,
    limit: int = 20,
    offset: int = 0,
    half_life_hours: float = 72.0,
) -> list[ScoredEvent]:
    """Фильтры по меткам + (опционально) векторная близость + свежесть + вес источников.

    score = 0.6*similarity + 0.25*recency + 0.15*source_weight   (с запросом)
    score = 0.7*recency + 0.3*source_weight                       (без запроса)
    Все компоненты отдаются наружу, чтобы агент мог объяснить ранжирование.
    """
    q = _apply_filters(select(Event), f)
    candidates_limit = (limit + offset) * 5
    if query_embedding is not None:
        distance = Event.embedding.cosine_distance(query_embedding)
        rows = s.execute(
            q.add_columns(distance.label("d"))
            .where(Event.embedding.is_not(None))
            .order_by(distance)
            .limit(candidates_limit)
        ).all()
        pairs = [(r[0], 1.0 - float(r[1])) for r in rows]
    else:
        rows = s.scalars(q.order_by(Event.last_seen_at.desc()).limit(candidates_limit)).all()
        pairs = [(e, None) for e in rows]

    now = datetime.now(UTC)
    scored = []
    for e, sim in pairs:
        age_h = max((now - e.last_seen_at).total_seconds() / 3600, 0)
        recency = math.exp(-math.log(2) * age_h / half_life_hours)
        source_weight = min(1.0, 0.5 * e.max_trust + 0.5 * min(e.n_sources, 5) / 5)
        if sim is None:
            score = 0.7 * recency + 0.3 * source_weight
        else:
            score = 0.6 * sim + 0.25 * recency + 0.15 * source_weight
        scored.append(ScoredEvent(e, round(score, 4), sim, round(recency, 4), round(source_weight, 4), matched_labels(e, f)))
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[offset : offset + limit]


def latest_events(s: Session, *, limit: int, offset: int) -> list[Event]:
    return list(s.scalars(select(Event).order_by(Event.last_seen_at.desc()).limit(limit).offset(offset)))
