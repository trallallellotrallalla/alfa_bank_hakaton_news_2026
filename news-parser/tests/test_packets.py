from datetime import UTC, datetime

from news_parser.output.packets import _fallback_profile, _news_text, analytics_chunk_id, doc_slug
from news_parser.filtering.profile import build_aspects
from news_parser.schemas.client import ClientProfile, Counterparty
from news_parser.output.stance import classify_stance
from news_parser.schemas.match import AnalyticsItem, NewsChunk, NewsItem
from news_parser.core.taxonomy import get_taxonomy

tax = get_taxonomy()

# блок client ровно в том виде, как его отдаёт data_loader.get_client_info
CLIENT = {
    "client_id": "U_176",
    "industry": "Деятельность автомобильного грузового транспорта",
    "revenue_rub": 18_500_000_000,
    "region": "Москва",
    "products": {"rko": True, "loa": True, "lea": False, "dep": True, "gar": True, "zpp": True, "factoring": False},
    "signals": {"credit_dependency": "high", "fx_exposure": "medium", "import_dependency": "high"},
    "top_counterparties": ["U_201", "U_305"],
    "linked_companies": ["U_201", "U_412"],
    "people_regions": [{"region": "Москва", "share": 0.62}],
}


def test_stance_examples():
    # пример из контракта команды
    assert classify_stance(
        "Регулятор сигнализирует о более длительном периоде высоких ставок. Рынок ожидал паузы, "
        "но риторика оказалась жёстче прогнозов. Мы не ждём быстрого снижения ставки."
    ) == "hawkish"
    assert classify_stance("Период быстрого удешевления кредитов временно приостановлен.") == "hawkish"
    assert classify_stance("Ожидаем продолжения цикла снижения ставки и смягчения политики.") == "dovish"
    assert classify_stance("Ключевые риски: санкции, угроза рецессии и кризис ликвидности.") == "risk"
    assert classify_stance("Добыча золота в августе составила 30 тонн.") == "neutral"


def test_chunk_id_format():
    assert doc_slug("Ключевая ставка ЦБ РФ.pdf") == "klyuchevaya_stavka_cb_rf"
    a = AnalyticsItem(ref="A1", chunk_id=5, origin="alfa_bank", doc_title="t", file_name="Ключевая ставка ЦБ РФ.pdf",
                      chunk_index=1, page_from=2, page_to=2, text="x", similarity=0.5, related_news=[])
    assert analytics_chunk_id(a) == "klyuchevaya_stavka_cb_rf::p2::c1"


def test_signals_change_weights_but_do_not_create_foreign_trade():
    p = _fallback_profile(CLIENT)
    p.signals = CLIENT["signals"]
    aspects = {a.id: a for a in build_aspects(p, tax)}
    assert aspects["financing"].weight > 0.9  # credit_dependency=high усиливает
    # import_dependency=high у data_loader — эвристика по слову «Деятельность»: без fts_flag ВЭД не создаём
    assert "foreign_trade" not in aspects
    p.fts_flag = True
    assert {a.id: a for a in build_aspects(p, tax)}["foreign_trade"].weight > 0.9


def test_region_aspect_requires_business_tags():
    region = {a.id: a for a in build_aspects(_fallback_profile(CLIENT), tax)}["region"]
    assert region.require_business_tags and region.filters.regions


def test_counterparty_roles_become_aspects():
    p = ClientProfile(
        mainokved_code="49.41",
        counterparties=[
            Counterparty(uid="U_201", role="supplier", mainokved_code="19.20", mainokved_name="Нефтепродукты", total_amt=2.5e9),
            Counterparty(uid="U_305", role="supplier", mainokved_code="29.10", mainokved_name="Автомобили", total_amt=9e8),
            Counterparty(uid="U_412", role="linked", mainokved_code="68.10", mainokved_name="Недвижимость"),
        ],
    )
    ids = {a.id for a in build_aspects(p, tax)}
    assert {"supplier_oil_gas", "supplier_automotive", "linked_real_estate"} <= ids


def _news(chunks: list[str]) -> NewsItem:
    now = datetime.now(UTC)
    return NewsItem(
        ref="N1", event_id=1, title="t", summary="саммари", event_type="other", direction="neutral", horizon="short_term",
        first_seen_at=now, last_seen_at=now, macro_factors=[], industries=[], regions=[], countries=[], facts=[],
        extraction_method="rules", n_sources=1, similarity=0.5, passed_rules=True, matched_aspects=[],
        chunks=[NewsChunk(chunk_id=i, article_id=1, source_name="РБК", published_at=now, text=t, similarity=0.5, aspect_id="x")
                for i, t in enumerate(chunks)],
        sources=[], related_analytics=[],
    )


def test_news_text_short_article_whole_long_article_relevant_chunks():
    assert _news_text(_news(["c"]), "Короткая статья.", 3000) == "Короткая статья."
    long_main = "Предложение. " * 1000
    relevant = ["Первый важный фрагмент про ставку. " * 5, "Второй фрагмент про кредиты. " * 5]
    text = _news_text(_news(relevant), long_main, 3000)
    assert "ставку" in text and "кредиты" in text and len(text) <= 3005
