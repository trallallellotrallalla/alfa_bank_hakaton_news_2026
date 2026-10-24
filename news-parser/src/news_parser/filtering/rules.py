"""Жёсткие правила: интерес клиента (аспект) -> какие теги обязана иметь новость.

Новость проходит по аспекту, если её теги совпали хотя бы с одним измерением аспекта
(макрофакторы / отрасли / ОКВЭД / регион / страна). Для региона нужна ещё и бизнес-метка
(иначе «Москва» пропустит всю городскую хронику). Совпадение с «Россия» не считается
совпадением с регионом клиента — общероссийские события приходят через другие аспекты.

Сами теги клиента строит filtering/profile.py, SQL-условия — storage/repository/filters.py.
"""

from datetime import datetime

from news_parser.filtering.profile import Aspect
from news_parser.storage.repository import EventFilters


def rule_filters(aspect: Aspect, *, since: datetime, include_structured: bool) -> EventFilters:
    f = aspect.filters
    return EventFilters(
        macro_factors=f.macro_factors or None,
        industries=f.industries or None,
        okved=f.okved or None,
        regions=f.regions or None,
        countries=f.countries or None,
        match="any",  # хватает совпадения по одному измерению аспекта
        include_federal=False,
        require_business_tags=aspect.require_business_tags,
        date_from=since,
        include_structured=include_structured,
    )


def no_rule_filters(*, since: datetime, include_structured: bool) -> EventFilters:
    """Для запасного поиска: только окно по времени, без тегов."""
    return EventFilters(date_from=since, include_structured=include_structured)
