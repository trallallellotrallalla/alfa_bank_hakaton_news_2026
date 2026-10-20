"""HTTP API модуля — единственная точка входа для остальных сервисов."""

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Security
from fastapi.security import APIKeyHeader

from news_parser.schemas.api import (
    AnalyticsHit,
    AnalyticsSearchRequest,
    ArticleDetail,
    EventDetail,
    EventHit,
    EventOut,
    EventSearchRequest,
    IngestRequest,
    IngestResponse,
    ScoreParts,
    SourceRef,
)
from news_parser.schemas.items import RawItem
from news_parser.services import Services, get_services
from news_parser.storage import repository as repo
from news_parser.storage.db import ping, session_scope
from news_parser.storage.models import Article

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(_api_key_header)) -> None:
    expected = get_services().settings.service_api_key
    if expected and key != expected:
        raise HTTPException(status_code=401, detail="неверный или отсутствующий X-API-Key")


public = APIRouter()
router = APIRouter(dependencies=[Depends(require_api_key)])


@public.get("/health", tags=["service"])
def health() -> dict:
    db_ok = ping()
    if not db_ok:
        raise HTTPException(status_code=503, detail="БД недоступна")
    return {"status": "ok", "db": db_ok}


# --- приём данных ---


@router.post("/ingest", response_model=IngestResponse, tags=["ingest"])
def ingest(req: IngestRequest) -> IngestResponse:
    """Добавить новость вручную (URL или текст) и сразу обработать — для демо
    и для проверки на «ранее не показанных» новостях."""
    item = RawItem(
        source_id="manual",
        source_name=req.source_name,
        source_type="manual",
        trust=0.5,
        title=req.title or "",  # пусто — возьмём заголовок скачанной страницы
        url=req.url,
        text=req.text,
        published_at=req.published_at or datetime.now(UTC),
        fetch_full_text=bool(req.url and not req.text),
    )
    result = get_services().pipeline.process_item(item, force=True)
    return IngestResponse(**result.__dict__)


@router.post("/collect/run", tags=["ingest"])
def run_collect(background: BackgroundTasks, source_id: list[str] | None = Query(None)) -> dict:
    """Запустить сбор вне расписания (в фоне)."""
    background.add_task(get_services().pipeline.collect, source_id)
    return {"status": "started", "sources": source_id or "all"}


@router.post("/reprocess", tags=["ingest"])
def reprocess(limit: int = 30) -> dict:
    """Повторить LLM-разметку статей, которые ждут бюджета (pending_llm)."""
    return get_services().pipeline.reprocess_pending(limit)


# --- события ---


def _event_out(e) -> EventOut:
    return EventOut.model_validate(e, from_attributes=True)


@router.post("/events/search", response_model=list[EventHit], tags=["events"])
def search_events(req: EventSearchRequest) -> list[EventHit]:
    """Главная ручка для агента: отобрать события под профиль клиента."""
    services: Services = get_services()
    query_vec = services.embedder.embed_query(req.query) if req.query else None
    filters = repo.EventFilters(
        macro_factors=req.macro_factors,
        industries=req.industries,
        okved=req.okved,
        regions=req.regions,
        countries=req.countries,
        event_types=req.event_types,
        match=req.match,
        include_federal=req.include_federal,
        date_from=req.date_from,
        date_to=req.date_to,
        min_sources=req.min_sources,
        include_structured=req.include_structured,
    )
    with session_scope() as s:
        hits = repo.search_events(s, filters, query_embedding=query_vec, limit=req.limit, offset=req.offset)
        return [
            EventHit(
                event=_event_out(h.event),
                ranking=ScoreParts(
                    score=h.score,
                    similarity=None if h.similarity is None else round(h.similarity, 4),
                    recency=h.recency,
                    source_weight=h.source_weight,
                    matched=h.matched,
                ),
            )
            for h in hits
        ]


@router.get("/events", response_model=list[EventOut], tags=["events"])
def latest_events(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> list[EventOut]:
    """Последние события без фильтров (общая лента)."""
    with session_scope() as s:
        return [_event_out(e) for e in repo.latest_events(s, limit=limit, offset=offset)]


@router.get("/events/{event_id}", response_model=EventDetail, tags=["events"])
def get_event(event_id: int) -> EventDetail:
    """Событие со всеми первоисточниками и фактами главной статьи."""
    with session_scope() as s:
        e = repo.get_event(s, event_id)
        if e is None:
            raise HTTPException(404, "событие не найдено")
        main = next((a for a in e.articles if a.id == e.main_article_id), None)
        sources = sorted(e.articles, key=lambda a: (-a.trust, a.published_at or a.fetched_at))
        return EventDetail(
            **_event_out(e).model_dump(),
            main_extraction=main.extraction if main else None,
            sources=[
                SourceRef(
                    article_id=a.id,
                    source_id=a.source_id,
                    source_name=a.source_name,
                    title=a.title,
                    url=a.url,
                    published_at=a.published_at,
                    trust=a.trust,
                    status=a.status,
                )
                for a in sources
            ],
        )


@router.get("/articles/{article_id}", response_model=ArticleDetail, tags=["events"])
def get_article(article_id: int) -> ArticleDetail:
    """Статья целиком + как она размечена (LLM/правила, id вызовов LLM) — для трассировки."""
    with session_scope() as s:
        a = s.get(Article, article_id)
        if a is None:
            raise HTTPException(404, "статья не найдена")
        return ArticleDetail.model_validate(a, from_attributes=True)


# --- аналитика Альфа-Банка ---


@router.post("/analytics/search", response_model=list[AnalyticsHit], tags=["analytics"])
def search_analytics(req: AnalyticsSearchRequest) -> list[AnalyticsHit]:
    """Фрагменты аналитики Альфа-Банка по смыслу и/или меткам."""
    services = get_services()
    query_vec = services.embedder.embed_query(req.query) if req.query else None
    with session_scope() as s:
        rows = repo.search_analytics(
            s,
            query_embedding=query_vec,
            macro_factors=req.macro_factors,
            industries=req.industries,
            limit=req.limit,
        )
        return [
            AnalyticsHit(
                id=c.id,
                origin=c.origin,
                doc_id=c.doc_id,
                doc_title=c.doc_title,
                file_name=c.file_name,
                page_from=c.page_from,
                page_to=c.page_to,
                text=c.text,
                macro_factors=c.macro_factors,
                industries=c.industries,
                similarity=sim,
            )
            for c, sim in rows
        ]


@router.get("/analytics/docs", tags=["analytics"])
def analytics_docs() -> list[dict]:
    with session_scope() as s:
        return repo.list_analytics_docs(s)


@router.post("/analytics/reload", tags=["analytics"])
def analytics_reload() -> dict:
    """Догрузить новые файлы из ALFA_DOCS_PATH (уже загруженные пропускаются)."""
    return get_services().load_analytics()


# --- справочники и состояние ---


@router.get("/taxonomy", tags=["service"])
def taxonomy() -> dict:
    """Все допустимые id меток — для фильтров и для маппинга профиля клиента."""
    return get_services().taxonomy.as_dict()


@router.get("/stats", tags=["service"])
def stats() -> dict:
    services = get_services()
    with session_scope() as s:
        data = repo.stats(s)
    data["llm_tokens_today"] = services.llm.usage.tokens_used_today()
    data["llm_daily_budget"] = services.settings.llm_daily_token_budget
    data["llm_configured"] = services.llm.configured
    return data
