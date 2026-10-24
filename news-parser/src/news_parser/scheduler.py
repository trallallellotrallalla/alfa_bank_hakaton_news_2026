"""Расписание фоновых задач: первый запуск, плановый сбор, дообработка через LLM.

Запускает его воркер (news_parser.worker) — в ОДНОМ экземпляре, иначе сбор пойдёт параллельно.
"""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from news_parser.core.container import get_services

log = logging.getLogger(__name__)


def _collect() -> None:
    result = get_services().pipeline.collect()
    log.info("плановый сбор завершён: %s", result.get("finished_at") or result)


def _reprocess() -> None:
    services = get_services()
    log.info("дообработка pending_llm: %s", services.pipeline.reprocess_pending())
    # аналитика, которую не удалось загрузить (кончился бюджет LLM, API лежал), догружается тут;
    # уже загруженные документы пропускаются без затрат
    result = services.load_analytics()
    if result["loaded"] or result["errors"]:
        log.info("аналитика: %s", result)


def _startup() -> None:
    """Однократно после старта: прогрев модели, загрузка аналитики, первый сбор."""
    services = get_services()
    services.embedder.warmup()
    if services.settings.load_analytics_on_start:
        log.info("аналитика Альфа-Банка: %s", services.load_analytics())
    # статьи, собранные до появления чанков, нарезаются один раз
    log.info("чанки статей: %s", services.pipeline.backfill_chunks())
    _collect()


def build_scheduler() -> BaseScheduler:
    settings = get_services().settings
    scheduler = BlockingScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1})
    scheduler.add_job(_startup, "date", run_date=datetime.now(UTC) + timedelta(seconds=2), id="startup")
    scheduler.add_job(
        _collect,
        "interval",
        minutes=settings.collect_interval_min,
        id="collect",
        next_run_time=datetime.now(UTC) + timedelta(minutes=settings.collect_interval_min),
    )
    scheduler.add_job(_reprocess, "interval", minutes=settings.reprocess_interval_min, id="reprocess")
    return scheduler
