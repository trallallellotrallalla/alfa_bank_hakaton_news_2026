"""Аналитика Альфа-Банка: документы и их фрагменты, подбор к новости в два шага, поиск."""

from datetime import date

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from news_parser.storage.models import AnalyticsChunk, AnalyticsDocument
from news_parser.storage.repository.chunks import widen_vector_search


def analytics_doc_exists(s: Session, doc_id: str) -> bool:
    return s.get(AnalyticsDocument, doc_id) is not None


def delete_all_analytics(s: Session) -> None:
    s.execute(delete(AnalyticsChunk))
    s.execute(delete(AnalyticsDocument))


def select_documents(
    s: Session,
    *,
    query_embedding: list[float],
    macro_factors: list[str] | None,
    industries: list[str] | None,
    not_older_than: date | None,
    limit: int,
) -> list[tuple[AnalyticsDocument, float]]:
    """Шаг 1: документы с общими тегами (жёсткое правило), ближайшие по смыслу выжимки.
    Документы старше not_older_than отбрасываются; без даты — остаются."""
    conds = []
    if macro_factors:
        conds.append(AnalyticsDocument.macro_factors.overlap(macro_factors))
    if industries:
        conds.append(AnalyticsDocument.industries.overlap(industries))
    if not conds:
        return []
    distance = AnalyticsDocument.embedding.cosine_distance(query_embedding)
    q = select(AnalyticsDocument, distance.label("d")).where(or_(*conds), AnalyticsDocument.embedding.is_not(None))
    if not_older_than:
        q = q.where(or_(AnalyticsDocument.published_date.is_(None), AnalyticsDocument.published_date >= not_older_than))
    rows = s.execute(q.order_by(distance).limit(limit)).all()
    return [(r[0], 1.0 - float(r[1])) for r in rows]


def chunks_in_documents(
    s: Session, *, query_embedding: list[float], doc_ids: list[str], limit: int
) -> list[tuple[AnalyticsChunk, float]]:
    """Шаг 2: фрагменты выбранных документов, ближайшие по смыслу к новости."""
    if not doc_ids:
        return []
    widen_vector_search(s)
    distance = AnalyticsChunk.embedding.cosine_distance(query_embedding)
    rows = s.execute(
        select(AnalyticsChunk, distance.label("d"))
        .where(AnalyticsChunk.doc_id.in_(doc_ids), AnalyticsChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    ).all()
    return [(r[0], 1.0 - float(r[1])) for r in rows]


def search_analytics(
    s: Session,
    *,
    query_embedding: list[float] | None,
    macro_factors: list[str] | None = None,
    industries: list[str] | None = None,
    limit: int = 5,
) -> list[tuple[AnalyticsChunk, float | None]]:
    """Свободный поиск по фрагментам (функция search_analytics интерфейса)."""
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
    widen_vector_search(s)
    distance = AnalyticsChunk.embedding.cosine_distance(query_embedding)
    rows = s.execute(q.add_columns(distance.label("d")).order_by(distance).limit(limit)).all()
    return [(r[0], round(1.0 - float(r[1]), 4)) for r in rows]


def list_analytics_docs(s: Session) -> list[dict]:
    counts = dict(
        s.execute(select(AnalyticsChunk.doc_id, func.count(AnalyticsChunk.id)).group_by(AnalyticsChunk.doc_id)).all()
    )
    docs = s.scalars(select(AnalyticsDocument).order_by(AnalyticsDocument.published_date.desc().nulls_last()))
    return [
        {
            "doc_id": d.doc_id,
            "title": d.title,
            "file_name": d.file_name,
            "published_date": d.published_date.isoformat() if d.published_date else None,
            "stance": d.stance,
            "macro_factors": d.macro_factors,
            "industries": d.industries,
            "summary": d.summary,
            "text_method": d.text_method,
            "profile_method": d.profile_method,
            "chunks": counts.get(d.doc_id, 0),
        }
        for d in docs
    ]
