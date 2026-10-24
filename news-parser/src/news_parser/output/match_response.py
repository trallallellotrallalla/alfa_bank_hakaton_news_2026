"""Сборка ответа match_client / match_profile из итогов отбора (filtering.matcher.Selection):
ref-метки N1…/A1…, новости с фактами и чанками, аналитика банка, готовый контекст для промпта.

Только форматирование: ничего не ищет и в БД не ходит.
"""

from datetime import UTC, datetime

from news_parser.core.taxonomy import Taxonomy
from news_parser.filtering.candidate import Candidate
from news_parser.filtering.matcher import Selection
from news_parser.filtering.profile import profile_summary
from news_parser.filtering.ranking import STATUS as RANKING_STATUS
from news_parser.output.context import render_context
from news_parser.schemas.client import ClientProfile
from news_parser.schemas.match import (
    AnalyticsItem,
    AspectMatch,
    AspectOut,
    MatchOptions,
    NewsChunk,
    NewsItem,
    NewsSource,
    ProfileMatchResponse,
)


def build_match_response(
    profile: ClientProfile,
    sel: Selection,
    opts: MatchOptions,
    taxonomy: Taxonomy,
    embedding_model: str,
) -> ProfileMatchResponse:
    news_refs = {c.event.id: f"N{i}" for i, c in enumerate(sel.candidates, start=1)}

    # аналитика: один фрагмент может подойти к нескольким новостям — собираем без повторов
    analytics: dict[int, tuple] = {}  # chunk_id -> (hit, лучшее сходство, {event_id})
    for c in sel.candidates:
        for h in c.analytics:
            prev = analytics.get(h.chunk.id)
            events = (prev[2] if prev else set()) | {c.event.id}
            analytics[h.chunk.id] = (h, max(h.similarity, prev[1] if prev else 0.0), events)
    ordered = sorted(analytics.values(), key=lambda a: a[1], reverse=True)
    analytics_refs = {h.chunk.id: f"A{i}" for i, (h, _, _) in enumerate(ordered, start=1)}

    response = ProfileMatchResponse(
        profile_uid=profile.uid,
        profile_summary=profile_summary(profile),
        aspects=[
            AspectOut(
                id=a.id,
                title=a.title,
                query=a.query,
                weight=a.weight,
                filters={k: v for k, v in vars(a.filters).items() if v},
                reason=a.reason,
            )
            for a in sel.aspects
        ],
        news=[
            _news_item(news_refs[c.event.id], c, opts, [analytics_refs[h.chunk.id] for h in c.analytics])
            for c in sel.candidates
        ],
        bank_analytics=[
            AnalyticsItem(
                ref=analytics_refs[h.chunk.id],
                chunk_id=h.chunk.id,
                origin=h.chunk.origin,
                doc_title=h.chunk.doc_title,
                file_name=h.chunk.file_name,
                chunk_index=h.chunk.chunk_index,
                page_from=h.chunk.page_from,
                page_to=h.chunk.page_to,
                text=h.chunk.text,
                similarity=round(sim, 4),
                related_news=sorted(news_refs[e] for e in events if e in news_refs),
                doc_summary=h.document.summary,
                doc_stance=h.document.stance,
                doc_date=h.document.published_date,
            )
            for h, sim, events in ordered
        ],
        context=None,
        meta={
            "embedding_model": embedding_model,
            "window_days": sel.window_days,
            "min_similarity": sel.min_similarity,
            "passed_rules": sel.passed_rules,
            "fallback_used": sel.fallback_used,
            "ranking": RANKING_STATUS,
            "generated_at": datetime.now(UTC).isoformat(),
        },
    )
    if opts.render_context:
        response.context = render_context(response, taxonomy, opts.max_context_chars)
    return response


def _news_item(ref: str, c: Candidate, opts: MatchOptions, analytics_refs: list[str]) -> NewsItem:
    e = c.event
    main = next((a for a in c.articles if a.id == e.main_article_id), c.articles[0] if c.articles else None)
    facts = (main.extraction or {}).get("facts", []) if main else []
    method = (main.extraction_meta or {}).get("method") if main else None
    best_chunks = sorted(c.chunks.values(), key=lambda h: h.hit.similarity, reverse=True)[: opts.chunks_per_news]
    seen_urls: set[str] = set()
    sources = []
    for a in sorted(c.articles, key=lambda a: -a.trust):
        if a.url and a.url in seen_urls:
            continue
        seen_urls.add(a.url or "")
        sources.append(NewsSource(article_id=a.id, source_name=a.source_name, url=a.url, published_at=a.published_at))
    return NewsItem(
        ref=ref,
        event_id=e.id,
        title=e.title,
        summary=e.summary,
        event_type=e.event_type,
        direction=e.direction,
        horizon=e.horizon,
        first_seen_at=e.first_seen_at,
        last_seen_at=e.last_seen_at,
        macro_factors=e.macro_factors,
        industries=e.industries,
        regions=e.regions,
        countries=e.countries,
        facts=facts,
        extraction_method=method,
        n_sources=e.n_sources,
        similarity=round(c.similarity, 4),
        passed_rules=c.passed_rules,
        matched_aspects=[
            AspectMatch(
                aspect_id=h.aspect.id,
                aspect_title=h.aspect.title,
                similarity=round(h.hit.similarity, 4),
                matched_labels=h.labels,
            )
            for h in sorted(c.by_aspect.values(), key=lambda h: h.hit.similarity, reverse=True)
        ],
        chunks=[
            NewsChunk(
                chunk_id=h.hit.chunk.id,
                article_id=h.hit.article.id,
                source_name=h.hit.article.source_name,
                published_at=h.hit.article.published_at,
                text=h.hit.chunk.text,
                similarity=round(h.hit.similarity, 4),
                aspect_id=h.aspect.id,
            )
            for h in best_chunks
        ],
        sources=sources,
        related_analytics=analytics_refs,
    )
