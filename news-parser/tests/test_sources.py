from news_parser.parser.analytics_loader import chunk_pages
from news_parser.parser.collectors.base import load_collectors
from news_parser.parser.collectors.cbr import parse_rates
from news_parser.core.settings import get_settings

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


def test_text_version_keeps_pages_and_replaces_scanned_pdf(tmp_path):
    from news_parser.parser.analytics_loader import read_pages

    txt = tmp_path / "doc.txt"
    txt.write_text("Ключевая ставка ЦБ РФ\n\nСтраница один.\fСтраница два.", encoding="utf-8")
    pages = read_pages(txt)
    assert len(pages) == 2 and pages[0].startswith("Ключевая ставка")
    chunks = chunk_pages(pages, max_chars=400)
    assert chunks[-1].page_to == 2
