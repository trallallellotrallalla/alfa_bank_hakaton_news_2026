"""RSS/Atom-ленты СМИ и регуляторов."""

import calendar
from datetime import UTC, datetime

import feedparser
import httpx

from news_parser.collectors.base import Collector, register
from news_parser.processing.cleaner import strip_html
from news_parser.schemas.items import RawItem


def _entry_datetime(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)


def _entry_text(entry) -> str | None:
    """Полный текст, если лента его отдаёт (РБК: rbc_news:full-text, Atom: content)."""
    for key in ("rbc_news_full-text", "full-text", "yandex_full-text"):
        if entry.get(key):
            return strip_html(entry[key])
    for content in entry.get("content") or []:
        value = content.get("value")
        if value and len(value) > 500:
            return strip_html(value)
    return None


@register
class RssCollector(Collector):
    type = "rss"

    def collect(self, http: httpx.Client) -> list[RawItem]:
        resp = http.get(self.url)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        fetch_full = bool(self.config.get("fetch_full_text", False))
        # headline_only: в ленте только заголовок/короткий анонс — работаем по нему
        headline_only = bool(self.config.get("headline_only", False))
        items = []
        for entry in feed.entries[: int(self.config.get("max_items", 30))]:
            title = strip_html(entry.get("title", ""))
            link = entry.get("link")
            if not title or not link:
                continue
            text = _entry_text(entry)
            summary = strip_html(entry.get("summary", "") or entry.get("description", ""))
            if headline_only and not text:
                text = f"{title}. {summary}".strip() if summary and summary != title else title
            items.append(
                self._item(
                    title=title,
                    url=link,
                    text=text,
                    summary=summary,
                    published_at=_entry_datetime(entry),
                    fetch_full_text=fetch_full and not text,
                )
            )
        return items
