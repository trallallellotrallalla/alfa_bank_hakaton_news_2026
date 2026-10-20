"""Загрузка аналитических материалов Альфа-Банка (PDF / TXT / MD) в отдельную коллекцию.

Документы режутся на фрагменты по границам предложений (не по фиксированному
числу символов посреди фразы), каждому фрагменту ставятся те же метки
macro_factors/industries, что и новостям, — так новость о ставке находит
записку Альфы о ставке. Разметка правилами, без LLM: документов мало, а
токены нужнее для новостей.

Загрузка идемпотентна: документ определяется по sha256 файла, повторно не грузится.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from news_parser.processing.cleaner import normalize_text
from news_parser.processing.embedder import Embedder
from news_parser.processing.prefilter import top_ids
from news_parser.storage import repository as repo
from news_parser.storage.db import session_scope
from news_parser.storage.models import AnalyticsChunk
from news_parser.taxonomy import Taxonomy

log = logging.getLogger(__name__)

SUPPORTED = {".pdf", ".txt", ".md"}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…»])\s+(?=[«\"(А-ЯЁA-Z0-9•–—-])")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")


@dataclass
class Chunk:
    index: int
    text: str
    page_from: int
    page_to: int


def read_pages(path: Path) -> list[str]:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return [page.extract_text() or "" for page in reader.pages]
    return [path.read_text(encoding="utf-8", errors="ignore")]


def _clean_page(raw: str) -> str:
    raw = _HYPHEN_BREAK.sub(r"\1\2", raw)  # «эконо-\nмика» -> «экономика»
    # строки PDF рвутся посреди предложения — склеиваем в сплошной текст
    return normalize_text(raw).replace("\n", " ")


def chunk_pages(pages: list[str], max_chars: int) -> list[Chunk]:
    """Упаковывает предложения в фрагменты до max_chars; соседние фрагменты
    перекрываются одним предложением, чтобы мысль на стыке не терялась."""
    sentences: list[tuple[str, int]] = []
    for page_no, raw in enumerate(pages, start=1):
        for sentence in _SENTENCE_SPLIT.split(_clean_page(raw)):
            sentence = sentence.strip()
            if len(sentence) > 2:
                sentences.append((sentence, page_no))

    chunks: list[Chunk] = []
    current: list[tuple[str, int]] = []
    size = 0
    for sentence, page in sentences:
        if current and size + len(sentence) > max_chars:
            chunks.append(_make_chunk(len(chunks), current))
            current = current[-1:]  # перекрытие
            size = len(current[0][0])
        current.append((sentence, page))
        size += len(sentence) + 1
    if current and (not chunks or len(current) > 1):
        chunks.append(_make_chunk(len(chunks), current))
    return chunks


def _make_chunk(index: int, parts: list[tuple[str, int]]) -> Chunk:
    return Chunk(index=index, text=" ".join(p[0] for p in parts), page_from=parts[0][1], page_to=parts[-1][1])


def _title(path: Path, pages: list[str]) -> str:
    for line in (pages[0] if pages else "").splitlines():
        line = line.strip()
        if len(line) > 10:
            return line[:200]
    return path.stem


def load_directory(directory: Path, taxonomy: Taxonomy, embedder: Embedder, max_chars: int) -> dict:
    if not directory.exists():
        log.warning("папка с аналитикой %s не найдена", directory)
        return {"loaded": [], "skipped": [], "errors": [f"нет папки {directory}"]}

    loaded, skipped, errors = [], [], []
    for path in sorted(p for p in directory.rglob("*") if p.suffix.lower() in SUPPORTED):
        try:
            doc_id = hashlib.sha256(path.read_bytes()).hexdigest()
            with session_scope() as s:
                if repo.analytics_doc_exists(s, doc_id):
                    skipped.append(path.name)
                    continue
            pages = read_pages(path)
            chunks = chunk_pages(pages, max_chars)
            if not chunks:
                errors.append(f"{path.name}: пустой текст (скан без текстового слоя?)")
                continue
            title = _title(path, pages)
            vectors = embedder.embed_passages([f"{title}. {c.text}" for c in chunks])
            with session_scope() as s:
                for chunk, vector in zip(chunks, vectors, strict=True):
                    s.add(
                        AnalyticsChunk(
                            doc_id=doc_id,
                            doc_title=title,
                            file_name=path.name,
                            chunk_index=chunk.index,
                            page_from=chunk.page_from,
                            page_to=chunk.page_to,
                            text=chunk.text,
                            macro_factors=top_ids(taxonomy.match_factors(chunk.text), limit=6),
                            industries=top_ids(taxonomy.match_industries(chunk.text), limit=6),
                            embedding=vector,
                        )
                    )
            loaded.append({"file": path.name, "title": title, "chunks": len(chunks)})
            log.info("аналитика загружена: %s (%d фрагментов)", path.name, len(chunks))
        except Exception as exc:
            log.exception("не удалось загрузить %s", path)
            errors.append(f"{path.name}: {exc!r}")
    return {"loaded": loaded, "skipped": skipped, "errors": errors}
