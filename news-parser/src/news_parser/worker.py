"""Воркер — основной процесс контейнера: фоновый сбор и обработка новостей по расписанию.

Запуск: python -m news_parser.worker
HTTP-сервера нет: остальные модули вызывают функции из news_parser.interface
(или CLI: python -m news_parser.cli ...).
"""

import logging

from news_parser.core.logs import setup_logging
from news_parser.core.settings import get_settings
from news_parser.scheduler import build_scheduler


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    log = logging.getLogger(__name__)
    if not settings.scheduler_enabled:
        log.info("SCHEDULER_ENABLED=false — фоновый сбор выключен, воркер завершается")
        return
    scheduler = build_scheduler()
    log.info("воркер запущен: сбор каждые %d мин", settings.collect_interval_min)
    try:
        scheduler.start()  # блокирует до остановки контейнера
    except (KeyboardInterrupt, SystemExit):
        log.info("воркер остановлен")


if __name__ == "__main__":
    main()
