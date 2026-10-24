"""Отбор новостей и аналитики Альфа-Банка под профиль клиента — по схеме команды:

 Клиент ─┬─► теги (ОКВЭД, продукты → справочник)  ─► 1. ПРАВИЛА (rules.py): жёсткий отсев по тегам
         └─► тексты-запросы аспектов ─► эмбеддинг ─► 2. ВЕКТОРНЫЙ ПОИСК по новостям, прошедшим правила
                                                     3. АНАЛИТИКА: к каждой новости — по её вектору
                                                        среди фрагментов с общими тегами
                                                     4. РАНЖИРОВАНИЕ (ranking.py) — пока заглушка

Шаги 1 и 2 — один SQL-запрос: правила в WHERE, сходство в ORDER BY. Новость без нужных
тегов не попадает в отбор ни при каком сходстве векторов.

Запасной поиск (MATCH_FALLBACK): если правила пропустили меньше MATCH_MIN_NEWS новостей,
добираем векторным поиском без правил с повышенным порогом (passed_rules=False).

Результат — Selection: кандидаты со статьями и аналитикой. Превращение в JSON — output/.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from news_parser.core.embedder import Embedder
from news_parser.core.settings import Settings
from news_parser.core.taxonomy import Taxonomy
from news_parser.filtering.candidate import AnalyticsHit, AspectHit, Candidate
from news_parser.filtering.profile import Aspect, build_aspects
from news_parser.filtering.ranking import rank
from news_parser.filtering.rules import no_rule_filters, rule_filters
from news_parser.schemas.client import ClientProfile
from news_parser.schemas.match import MatchOptions
from news_parser.storage import repository as repo
from news_parser.storage.db import session_scope
from news_parser.storage.models import Event


@dataclass
class Selection:
    """Итог отбора — всё, что нужно для сборки ответа, без форматирования."""

    aspects: list[Aspect]
    candidates: list[Candidate]  # уже обрезано до limit_news, со статьями и аналитикой
    passed_rules: int  # сколько новостей прошло жёсткие правила
    fallback_used: bool
    window_days: int
    min_similarity: float


class ProfileMatcher:
    def __init__(self, embedder: Embedder, taxonomy: Taxonomy, settings: Settings):
        self.embedder = embedder
        self.taxonomy = taxonomy
        self.settings = settings

    def select(self, profile: ClientProfile, opts: MatchOptions) -> Selection:
        window_days = opts.window_days or self.settings.match_window_days
        min_sim = self.settings.match_min_similarity if opts.min_similarity is None else opts.min_similarity
        since = datetime.now(UTC) - timedelta(days=window_days)
        aspects = [a for a in build_aspects(profile, self.taxonomy) if not a.filters.is_empty()]
        vectors = self.embedder.embed_queries([a.query for a in aspects])
        per_aspect = max(30, opts.limit_news * 6)

        with session_scope() as s:
            # 1–2. правила + векторный поиск среди прошедших
            candidates: dict[int, Candidate] = {}
            for aspect, vec in zip(aspects, vectors, strict=True):
                rules = rule_filters(aspect, since=since, include_structured=opts.include_structured)
                for hit in repo.search_chunks(s, query_embedding=vec, filters=rules, limit=per_aspect):
                    if hit.similarity >= min_sim:
                        labels = repo.matched_labels(hit.event, rules)
                        candidates.setdefault(hit.event.id, Candidate(hit.event)).add(AspectHit(hit, aspect, labels))
            passed_rules = len(candidates)

            fallback_used = self.settings.match_fallback and passed_rules < self.settings.match_min_news
            if fallback_used:
                self._fallback(s, aspects, vectors, candidates, since, opts, min_sim, per_aspect)

            ordered = sorted(candidates.values(), key=lambda c: c.similarity, reverse=True)
            ordered.sort(key=lambda c: not c.passed_rules)  # правила важнее запасного поиска
            top = rank(ordered)[: opts.limit_news]

            # 3. статьи событий и аналитика к каждой новости
            articles = repo.event_articles(s, [c.event.id for c in top])
            for cand in top:
                cand.articles = articles[cand.event.id]
                cand.analytics = self._analytics_for(s, cand.event, opts.analytics_per_news, min_sim)

        return Selection(aspects, top, passed_rules, fallback_used, window_days, min_sim)

    def _fallback(self, s: Session, aspects, vectors, candidates: dict[int, Candidate], since, opts, min_sim, per_aspect):
        strict_sim = min_sim + self.settings.match_fallback_margin
        no_rules = no_rule_filters(since=since, include_structured=opts.include_structured)
        for aspect, vec in zip(aspects, vectors, strict=True):
            for hit in repo.search_chunks(s, query_embedding=vec, filters=no_rules, limit=per_aspect // 2):
                already_passed = hit.event.id in candidates and candidates[hit.event.id].passed_rules
                if hit.similarity < strict_sim or already_passed:
                    continue
                cand = candidates.setdefault(hit.event.id, Candidate(hit.event, passed_rules=False))
                cand.add(AspectHit(hit, aspect, {}))

    def _analytics_for(self, s: Session, event: Event, limit: int, min_sim: float) -> list[AnalyticsHit]:
        """Аналитика к новости в два шага:
        1. документы — с общими с новостью тегами (жёсткое правило), не старше ANALYTICS_MAX_AGE_DAYS,
           ближайшие по смыслу выжимки документа к новости (не больше ANALYTICS_DOCS_PER_NEWS);
        2. фрагменты — только внутри выбранных документов, ближайшие по смыслу к новости.
        Так фрагмент не «выпрыгнет» из документа на чужую тему. Новость без тегов аналитики не получает."""
        if not limit or event.embedding is None or not (event.macro_factors or event.industries):
            return []
        vec = [float(x) for x in event.embedding]
        docs = repo.select_documents(
            s,
            query_embedding=vec,
            macro_factors=event.macro_factors or None,
            industries=event.industries or None,
            not_older_than=date.today() - timedelta(days=self.settings.analytics_max_age_days),
            limit=self.settings.analytics_docs_per_news,
        )
        by_id = {doc.doc_id: doc for doc, sim in docs if sim >= min_sim}
        rows = repo.chunks_in_documents(s, query_embedding=vec, doc_ids=list(by_id), limit=limit)
        return [AnalyticsHit(chunk, sim, by_id[chunk.doc_id]) for chunk, sim in rows if sim >= min_sim]
