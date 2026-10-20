from news_parser.analytics.alfa_loader import chunk_pages
from news_parser.collectors.base import load_collectors
from news_parser.collectors.cbr import parse_rates
from news_parser.settings import get_settings

CBR_XML = """<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="21.10.2026" name="Foreign Currency Market">
<Valute ID="R01235"><NumCode>840</NumCode><CharCode>USD</CharCode><Nominal>1</Nominal><Name>Доллар США</Name><Value>81,5000</Value></Valute>
<Valute ID="R01375"><NumCode>156</NumCode><CharCode>CNY</CharCode><Nominal>10</Nominal><Name>Юань</Name><Value>114,2000</Value></Valute>
</ValCurs>""".encode("cp1251")


def test_parse_cbr_rates_with_nominal():
    date, rates = parse_rates(CBR_XML)
    assert date.day == 21
    assert rates["USD"] == 81.5
    assert abs(rates["CNY"] - 11.42) < 1e-9


def test_sources_config_loads():
    ids = {c.id for c in load_collectors(get_settings().sources_config)}
    assert {"rbc", "cbr_fx", "moex_indices"} <= ids


def test_chunker_respects_size_and_pages():
    page1 = "Инфляция замедлилась до 6%. " * 30
    page2 = "Ставка останется высокой до конца года. " * 30
    chunks = chunk_pages([page1, page2], max_chars=400)
    assert len(chunks) > 3
    assert all(len(c.text) <= 450 for c in chunks)
    assert chunks[0].page_from == 1 and chunks[-1].page_to == 2
