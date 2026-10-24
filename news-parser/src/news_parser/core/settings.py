"""Конфигурация модуля. Всё берётся из переменных окружения (или файла .env).

Описание каждой переменной — в .env.example и README.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent.parent  # news_parser/ (здесь лежит config/)
REPO_ROOT = PACKAGE_DIR.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), extra="ignore")

    # --- База данных (PostgreSQL + pgvector) ---
    database_url: str = "postgresql+psycopg://news:news@localhost:5432/news"
    db_schema: str = "news"

    # --- LLM (OpenAI-совместимый API организаторов кейса) ---
    llm_api_url: str = "https://api.alfahack-gateway26.ru/v1"  # без /chat/completions
    llm_api_key: str = ""  # пусто — LLM выключена, разметка правилами
    llm_model: str = "qwen/qwen3.6-35b-a3b"  # ID из списка разрешённых (llm/client.py)
    llm_timeout_s: float = 90.0
    llm_json_mode: bool = False  # response_format=json_object — включать, только если API его поддерживает
    llm_max_tokens: int = 2000  # с запасом: Qwen может начать ответ с рассуждений
    # Рассуждения модели перед ответом: "none" — выключены (Qwen3.6 иначе тратит весь лимит на «мысли»
    # и отдаёт пустой ответ). Пусто — параметр не отправляется (для моделей без рассуждений).
    llm_reasoning_effort: str = "none"
    llm_extra_body: str = ""  # JSON с доп. параметрами запроса, отправляется как есть
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

    news_chunk_chars: int = 900  # размер чанка статьи (символов)
    news_max_chunks: int = 12  # длинные статьи: дальше 12 чанков суть уже не нужна

    # --- Подбор новостей под профиль клиента (get_packets, match_client) ---
    match_window_days: int = 14  # насколько старые события учитывать
    match_min_similarity: float = 0.3  # ниже — чанк считается не связанным с клиентом
    # Запасной поиск: если жёсткие правила пропустили меньше MATCH_MIN_NEWS новостей,
    # добрать векторным поиском без правил (с порогом сходства выше на MATCH_FALLBACK_MARGIN).
    # Такие новости помечаются passed_rules=false. MATCH_FALLBACK=false — только правила.
    match_fallback: bool = True
    match_min_news: int = 3
    match_fallback_margin: float = 0.15
    # Откуда брать профиль по uid (get_packets, match_client): таблицы companies и
    # payments модуля клиентских данных (schema.sql). Пусто — та же база, что DATABASE_URL.
    profiles_database_url: str | None = None
    profiles_db_schema: str = "public"

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
    # PDF-сканы (без текстового слоя) распознаются мультимодальной моделью: текст + графики + таблицы
    analytics_vision: bool = True
    llm_vision_model: str = "qwen/qwen3-vl-30b-a3b-instruct"
    analytics_vision_max_side: int = 1400  # длинная сторона картинки страницы, px (качество/токены)
    analytics_vision_workers: int = 4  # страниц параллельно (модель отвечает ~30 с на страницу)
    analytics_profile_max_chars: int = 60000  # сколько текста документа отдавать LLM для профиля
    # Подбор аналитики к новости в два шага: документы (по тегам и выжимке) -> фрагменты в них
    analytics_docs_per_news: int = 2
    analytics_max_age_days: int = 730  # документы старше не подбираются (без даты — подбираются)

    # --- Логи ---
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
