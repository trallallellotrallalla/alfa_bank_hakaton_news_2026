"""Справочник меток (config/taxonomy.yaml) и rule-based разметка по ключевым словам."""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from news_parser.settings import get_settings


def _compile_keyword(keyword: str) -> str:
    """'ключев ставк' -> основы слов подряд; 're:...' -> регулярка целым словом."""
    if keyword.startswith("re:"):
        return rf"(?<!\w)(?:{keyword[3:]})(?!\w)"
    tokens = [re.escape(t) + r"\w*" for t in keyword.lower().split()]
    return r"(?<!\w)" + r"\s+".join(tokens)


def _compile_group(keywords: list[str]) -> re.Pattern[str] | None:
    if not keywords:
        return None
    return re.compile("|".join(_compile_keyword(k) for k in keywords), re.IGNORECASE)


@dataclass
class Taxonomy:
    macro_factors: dict[str, str]  # id -> название
    industries: dict[str, str]  # id -> название
    industry_okved: dict[str, list[str]]  # id -> двузначные коды ОКВЭД
    event_types: dict[str, str]
    _factor_patterns: dict[str, re.Pattern[str]] = field(default_factory=dict, repr=False)
    _industry_patterns: dict[str, re.Pattern[str]] = field(default_factory=dict, repr=False)
    _stop_pattern: re.Pattern[str] | None = field(default=None, repr=False)
    _business_pattern: re.Pattern[str] | None = field(default=None, repr=False)
    stop_url_parts: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Taxonomy":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        tax = cls(
            macro_factors={k: v["name"] for k, v in raw["macro_factors"].items()},
            industries={k: v["name"] for k, v in raw["industries"].items()},
            industry_okved={k: [str(c) for c in v["okved"]] for k, v in raw["industries"].items()},
            event_types=dict(raw["event_types"]),
            stop_url_parts=list(raw.get("stop_url_parts", [])),
        )
        for k, v in raw["macro_factors"].items():
            if p := _compile_group(v.get("keywords", [])):
                tax._factor_patterns[k] = p
        for k, v in raw["industries"].items():
            if p := _compile_group(v.get("keywords", [])):
                tax._industry_patterns[k] = p
        tax._stop_pattern = _compile_group(raw.get("stop_keywords", []))
        tax._business_pattern = _compile_group(raw.get("business_keywords", []))
        return tax

    # --- rule-based разметка ---

    def match_factors(self, text: str) -> dict[str, int]:
        """id фактора -> число совпадений ключевых слов."""
        return _count(self._factor_patterns, text)

    def match_industries(self, text: str) -> dict[str, int]:
        return _count(self._industry_patterns, text)

    def stop_hits(self, text: str) -> int:
        return len(self._stop_pattern.findall(text)) if self._stop_pattern else 0

    def business_hits(self, text: str) -> int:
        return len(self._business_pattern.findall(text)) if self._business_pattern else 0

    # --- нормализация того, что вернула LLM ---

    def clean_factors(self, ids: list[str]) -> list[str]:
        return _known(ids, self.macro_factors)

    def clean_industries(self, ids: list[str]) -> list[str]:
        return _known(ids, self.industries)

    def clean_event_type(self, value: str | None) -> str:
        return value if value in self.event_types else "other"

    def okved_for(self, industry_ids: list[str]) -> list[str]:
        codes: set[str] = set()
        for i in industry_ids:
            codes.update(self.industry_okved.get(i, []))
        return sorted(codes)

    def as_dict(self) -> dict:
        return {
            "macro_factors": self.macro_factors,
            "industries": {
                k: {"name": v, "okved": self.industry_okved[k]} for k, v in self.industries.items()
            },
            "event_types": self.event_types,
        }


def _count(patterns: dict[str, re.Pattern[str]], text: str) -> dict[str, int]:
    hits = {}
    for key, pattern in patterns.items():
        n = len(pattern.findall(text))
        if n:
            hits[key] = n
    return hits


def _known(ids: list[str], vocabulary: dict[str, str]) -> list[str]:
    seen: list[str] = []
    for i in ids:
        i = str(i).strip()
        if i in vocabulary and i not in seen:
            seen.append(i)
    return seen


@lru_cache
def get_taxonomy() -> Taxonomy:
    return Taxonomy.load(get_settings().taxonomy_config)
