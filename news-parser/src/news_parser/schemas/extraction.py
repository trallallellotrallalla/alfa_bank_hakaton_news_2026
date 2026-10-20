"""Структурированное представление новости — результат извлечения.

Эта же структура лежит в articles.extraction (JSONB) и отдаётся через API,
поэтому это часть контракта модуля с остальной командой.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

EntityType = Literal["company", "regulator", "government", "person", "country", "organization", "other"]
Direction = Literal["positive", "negative", "mixed", "neutral"]
Horizon = Literal["short_term", "medium_term", "long_term"]
ExtractionMethod = Literal["llm", "rules", "structured"]


class Fact(BaseModel):
    text: str
    # true — факт, прямо утверждаемый в тексте; false — прогноз, мнение, слух, ожидание
    confirmed: bool = True


class Number(BaseModel):
    name: str
    value: float | None = None
    unit: str | None = None


class Entity(BaseModel):
    name: str
    type: EntityType = "other"

    @field_validator("type", mode="before")
    @classmethod
    def _unknown_type(cls, v: object) -> object:
        allowed = {"company", "regulator", "government", "person", "country", "organization"}
        return v if v in allowed else "other"


class Extraction(BaseModel):
    """То, что модель (или правила) достали из статьи."""

    relevant: bool = True  # значима ли новость для бизнеса вообще
    summary: str = Field(min_length=1)
    facts: list[Fact] = []
    numbers: list[Number] = []
    entities: list[Entity] = []
    event_type: str = "other"
    macro_factors: list[str] = []
    industries: list[str] = []
    regions: list[str] = []  # субъекты РФ; "Россия" — если событие федеральное
    countries: list[str] = []  # другие страны, кроме России
    direction: Direction = "neutral"
    horizon: Horizon = "short_term"

    @field_validator("direction", mode="before")
    @classmethod
    def _direction(cls, v: object) -> object:
        return v if v in {"positive", "negative", "mixed", "neutral"} else "neutral"

    @field_validator("horizon", mode="before")
    @classmethod
    def _horizon(cls, v: object) -> object:
        return v if v in {"short_term", "medium_term", "long_term"} else "short_term"

    @field_validator("regions", "countries", mode="before")
    @classmethod
    def _strings(cls, v: object) -> object:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return v


class ExtractionMeta(BaseModel):
    """Как получена разметка — нужно для трассируемости выводов."""

    method: ExtractionMethod
    model: str | None = None
    llm_call_ids: list[int] = []
    rule_factors: dict[str, int] = {}  # что нашли правила (для сравнения с LLM)
    rule_industries: dict[str, int] = {}
    note: str | None = None
