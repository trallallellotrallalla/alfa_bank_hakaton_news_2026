"""Общий интерфейс коллектора и реестр типов источников."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import httpx
import yaml

from news_parser.schemas.items import RawItem

log = logging.getLogger(__name__)


class Collector(ABC):
    """Коллектор знает, как достать список свежих элементов из одного источника.
    Полный текст, очистка и всё остальное — забота пайплайна."""

    type: str

    def __init__(self, config: dict):
        self.config = config
        self.id: str = config["id"]
        self.name: str = config.get("name", self.id)
        self.url: str = config["url"]
        self.trust: float = float(config.get("trust", 0.5))

    @abstractmethod
    def collect(self, http: httpx.Client) -> list[RawItem]: ...

    def _item(self, **kwargs) -> RawItem:
        kwargs.setdefault("min_text_chars", self.config.get("min_text_chars"))
        return RawItem(source_id=self.id, source_name=self.name, source_type=self.type, trust=self.trust, **kwargs)


_REGISTRY: dict[str, type[Collector]] = {}


def register(cls: type[Collector]) -> type[Collector]:
    _REGISTRY[cls.type] = cls
    return cls


def load_collectors(path: Path) -> list[Collector]:
    # импорт ради регистрации типов
    from news_parser.parser.collectors import cbr, moex, rss  # noqa: F401

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    collectors = []
    for cfg in raw.get("sources", []):
        if cfg.get("enabled", True) is False:
            continue
        cls = _REGISTRY.get(cfg.get("type"))
        if cls is None:
            log.warning("неизвестный тип источника %r у %s — пропускаю", cfg.get("type"), cfg.get("id"))
            continue
        collectors.append(cls(cfg))
    return collectors
