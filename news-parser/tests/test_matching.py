from datetime import UTC, datetime

from news_parser.output.context import render_context
from news_parser.filtering.profile import build_aspects, normalize_region, profile_summary
from news_parser.schemas.client import ClientProfile, Counterparty
from news_parser.parser.chunking import chunk_text
from news_parser.schemas.match import (
    AnalyticsItem,
    AspectMatch,
    AspectOut,
    NewsChunk,
    NewsItem,
    NewsSource,
    ProfileMatchResponse,
)
from news_parser.core.taxonomy import get_taxonomy

tax = get_taxonomy()

# строка таблицы companies (schema.sql) как есть, с лишней колонкой
ROW = {
    "uid": "U1",
    "mainokved_code": "41.20",
    "mainokved_name": "Строительство жилых и нежилых зданий",
    "has_loa": True,
    "has_dep": True,
    "has_zpp": False,
    "fts_flag": True,
    "fts_country_name": "Китай",
    "revenue_company": 23_400_000_000,
    "city": "Москва",
    "region": "г. Москва",
    "unknown_column": 1,
}


def test_profile_accepts_db_row_and_builds_aspects():
    p = ClientProfile.model_validate(ROW)
    p.counterparties = [
        Counterparty(role="supplier", mainokved_code="23.61", mainokved_name="Производство бетона", total_amt=5e8),
        Counterparty(role="supplier", mainokved_code="24.10", mainokved_name="Металлургия", total_amt=9e8),
    ]
    aspects = {a.id: a for a in build_aspects(p, tax)}
    assert {"industry", "financing", "liquidity", "foreign_trade", "region", "macro"} <= aspects.keys()
    assert "workforce" not in aspects  # нет зарплатного проекта
    assert aspects["industry"].filters.industries == ["construction"]
    assert aspects["foreign_trade"].filters.countries == ["Китай", "КНР"]
    assert "Москва" in aspects["region"].filters.regions
    # бетон — та же отрасль, что у клиента (construction), поэтому берётся металлург
    assert "supplier_metals_mining" in aspects


def test_profile_summary_is_readable():
    text = profile_summary(ClientProfile.model_validate(ROW))
    assert "23.4 млрд" in text and "кредиты" in text and "Китай" in text


def test_okved_and_region_mapping():
    assert tax.industries_for_okved("41.20") == ["construction"]
    assert tax.industries_for_okved(None) == []
    assert normalize_region("г. Москва") == "Москва"


def test_chunk_text_splits_long_and_keeps_short():
    long_text = "Банк России сохранил ставку. " * 80
    chunks = chunk_text(long_text, max_chars=300, max_chunks=5)
    assert len(chunks) == 5 and all(len(c) <= 330 for c in chunks)
    assert chunk_text("Только заголовок", 300) == ["Только заголовок"]


def _response(n_news: int) -> ProfileMatchResponse:
    now = datetime.now(UTC)
    news = [
        NewsItem(
            ref=f"N{i}", event_id=i, title=f"Новость {i}", summary="ЦБ сохранил ставку", event_type="regulator_decision",
            direction="negative", horizon="short_term", first_seen_at=now, last_seen_at=now,
            macro_factors=["key_rate"], industries=[], regions=[], countries=[],
            facts=[{"text": "Ставка 14%", "confirmed": True}, {"text": "Снижение в декабре", "confirmed": False}],
            extraction_method="llm", n_sources=2, similarity=0.8, passed_rules=True,
            matched_aspects=[AspectMatch(aspect_id="financing", aspect_title="Стоимость заёмных денег", similarity=0.7, matched_labels={"macro_factors": ["key_rate"]})],
            chunks=[NewsChunk(chunk_id=i, article_id=i, source_name="РБК", published_at=now, text="Текст фрагмента " * 20, similarity=0.7, aspect_id="financing")],
            sources=[NewsSource(article_id=i, source_name="РБК", url="https://x", published_at=now)],
            related_analytics=["A1"],
        )
        for i in range(1, n_news + 1)
    ]
    bank = [AnalyticsItem(ref="A1", chunk_id=1, origin="alfa_bank", doc_title="Ключевая ставка ЦБ РФ", file_name="kr.pdf", chunk_index=0,
                          page_from=2, page_to=3, text="Мы ожидаем паузу.", similarity=0.6, related_news=["N1"])]
    aspects = [AspectOut(id="financing", title="Стоимость заёмных денег", query="q", weight=0.9, filters={}, reason="has_loa")]
    return ProfileMatchResponse(profile_uid="U1", profile_summary="Строительная компания.", aspects=aspects,
                                news=news, bank_analytics=bank, context=None, meta={})


def test_context_separates_facts_and_bank_view():
    ctx = render_context(_response(2), tax, 12000)
    assert "[N1] Новость 1" in ctx and "[A1] «Ключевая ставка ЦБ РФ», стр. 2–3" in ctx
    assert "[подтверждено] Ставка 14%" in ctx and "[прогноз/мнение] Снижение в декабре" in ctx
    assert ctx.index("## Новости") < ctx.index("## Аналитика Альфа-Банка")
    assert "https://x" not in ctx  # URL агенту не нужен


def test_context_respects_budget():
    ctx = render_context(_response(30), tax, 3000)
    assert len(ctx) <= 3200
    assert "не поместилось" in ctx


def test_okved_subclass_refines_industry():
    # оптовик топливом — это прежде всего нефтегаз, а не «оптовая торговля вообще»
    assert tax.industries_for_okved("46.71") == ["oil_gas", "wholesale"]
    assert tax.industries_for_okved("46.71.1") == ["oil_gas", "wholesale"]
    assert tax.industries_for_okved("47.30") == ["oil_gas", "retail"]
    assert tax.industries_for_okved("46.31") == ["food", "wholesale"]  # «46.3» покрывает подклассы
    assert tax.industries_for_okved("46.90") == ["wholesale"]  # без уточнения — как раньше
    assert tax.industries_for_okved("41.20") == ["construction"]


def test_fuel_wholesaler_profile():
    p = ClientProfile(mainokved_code="46.71", mainokved_name="Торговля оптовая топливом",
                      fts_flag=True, fts_country_name="КИРГИЗИЯ, КАЗАХСТАН")
    aspects = {a.id: a for a in build_aspects(p, tax)}
    assert "oil_gas" in aspects["industry"].filters.industries
    assert aspects["foreign_trade"].filters.countries == ["Киргизия", "Кыргызстан", "Киргизстан", "Казахстан"]
    assert aspects["foreign_trade"].title == "ВЭД (Киргизия, Казахстан)"
    assert "страны: Киргизия, Казахстан" in profile_summary(p)


def test_parse_countries():
    from news_parser.filtering.profile import parse_countries

    assert parse_countries("ОАЭ, ИНДИЯ, КИТАЙ") == ["ОАЭ", "Индия", "Китай"]
    assert parse_countries("КИТАЙ, ЮЖНАЯ КОРЕЯ") == ["Китай", "Южная Корея"]
    assert parse_countries("БОСНИЯ И ГЕРЦЕГОВИНА; РОССИЯ") == ["Босния и Герцеговина"]
    assert parse_countries(None) == []
