from news_parser.processing.prefilter import prefilter, top_ids
from news_parser.taxonomy import get_taxonomy

tax = get_taxonomy()
BODY = (
    "Совет директоров Банка России сохранил ключевую ставку на уровне 14% годовых. "
    "Регулятор ужесточил риторику: инфляция остаётся выше цели, кредитование растёт, "
    "застройщики и девелоперы жалуются на дорогую ипотеку. " * 2
)


def test_key_rate_news_is_tagged():
    r = prefilter(tax, title="ЦБ сохранил ключевую ставку", text=BODY, url=None, min_chars=100, require_signal=True)
    assert r.keep
    assert "key_rate" in r.factors and "inflation" in r.factors
    assert "construction" in r.industries
    assert top_ids(r.factors)[0] == "key_rate"


def test_sport_is_filtered():
    text = "Футбольный клуб выиграл матч чемпионата со счётом 2:1, болельщики праздновали победу. " * 4
    r = prefilter(tax, title="Хоккей: матч чемпионата", text=text, url=None, min_chars=100, require_signal=True)
    assert not r.keep


def test_short_text_is_filtered():
    r = prefilter(tax, title="Ставка", text="коротко", url=None, min_chars=100, require_signal=True)
    assert not r.keep and r.reason.startswith("too_short")


def test_stop_url():
    r = prefilter(tax, title="x", text=BODY, url="https://site.ru/sport/123", min_chars=100, require_signal=True)
    assert r.reason == "stop_url"


def test_short_stems_do_not_overmatch():
    # «газета» не должна давать фактор «газ», «стало» — «металлы»
    hits = tax.match_factors("В газете написали, что стало известно о новых планах.")
    assert "gas" not in hits and "metals" not in hits
    assert "gas" in tax.match_factors("Экспорт газа в Китай вырос")


def test_llm_ids_are_cleaned_and_okved_mapped():
    assert tax.clean_factors(["key_rate", "made_up", "key_rate"]) == ["key_rate"]
    assert tax.clean_event_type("nonsense") == "other"
    assert "41" in tax.okved_for(["construction"])
