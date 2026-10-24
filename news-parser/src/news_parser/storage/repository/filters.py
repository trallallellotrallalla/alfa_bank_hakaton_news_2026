"""Фильтры событий по тегам — SQL-сторона жёстких правил.

EventFilters описывает, какие теги должны совпасть; _apply_filters превращает это в WHERE;
matched_labels объясняет, какие именно теги совпали (для трассировки «почему отобрано»).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, func, or_

from news_parser.storage.models import Event


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
    require_business_tags: bool = False  # у события должен быть хотя бы один макрофактор или отрасль


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
    if f.require_business_tags:
        q = q.where(or_(func.cardinality(Event.macro_factors) > 0, func.cardinality(Event.industries) > 0))
    conds = _dimension_conditions(f)
    if conds:
        q = q.where(and_(*conds) if f.match == "all" else or_(*conds))
    return q


def matched_labels(e: Event, f: EventFilters) -> dict[str, list[str]]:
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
