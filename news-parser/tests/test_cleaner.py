from news_parser.parser.cleaner import content_hash, normalize_text, strip_html


def test_normalize_collapses_whitespace():
    assert normalize_text("  a  b \n\n\n\n c  ") == "a b\n\nc"


def test_strip_html_from_rss_summary():
    raw = "<!-- x --><p>Банк&nbsp;России &laquo;сохранил&raquo; ставку</p><p>14%</p>"
    assert strip_html(raw) == "Банк России «сохранил» ставку\n\n14%"


def test_hash_ignores_case_punctuation_and_spaces():
    a = content_hash("ЦБ сохранил ставку", "Ставка — 14%.")
    b = content_hash("цб  сохранил ставку!", "ставка 14 %")
    assert a == b
    assert a != content_hash("ЦБ снизил ставку", "Ставка — 13%.")
