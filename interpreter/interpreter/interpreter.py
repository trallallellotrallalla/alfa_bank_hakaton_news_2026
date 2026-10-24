import json
import os
import re
import random
from pathlib import Path

import jsonschema
from dotenv import load_dotenv
from openai import OpenAI

_DIR = Path(__file__).resolve().parent
# Загружаем единый .env из корня репозитория (или папки модуля / рабочей директории)
load_dotenv(_DIR.parent.parent / ".env")
load_dotenv(_DIR.parent / ".env")
load_dotenv()

ALLOWED_MODELS = frozenset({
    "google/gemma-4-26b-a4b-it",
    "z-ai/glm-5.3-flash",
    "qwen/qwen3.6-35b-a3b",
    "deepseek/deepseek-v4.1-flash",
    "qwen/qwen3-vl-30b-a3b-instruct",
    "moonshotai/kimi-k2.6",
})

DEFAULT_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.6-35b-a3b")
DEFAULT_BASE_URL = (
    os.getenv("LLM_BASE_URL")
    or os.getenv("LLM_API_URL")
    or "https://api.alfahack-gateway26.ru/v1"
)

SYSTEM_PROMPT = (_DIR / "prompt.md").read_text(encoding="utf-8")
LLM_SCHEMA = json.loads((_DIR / "schema.json").read_text(encoding="utf-8"))

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

def new_interpretation_id() -> int:
    """Уникальный int-id интерпретации. 15 цифр — практически без коллизий."""
    return random.randint(10**14, 10**15 - 1)

def strip_json_fence(text: str) -> str:
    text = _THINK.sub("", text or "")
    head, sep, _ = text.partition("<think>")
    text = (head if sep else text).strip()
    m = _FENCE.match(text)
    return m.group(1) if m else text


def _resolve_api_key(api_key: str | None) -> str:
    key = api_key or os.getenv("LLM_API_KEY")
    if not key:
        raise ValueError(
            "LLM_API_KEY не задан. Положите его в .env или передайте api_key= в interpret()."
        )
    return key


def _validate_input(inp: dict) -> None:
    if not isinstance(inp, dict):
        raise ValueError("вход должен быть объектом (dict)")
    for k in ("client", "news"):
        if k not in inp:
            raise ValueError(f"во входе отсутствует ключ: {k}")
    for k in ("client_id", "industry", "products", "signals"):
        if k not in inp["client"]:
            raise ValueError(f"в client отсутствует ключ: {k}")
    for k in ("news_id", "title", "published_at", "text"):
        if k not in inp["news"]:
            raise ValueError(f"в news отсутствует ключ: {k}")
    if not isinstance(inp["news"]["news_id"], int):
        raise ValueError("news.news_id должен быть int")

def _validate_llm_output(raw: dict, inp: dict) -> None:
    try:
        jsonschema.validate(instance=raw, schema=LLM_SCHEMA)
    except jsonschema.ValidationError as e:
        raise ValueError(f"ответ LLM не прошёл валидацию по схеме: {e.message}") from e

    allowed_chunks = {c["chunk_id"] for c in inp.get("analytics", [])}
    if raw["used_chunk_id"] not in allowed_chunks:
        raise ValueError(
            f"used_chunk_id отсутствует в analytics: {raw['used_chunk_id']}"
        )

    allowed_signals = set(inp["client"]["signals"].keys())
    for s in raw["used_signals"]:
        if s not in allowed_signals:
            raise ValueError(f"неизвестный сигнал в used_signals: {s}")

def assemble_output(raw: dict, inp: dict, interpretation_id: int) -> dict:
    news = inp["news"]
    chunks = {c["chunk_id"]: c for c in inp.get("analytics", [])}
    chunk = chunks[raw["used_chunk_id"]]

    sources = [{"type": "news", "id": news["news_id"]}]
    sources.append({"type": "analytics", "chunk_id": chunk["chunk_id"]})
    for sig in raw["used_signals"]:
        sources.append({"type": "client_signal", "id": sig})

    return {
        "interpretation_id": interpretation_id,
        "client_id": inp["client"]["client_id"],
        "event": {
            "news_id": news["news_id"],
            "title": news["title"],
            "published_at": news["published_at"],
        },
        "what_happened": raw["what_happened"],
        "why_it_matters": raw["why_it_matters"],
        "risks": raw["risks"],
        "opportunities": raw["opportunities"],
        "recommended_actions": raw["recommended_actions"],
        "attribution": {
            "bank_view": {
                "text": raw["bank_view_text"],
                "chunk_id": chunk["chunk_id"],
                "doc_title": chunk["doc_title"],
                "page": chunk.get("page") if chunk.get("page") is not None else 1,
            },
            "model_inference": raw["model_inference"],
        },
        "sources": sources,
        "confidence": raw["confidence"],
    }


def fallback_output(input_json: dict, interpretation_id: int, reason: str) -> dict:
    news = input_json["news"]
    a = (input_json.get("analytics") or [{}])[0]
    return {
        "interpretation_id": interpretation_id,
        "client_id": input_json["client"]["client_id"],
        "event": {
            "news_id": news["news_id"],
            "title": news["title"],
            "published_at": news["published_at"],
        },
        "what_happened": news["text"].split(".")[0].strip() + ".",
        "why_it_matters": "Недостаточно данных для персонализированной интерпретации.",
        "risks": [],
        "opportunities": [],
        "recommended_actions": [],
        "attribution": {
            "bank_view": {
                "text": "Позиция банка не сформирована.",
                "chunk_id": a.get("chunk_id", "none"),
                "doc_title": a.get("doc_title", "none"),
                "page": a.get("page") if a.get("page") is not None else 1,
            },
            "model_inference": f"Fallback: {reason}",
        },
        "sources": [{"type": "news", "id": news["news_id"]}],
        "confidence": 0.0,
    }


def interpret(
    input_json: dict,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.0,
    max_retries: int = 1,
    timeout: float = 60.0,
) -> dict:
    """
    Генерирует интерпретацию. LLM возвращает только новую информацию,
    метаданные (id, заголовки, chunk_id, doc_title, page, sources)
    подставляет код.
    """
    key = _resolve_api_key(api_key)
    model = model or os.getenv("LLM_MODEL") or DEFAULT_MODEL
    base_url = (
        base_url
        or os.getenv("LLM_BASE_URL")
        or os.getenv("LLM_API_URL")
        or DEFAULT_BASE_URL
    )

    if model not in ALLOWED_MODELS:
        raise ValueError(f"model '{model}' не входит в разрешённый список")

    _validate_input(input_json)
    interpretation_id = input_json.get("_interpretation_id") or new_interpretation_id()

    if not input_json.get("analytics"):
        return fallback_output(input_json, interpretation_id, "analytics is empty")

    payload = {
        "client": input_json["client"],
        "news": input_json["news"],
        "analytics": input_json["analytics"],
        "_interpretation_id": interpretation_id,
    }
    client = OpenAI(api_key=key, base_url=base_url, timeout=timeout, max_retries=2)
    reasoning_effort = os.getenv("LLM_REASONING_EFFORT", "none").strip()
    extra_body = {"reasoning_effort": reasoning_effort} if reasoning_effort else None

    last_error = None
    for attempt in range(max_retries + 1):
        user = dict(payload)
        if attempt > 0 and last_error:
            user["_previous_error"] = last_error

        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            extra_body=extra_body,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
        )
        raw_text = strip_json_fence(resp.choices[0].message.content)

        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as e:
            last_error = f"invalid JSON: {e}"
            continue

        try:
            _validate_llm_output(raw, payload)
        except Exception as e:
            last_error = str(e)
            continue

        return assemble_output(raw, payload, interpretation_id)

    print(f"[FALLBACK] {last_error}")
    return fallback_output(input_json, interpretation_id, last_error or "unknown error")