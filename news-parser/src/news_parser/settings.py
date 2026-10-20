"""Конфигурация модуля. Всё берётся из переменных окружения (или файла .env).

Описание каждой переменной — в .env.example и README.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- База данных (PostgreSQL + pgvector) ---
    database_url: str = "postgresql+psycopg://news:news@localhost:5432/news"
    db_schema: str = "news"

    # --- LLM (OpenAI-совместимый API, который выдают организаторы) ---
    llm_api_url: str = ""  # например https://host/v1 — без /chat/completions
    llm_api_key: str = ""
    llm_model: str = "gemma-4-26b-a4b"
    llm_timeout_s: float = 90.0
    llm_json_mode: bool = True  # передавать response_format=json_object
    llm_daily_token_budget: int = 300_000  # лимит токенов модуля в сутки (UTC)
    llm_max_input_chars: int = 6000  # длинные статьи обрезаются перед LLM

    # --- Эмбеддинги (локальная модель через fastembed, токены не тратит) ---
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    embedding_dim: int = 768  # должна совпадать с моделью; меняется только вместе с миграцией
    embedding_cache_dir: str | None = None

    # --- Обработка ---
    min_text_chars: int = 200  # короче — считаем мусором
    prefilter_require_signal: bool = True  # без бизнес-сигнала статья не идёт в LLM
    cluster_similarity_threshold: float = 0.86  # косинусная близость для склейки в событие
    cluster_window_hours: int = 72  # с событиями старше этого окна не склеиваем

    # --- Сбор ---
    sources_config: Path = PACKAGE_DIR / "config" / "sources.yaml"
    taxonomy_config: Path = PACKAGE_DIR / "config" / "taxonomy.yaml"
    http_user_agent: str = "Mozilla/5.0 (compatible; AlfaHackNewsParser/0.1)"
    http_timeout_s: float = 20.0
    http_delay_s: float = 0.5  # пауза между запросами полного текста к одному сайту

    # --- Планировщик ---
    scheduler_enabled: bool = True
    collect_interval_min: int = 15
    reprocess_interval_min: int = 30

    # --- Аналитика Альфа-Банка ---
    alfa_docs_path: Path = Path("/data/alfa")
    load_analytics_on_start: bool = True
    analytics_chunk_chars: int = 1200

    # --- Сервис ---
    service_api_key: str = ""  # если задан — все ручки, кроме /health, требуют X-API-Key
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
