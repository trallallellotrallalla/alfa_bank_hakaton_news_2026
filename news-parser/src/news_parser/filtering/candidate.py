"""Кандидат — новость (событие), прошедшая жёсткие правила и векторный поиск,
вместе со всем, что о ней узнал этап отбора: какие чанки и по каким интересам клиента
совпали, статьи события и подобранная к нему аналитика Альфа-Банка."""

from dataclasses import dataclass, field

from news_parser.filtering.profile import Aspect
from news_parser.storage import repository as repo
from news_parser.storage.models import AnalyticsChunk, AnalyticsDocument, Article, Event


@dataclass
class AspectHit:
    hit: repo.ChunkHit
    aspect: Aspect
    labels: dict[str, list[str]]  # какие теги события совпали с правилом аспекта ({} — запасной поиск)


@dataclass
class AnalyticsHit:
    """Фрагмент аналитики, подобранный к новости, вместе с его документом (выжимка, позиция банка)."""

    chunk: AnalyticsChunk
    similarity: float  # сходство фрагмента с новостью
    document: AnalyticsDocument


@dataclass
class Candidate:
    event: Event
    passed_rules: bool = True  # False — найдено запасным поиском без правил
    chunks: dict[int, AspectHit] = field(default_factory=dict)  # chunk_id -> попадание
    by_aspect: dict[str, AspectHit] = field(default_factory=dict)  # aspect_id -> лучший чанк
    articles: list[Article] = field(default_factory=list)  # все статьи события (первоисточники)
    analytics: list[AnalyticsHit] = field(default_factory=list)

    def add(self, h: AspectHit) -> None:
        cid = h.hit.chunk.id
        if cid not in self.chunks or h.hit.similarity > self.chunks[cid].hit.similarity:
            self.chunks[cid] = h
        best = self.by_aspect.get(h.aspect.id)
        if best is None or h.hit.similarity > best.hit.similarity:
            self.by_aspect[h.aspect.id] = h

    @property
    def similarity(self) -> float:
        return max(h.hit.similarity for h in self.by_aspect.values())
