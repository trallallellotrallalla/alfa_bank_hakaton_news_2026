"""Точка входа сервиса: FastAPI + фоновый планировщик сбора.

Запуск: uvicorn news_parser.main:app --host 0.0.0.0 --port 8000
Документация API (Swagger): http://<host>:8000/docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from news_parser.api.routes import public, router
from news_parser.settings import get_settings


def setup_logging(level: str) -> None:
    # логи в stdout — их собирает Docker (docker logs)
    logging.basicConfig(level=level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    scheduler = None
    if settings.scheduler_enabled:
        from news_parser.scheduler import build_scheduler

        scheduler = build_scheduler()
        scheduler.start()
        logging.getLogger(__name__).info("планировщик запущен, сбор каждые %d мин", settings.collect_interval_min)
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="News Parser",
    version="0.1.0",
    description="Сбор, очистка, классификация и поиск новостей и аналитики Альфа-Банка для RAG.",
    lifespan=lifespan,
)
app.include_router(public)
app.include_router(router)
