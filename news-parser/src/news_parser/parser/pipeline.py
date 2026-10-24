"""Пайплайн обработки: сбор → текст → дедуп → префильтр → извлечение → эмбеддинг → событие.

Каждый элемент обрабатывается независимо: ошибка в одной статье не роняет сбор.
Медленные шаги (сеть, LLM, эмбеддинги) выполняются вне транзакций БД.
"""

import logging
import re
import threading
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import httpx

from news_parser.parser.collectors.base import load_collectors
from news_parser.parser.chunking import chunk_text
from news_parser.parser.cleaner import content_hash, extract_main_text, normalize_text
from news_parser.parser.clustering import assign_event, attach_duplicate, refresh_event_after_llm
from news_parser.core.embedder import Embedder
from news_parser.llm.classifier import Extractor
from news_parser.parser.fetcher import ArticleFetcher
from news_parser.llm.client import BudgetExceeded, LlmClient, LlmUnavailable
from news_parser.parser.prefilter import PrefilterResult, prefilter, top_ids
from news_parser.schemas.extraction import Extraction, ExtractionMeta
from news_parser.schemas.items import RawItem
from news_parser.core.settings import Settings
from news_parser.storage import repository as repo
from news_parser.storage.db import session_scope
from news_parser.storage.models import Article, ArticleChunk
from news_parser.core.taxonomy import Taxonomy

log = logging.getLogger(__name__)

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


@dataclass
class ProcessResult:
    status: str  # known_url | duplicate | filtered | extracted | rules_only | pending_llm | structured
    article_id: int | None = None
    event_id: int | None = None
    reason: str | None = None


@dataclass
class SourceReport:
    source_id: str
    items: int = 0
    statuses: dict[str, int] = field(default_factory=dict)
    error: str | None = None


def rules_extraction(title: str, text: str, pf: PrefilterResult) -> Extraction:
    """Запасная разметка без LLM: первые предложения + метки по ключевым словам."""
    sentences = _SENTENCE_END.split(text.replace("\n", " "))
    summary = ""
    for sentence in sentences:
        if len(summary) + len(sentence) > 400:
            break
        summary = f"{summary} {sentence}".strip()
    return Extraction(
        summary=summary or title,
        macro_factors=top_ids(pf.factors),
        industries=top_ids(pf.industries),
    )


def _add_chunks(s, article: Article, event_id: int | None, chunks: list[str], vectors: list[list[float]]) -> None:
    for i, (text, vector) in enumerate(zip(chunks, vectors, strict=True)):
        s.add(ArticleChunk(article_id=article.id, event_id=event_id, chunk_index=i, text=text, embedding=vector))


def embedding_text(title: str, ex: Extraction) -> str:
    facts = " ".join(f.text for f in ex.facts[:5])
    return f"{title}. {ex.summary} {facts}".strip()


class Pipeline:
    def __init__(self, settings: Settings, taxonomy: Taxonomy, embedder: Embedder, llm: LlmClient):
        self.settings = settings
        self.taxonomy = taxonomy
        self.embedder = embedder
        self.llm = llm
        self.extractor = Extractor(llm, taxonomy, settings.llm_max_input_chars)
        self.http = httpx.Client(
            timeout=settings.http_timeout_s,
            headers={"User-Agent": settings.http_user_agent},
            follow_redirects=True,
        )
        self.fetcher = ArticleFetcher(self.http, settings.http_user_agent, settings.http_delay_s)
        self._collect_lock = threading.Lock()
        self._write_lock = threading.Lock()  # кластеризация последовательна, иначе дубли событий

    # --- сбор по всем источникам ---

    def collect(self, source_ids: list[str] | None = None) -> dict:
        if not self._collect_lock.acquire(blocking=False):
            return {"skipped": "сбор уже идёт"}
        started = datetime.now(UTC)
        reports = []
        try:
            for collector in load_collectors(self.settings.sources_config):
                if source_ids and collector.id not in source_ids:
                    continue
                report = SourceReport(collector.id)
                try:
                    items = collector.collect(self.http)
                except Exception as exc:
                    log.warning("источник %s недоступен: %r", collector.id, exc)
                    report.error = repr(exc)[:500]
                    reports.append(report)
                    continue
                report.items = len(items)
                counter: Counter[str] = Counter()
                for item in items:
                    try:
                        counter[self.process_item(item).status] += 1
                    except Exception:
                        log.exception("ошибка обработки %s", item.url)
                        counter["error"] += 1
                report.statuses = dict(counter)
                reports.append(report)
                log.info("источник %s: %s", collector.id, report.statuses)
        finally:
            self._collect_lock.release()
        return {
            "started_at": started.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "sources": [asdict(r) for r in reports],
        }

    # --- обработка одного элемента ---

    def process_item(self, item: RawItem, *, force: bool = False) -> ProcessResult:
        """force=True — элемент добавлен вручную: не отсекаем по «бизнес-сигналу»,
        решение о релевантности оставляем модели."""
        if item.url:
            with session_scope() as s:
                known = repo.find_article_by_url(s, item.url)
                if known:
                    return ProcessResult("known_url", known.id, known.event_id)

        text, page_title = self._resolve_text(item)
        title = normalize_text(item.title or page_title or item.url or "")

        # 1. дедуп, префильтр, запись статьи
        with self._write_lock, session_scope() as s:
            # ищем оригинал ДО вставки, иначе autoflush найдёт саму новую статью
            original = repo.find_original_by_hash(s, content_hash(title, text))
            article = Article(
                source_id=item.source_id,
                source_name=item.source_name,
                source_type=item.source_type,
                trust=item.trust,
                url=item.url,
                title=title,
                text=text,
                content_hash=content_hash(title, text),
                published_at=item.published_at,
                status="new",
            )
            s.add(article)
            if original:
                article.status, article.status_reason = "duplicate", f"same_as:{original.id}"
                s.flush()
                attach_duplicate(s, article, original)
                return ProcessResult("duplicate", article.id, article.event_id, article.status_reason)

            pf = None
            if item.preset is None:
                pf = prefilter(
                    self.taxonomy,
                    title=title,
                    text=text,
                    min_chars=item.min_text_chars or self.settings.min_text_chars,
                    require_signal=self.settings.prefilter_require_signal and not force,
                )
                if not pf.keep:
                    article.status, article.status_reason = "filtered", pf.reason
                    s.flush()
                    return ProcessResult("filtered", article.id, None, pf.reason)
            s.flush()
            article_id = article.id

        # 2. извлечение (вне транзакции: LLM может отвечать десятки секунд)
        if item.preset is not None:
            ex, meta, status = item.preset, ExtractionMeta(method="structured"), "structured"
        else:
            ex, meta, status = self._extract(article_id, title, text, pf)

        if not ex.relevant:
            with session_scope() as s:
                a = s.get(Article, article_id)
                a.status, a.status_reason = "filtered", "llm_not_relevant"
                a.extraction, a.extraction_meta = ex.model_dump(), meta.model_dump()
            return ProcessResult("filtered", article_id, None, "llm_not_relevant")

        # 3. эмбеддинги (статья целиком + её чанки одним батчем) и событие
        chunks = self._chunks(title, text)
        vectors = self.embedder.embed_passages([embedding_text(title, ex)] + [f"{title}. {c}" for c in chunks])
        vector, chunk_vectors = vectors[0], vectors[1:]
        with self._write_lock, session_scope() as s:
            a = s.get(Article, article_id)
            a.status = status
            a.status_reason = meta.note
            a.extraction, a.extraction_meta = ex.model_dump(), meta.model_dump()
            a.embedding = vector
            event = assign_event(
                s,
                a,
                ex,
                self.taxonomy,
                threshold=self.settings.cluster_similarity_threshold,
                window_hours=self.settings.cluster_window_hours,
                structured=item.preset is not None,
                prefer_as_main=status in ("extracted", "structured"),
            )
            _add_chunks(s, a, event.id, chunks, chunk_vectors)
            return ProcessResult(status, article_id, event.id)

    def _chunks(self, title: str, text: str) -> list[str]:
        return chunk_text(text, self.settings.news_chunk_chars, self.settings.news_max_chunks) or [title]

    def backfill_chunks(self, batch: int = 50) -> dict:
        """Нарезать на чанки статьи, собранные до появления чанков (или пропущенные)."""
        total = 0
        while True:
            with session_scope() as s:
                todo = [(a.id, a.title, a.text, a.event_id) for a in repo.articles_without_chunks(s, limit=batch)]
            if not todo:
                break
            prepared = [(aid, title, event_id, self._chunks(title, text)) for aid, title, text, event_id in todo]
            texts = [f"{title}. {c}" for _, title, _, chunks in prepared for c in chunks]
            vectors = iter(self.embedder.embed_passages(texts))
            with self._write_lock, session_scope() as s:
                for aid, _title, event_id, chunks in prepared:
                    a = s.get(Article, aid)
                    _add_chunks(s, a, event_id, chunks, [next(vectors) for _ in chunks])
            total += len(todo)
        return {"articles_chunked": total}

    def _resolve_text(self, item: RawItem) -> tuple[str, str | None]:
        """Текст статьи (и заголовок страницы, если её пришлось скачивать)."""
        text, page_title = item.text or "", None
        if not text and item.html:
            text = extract_main_text(item.html, url=item.url)
        if not text and item.fetch_full_text and item.url:
            page = self.fetcher.fetch(item.url)
            if page:
                text, page_title = page.text, page.title
        if not text:
            text = item.summary or ""
        return normalize_text(text), page_title

    def _extract(
        self, article_id: int, title: str, text: str, pf: PrefilterResult
    ) -> tuple[Extraction, ExtractionMeta, str]:
        meta = ExtractionMeta(method="rules", rule_factors=pf.factors, rule_industries=pf.industries)
        if not self.llm.configured:
            return rules_extraction(title, text, pf), meta, "rules_only"
        try:
            result = self.extractor.extract(title=title, text=text, article_id=article_id)
        except BudgetExceeded as exc:
            meta.note = f"budget: {exc}"
            return rules_extraction(title, text, pf), meta, "pending_llm"
        except LlmUnavailable as exc:
            meta.note = f"llm_unavailable: {exc}"[:500]
            return rules_extraction(title, text, pf), meta, "pending_llm"
        except ValueError as exc:
            meta.note = f"invalid_llm_output: {exc}"[:500]
            return rules_extraction(title, text, pf), meta, "rules_only"
        meta.method, meta.model, meta.llm_call_ids = "llm", self.llm.model, result.call_ids
        return result.extraction, meta, "extracted"

    # --- дообработка статей, которые не дошли до LLM ---

    def reprocess_pending(self, limit: int = 30) -> dict:
        """Статьи со статусом pending_llm (не хватило бюджета / LLM лежала) —
        пробуем ещё раз и уточняем метки их событий."""
        with session_scope() as s:
            pending = [(a.id, a.title, a.text) for a in repo.pending_llm_articles(s, limit=limit)]
        done = 0
        for article_id, title, text in pending:
            try:
                result = self.extractor.extract(title=title, text=text, article_id=article_id)
            except LlmUnavailable:
                break  # бюджет/LLM всё ещё недоступны — дальше нет смысла
            except ValueError as exc:
                with session_scope() as s:
                    a = s.get(Article, article_id)
                    a.status, a.status_reason = "rules_only", f"invalid_llm_output: {exc}"[:500]
                continue
            with self._write_lock, session_scope() as s:
                a = s.get(Article, article_id)
                meta = ExtractionMeta.model_validate(a.extraction_meta or {"method": "rules"})
                meta.method, meta.model, meta.llm_call_ids, meta.note = "llm", self.llm.model, result.call_ids, None
                a.extraction, a.extraction_meta = result.extraction.model_dump(), meta.model_dump()
                a.status, a.status_reason = "extracted", None
                refresh_event_after_llm(s, a, result.extraction, self.taxonomy)
            done += 1
        return {"pending": len(pending), "extracted": done}
