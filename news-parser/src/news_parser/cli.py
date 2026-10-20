"""Команды для ручного запуска без HTTP.

python -m news_parser.cli collect [--source rbc ...]   — один проход сбора
python -m news_parser.cli load-analytics               — загрузить аналитику Альфа-Банка
python -m news_parser.cli reprocess                    — дообработать pending_llm
python -m news_parser.cli warmup [--model NAME]        — скачать модель эмбеддингов (в Dockerfile)
"""

import argparse
import json
import logging

from news_parser.main import setup_logging
from news_parser.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="news_parser")
    sub = parser.add_subparsers(dest="cmd", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--source", action="append", help="id источника из sources.yaml (можно несколько)")
    sub.add_parser("load-analytics")
    sub.add_parser("reprocess")
    warmup = sub.add_parser("warmup")
    warmup.add_argument("--model", default=None)
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)

    if args.cmd == "warmup":
        # без БД: только скачать модель в кеш
        from news_parser.processing.embedder import Embedder

        model = args.model or settings.embedding_model
        embedder = Embedder(model, settings.embedding_dim, settings.embedding_cache_dir)
        embedder.warmup()
        logging.info("модель %s готова", model)
        return

    from news_parser.services import get_services

    services = get_services()
    if args.cmd == "collect":
        result = services.pipeline.collect(args.source)
    elif args.cmd == "load-analytics":
        result = services.load_analytics()
    else:
        result = services.pipeline.reprocess_pending()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
