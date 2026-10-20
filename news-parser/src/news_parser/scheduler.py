"""Фоновые задачи внутри процесса сервиса (без системного cron).

Важно: запускайте сервис в ОДНОМ процессе uvicorn (без --workers N),
иначе каждый воркер запустит свой планировщик и сбор пойдёт параллельно.
"""

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from news_parser.services import get_services

log = logging.getLogger(__name__)


def _collect() -> None:
    result = get_services().pipeline.collect()
    log.info("плановый сбор завершён: %s", result.get("finished_at") or result)


def _reprocess() -> None:
    log.info("дообработка pending_llm: %s", get_services().pipeline.reprocess_pending())


def _startup() -> None:
    """Однократно после старта: прогрев модели, загрузка аналитики, первый сбор."""
    services = get_services()
    services.embedder.warmup()
    if services.settings.load_analytics_on_start:
        log.info("аналитика Альфа-Банка: %s", services.load_analytics())
    _collect()


def build_scheduler() -> BackgroundScheduler:
    settings = get_services().settings
    scheduler = BackgroundScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1})
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
