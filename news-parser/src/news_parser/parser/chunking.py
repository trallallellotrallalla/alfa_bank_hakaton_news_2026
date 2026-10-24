"""Нарезка текста на смысловые фрагменты (чанки) по границам предложений.

Общая для новостей и аналитики Альфа-Банка: агенту отдаются именно чанки —
готовые куски текста, которые локальная LLM читает без доступа к URL.
"""

import re
from dataclasses import dataclass

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…»])\s+(?=[«\"(А-ЯЁA-Z0-9•–—-])")


@dataclass
class Chunk:
    index: int
    text: str
    page_from: int
    page_to: int


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if len(s.strip()) > 2]


def pack_sentences(sentences: list[tuple[str, int]], max_chars: int) -> list[Chunk]:
    """Упаковывает предложения (текст, номер страницы) в фрагменты до max_chars;
    соседние фрагменты перекрываются одним предложением, чтобы мысль на стыке не терялась."""
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


def chunk_text(text: str, max_chars: int, max_chunks: int | None = None) -> list[str]:
    """Чанки статьи: абзацы режутся на предложения, предложения упаковываются
    в фрагменты. Короткая статья (или только заголовок) — один чанк."""
    sentences = [(s, 1) for paragraph in text.split("\n") for s in split_sentences(paragraph)]
    if not sentences:
        return [text.strip()] if text.strip() else []
    chunks = [c.text for c in pack_sentences(sentences, max_chars)]
    return chunks[:max_chunks] if max_chunks else chunks
