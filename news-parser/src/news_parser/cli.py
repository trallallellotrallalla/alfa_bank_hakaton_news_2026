"""Командная строка — те же функции, что в news_parser.interface; вывод — JSON в stdout.

Из контейнера:  docker compose exec news-parser python -m news_parser.cli <команда> ...

  interpret U_176 [--limit 5] [--model ...] [--trace]               — сквозной пайплайн: парсер -> интерпретатор
  packets U_176 [--limit 5] [--analytics-per-news 3] [--trace]      — итоговый JSON для LLM-агента
  match U_176 [--limit 8]                                           — подбор под клиента (+ контекст для промпта)
  aspects U_176                                                     — как клиент раскладывается на аспекты
  ingest --title ... --text ... | --url ...                         — добавить новость и сразу обработать
  collect [--source rbc ...]                                        — один проход сбора
  reprocess [--limit 30]                                            — дообработать pending_llm через LLM
  backfill-chunks                                                   — нарезать на чанки статьи без чанков
  events [--limit 20]  |  event ID  |  article ID                   — лента, событие, статья
  search-events [--query ...] [--okved 41.20] [--factor key_rate]   — поиск событий по фильтрам
  analytics-search [--query ...]  |  analytics-docs  |  load-analytics [--force]
  embed "текст" [...] [--passage]                                   — векторы модели базы знаний
  health  |  stats  |  taxonomy
  warmup [--model NAME]                                             — скачать модель эмбеддингов
"""

import argparse
import json
import sys

from news_parser.core.logs import setup_logging
from news_parser.core.settings import get_settings


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="news_parser")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("interpret", help="сквозной пайплайн: подбор пакетов под клиента -> LLM-интерпретация")
    a.add_argument("client_id")
    a.add_argument("--limit", type=int, default=5)
    a.add_argument("--analytics-per-news", type=int, default=3)
    a.add_argument("--news-text-chars", type=int, default=3000)
    a.add_argument("--window-days", type=int)
    a.add_argument("--min-similarity", type=float)
    a.add_argument("--model")
    a.add_argument("--timeout", type=float, default=60.0)
    a.add_argument("--trace", action="store_true")

    a = sub.add_parser("packets", help="итоговый JSON для LLM-агента")
    a.add_argument("client_id")
    a.add_argument("--limit", type=int, default=5)
    a.add_argument("--analytics-per-news", type=int, default=3)
    a.add_argument("--news-text-chars", type=int, default=3000)
    a.add_argument("--window-days", type=int)
    a.add_argument("--min-similarity", type=float)
    a.add_argument("--trace", action="store_true")

    a = sub.add_parser("match", help="подбор под клиента по uid")
    a.add_argument("client_id")
    a.add_argument("--limit", type=int, default=8)
    a.add_argument("--window-days", type=int)
    a.add_argument("--no-context", action="store_true")

    a = sub.add_parser("aspects", help="аспекты клиента по uid")
    a.add_argument("client_id")

    a = sub.add_parser("ingest", help="добавить новость вручную")
    a.add_argument("--url")
    a.add_argument("--title")
    a.add_argument("--text")

    a = sub.add_parser("collect", help="один проход сбора")
    a.add_argument("--source", action="append", help="id источника из sources.yaml (можно несколько)")
    a = sub.add_parser("reprocess", help="дообработать pending_llm")
    a.add_argument("--limit", type=int, default=30)
    sub.add_parser("backfill-chunks")

    a = sub.add_parser("events", help="лента событий")
    a.add_argument("--limit", type=int, default=20)
    a.add_argument("--offset", type=int, default=0)
    a = sub.add_parser("event")
    a.add_argument("event_id", type=int)
    a = sub.add_parser("article")
    a.add_argument("article_id", type=int)
    a = sub.add_parser("search-events")
    a.add_argument("--query")
    a.add_argument("--okved", action="append")
    a.add_argument("--factor", action="append", dest="macro_factors")
    a.add_argument("--industry", action="append", dest="industries")
    a.add_argument("--region", action="append", dest="regions")
    a.add_argument("--limit", type=int, default=20)

    a = sub.add_parser("analytics-search")
    a.add_argument("--query")
    a.add_argument("--factor", action="append", dest="macro_factors")
    a.add_argument("--limit", type=int, default=5)
    sub.add_parser("analytics-docs")
    a = sub.add_parser("load-analytics")
    a.add_argument("--force", action="store_true", help="перезагрузить все документы (кеш распознавания используется)")

    a = sub.add_parser("embed")
    a.add_argument("texts", nargs="+")
    a.add_argument("--passage", action="store_true")

    sub.add_parser("health")
    sub.add_parser("stats")
    sub.add_parser("taxonomy")
    a = sub.add_parser("warmup")
    a.add_argument("--model", default=None)
    return p


def _run(args) -> object:
    from news_parser import interface as api
    from news_parser.storage.clients import load_profile

    match args.cmd:
        case "interpret":
            return api.interpret_client(
                args.client_id,
                limit=args.limit,
                analytics_per_news=args.analytics_per_news,
                news_text_chars=args.news_text_chars,
                window_days=args.window_days,
                min_similarity=args.min_similarity,
                model=args.model,
                timeout=args.timeout,
                trace=args.trace,
            )
        case "packets":
            return api.get_packets(
                args.client_id,
                limit=args.limit,
                analytics_per_news=args.analytics_per_news,
                news_text_chars=args.news_text_chars,
                window_days=args.window_days,
                min_similarity=args.min_similarity,
                trace=args.trace,
            )
        case "match":
            return api.match_client(
                args.client_id, limit_news=args.limit, window_days=args.window_days, render_context=not args.no_context
            )
        case "aspects":
            profile = load_profile(args.client_id)
            if profile is None:
                raise api.ClientNotFound(f"клиент {args.client_id} не найден")
            return api.profile_aspects(profile)
        case "ingest":
            return api.ingest(url=args.url, title=args.title, text=args.text)
        case "collect":
            return api.collect(args.source)
        case "reprocess":
            return api.reprocess(args.limit)
        case "backfill-chunks":
            return api.backfill_chunks()
        case "events":
            return api.latest_events(args.limit, args.offset)
        case "event":
            return api.get_event(args.event_id)
        case "article":
            return api.get_article(args.article_id)
        case "search-events":
            keys = ("query", "okved", "macro_factors", "industries", "regions")
            filters = {k: v for k, v in vars(args).items() if k in keys and v}
            return api.search_events(limit=args.limit, **filters)
        case "analytics-search":
            return api.search_analytics(args.query, macro_factors=args.macro_factors, limit=args.limit)
        case "analytics-docs":
            return api.analytics_docs()
        case "load-analytics":
            return api.load_analytics(force=args.force)
        case "embed":
            return api.embed(args.texts, kind="passage" if args.passage else "query")
        case "health":
            return api.health()
        case "stats":
            return api.stats()
        case "taxonomy":
            return api.taxonomy()


def main() -> None:
    args = _parser().parse_args()
    settings = get_settings()
    setup_logging(settings.log_level)

    if args.cmd == "warmup":  # без БД: только скачать модель в кеш
        from news_parser.core.embedder import Embedder

        Embedder(args.model or settings.embedding_model, settings.embedding_dim, settings.embedding_cache_dir).warmup()
        return

    from news_parser.interface import ClientNotFound, PacketsUnavailable, ProfileSourceUnavailable

    try:
        result = _run(args)
    except ClientNotFound as exc:
        print(json.dumps({"error": "client_not_found", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
    except (PacketsUnavailable, ProfileSourceUnavailable) as exc:
        print(json.dumps({"error": "unavailable", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    # health: ненулевой код, если БД недоступна — для healthcheck Docker
    if args.cmd == "health" and not result["db"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
