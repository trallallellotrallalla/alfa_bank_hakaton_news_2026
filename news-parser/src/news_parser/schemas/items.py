"""Сырые элементы, которые возвращают коллекторы, до какой-либо обработки."""

from dataclasses import dataclass
from datetime import datetime

from news_parser.schemas.extraction import Extraction


@dataclass
class RawItem:
    source_id: str
    source_name: str
    source_type: str  # rss | cbr_fx | moex_index | manual
    trust: float
    title: str
    url: str | None = None
    text: str | None = None  # готовый plain text (если есть)
    html: str | None = None  # HTML, из которого надо вытащить текст
    summary: str | None = None  # анонс из RSS — запасной вариант текста
    published_at: datetime | None = None
    fetch_full_text: bool = False  # скачать полный текст по url
    min_text_chars: int | None = None  # свой порог длины (для источников, отдающих только анонс)
    # Для структурированных источников (ЦБ, биржа) разметка известна заранее —
    # LLM не вызывается, событие не склеивается с похожими «вчерашними» цифрами.
    preset: Extraction | None = None
