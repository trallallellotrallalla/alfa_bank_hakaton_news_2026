"""Сборка зависимостей модуля в одном месте (одни и те же объекты для API, планировщика и CLI).

Здесь же связаны слои: отбор (filtering) -> сборка ответа (output).
"""

from dataclasses import dataclass
from functools import lru_cache

from news_parser.parser.analytics_loader import AnalyticsLoader
from news_parser.filtering.matcher import ProfileMatcher
from news_parser.schemas.client import ClientProfile
from news_parser.output.match_response import build_match_response
from news_parser.schemas.match import MatchOptions, ProfileMatchResponse
from news_parser.parser.pipeline import Pipeline
from news_parser.core.embedder import Embedder
from news_parser.llm.client import LlmClient
from news_parser.core.settings import Settings, get_settings
from news_parser.storage.repository import DbUsageStore
from news_parser.core.taxonomy import Taxonomy, get_taxonomy


@dataclass
class Services:
    settings: Settings
    taxonomy: Taxonomy
    embedder: Embedder
    llm: LlmClient
    pipeline: Pipeline
    matcher: ProfileMatcher
    analytics_loader: AnalyticsLoader

    def match(self, profile: ClientProfile, opts: MatchOptions) -> ProfileMatchResponse:
        """Отбор под клиента (правила -> вектор -> аналитика) и сборка ответа."""
        selection = self.matcher.select(profile, opts)
        return build_match_response(profile, selection, opts, self.taxonomy, self.embedder.model_name)

    def load_analytics(self, force: bool = False) -> dict:
        """Загрузить новые документы из ALFA_DOCS_PATH (force — перезагрузить все; кеш распознавания
        и профилей рядом с файлами при этом используется, токены повторно не тратятся)."""
        return self.analytics_loader.load_directory(self.settings.alfa_docs_path, force=force)


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
        max_tokens=settings.llm_max_tokens,
        extra_body=settings.llm_extra_body,
        reasoning_effort=settings.llm_reasoning_effort,
    )
    # тот же API и ключ, но мультимодальная модель — для распознавания PDF-сканов аналитики
    vision_llm = LlmClient(
        api_url=settings.llm_api_url,
        api_key=settings.llm_api_key,
        model=settings.llm_vision_model,
        usage=DbUsageStore(),
        daily_budget=settings.llm_daily_token_budget,
        timeout_s=max(settings.llm_timeout_s, 180.0),
        json_mode=False,
        max_tokens=3000,
        reasoning_effort=settings.llm_reasoning_effort,
    )
    return Services(
        settings,
        taxonomy,
        embedder,
        llm,
        Pipeline(settings, taxonomy, embedder, llm),
        ProfileMatcher(embedder, taxonomy, settings),
        AnalyticsLoader(settings, taxonomy, embedder, llm, vision_llm),
    )
