"""Очистка текста: HTML -> основной текст, нормализация, хеш для дедупликации."""

import hashlib
import html
import re

import trafilatura

_WS = re.compile(r"[ \t   ]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")
_TAGS = re.compile(r"<[^>]+>")
_NON_WORD = re.compile(r"[^\w]+")


def extract_main_text(page_html: str, url: str | None = None) -> str:
    """Достаёт из HTML-страницы текст статьи без меню, рекламы, «читайте также»."""
    text = trafilatura.extract(
        page_html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    return normalize_text(text or "")


def strip_html(fragment: str) -> str:
    """Для коротких HTML-фрагментов (анонсы в RSS), где trafilatura избыточна."""
    fragment = re.sub(r"<!--.*?-->", " ", fragment, flags=re.S)
    fragment = re.sub(r"</?(p|br|div|li)[^>]*>", "\n", fragment, flags=re.I)
    return normalize_text(html.unescape(_TAGS.sub(" ", fragment)))


def normalize_text(text: str) -> str:
    text = html.unescape(text).replace("\r", "\n")
    lines = [_WS.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return _MANY_NEWLINES.sub("\n\n", text).strip()


def content_hash(title: str, text: str) -> str:
    """Хеш, устойчивый к регистру, пунктуации и пробелам: одинаковый текст
    у разных источников даёт один и тот же хеш."""
    basis = _NON_WORD.sub(" ", f"{title}\n{text}".lower()).strip()
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()
