"""Профиль клиента → «аспекты» для поиска в общей векторной базе.

Почему не один вектор на клиента: профиль — это таблица (коды, флаги, суммы),
модель эмбеддингов понимает её плохо, а один усреднённый вектор теряет
отдельные интересы (ставка, пошлины, отрасль контрагентов). Поэтому профиль
раскладывается на аспекты: у каждого — человекочитаемый текст-запрос
(векторизуется той же моделью, что новости и аналитика) и явные фильтры по
меткам таксономии. Аспект = «почему эта новость важна клиенту».

Поля ClientProfile совпадают с колонками таблицы companies из schema.sql,
так что строку из БД клиентских данных можно передавать как есть.
"""

import re
from dataclasses import dataclass, field

from news_parser.core.taxonomy import Taxonomy
from news_parser.schemas.client import ClientProfile, Counterparty


@dataclass
class AspectFilters:
    macro_factors: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    okved: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.macro_factors or self.industries or self.okved or self.regions or self.countries)


@dataclass
class Aspect:
    id: str
    title: str  # для человека и для объяснения «почему отобрано»
    query: str  # текст, который векторизуется
    weight: float  # важность аспекта для клиента (пригодится этапу ранжирования)
    filters: AspectFilters
    reason: str  # из каких полей профиля аспект возник (трассируемость)
    # кроме совпадения фильтра, у новости должна быть хотя бы одна бизнес-метка
    # (для региона: иначе «Москва» пропустит всю городскую хронику)
    require_business_tags: bool = False


def _yes(v: bool | None) -> bool:
    return bool(v)


SIGNAL_MULTIPLIER = {"low": 0.7, "medium": 1.0, "high": 1.25}
MAX_COUNTERPARTY_ASPECTS = 2  # на роль; больше — контрагенты забьют выдачу


def _signal(p: "ClientProfile", name: str) -> str | None:
    value = (p.signals or {}).get(name)
    return value if value in SIGNAL_MULTIPLIER else None


def _mult(*levels: str | None) -> float:
    known = [SIGNAL_MULTIPLIER[x] for x in levels if x]
    return max(known) if known else 1.0


_COUNTRY_ABBR = {"ОАЭ", "США", "ЮАР", "КНДР", "КНР"}
# как ещё страну может назвать LLM при разметке новости (теги стран сравниваются точно)
_COUNTRY_ALIASES = {
    "Киргизия": ["Кыргызстан", "Киргизстан"],
    "Беларусь": ["Белоруссия"],
    "Молдова": ["Молдавия"],
    "Китай": ["КНР"],
    "Южная Корея": ["Республика Корея", "Корея"],
    "Северная Корея": ["КНДР"],
    "ОАЭ": ["Объединенные Арабские Эмираты", "Объединённые Арабские Эмираты"],
    "США": ["Соединенные Штаты", "Соединённые Штаты"],
    "Великобритания": ["Британия"],
    "Нидерланды": ["Голландия"],
}
_RUSSIA = {"россия", "российская федерация", "рф"}


def parse_countries(raw: str | None) -> list[str]:
    """Страны ВЭД из данных ФТС: «КИТАЙ, ЮЖНАЯ КОРЕЯ, ОАЭ» -> ["Китай", "Южная Корея", "ОАЭ"]."""
    out: list[str] = []
    for part in re.split(r"[,;/]", raw or ""):
        name = " ".join(part.split())
        if not name or name.lower() in _RUSSIA:
            continue
        words = []
        for w in name.split(" "):
            if w.upper() in _COUNTRY_ABBR:
                words.append(w.upper())
            elif w.lower() == "и":  # «Босния и Герцеговина»
                words.append("и")
            else:
                words.append("-".join(x[:1].upper() + x[1:].lower() for x in w.split("-")))
        out.append(" ".join(words))
    return list(dict.fromkeys(out))


def country_filter_values(countries: list[str]) -> list[str]:
    """Значения для фильтра по тегу страны: сами названия + их варианты."""
    return list(dict.fromkeys(v for c in countries for v in [c, *_COUNTRY_ALIASES.get(c, [])]))


def normalize_region(region: str) -> str:
    """«г. Москва» -> «Москва»: так регионы пишет LLM при разметке новостей."""
    r = region.strip()
    for prefix in ("г. ", "г.", "город "):
        if r.lower().startswith(prefix):
            r = r[len(prefix) :].strip()
    return r


def _revenue_text(revenue: float | None) -> str | None:
    if not revenue:
        return None
    if revenue >= 1e9:
        return f"выручка около {revenue / 1e9:.1f} млрд руб"
    return f"выручка около {revenue / 1e6:.0f} млн руб"


def profile_summary(p: ClientProfile) -> str:
    """Краткое описание клиента словами — для промпта агента."""
    parts = []
    if p.mainokved_name or p.mainokved_code:
        parts.append(f"Основной вид деятельности: {p.mainokved_name or ''} (ОКВЭД {p.mainokved_code or '—'}).")
    region = normalize_region(p.region) if p.region else None
    place = ", ".join(x for x in (p.city, region if region != p.city else None) if x)
    if place:
        parts.append(f"Регистрация: {place}.")
    scale = [x for x in (_revenue_text(p.revenue_company), p.workers_fns_gradation and f"сотрудников: {p.workers_fns_gradation}") if x]
    if scale:
        parts.append("Масштаб: " + ", ".join(scale) + ".")
    if p.company_age_years_gradation:
        parts.append(f"Возраст компании: {p.company_age_years_gradation}.")
    if p.eco_mark_label:
        parts.append(f"Стадия развития: {p.eco_mark_label}.")
    products = [
        name
        for flag, name in (
            (p.has_loa, "кредиты"),
            (p.has_lea, "лизинг"),
            (p.has_gar, "банковские гарантии"),
            (p.has_factoring, "факторинг"),
            (p.has_dep, "депозиты"),
            (p.has_zpp, "зарплатный проект"),
            (p.has_rko, "РКО"),
        )
        if _yes(flag)
    ]
    if products:
        parts.append("Продукты Альфа-Банка: " + ", ".join(products) + ".")
    if _yes(p.fts_flag):
        countries = parse_countries(p.fts_country_name)
        where = f" (страны: {', '.join(countries)})" if countries else ""
        parts.append(f"Ведёт внешнеэкономическую деятельность{where}.")
    if p.group_id:
        parts.append("Входит в группу компаний.")
    for cp in p.counterparties[:6]:
        role = {"supplier": "Крупный поставщик", "customer": "Крупный покупатель", "linked": "Связанная компания"}[cp.role]
        if cp.mainokved_name:
            parts.append(f"{role}: отрасль «{cp.mainokved_name}».")
    return " ".join(parts) or "Данных о компании нет."


def _counterparty_reason(cp: Counterparty) -> str:
    source = {
        "supplier": "payments: крупный поставщик",
        "customer": "payments: крупный покупатель",
        "linked": "person_company: связанная компания",
    }[cp.role]
    return f"{source} {cp.uid or ''}".strip()


def build_aspects(p: ClientProfile, taxonomy: Taxonomy) -> list[Aspect]:
    aspects: list[Aspect] = []
    own_industries = taxonomy.industries_for_okved(p.mainokved_code)

    # 1. Отрасль — главный аспект.
    if p.mainokved_code or p.mainokved_name:
        industry_name = p.mainokved_name or ", ".join(taxonomy.industries[i] for i in own_industries)
        aspects.append(
            Aspect(
                id="industry",
                title=f"Отрасль: {industry_name}",
                query=f"Новости отрасли «{industry_name}»: спрос, цены, регулирование, крупные компании и проекты.",
                weight=1.0,
                filters=AspectFilters(industries=own_industries, okved=[p.mainokved_code] if p.mainokved_code else []),
                reason="mainokved_code, mainokved_name",
            )
        )

    # 2. Заёмное финансирование.
    borrowed = [
        name
        for flag, name in ((p.has_loa, "кредиты"), (p.has_lea, "лизинг"), (p.has_gar, "гарантии"), (p.has_factoring, "факторинг"))
        if _yes(flag)
    ]
    credit = _signal(p, "credit_dependency")
    if borrowed or credit in ("medium", "high"):
        products = f" ({', '.join(borrowed)})" if borrowed else ""
        aspects.append(
            Aspect(
                id="financing",
                title="Стоимость заёмных денег",
                query=(
                    "Стоимость заёмного финансирования для бизнеса: ключевая ставка Банка России, "
                    f"ставки по кредитам и условия кредитования{products}."
                ),
                weight=round(0.9 * _mult(credit), 3),
                filters=AspectFilters(macro_factors=["key_rate", "credit_market"]),
                reason="has_loa, has_lea, has_gar, has_factoring" + (f"; signals.credit_dependency={credit}" if credit else ""),
            )
        )

    # 3. Свободная ликвидность.
    if _yes(p.has_dep):
        aspects.append(
            Aspect(
                id="liquidity",
                title="Доходность свободных денег",
                query="Доходность депозитов и размещения ликвидности компаний: ключевая ставка, доходность облигаций ОФЗ.",
                weight=0.6,
                filters=AspectFilters(macro_factors=["key_rate", "bond_market"]),
                reason="has_dep",
            )
        )

    # 4. Внешнеэкономическая деятельность.
    # ВЭД — только по данным ФТС (fts_flag). Сигналы fx_exposure / import_dependency
    # лишь меняют вес: в data_loader они считаются эвристикой по первому слову названия
    # ОКВЭД («Деятельность…») и ложно ставят импорт почти всем клиентам.
    fx, imports = _signal(p, "fx_exposure"), _signal(p, "import_dependency")
    if _yes(p.fts_flag):
        countries = parse_countries(p.fts_country_name)
        shown = ", ".join(countries[:5]) + (" и др." if len(countries) > 5 else "")
        aspects.append(
            Aspect(
                id="foreign_trade",
                title=f"ВЭД ({shown})" if countries else "ВЭД",
                query=(
                    f"Внешнеэкономическая деятельность{f' (страны: {shown})' if countries else ''}: курс рубля, "
                    "таможенные пошлины, санкции, логистика импорта и экспорта, расчёты с иностранными партнёрами."
                ),
                weight=round(0.9 * _mult(fx, imports), 3),
                filters=AspectFilters(
                    macro_factors=["fx_rub", "customs_tariffs", "sanctions", "foreign_trade", "logistics"],
                    countries=country_filter_values(countries),
                ),
                reason="fts_flag, fts_country_name"
                + "".join(f"; signals.{k}={v}" for k, v in (("fx_exposure", fx), ("import_dependency", imports)) if v),
            )
        )

    # 5. Персонал и налоги на ФОТ.
    if _yes(p.has_zpp):
        aspects.append(
            Aspect(
                id="workforce",
                title="Персонал и зарплаты",
                query="Рынок труда: дефицит кадров, рост зарплат, НДФЛ и страховые взносы работодателей.",
                weight=0.5,
                filters=AspectFilters(macro_factors=["labor_market", "taxes"]),
                reason="has_zpp, workers_*_gradation",
            )
        )

    # 6. Регион.
    if p.region:
        region = normalize_region(p.region)
        aspects.append(
            Aspect(
                id="region",
                title=f"Регион: {region}",
                query=f"Экономика и бизнес региона {region}: решения властей, инфраструктура, крупные проекты.",
                weight=0.5,
                filters=AspectFilters(regions=sorted({region, p.region.strip()})),
                reason="region, city",
                require_business_tags=True,
            )
        )

    # 7. Отрасли ключевых контрагентов (кроме собственной) — риски цепочки.
    #    До двух отраслей на роль: у перевозчика важны и топливо, и производители техники.
    seen = set(own_industries)
    by_role: dict[str, list[Counterparty]] = {"supplier": [], "customer": [], "linked": []}
    for cp in sorted(p.counterparties, key=lambda c: -(c.total_amt or 0)):
        by_role[cp.role].append(cp)
    roles = (
        ("supplier", "Поставщики", "поставщиков", 0.6),
        ("customer", "Покупатели", "покупателей", 0.6),
        ("linked", "Связанные компании", "связанных компаний (общие владельцы и руководители)", 0.5),
    )
    for role, title, word, weight in roles:
        taken = 0
        for cp in by_role[role]:
            if taken == MAX_COUNTERPARTY_ASPECTS:
                break
            cp_industries = [i for i in taxonomy.industries_for_okved(cp.mainokved_code) if i not in seen]
            if not cp_industries or not (cp.mainokved_name or cp.mainokved_code):
                continue
            seen.update(cp_industries)
            name = cp.mainokved_name or taxonomy.industries[cp_industries[0]]
            aspects.append(
                Aspect(
                    id=f"{role}_{cp_industries[0]}",
                    title=f"{title}: {name}",
                    query=f"Отрасль ключевых {word} «{name}»: проблемы, цены, перебои и спрос в этой отрасли.",
                    weight=weight,
                    filters=AspectFilters(industries=cp_industries, okved=[cp.mainokved_code] if cp.mainokved_code else []),
                    reason=_counterparty_reason(cp),
                )
            )
            taken += 1

    # 8. Общий макрофон — нужен любому крупному бизнесу, но с низким весом.
    aspects.append(
        Aspect(
            id="macro",
            title="Макроэкономика",
            query="Макроэкономика России: инфляция, рост ВВП, курс рубля, налоговые изменения для бизнеса.",
            weight=0.4,
            filters=AspectFilters(macro_factors=["inflation", "gdp_growth", "taxes", "budget_policy"]),
            reason="базовый аспект для любого клиента",
        )
    )
    return aspects
