"""Официальные курсы валют ЦБ РФ (XML_daily.asp).

Это не новость, а цифры, поэтому событие создаётся только при существенном
изменении курса (alert_threshold_pct). Разметка известна заранее — LLM не нужна.
"""

import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

import httpx

from news_parser.collectors.base import Collector, register
from news_parser.schemas.extraction import Entity, Extraction, Fact, Number
from news_parser.schemas.items import RawItem


def parse_rates(xml_bytes: bytes) -> tuple[datetime, dict[str, float]]:
    root = ET.fromstring(xml_bytes)
    date = datetime.strptime(root.attrib["Date"], "%d.%m.%Y").replace(tzinfo=UTC)
    rates = {}
    for v in root.findall("Valute"):
        code = v.findtext("CharCode")
        value = float(v.findtext("Value", "0").replace(",", "."))
        nominal = int(v.findtext("Nominal", "1"))
        if code and nominal:
            rates[code] = value / nominal
    return date, rates


def _fmt(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


@register
class CbrFxCollector(Collector):
    type = "cbr_fx"

    def _fetch(self, http: httpx.Client, date: datetime | None) -> tuple[datetime, dict[str, float]]:
        params = {"date_req": date.strftime("%d/%m/%Y")} if date else None
        resp = http.get(self.url, params=params)
        resp.raise_for_status()
        return parse_rates(resp.content)

    def collect(self, http: httpx.Client) -> list[RawItem]:
        currencies = self.config.get("currencies", ["USD", "EUR", "CNY"])
        threshold = float(self.config.get("alert_threshold_pct", 1.0))

        last_date, last = self._fetch(http, None)
        # ищем предыдущую дату установления курсов (выходные ЦБ пропускает)
        prev_date, prev = last_date, last
        probe = last_date
        for _ in range(7):
            probe -= timedelta(days=1)
            prev_date, prev = self._fetch(http, probe)
            if prev_date != last_date:
                break
        if prev_date == last_date:
            return []

        changes = {
            c: (last[c], (last[c] / prev[c] - 1) * 100) for c in currencies if c in last and c in prev and prev[c]
        }
        significant = {c: v for c, v in changes.items() if abs(v[1]) >= threshold}
        if not significant:
            return []
        return [self._build_item(last_date, prev_date, changes, significant)]

    def _build_item(self, last_date, prev_date, changes, significant) -> RawItem:
        d1, d0 = last_date.strftime("%d.%m.%Y"), prev_date.strftime("%d.%m.%Y")
        lines = [f"{c}: {_fmt(rate, 4)} руб. ({chg:+.2f}% к {d0})" for c, (rate, chg) in changes.items()]
        weakening = sum(1 for _, chg in significant.values() if chg > 0)
        trend = "ослабление рубля" if weakening > len(significant) / 2 else "укрепление рубля"
        title = f"ЦБ РФ на {d1}: {trend} — " + ", ".join(
            f"{c} {_fmt(rate)} руб. ({chg:+.1f}%)" for c, (rate, chg) in significant.items()
        )
        text = (
            f"Банк России установил официальные курсы валют на {d1}.\n"
            + "\n".join(lines)
            + f"\nСущественное изменение (порог {self.config.get('alert_threshold_pct', 1.0)}%): {trend}."
        )
        preset = Extraction(
            summary=f"Официальный курс ЦБ на {d1}: {trend} ({', '.join(significant)}).",
            facts=[Fact(text=line, confirmed=True) for line in lines],
            numbers=[Number(name=f"курс {c}", value=round(rate, 4), unit="руб.") for c, (rate, _) in changes.items()]
            + [Number(name=f"изменение {c}", value=round(chg, 2), unit="%") for c, (_, chg) in changes.items()],
            entities=[Entity(name="Банк России", type="regulator")],
            event_type="market_move",
            macro_factors=["fx_rub", "foreign_trade"],
            regions=["Россия"],
            # ослабление рубля: плюс экспортёрам, минус импортёрам — для бизнеса в целом «mixed»
            direction="mixed",
            horizon="short_term",
        )
        return self._item(
            title=title,
            url=f"{self.url}?date_req={last_date.strftime('%d/%m/%Y')}",
            text=text,
            published_at=last_date,
            preset=preset,
        )
