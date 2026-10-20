"""Все запросы к БД модуля собраны здесь — остальной код не пишет SQL сам."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from news_parser.storage.db import session_scope
from news_parser.storage.models import AnalyticsChunk, Article, Event, LlmCall

# --- журнал и бюджет LLM ---


class DbUsageStore:
    """Пишет журнал вызовов LLM в отдельной транзакции: запись сохранится,
    даже если обработка статьи потом упадёт и откатится."""

    def tokens_used_today(self) -> int:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        with session_scope() as s:
            return int(
                s.scalar(select(func.coalesce(func.sum(LlmCall.total_tokens), 0)).where(LlmCall.created_at >= start))
                or 0
            )

    def log_call(self, *, model, purpose, article_id, prompt_tokens, completion_tokens, latency_ms, ok, error) -> int:
        with session_scope() as s:
            call = LlmCall(
                model=model,
                purpose=purpose,
                article_id=article_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_ms=latency_ms,
                ok=ok,
                error=error,
            )
            s.add(call)
            s.flush()
            return call.id


# --- статьи ---


def find_article_by_url(s: Session, url: str) -> Article | None:
    return s.scalar(select(Article).where(Article.url == url).order_by(Article.id).limit(1))


def find_original_by_hash(s: Session, content_hash: str) -> Article | None:
    return s.scalar(
        select(Article)
        .where(Article.content_hash == content_hash, Article.status.not_in(["duplicate", "filtered"]))
        .order_by(Article.id)
        .limit(1)
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


# --- события ---


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
class EventFilters:
    macro_factors: list[str] | None = None
    industries: list[str] | None = None
    okved: list[str] | None = None  # коды клиента в любом виде: "41.20", "41"
    regions: list[str] | None = None
    countries: list[str] | None = None
    event_types: list[str] | None = None
    match: str = "any"  # any — достаточно совпасть по одному из измерений; all — по всем заданным
    include_federal: bool = True  # для фильтра по регионам добавлять общероссийские события
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_sources: int = 1
    include_structured: bool = True


@dataclass
class ScoredEvent:
    event: Event
    score: float
    similarity: float | None
    recency: float
    source_weight: float
    matched: dict[str, list[str]]  # по каким меткам совпало — для объяснимости


def _okved_prefixes(codes: list[str]) -> list[str]:
    return sorted({c.strip()[:2] for c in codes if c and c.strip()[:2].isdigit()})


def _dimension_conditions(f: EventFilters) -> list:
    conds = []
    if f.macro_factors:
        conds.append(Event.macro_factors.overlap(f.macro_factors))
    if f.industries:
        conds.append(Event.industries.overlap(f.industries))
    if f.okved and (prefixes := _okved_prefixes(f.okved)):
        conds.append(Event.okved.overlap(prefixes))
    if f.regions:
        regions = list(f.regions) + (["Россия"] if f.include_federal else [])
        conds.append(Event.regions.overlap(regions))
    if f.countries:
        conds.append(Event.countries.overlap(f.countries))
    return conds


def _apply_filters(q: Select, f: EventFilters) -> Select:
    if f.date_from:
        q = q.where(Event.last_seen_at >= f.date_from)
    if f.date_to:
        q = q.where(Event.first_seen_at <= f.date_to)
    if f.min_sources > 1:
        q = q.where(Event.n_sources >= f.min_sources)
    if f.event_types:
        q = q.where(Event.event_type.in_(f.event_types))
    if not f.include_structured:
        q = q.where(Event.is_structured.is_(False))
    conds = _dimension_conditions(f)
    if conds:
        q = q.where(and_(*conds) if f.match == "all" else or_(*conds))
    return q


def _matched(e: Event, f: EventFilters) -> dict[str, list[str]]:
    m: dict[str, list[str]] = {}
    pairs = [
        ("macro_factors", e.macro_factors, f.macro_factors),
        ("industries", e.industries, f.industries),
        ("okved", e.okved, _okved_prefixes(f.okved or [])),
        ("regions", e.regions, (f.regions or []) + (["Россия"] if f.regions and f.include_federal else [])),
        ("countries", e.countries, f.countries),
    ]
    for name, have, want in pairs:
        if want and (common := sorted(set(have) & set(want))):
            m[name] = common
    return m


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
        scored.append(ScoredEvent(e, round(score, 4), sim, round(recency, 4), round(source_weight, 4), _matched(e, f)))
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[offset : offset + limit]


def latest_events(s: Session, *, limit: int, offset: int) -> list[Event]:
    return list(s.scalars(select(Event).order_by(Event.last_seen_at.desc()).limit(limit).offset(offset)))


# --- аналитика ---


def analytics_doc_exists(s: Session, doc_id: str) -> bool:
    return s.scalar(select(AnalyticsChunk.id).where(AnalyticsChunk.doc_id == doc_id).limit(1)) is not None


def search_analytics(
    s: Session,
    *,
    query_embedding: list[float] | None,
    macro_factors: list[str] | None = None,
    industries: list[str] | None = None,
    limit: int = 5,
) -> list[tuple[AnalyticsChunk, float | None]]:
    q = select(AnalyticsChunk)
    conds = []
    if macro_factors:
        conds.append(AnalyticsChunk.macro_factors.overlap(macro_factors))
    if industries:
        conds.append(AnalyticsChunk.industries.overlap(industries))
    if conds:
        q = q.where(or_(*conds))
    if query_embedding is None:
        return [(c, None) for c in s.scalars(q.order_by(AnalyticsChunk.id).limit(limit))]
    distance = AnalyticsChunk.embedding.cosine_distance(query_embedding)
    rows = s.execute(q.add_columns(distance.label("d")).order_by(distance).limit(limit)).all()
    return [(r[0], round(1.0 - float(r[1]), 4)) for r in rows]


def list_analytics_docs(s: Session) -> list[dict]:
    rows = s.execute(
        select(
            AnalyticsChunk.doc_id,
            AnalyticsChunk.doc_title,
            AnalyticsChunk.file_name,
            func.count(AnalyticsChunk.id),
        ).group_by(AnalyticsChunk.doc_id, AnalyticsChunk.doc_title, AnalyticsChunk.file_name)
    ).all()
    return [{"doc_id": r[0], "title": r[1], "file_name": r[2], "chunks": r[3]} for r in rows]


# --- статистика ---


def stats(s: Session) -> dict:
    by_status = dict(s.execute(select(Article.status, func.count()).group_by(Article.status)).all())
    by_source = dict(s.execute(select(Article.source_id, func.count()).group_by(Article.source_id)).all())
    return {
        "articles_by_status": by_status,
        "articles_by_source": by_source,
        "events": s.scalar(select(func.count()).select_from(Event)),
        "analytics_chunks": s.scalar(select(func.count()).select_from(AnalyticsChunk)),
    }
