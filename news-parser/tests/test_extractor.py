import json

import pytest

from news_parser.processing.extractor import Extractor, parse_json_object
from news_parser.processing.llm_client import LlmResponse
from news_parser.taxonomy import get_taxonomy

GOOD = {
    "relevant": True,
    "summary": "ЦБ сохранил ставку 14%",
    "facts": [{"text": "Ставка 14%", "confirmed": True}, {"text": "Снижение возможно в декабре", "confirmed": False}],
    "numbers": [{"name": "ключевая ставка", "value": 14, "unit": "%"}],
    "entities": [{"name": "Банк России", "type": "regulator"}, {"name": "X", "type": "alien"}],
    "event_type": "regulator_decision",
    "macro_factors": ["key_rate", "unknown_factor"],
    "industries": ["construction"],
    "regions": ["Россия"],
    "countries": [],
    "direction": "negative",
    "horizon": "short_term",
}


class FakeLlm:
    model = "fake"
    configured = True

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    def chat(self, messages, *, purpose, article_id=None, max_tokens=1200):
        self.calls += 1
        return LlmResponse(content=self.answers.pop(0), call_id=self.calls, total_tokens=10)


def test_parse_json_with_fences():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Вот ответ: {"a": {"b": 2}} спасибо') == {"a": {"b": 2}}


def test_extract_cleans_unknown_ids():
    ex = Extractor(FakeLlm([json.dumps(GOOD)]), get_taxonomy(), 1000)
    r = ex.extract(title="t", text="x", source="s", article_id=1).extraction
    assert r.macro_factors == ["key_rate"]
    assert r.entities[1].type == "other"
    assert [f.confirmed for f in r.facts] == [True, False]


def test_extract_retries_once_then_succeeds():
    llm = FakeLlm(["не json", json.dumps(GOOD)])
    result = Extractor(llm, get_taxonomy(), 1000).extract(title="t", text="x", source="s", article_id=1)
    assert llm.calls == 2 and result.call_ids == [1, 2]


def test_extract_gives_up_after_two_bad_answers():
    with pytest.raises(ValueError):
        Extractor(FakeLlm(["плохо", "{}"]), get_taxonomy(), 1000).extract(title="t", text="x", source="s", article_id=1)
