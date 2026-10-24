"""Пакеты для LLM в формате команды — по одному на значимую новость:

    {
      "client":    {...},     # как есть из data_loader.get_client_info (контракт модуля клиентских данных)
      "news":      {news_id, url, title, published_at, source, text},
      "analytics": [{chunk_id, doc_title, page, text, stance, doc_summary, doc_date}, ...]   # 0–5 фрагментов
    }

Как подбирается (filtering/matcher.py): профиль клиента -> теги и тексты аспектов ->
жёсткий отсев новостей по тегам -> векторный поиск среди прошедших -> к каждой новости
аналитика по её вектору и общим тегам. Ранжирования пока нет: порядок = сходство.
В news.text — текст статьи (короткая — целиком, длинная — самые релевантные клиенту
фрагменты), поэтому LLM не нужно ходить по URL: url — только для пользователя.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from news_parser.schemas.client import ClientProfile
from news_parser.output.stance import classify_stance
from news_parser.schemas.match import AnalyticsItem, MatchOptions, NewsItem, ProfileMatchResponse
from news_parser.storage import repository as repo
from news_parser.storage.clients import ProfileSourceUnavailable, load_profile
from news_parser.storage.db import session_scope


class PacketsUnavailable(Exception):
    """Нет библиотеки data_loader или её БД — ответ 503."""


class ClientNotFound(Exception):
    pass


@dataclass
class PacketOptions:
    limit: int = 5  # сколько новостей (пакетов) вернуть
    analytics_per_news: int = 3  # до 5 чанков аналитики в пакете (0, если общего с банком нет)
    news_text_chars: int = 3000  # максимум текста новости в пакете
    window_days: int | None = None
    min_similarity: float | None = None
    trace: bool = False  # добавить в пакет блок trace: почему новость и аналитика отобраны


_TRANSLIT = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
         "u", "f", "h", "c", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"],
        strict=True,
    )
)


def doc_slug(file_name: str, max_len: int = 40) -> str:
    """«Ключевая ставка ЦБ РФ.pdf» -> «klyuchevaya_stavka_cb_rf»."""
    stem = file_name.rsplit(".", 1)[0].lower()
    latin = "".join(_TRANSLIT.get(ch, ch) for ch in stem)
    return re.sub(r"[^a-z0-9]+", "_", latin).strip("_")[:max_len].rstrip("_") or "doc"


def analytics_chunk_id(a: AnalyticsItem) -> str:
    """Формат команды: doc_id::page::chunk."""
    return f"{doc_slug(a.file_name)}::p{a.page_from or 0}::c{a.chunk_index}"


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("\n"))
    return (cut[: end + 1] if end > max_chars // 2 else cut).rstrip() + " …"


def _news_text(n: NewsItem, main_text: str | None, max_chars: int) -> str:
    """Короткая статья — целиком; длинная — релевантные клиенту чанки по порядку."""
    if main_text and len(main_text) <= max_chars:
        return main_text
    pieces = list(dict.fromkeys(c.text for c in sorted(n.chunks, key=lambda c: c.chunk_id)))
    text = "\n\n".join(pieces)
    if len(text) < 200 and main_text:
        text = main_text
    return _truncate(text or n.summary, max_chars)


def _fallback_profile(client: dict) -> ClientProfile:
    """Если таблиц companies/payments не видно напрямую — строим профиль из блока client."""
    products = client.get("products") or {}
    return ClientProfile(
        uid=client.get("client_id"),
        mainokved_name=client.get("industry"),
        revenue_company=client.get("revenue_rub"),
        region=client.get("region"),
        **{f"has_{k}": v for k, v in products.items() if k in ("rko", "loa", "lea", "dep", "gar", "zpp", "factoring")},
    )


def _get_client_info(client_id: str) -> dict:
    try:
        from data_loader import get_client_info  # библиотека модуля клиентских данных (корень репо)
    except ImportError:
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[4]
        if (repo_root / "data_loader").is_dir() and str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        try:
            from data_loader import get_client_info
        except ImportError as exc:
            raise PacketsUnavailable(
                "библиотека data_loader не найдена: добавьте корень репозитория в PYTHONPATH "
                "(в Docker это делает Dockerfile)"
            ) from exc
    try:
        client = get_client_info(client_id)
    except Exception as exc:  # psycopg2: нет БД, не создан/не обновлён top_counterparties и т.п.
        raise PacketsUnavailable(f"data_loader.get_client_info({client_id!r}) упал: {exc!r}") from exc
    if not isinstance(client, dict) or "error" in client:
        raise ClientNotFound((client or {}).get("error", f"клиент {client_id} не найден"))
    return client


MatchFn = Callable[[ClientProfile, MatchOptions], ProfileMatchResponse]


def build_packets(client_id: str, match: MatchFn, opts: PacketOptions) -> list[dict]:
    """match — отбор + сборка ответа (core.container.Services.match)."""
    client = _get_client_info(client_id)

    # Для поиска нужен профиль богаче блока client: код ОКВЭД, ВЭД, отрасли контрагентов.
    try:
        profile = load_profile(client_id) or _fallback_profile(client)
    except ProfileSourceUnavailable:
        profile = _fallback_profile(client)
    profile.signals = client.get("signals") or {}

    result = match(
        profile,
        MatchOptions(
            window_days=opts.window_days,
            min_similarity=opts.min_similarity,
            limit_news=opts.limit,
            chunks_per_news=3,
            analytics_per_news=min(opts.analytics_per_news, 5),
            render_context=False,
        ),
    )
    with session_scope() as s:
        mains = {
            event_id: (a.url, a.source_name, a.published_at, a.text)
            for event_id, a in repo.main_articles(s, [n.event_id for n in result.news]).items()
        }
    bank = {a.ref: a for a in result.bank_analytics}

    packets = []
    for n in result.news:
        url, source, published_at, main_text = mains.get(n.event_id, (None, None, None, None))
        if url is None and n.sources:
            url, source = n.sources[0].url, n.sources[0].source_name
        published: datetime = published_at or n.first_seen_at

        # аналитика — только подобранная к этой новости (общие теги + вектор новости).
        # Если общего с аналитикой банка нет, список пуст: лучше ничего, чем чужая аналитика.
        chosen = [bank[r] for r in n.related_analytics if r in bank]

        packet = {
            "client": client,
            "news": {
                "news_id": n.event_id,
                "url": url,
                "title": n.title,
                "published_at": published.date().isoformat(),
                "source": source,
                "text": _news_text(n, main_text, opts.news_text_chars),
            },
            "analytics": [
                {
                    "chunk_id": analytics_chunk_id(a),
                    "doc_title": a.doc_title,
                    "page": a.page_from if a.page_from is not None else 1,
                    "text": a.text,
                    # позиция банка: из профиля документа (LLM), без него — правила по тексту фрагмента
                    "stance": a.doc_stance or classify_stance(a.text),
                    "doc_summary": a.doc_summary,  # главные тезисы банка во всём документе
                    "doc_date": a.doc_date.isoformat() if a.doc_date else None,
                }
                for a in chosen
            ],
        }
        if opts.trace:
            packet["trace"] = {
                "passed_rules": n.passed_rules,
                "similarity": n.similarity,
                "matched_aspects": [m.model_dump() for m in n.matched_aspects],
                "facts": n.facts,
                "n_sources": n.n_sources,
                "analytics": [{"chunk_id": analytics_chunk_id(a), "similarity": a.similarity} for a in chosen],
                "aspects": [a.model_dump() for a in result.aspects],
                "match_meta": result.meta,
            }
        packets.append(packet)
    return packets
