"""Скачивание полного текста статьи с уважением к robots.txt и паузой между запросами."""

import logging
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

from news_parser.processing.cleaner import extract_main_text

log = logging.getLogger(__name__)


@dataclass
class FetchedPage:
    title: str | None
    text: str


class ArticleFetcher:
    def __init__(self, http: httpx.Client, user_agent: str, delay_s: float):
        self.http = http
        self.user_agent = user_agent
        self.delay_s = delay_s
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}
        self._lock = threading.Lock()

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                resp = self.http.get(f"{host}/robots.txt")
                if resp.status_code >= 400:
                    parser = None  # robots.txt нет — ограничений нет
                else:
                    parser.parse(resp.text.splitlines())
            except httpx.HTTPError:
                parser = None
            self._robots[host] = parser
        parser = self._robots[host]
        return parser is None or parser.can_fetch(self.user_agent, url)

    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        with self._lock:
            wait = self._last_hit.get(host, 0) + self.delay_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_hit[host] = time.monotonic()

    def fetch(self, url: str) -> FetchedPage | None:
        """Заголовок и текст статьи или None (запрещено robots.txt / ошибка / пустая страница)."""
        if not self._allowed(url):
            log.info("robots.txt запрещает %s", url)
            return None
        self._throttle(url)
        try:
            resp = self.http.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.info("не удалось скачать %s: %r", url, exc)
            return None
        text = extract_main_text(resp.text, url=url)
        if not text:
            return None
        meta = trafilatura.extract_metadata(resp.text)
        return FetchedPage(title=(meta.title if meta and meta.title else None), text=text)
