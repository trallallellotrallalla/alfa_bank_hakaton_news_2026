"""Сборка зависимостей модуля в одном месте (одни и те же объекты для API, планировщика и CLI)."""

from dataclasses import dataclass
from functools import lru_cache

from news_parser.analytics.alfa_loader import load_directory
from news_parser.pipeline import Pipeline
from news_parser.processing.embedder import Embedder
from news_parser.processing.llm_client import LlmClient
from news_parser.settings import Settings, get_settings
from news_parser.storage.repository import DbUsageStore
from news_parser.taxonomy import Taxonomy, get_taxonomy


@dataclass
class Services:
    settings: Settings
    taxonomy: Taxonomy
    embedder: Embedder
    llm: LlmClient
    pipeline: Pipeline

    def load_analytics(self) -> dict:
        return load_directory(
            self.settings.alfa_docs_path, self.taxonomy, self.embedder, self.settings.analytics_chunk_chars
        )


@lru_cache
def get_services() -> Services:
    settings = get_settings()
    taxonomy = get_taxonomy()
    embedder = Embedder(settings.embedding_model, settings.embedding_dim, settings.embedding_cache_dir)
    llm = LlmClient(
        api_url=settings.llm_api_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        usage=DbUsageStore(),
        daily_budget=settings.llm_daily_token_budget,
        timeout_s=settings.llm_timeout_s,
        json_mode=settings.llm_json_mode,
    )
    return Services(settings, taxonomy, embedder, llm, Pipeline(settings, taxonomy, embedder, llm))
