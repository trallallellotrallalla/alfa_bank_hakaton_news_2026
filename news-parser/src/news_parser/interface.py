"""Публичный интерфейс модуля — функции вместо HTTP.

Другие модули команды вызывают их напрямую:

    from news_parser import get_packets, interpret_client
    packets = get_packets("U_176", limit=5)               # [{client, news, analytics}, ...]
    interpretations = interpret_client("U_176", limit=5)  # сквозной пайплайн: парсер -> интерпретатор

или из консоли / другого контейнера через CLI (тот же набор функций, вывод — JSON):

    python -m news_parser.cli packets U_176 --limit 5
    python -m news_parser.cli interpret U_176 --limit 5

Все функции возвращают готовые к JSON данные (dict / list / None) — без pydantic- и ORM-объектов.
Ошибки, которые стоит обрабатывать: ClientNotFound, PacketsUnavailable, ProfileSourceUnavailable.
"""

from datetime import UTC, datetime

from news_parser.core.container import get_services
from news_parser.filtering.profile import build_aspects
from news_parser.output.packets import ClientNotFound, PacketOptions, PacketsUnavailable, build_packets
from news_parser.schemas.client import ClientProfile
from news_parser.schemas.items import RawItem
from news_parser.schemas.match import AspectOut, EmbedRequest, MatchOptions
from news_parser.schemas.views import (
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
from news_parser.storage import repository as repo
from news_parser.storage.clients import ProfileSourceUnavailable, load_profile
from news_parser.storage.db import ping, session_scope
from news_parser.storage.models import Article

__all__ = [
    "ClientNotFound", "PacketsUnavailable", "ProfileSourceUnavailable",
    "get_packets", "interpret_packet", "interpret_client", "interpret",
    "match_client", "match_profile", "profile_aspects", "embed",
    "ingest", "collect", "reprocess", "backfill_chunks",
    "latest_events", "search_events", "get_event", "get_article",
    "search_analytics", "analytics_docs", "load_analytics",
    "health", "stats", "taxonomy",
]


def _json(model) -> dict:
    return model.model_dump(mode="json")


def _load_interpreter():
    try:
        from interpreter import fallback_output, interpret as _interpret, new_interpretation_id
        return _interpret, fallback_output, new_interpretation_id
    except ImportError:
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        if (repo_root / "interpreter").is_dir() and str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        try:
            from interpreter import fallback_output, interpret as _interpret, new_interpretation_id
            return _interpret, fallback_output, new_interpretation_id
        except ImportError as exc:
            raise PacketsUnavailable(
                "модуль interpreter не найден: добавьте корень репозитория в PYTHONPATH "
                "(в Docker это делает Dockerfile)"
            ) from exc


# ---------------------------------------------------------------------------
# Итоговый JSON под клиента (главное для LLM-агента и сквозного пайплайна)
# ---------------------------------------------------------------------------


def get_packets(
    client_id: str,
    *,
    limit: int = 5,
    analytics_per_news: int = 3,
    news_text_chars: int = 3000,
    window_days: int | None = None,
    min_similarity: float | None = None,
    trace: bool = False,
) -> list[dict]:
    """Пакеты для LLM в формате команды: [{client, news, analytics[0–5]}] — по одному на
    значимую для клиента новость. client — как есть из data_loader.get_client_info.
    trace=True добавляет блок trace: почему новость отобрана.

    Ошибки: ClientNotFound (нет клиента), PacketsUnavailable (нет data_loader или его БД)."""
    opts = PacketOptions(
        limit=limit,
        analytics_per_news=analytics_per_news,
        news_text_chars=news_text_chars,
        window_days=window_days,
        min_similarity=min_similarity,
        trace=trace,
    )
    return build_packets(client_id, get_services().match, opts)


def interpret_packet(
    packet: dict,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.0,
    max_retries: int = 1,
    timeout: float = 60.0,
) -> dict:
    """Интерпретация одного пакета {client, news, analytics} через модуль interpreter."""
    _interpret, fallback_output, new_interpretation_id = _load_interpreter()
    settings = get_services().settings
    try:
        out = _interpret(
            packet,
            api_key=api_key or settings.llm_api_key or None,
            model=model or settings.llm_model or None,
            base_url=base_url or settings.llm_api_url or None,
            temperature=temperature,
            max_retries=max_retries,
            timeout=timeout,
        )
    except ValueError:
        raise
    except Exception as exc:
        out = fallback_output(packet, new_interpretation_id(), f"network/LLM error: {exc}")
    if "trace" in packet:
        out["trace"] = packet["trace"]
    return out


interpret = interpret_packet


def interpret_client(
    client_id: str,
    *,
    limit: int = 5,
    analytics_per_news: int = 3,
    news_text_chars: int = 3000,
    window_days: int | None = None,
    min_similarity: float | None = None,
    trace: bool = False,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.0,
    max_retries: int = 1,
    timeout: float = 60.0,
) -> list[dict]:
    """Сквозной пайплайн двух модулей:
    1) news-parser отбирает релевантные клиенту новости и аналитику (get_packets),
    2) каждый пакет подаётся в LLM-интерпретатор (interpreter.interpret).
    Возвращает список готовых персонализированных интерпретаций."""
    _load_interpreter()  # проверяем наличие interpreter до обращения к БД/LLM
    packets = get_packets(
        client_id,
        limit=limit,
        analytics_per_news=analytics_per_news,
        news_text_chars=news_text_chars,
        window_days=window_days,
        min_similarity=min_similarity,
        trace=trace,
    )
    return [
        interpret_packet(
            p,
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=temperature,
            max_retries=max_retries,
            timeout=timeout,
        )
        for p in packets
    ]


def match_profile(profile: dict | ClientProfile, **options) -> dict:
    """Подбор под профиль (поля как в таблице companies + counterparties): новости с фактами
    и чанками, аналитика банка с ref-метками N1/A1, готовый текст для промпта (context).
    options — поля MatchOptions: limit_news, chunks_per_news, analytics_per_news, window_days,
    min_similarity, include_structured, render_context, max_context_chars."""
    p = profile if isinstance(profile, ClientProfile) else ClientProfile.model_validate(profile)
    return _json(get_services().match(p, MatchOptions(**options)))


def match_client(client_id: str, **options) -> dict:
    """То же по uid: профиль и крупные контрагенты читаются из companies / payments.
    Ошибки: ClientNotFound, ProfileSourceUnavailable."""
    profile = load_profile(client_id)
    if profile is None:
        raise ClientNotFound(f"клиент {client_id} не найден")
    return _json(get_services().match(profile, MatchOptions(**options)))


def profile_aspects(profile: dict | ClientProfile) -> list[dict]:
    """Как профиль раскладывается на аспекты поиска (теги + текст-запрос) — для отладки."""
    p = profile if isinstance(profile, ClientProfile) else ClientProfile.model_validate(profile)
    return [
        _json(
            AspectOut(
                id=a.id,
                title=a.title,
                query=a.query,
                weight=a.weight,
                filters={k: v for k, v in vars(a.filters).items() if v},
                reason=a.reason,
            )
        )
        for a in build_aspects(p, get_services().taxonomy)
    ]


def embed(texts: list[str], kind: str = "query") -> dict:
    """Векторы той же моделью, что база знаний (сравнивать векторы разных моделей нельзя).
    kind: query — для запросов, passage — для документов."""
    req = EmbedRequest(texts=texts, kind=kind)
    embedder = get_services().embedder
    vectors = embedder.embed_queries(req.texts) if req.kind == "query" else embedder.embed_passages(req.texts)
    return {"model": embedder.model_name, "dim": embedder.dim, "vectors": vectors}


# ---------------------------------------------------------------------------
# Парсер: приём и обработка новостей
# ---------------------------------------------------------------------------


def ingest(
    *,
    url: str | None = None,
    title: str | None = None,
    text: str | None = None,
    published_at: datetime | None = None,
    source_name: str = "Ручной ввод",
) -> dict:
    """Добавить новость вручную (url — скачаем, или title + text) и сразу обработать:
    префильтр → LLM-классификатор → событие + чанки. Возвращает {status, article_id, event_id, reason}."""
    req = IngestRequest(url=url, title=title, text=text, published_at=published_at, source_name=source_name)
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
    return _json(IngestResponse(**result.__dict__))


def collect(source_ids: list[str] | None = None) -> dict:
    """Один проход сбора по источникам из sources.yaml (все или указанные). Синхронно."""
    return get_services().pipeline.collect(source_ids)


def reprocess(limit: int = 30) -> dict:
    """Повторить LLM-разметку статей, которые ждут бюджета или API (pending_llm)."""
    return get_services().pipeline.reprocess_pending(limit)


def backfill_chunks() -> dict:
    """Нарезать на чанки статьи, у которых их ещё нет."""
    return get_services().pipeline.backfill_chunks()


# ---------------------------------------------------------------------------
# События и статьи
# ---------------------------------------------------------------------------


def _event_out(e) -> EventOut:
    return EventOut.model_validate(e, from_attributes=True)


def latest_events(limit: int = 20, offset: int = 0) -> list[dict]:
    """Общая лента событий, свежие сверху."""
    with session_scope() as s:
        return [_json(_event_out(e)) for e in repo.latest_events(s, limit=limit, offset=offset)]


def search_events(**filters) -> list[dict]:
    """События по фильтрам и/или текстовому запросу, с разбивкой скоринга.
    filters — поля EventSearchRequest: query, macro_factors, industries, okved, regions, countries,
    event_types, match ("any"/"all"), include_federal, include_structured, date_from, date_to,
    min_sources, limit, offset."""
    req = EventSearchRequest(**filters)
    services = get_services()
    query_vec = services.embedder.embed_query(req.query) if req.query else None
    f = repo.EventFilters(
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
        hits = repo.search_events(s, f, query_embedding=query_vec, limit=req.limit, offset=req.offset)
        return [
            _json(
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
            )
            for h in hits
        ]


def get_event(event_id: int) -> dict | None:
    """Событие со всеми первоисточниками и фактами главной статьи (None — нет такого)."""
    with session_scope() as s:
        e = repo.get_event(s, event_id)
        if e is None:
            return None
        main = next((a for a in e.articles if a.id == e.main_article_id), None)
        sources = sorted(e.articles, key=lambda a: (-a.trust, a.published_at or a.fetched_at))
        return _json(
            EventDetail(
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
        )


def get_article(article_id: int) -> dict | None:
    """Статья целиком + как она размечена (LLM/правила, id вызовов LLM) — для трассировки."""
    with session_scope() as s:
        a = s.get(Article, article_id)
        return None if a is None else _json(ArticleDetail.model_validate(a, from_attributes=True))


# ---------------------------------------------------------------------------
# Аналитика Альфа-Банка
# ---------------------------------------------------------------------------


def search_analytics(
    query: str | None = None,
    *,
    macro_factors: list[str] | None = None,
    industries: list[str] | None = None,
    limit: int = 5,
) -> list[dict]:
    """Фрагменты аналитики по смыслу запроса и/или тегам."""
    req = AnalyticsSearchRequest(query=query, macro_factors=macro_factors, industries=industries, limit=limit)
    query_vec = get_services().embedder.embed_query(req.query) if req.query else None
    with session_scope() as s:
        rows = repo.search_analytics(
            s,
            query_embedding=query_vec,
            macro_factors=req.macro_factors,
            industries=req.industries,
            limit=req.limit,
        )
        return [
            _json(
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
            )
            for c, sim in rows
        ]


def analytics_docs() -> list[dict]:
    """Какие документы аналитики загружены."""
    with session_scope() as s:
        return repo.list_analytics_docs(s)


def load_analytics(force: bool = False) -> dict:
    """Загрузить новые файлы из ALFA_DOCS_PATH (уже загруженные пропускаются).
    PDF-сканы распознаются Qwen3-VL, документы профилируются LLM; результат кешируется
    в <имя>.analysis.json рядом с файлом. force=True — перезагрузить все документы (кеш используется)."""
    return get_services().load_analytics(force=force)


# ---------------------------------------------------------------------------
# Служебное
# ---------------------------------------------------------------------------


def health() -> dict:
    """Жив ли модуль: доступна ли БД."""
    db_ok = ping()
    return {"status": "ok" if db_ok else "db_unavailable", "db": db_ok}


def stats() -> dict:
    """Статистика: статьи по статусам и источникам, события, чанки, токены LLM за сегодня."""
    services = get_services()
    with session_scope() as s:
        data = repo.stats(s)
    data["llm_tokens_today"] = services.llm.usage.tokens_used_today()
    data["llm_daily_budget"] = services.settings.llm_daily_token_budget
    data["llm_configured"] = services.llm.configured
    return data


def taxonomy() -> dict:
    """Справочник тегов: допустимые id факторов, отраслей (с ОКВЭД) и типов событий."""
    return get_services().taxonomy.as_dict()
