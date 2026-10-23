"""
Простой прогон interpreter на тестовых кейсах.
Запуск из корня проекта: python tests/test_interpreter.py

- входные данные — tests/inputs.json
- офлайн-тесты работают без сети
- онлайн-тесты пропускаются ([SKIP]), если хост недоступен
- печатает полный output.json по каждому онлайн-кейсу
- результаты пишутся в консоль и логируются
"""
import copy
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")

from interpreter import (
    ALLOWED_MODELS,
    DEFAULT_MODEL,
    fallback_output,
    interpret,
    new_interpretation_id,
    strip_json_fence,
)


_DIR = Path(__file__).parent
FIXTURES = _DIR / "inputs.json"
INPUTS = json.loads(FIXTURES.read_text(encoding="utf-8"))

INPUT_RATES = INPUTS["rates"]
INPUT_SANCTIONS = INPUTS["sanctions"]
INPUT_REGION = INPUTS["region"]
INPUT_CURRENCY = INPUTS["currency"]
INPUT_MINIMAL = INPUTS["minimal"]
INPUT_BAD = INPUTS["bad"]

CASES_ONLINE = {
    "rates": INPUT_RATES,
    "sanctions": INPUT_SANCTIONS,
    "region": INPUT_REGION,
    "currency": INPUT_CURRENCY,
}


LOG_PATH = _DIR / "test_results.log"
_log_lines = []


def log(line: str) -> None:
    print(line)
    _log_lines.append(line)


def dump_results() -> None:
    total = len(_results)
    passed = sum(1 for _, s, _, _ in _results if s == PASS)
    failed = sum(1 for _, s, _, _ in _results if s == FAIL)
    skipped = sum(1 for _, s, _, _ in _results if s == SKIP)
    total_time = sum(t for _, _, _, t in _results)

    log("РЕЗУЛЬТАТ")
    log(f"всего: {total}  прошло: {passed}  упало: {failed}  пропущено: {skipped}  время: {total_time:.2f}s")
    log(f"лог: {LOG_PATH.name}")

    if failed:
        for name, status, err, elapsed in _results:
            if status == FAIL:
                log(f"  - {name} ({elapsed:.2f}s): {err}")

    LOG_PATH.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")

    if failed:
        raise SystemExit(1)


PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
_results = []


def check(name: str, fn):
    t0 = time.perf_counter()
    try:
        fn()
        elapsed = time.perf_counter() - t0
        _results.append((name, PASS, "", elapsed))
        log(f"[{PASS}] {name}  ({elapsed:.2f}s)")
    except Exception as e:
        elapsed = time.perf_counter() - t0
        _results.append((name, FAIL, str(e), elapsed))
        log(f"[{FAIL}] {name}  ({elapsed:.2f}s): {e}")


def skip(name: str, reason: str, elapsed: float = 0.0):
    _results.append((name, SKIP, reason, elapsed))
    log(f"[{SKIP}] {name}  ({elapsed:.2f}s): {reason}")


def print_output(out: dict) -> None:
    log("    output.json:")
    for line in json.dumps(out, ensure_ascii=False, indent=4).splitlines():
        log("      " + line)


def validate_shape(out: dict, inp: dict) -> None:
    for k in ("interpretation_id", "client_id", "event", "what_happened",
              "why_it_matters", "risks", "opportunities", "recommended_actions",
              "attribution", "sources", "confidence"):
        assert k in out, f"missing output key: {k}"

    assert isinstance(out["interpretation_id"], int), \
        f"interpretation_id must be int, got {type(out['interpretation_id']).__name__}"
    assert out["interpretation_id"] > 0

    assert out["client_id"] == inp["client"]["client_id"]
    assert out["event"]["news_id"] == inp["news"]["news_id"]
    assert out["event"]["title"] == inp["news"]["title"]
    assert out["event"]["published_at"] == inp["news"]["published_at"]

    assert isinstance(out["risks"], list) and len(out["risks"]) <= 3
    assert isinstance(out["opportunities"], list) and len(out["opportunities"]) <= 3
    assert isinstance(out["recommended_actions"], list) and len(out["recommended_actions"]) <= 3

    bv = out["attribution"]["bank_view"]
    assert {"text", "chunk_id", "doc_title", "page"} <= bv.keys()

    allowed_news = {inp["news"]["news_id"]}
    allowed_chunks = {c["chunk_id"] for c in inp.get("analytics", [])}
    allowed_signals = set(inp["client"]["signals"].keys())

    for s in out["sources"]:
        if s["type"] == "news":
            assert s["id"] in allowed_news, f"unknown news_id: {s['id']}"
        elif s["type"] == "analytics":
            assert s["chunk_id"] in allowed_chunks, f"unknown chunk_id: {s['chunk_id']}"
        elif s["type"] == "client_signal":
            assert s["id"] in allowed_signals, f"unknown signal: {s['id']}"
        else:
            raise AssertionError(f"unknown source type: {s['type']}")

    assert 0.0 <= out["confidence"] <= 1.0


def llm_http_ok(timeout: float = 8.0) -> bool:
    key = os.getenv("LLM_API_KEY")
    if not key:
        return False
    try:
        req = urllib.request.Request(
            "https://changellenge.up.railway.app/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception as e:
        log(f"    [SKIP] /v1/models недоступен: {type(e).__name__}: {e}")
        return False


def is_network_error(msg: str) -> bool:
    m = msg.lower()
    return any(s in m for s in (
        "timed out", "timeout", "connection", "reset", "unreachable",
        "504", "502", "503", "gateway", "bad gateway",
        "service unavailable", "upstream",
    ))


log("\nОФЛАЙН")


def t_bad_input():
    try:
        interpret(INPUT_BAD, api_key="sk-test")
        raise AssertionError("ожидался ValueError")
    except ValueError as e:
        assert "в client отсутствует ключ" in str(e), e


def t_non_int_news_id():
    bad = copy.deepcopy(INPUT_RATES)
    bad["news"]["news_id"] = "1001"
    try:
        interpret(bad, api_key="sk-test")
        raise AssertionError("ожидался ValueError")
    except ValueError as e:
        assert "news.news_id должен быть int" in str(e), e


def t_disallowed_model():
    try:
        interpret(INPUT_RATES, api_key="sk-test", model="gpt-4")
        raise AssertionError("ожидался ValueError")
    except ValueError as e:
        assert "не входит в разрешённый список" in str(e), e


def t_missing_api_key():
    old = os.environ.pop("LLM_API_KEY", None)
    try:
        interpret(INPUT_RATES)
        raise AssertionError("ожидался ValueError")
    except ValueError as e:
        assert "LLM_API_KEY" in str(e), e
    finally:
        if old is not None:
            os.environ["LLM_API_KEY"] = old


def t_fallback_structure():
    iid = new_interpretation_id()
    assert isinstance(iid, int) and iid > 0

    out = fallback_output(INPUT_MINIMAL, iid, "test")
    assert out["interpretation_id"] == iid
    assert isinstance(out["interpretation_id"], int)
    assert out["confidence"] == 0.0
    assert out["sources"] == [{"type": "news", "id": INPUT_MINIMAL["news"]["news_id"]}]
    assert "Fallback" in out["attribution"]["model_inference"]


def t_fallback_shape():
    out = fallback_output(INPUT_RATES, new_interpretation_id(), "test")
    validate_shape(out, INPUT_RATES)


def t_id_unique():
    ids = {new_interpretation_id() for _ in range(1000)}
    assert len(ids) == 1000, "collisions in 1000 generated ids"
    assert all(isinstance(i, int) and i > 0 for i in ids)

def t_strip_fence():
    assert strip_json_fence('{"a":1}') == '{"a":1}'
    assert strip_json_fence('```json\n{"a":1}\n```') == '{"a":1}'
    assert strip_json_fence('```\n{"a":1}\n```') == '{"a":1}'


def t_allowed_models():
    assert len(ALLOWED_MODELS) == 6
    assert DEFAULT_MODEL in ALLOWED_MODELS


check("невалидный вход -> ValueError", t_bad_input)
check("news_id не int -> ValueError", t_non_int_news_id)
check("запрещённая модель -> ValueError", t_disallowed_model)
check("нет API-ключа -> ValueError", t_missing_api_key)
check("fallback структура", t_fallback_structure)
check("fallback проходит shape-проверку", t_fallback_shape)
check("id уникальны", t_id_unique)
check("strip_json_fence", t_strip_fence)
check("allow-list моделей", t_allowed_models)


log("\nОНЛАЙН")

if not os.getenv("LLM_API_KEY"):
    skip("онлайн-блок", "LLM_API_KEY не задан")
else:
    for name, inp in CASES_ONLINE.items():
        t0 = time.perf_counter()
        if not llm_http_ok():
            skip(f"interpret [{name}]", "хост недоступен (VPN?)", time.perf_counter() - t0)
            continue

        def run(name=name, inp=inp):
            out = interpret(inp, timeout=90)
            validate_shape(out, inp)
            print_output(out)

        try:
            run()
            elapsed = time.perf_counter() - t0
            _results.append((f"interpret [{name}]", PASS, "", elapsed))
            log(f"[{PASS}] interpret [{name}]  ({elapsed:.2f}s)")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            if is_network_error(str(e)):
                skip(f"interpret [{name}]", f"{type(e).__name__}: {e}", elapsed)
            else:
                _results.append((f"interpret [{name}]", FAIL, str(e), elapsed))
                log(f"[{FAIL}] interpret [{name}]  ({elapsed:.2f}s): {e}")

        time.sleep(3)


    def _run_extra(name: str, fn):
        t0 = time.perf_counter()
        if not llm_http_ok():
            skip(name, "хост недоступен", time.perf_counter() - t0)
            return
        try:
            fn()
            elapsed = time.perf_counter() - t0
            _results.append((name, PASS, "", elapsed))
            log(f"[{PASS}] {name}  ({elapsed:.2f}s)")
        except Exception as e:
            elapsed = time.perf_counter() - t0
            if is_network_error(str(e)):
                skip(name, f"{type(e).__name__}: {e}", elapsed)
            else:
                _results.append((name, FAIL, str(e), elapsed))
                log(f"[{FAIL}] {name}  ({elapsed:.2f}s): {e}")


    def t_rates_bank_view():
        out = interpret(INPUT_RATES, timeout=90)
        bv = out["attribution"]["bank_view"]
        chunk = INPUT_RATES["analytics"][0]
        assert bv["chunk_id"] == chunk["chunk_id"]
        assert bv["doc_title"] == chunk["doc_title"]
        assert bv["page"] == chunk["page"]


    def t_region_people_regions():
        out = interpret(INPUT_REGION, timeout=90)
        assert "Казан" in out["why_it_matters"] or "kazan" in out["why_it_matters"].lower()


    def t_currency_fx_signal():
        out = interpret(INPUT_CURRENCY, timeout=90)
        sig_ids = {s["id"] for s in out["sources"] if s["type"] == "client_signal"}
        assert sig_ids & {"fx_exposure", "import_dependency"}, sig_ids


    def t_model_override():
        out = interpret(INPUT_RATES, timeout=90, model="deepseek/deepseek-v4.1-flash")
        validate_shape(out, INPUT_RATES)


    _run_extra("bank_view ссылается на реальный чанк", t_rates_bank_view)
    _run_extra("region: why_it_matters упоминает Казань", t_region_people_regions)
    _run_extra("currency: sources содержит fx/import сигнал", t_currency_fx_signal)
    _run_extra("смена модели через параметр", t_model_override)


dump_results()