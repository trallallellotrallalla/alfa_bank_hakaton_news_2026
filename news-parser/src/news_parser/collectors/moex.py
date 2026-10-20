"""Индексы Московской биржи (MOEX ISS, история закрытий).

Как и курсы ЦБ: событие только при существенном дневном движении индекса.
"""

from datetime import UTC, datetime, timedelta

import httpx

from news_parser.collectors.base import Collector, register
from news_parser.schemas.extraction import Entity, Extraction, Fact, Number
from news_parser.schemas.items import RawItem


def _factor_for(index_id: str) -> str:
    return "bond_market" if index_id.upper().startswith("RGBI") else "equity_market"


@register
class MoexIndexCollector(Collector):
    type = "moex_index"

    def _closes(self, http: httpx.Client, index_id: str) -> list[tuple[str, float]]:
        resp = http.get(
            f"{self.url}/{index_id}.json",
            params={
                "iss.meta": "off",
                "history.columns": "TRADEDATE,CLOSE",
                "from": (datetime.now(UTC) - timedelta(days=14)).strftime("%Y-%m-%d"),
            },
        )
        resp.raise_for_status()
        rows = resp.json()["history"]["data"]
        return [(d, float(c)) for d, c in rows if c is not None]

    def collect(self, http: httpx.Client) -> list[RawItem]:
        threshold = float(self.config.get("alert_threshold_pct", 1.5))
        items = []
        for index_id, index_name in (self.config.get("indices") or {}).items():
            closes = self._closes(http, index_id)
            if len(closes) < 2:
                continue
            (d0, c0), (d1, c1) = closes[-2], closes[-1]
            change = (c1 / c0 - 1) * 100
            if abs(change) < threshold:
                continue
            items.append(self._build_item(index_id, index_name, d0, c0, d1, c1, change))
        return items

    def _build_item(self, index_id, index_name, d0, c0, d1, c1, change) -> RawItem:
        verb = "вырос" if change > 0 else "снизился"
        title = f"{index_name} {verb} на {abs(change):.2f}% по итогам торгов {d1}"
        fact = f"{index_name} ({index_id}) закрылся на уровне {c1:.2f} п. против {c0:.2f} п. {d0} ({change:+.2f}%)."
        preset = Extraction(
            summary=title + ".",
            facts=[Fact(text=fact, confirmed=True)],
            numbers=[
                Number(name=f"{index_id} закрытие", value=c1, unit="п."),
                Number(name=f"{index_id} изменение", value=round(change, 2), unit="%"),
            ],
            entities=[Entity(name="Московская биржа", type="organization")],
            event_type="market_move",
            macro_factors=[_factor_for(index_id)],
            regions=["Россия"],
            direction="positive" if change > 0 else "negative",
            horizon="short_term",
        )
        return self._item(
            title=title,
            url=f"{self.url}/{index_id}.json?till={d1}",
            text=fact,
            published_at=datetime.strptime(d1, "%Y-%m-%d").replace(tzinfo=UTC),
            preset=preset,
        )
