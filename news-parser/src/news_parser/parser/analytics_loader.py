"""Загрузка аналитических материалов Альфа-Банка (PDF / TXT / MD).

Для каждого документа:
1. ТЕКСТ СТРАНИЦ — по порядку, что найдётся первым:
   - текстовый слой PDF;
   - кеш прошлого распознавания (<имя>.analysis.json рядом с файлом);
   - Qwen3-VL по картинкам страниц: текст + описание графиков и таблиц (для PDF-сканов);
   - одноимённый .txt (например, OCR на Mac) — если LLM недоступна.
2. ЧИСТКА — авторы, контакты, колонтитулы, дисклеймеры (analytics_cleaner.py).
3. ПРОФИЛЬ ДОКУМЕНТА — название, дата, главные тезисы банка, позиция (stance), теги:
   через LLM, без неё — правила по ключевым словам.
4. ФРАГМЕНТЫ — нарезка по предложениям с номерами страниц; теги фрагмента = его
   собственные + теги документа; векторы фрагментов и документа.

Распознавание и профиль стоят токенов, поэтому сохраняются в <имя>.analysis.json рядом
с исходным файлом: при перезапуске и у других членов команды (если передать им файл)
токены повторно не тратятся. Кеш привязан к sha256 исходника — поменялся файл, кеш устарел.

Загрузка идемпотентна: документ определяется по sha256 файла и повторно не грузится
(force=True — перезагрузить всё; кеш при этом используется).
"""

import hashlib
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import text

from news_parser.core.embedder import Embedder
from news_parser.core.settings import Settings
from news_parser.core.taxonomy import Taxonomy
from news_parser.llm.client import LlmClient, LlmUnavailable
from news_parser.llm.doc_profiler import DocProfile, profile_document
from news_parser.llm.vision import transcribe_pages
from news_parser.parser.analytics_cleaner import clean_page
from news_parser.parser.chunking import Chunk, pack_sentences, split_sentences
from news_parser.parser.cleaner import normalize_text
from news_parser.parser.prefilter import top_ids
from news_parser.storage import repository as repo
from news_parser.storage.db import get_engine, session_scope
from news_parser.storage.models import AnalyticsChunk, AnalyticsDocument

log = logging.getLogger(__name__)

SUPPORTED = {".pdf", ".txt", ".md"}
CACHE_SUFFIX = ".analysis.json"
CACHE_VERSION = 1
DOC_TAGS = 3  # без LLM: сколько главных тегов документа (по правилам) получает каждый фрагмент
MIN_TEXT_PER_PAGE = 100  # меньше символов на страницу в среднем — PDF сохранён картинками
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
LOCK_KEY = 7_311_001  # ключ advisory-блокировки загрузки аналитики в Postgres


def read_pages(path: Path) -> list[str]:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return [page.extract_text() or "" for page in reader.pages]
    # в текстовых версиях страницы разделены символом перевода страницы (\f), как у pdftotext
    return path.read_text(encoding="utf-8", errors="ignore").split("\f")


def _clean_page(raw: str) -> str:
    raw = _HYPHEN_BREAK.sub(r"\1\2", raw)  # «эконо-\nмика» -> «экономика»
    # строки PDF рвутся посреди предложения — склеиваем в сплошной текст
    return normalize_text(raw).replace("\n", " ")


def chunk_pages(pages: list[str], max_chars: int) -> list[Chunk]:
    """Чанки документа с сохранением номеров страниц (для ссылки «стр. N»)."""
    sentences = [
        (sentence, page_no)
        for page_no, raw in enumerate(pages, start=1)
        for sentence in split_sentences(_clean_page(raw))
    ]
    return pack_sentences(sentences, max_chars)


def _union(a: list[str], b: list[str]) -> list[str]:
    return list(dict.fromkeys([*a, *b]))


def _first_line_title(pages: list[str], fallback: str) -> str:
    for line in (pages[0] if pages else "").splitlines():
        line = line.strip()
        if len(line) > 10:
            return line[:200]
    return fallback


def _page_images(pdf: Path) -> list:
    """Самая крупная картинка каждой страницы (у PDF-сканов это вся страница)."""
    images = []
    for page in PdfReader(str(pdf)).pages:
        imgs = sorted(page.images, key=lambda im: im.image.size[0] * im.image.size[1], reverse=True)
        images.append(imgs[0].image if imgs else None)
    return images


@dataclass
class _Cache:
    path: Path
    data: dict = field(default_factory=dict)
    changed: bool = False

    @classmethod
    def load(cls, path: Path, sha: str) -> "_Cache":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("source_sha256") == sha and data.get("version") == CACHE_VERSION:
                return cls(path, data)
        except (OSError, ValueError):
            pass
        return cls(path, {"version": CACHE_VERSION, "source_sha256": sha})

    def save(self) -> None:
        if not self.changed:
            return
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as exc:  # папка смонтирована только на чтение и т.п.
            log.warning("не удалось сохранить кеш %s (%s): при перезагрузке токены уйдут снова", self.path.name, exc)


class AnalyticsLoader:
    def __init__(
        self,
        settings: Settings,
        taxonomy: Taxonomy,
        embedder: Embedder,
        text_llm: LlmClient,
        vision_llm: LlmClient,
    ):
        self.settings = settings
        self.taxonomy = taxonomy
        self.embedder = embedder
        self.text_llm = text_llm
        self.vision_llm = vision_llm

    # --- публичное ---

    def load_directory(self, directory: Path, *, force: bool = False) -> dict:
        if not directory.exists():
            log.warning("папка с аналитикой %s не найдена", directory)
            return {"loaded": [], "skipped": [], "errors": [f"нет папки {directory}"]}
        # одна загрузка за раз во всех процессах (воркер и ручной запуск CLI), иначе
        # оба возьмутся за одни и те же файлы и потратят токены дважды
        with get_engine().connect() as lock_conn:
            if not lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar():
                return {"loaded": [], "skipped": [], "errors": ["загрузка аналитики уже идёт в другом процессе"]}
            try:
                return self._load_all(directory, force)
            finally:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})

    def _load_all(self, directory: Path, force: bool) -> dict:
        if force:
            with session_scope() as s:
                repo.delete_all_analytics(s)

        # документ = группа файлов с одним именем: PDF главный, .txt/.md — его текстовая версия
        groups: dict[Path, dict[str, Path]] = defaultdict(dict)
        for p in directory.rglob("*"):
            if p.suffix.lower() in SUPPORTED and not p.name.endswith(CACHE_SUFFIX):
                groups[p.with_suffix("")][p.suffix.lower()] = p

        loaded, skipped, errors = [], [], []
        for stem in sorted(groups):
            files = groups[stem]
            src = files.get(".pdf") or files.get(".txt") or files.get(".md")
            try:
                result = self._load_document(src, files)
                (loaded if result else skipped).append(result or src.name)
            except LlmUnavailable as exc:
                errors.append(f"{src.name}: LLM недоступна ({exc}) — повторится при следующей загрузке")
            except Exception as exc:
                log.exception("не удалось загрузить %s", src)
                errors.append(f"{src.name}: {exc!r}")
        return {"loaded": loaded, "skipped": skipped, "errors": errors}

    # --- один документ ---

    def _load_document(self, src: Path, files: dict[str, Path]) -> dict | None:
        doc_id = hashlib.sha256(src.read_bytes()).hexdigest()
        with session_scope() as s:
            if repo.analytics_doc_exists(s, doc_id):
                return None
        cache = _Cache.load(src.with_name(src.stem + CACHE_SUFFIX), doc_id)

        raw_pages, text_method = self._pages(src, files, cache)
        pages = [clean_page(p) for p in raw_pages]
        if not any(p.strip() for p in pages):
            raise ValueError("пустой текст: нет текстового слоя, LLM недоступна и нет .txt-версии")
        profile, profile_method = self._profile(src, pages, cache)
        cache.save()

        title = profile.title if profile else _first_line_title(pages, src.stem)
        doc_text = f"{title}\n" + "\n".join(pages)
        if profile:
            doc_factors, doc_industries = profile.macro_factors, profile.industries
        else:
            doc_factors = top_ids(self.taxonomy.match_factors(doc_text), limit=DOC_TAGS)
            doc_industries = top_ids(self.taxonomy.match_industries(doc_text), limit=DOC_TAGS)

        chunks = chunk_pages(pages, self.settings.analytics_chunk_chars)
        summary = profile.summary_text() if profile and profile.summary else None
        doc_vec, *chunk_vecs = self.embedder.embed_passages(
            [f"{title}. {summary or doc_text[:1500]}"] + [f"{title}. {c.text}" for c in chunks]
        )
        with session_scope() as s:
            s.add(
                AnalyticsDocument(
                    doc_id=doc_id,
                    file_name=src.name,
                    title=title,
                    published_date=profile.published_date if profile else None,
                    summary=summary,
                    stance=profile.stance if profile else None,
                    macro_factors=doc_factors,
                    industries=doc_industries,
                    text_method=text_method,
                    profile_method=profile_method,
                    embedding=doc_vec,
                )
            )
            for chunk, vector in zip(chunks, chunk_vecs, strict=True):
                s.add(
                    AnalyticsChunk(
                        doc_id=doc_id,
                        doc_title=title,
                        file_name=src.name,
                        chunk_index=chunk.index,
                        page_from=chunk.page_from,
                        page_to=chunk.page_to,
                        text=chunk.text,
                        macro_factors=_union(top_ids(self.taxonomy.match_factors(chunk.text), limit=6), doc_factors),
                        industries=_union(top_ids(self.taxonomy.match_industries(chunk.text), limit=6), doc_industries),
                        embedding=vector,
                    )
                )
        log.info("аналитика загружена: %s (%s, профиль: %s, фрагментов: %d)", src.name, text_method, profile_method, len(chunks))
        return {"file": src.name, "title": title, "chunks": len(chunks), "text": text_method, "profile": profile_method}

    def _pages(self, src: Path, files: dict[str, Path], cache: _Cache) -> tuple[list[str], str]:
        if src.suffix.lower() != ".pdf":
            return read_pages(src), "text"
        pages = read_pages(src)
        if sum(len(p) for p in pages) >= MIN_TEXT_PER_PAGE * max(len(pages), 1):
            return pages, "text_layer"
        if cache.data.get("pages"):
            return cache.data["pages"], cache.data.get("text_method", "vision")
        if self.settings.analytics_vision and self.vision_llm.configured:
            log.info("%s: нет текстового слоя — распознаю %d стр. через %s", src.name, len(pages), self.vision_llm.model)
            pages = transcribe_pages(
                self.vision_llm,
                _page_images(src),
                max_side=self.settings.analytics_vision_max_side,
                workers=self.settings.analytics_vision_workers,
            )
            cache.data.update(pages=pages, text_method="vision", vision_model=self.vision_llm.model)
            cache.changed = True
            return pages, "vision"
        text_version = files.get(".txt") or files.get(".md")
        if text_version:
            return read_pages(text_version), "ocr_txt"
        return pages, "text_layer"

    def _profile(self, src: Path, pages: list[str], cache: _Cache) -> tuple[DocProfile | None, str]:
        if cache.data.get("profile"):
            return DocProfile.model_validate(cache.data["profile"]), "llm"
        if not self.text_llm.configured:
            return None, "rules"
        try:
            profile = profile_document(
                self.text_llm,
                self.taxonomy,
                title_hint=src.stem,
                text="\n\n".join(f"[стр. {i}]\n{p}" for i, p in enumerate(pages, start=1)),
                max_chars=self.settings.analytics_profile_max_chars,
            )
        except ValueError as exc:  # модель дважды ответила не по схеме — обойдёмся правилами
            log.warning("%s: профиль через LLM не получился (%s) — правила", src.name, exc)
            return None, "rules"
        cache.data.update(profile=profile.model_dump(mode="json"), profile_model=self.text_llm.model)
        cache.changed = True
        return profile, "llm"
