# interpreter

Центральная LLM-часть проекта. Принимает исчерпывающую информацию для анализа (клиент + новость + аналитика банка) и возвращает персонализированную интерпретацию события для конкретного клиента.

Модуль отвечает только за вызов LLM и валидацию её ответа. Всё остальное
(отбор новостей, отбор чанков аналитики, ранжирование, UI) — вне модуля.

---

## Что делает

1. Принимает `input_json` с тремя блоками: `client`, `news`, `analytics`.
2. Формирует запрос к разрешённой LLM через OpenAI-compatible API.
3. Проверяет ответ по `schema.json`.
4. Проверяет, что `used_chunk_id` и `used_signals` ссылаются только на вход.
5. Подставляет метаданные (`interpretation_id`, `client_id`, `event`,
   `attribution.bank_view.chunk_id/doc_title/page`, `sources`) напрямую из input_json. 
6. При ошибке — один ретрай, затем fallback с `confidence: 0.0`.

LLM генерирует следующие поля:

- `what_happened`
- `why_it_matters`
- `risks`, `opportunities`, `recommended_actions`
- `bank_view_text`
- `model_inference`
- `used_chunk_id`, `used_signals`, `confidence`

Всё остальное — сборка на бэкенде. Это уменьшает токены, убирает ошибки
копирования (`doc_title`/`page` не могут разойтись с `analytics[]`) и
упрощает валидацию.

---

## Структура

```
interpreter/
├── __init__.py        # определяет публичный API
├── interpreter.py     # вызов LLM, валидация, сборка выхода
├── prompt.md          # системный промпт для LLM
├── schema.json        # jsonschema ответа LLM
└── README.md
```

---

## Установка

```bash
pip install openai>=1.40.0 jsonschema>=4.22.0 python-dotenv>=1.0.0
```

Или из `requirements.txt`:

```
openai>=1.40.0
jsonschema>=4.22.0
python-dotenv>=1.0.0
```

---

## Настройка

В корне проекта — `.env`:

```bash
LLM_API_KEY=sk-...
# опционально
LLM_MODEL=qwen/qwen3.6-35b-a3b
LLM_BASE_URL=https://changellenge.up.railway.app/v1
```

`.env.example` (коммитится):

```bash
LLM_API_KEY=sk-your-key-here
LLM_MODEL=qwen/qwen3.6-35b-a3b
LLM_BASE_URL=https://changellenge.up.railway.app/v1
```

`.gitignore`:

```
.env
.env.*
!.env.example
__pycache__/
*.pyc
```

---

## Использование

```python
from interpreter import interpret

output = interpret(input_json)                 # ключ и модель из .env
output = interpret(input_json, model="deepseek/deepseek-v4.1-flash")
output = interpret(input_json, api_key="sk-...", timeout=90)
```

`input_json`:

```json
{
  "client": {
    "client_id": "U_176",
    "industry": "Деятельность автомобильного грузового транспорта",
    "revenue_rub": 18500000000,
    "region": "Москва",
    "products": {"rko": true, "loa": true, "lea": false, "dep": true,
                 "gar": true, "zpp": true, "factoring": false},
    "signals": {"credit_dependency": "high", "fx_exposure": "medium",
                "import_dependency": "high"},
    "top_counterparties": ["U_201", "U_305"],
    "linked_companies": ["U_201", "U_412"],
    "people_regions": [
      {"region": "Москва", "share": 0.62},
      {"region": "Санкт-Петербург", "share": 0.23}
    ]
  },
  "news": {
    "news_id": 1001,
    "url": "https://example.com/news/1001",
    "title": "ЦБ сохранил ключевую ставку на 14%",
    "published_at": "2026-09-11",
    "source": "Интерфакс",
    "text": "Совет директоров Банка России принял решение сохранить ключевую ставку на уровне 14% годовых. ..."
  },
  "analytics": [
    {
      "chunk_id": "cb_key_rate_14::p2::c1",
      "doc_title": "Ключевая ставка ЦБ РФ: ставка без изменения на 14,0%, риторика стала жестче",
      "page": 2,
      "text": "Регулятор сигнализирует о более длительном периоде высоких ставок. ...",
      "stance": "hawkish"
    }
  ]
}
```

`output`:

```json
{
  "interpretation_id": 381924761028374,
  "client_id": "U_176",
  "event": {
    "news_id": 1001,
    "title": "ЦБ сохранил ключевую ставку на 14%",
    "published_at": "2026-09-11"
  },
  "what_happened": "11 сентября 2026 года ЦБ сохранил ключевую ставку на 14%. Это первая пауза после 10 снижений с июня 2025 года, риторика регулятора ужесточилась.",
  "why_it_matters": "У компании высокая зависимость от заёмного финансирования и есть кредитные продукты — сохранение ставки означает, что стоимость обслуживания долга не снизится в ближайший квартал.",
  "risks": [
    "Стоимость обслуживания кредитов не снизится в ближайший квартал",
    "Давление на маржу в грузоперевозках сохранится"
  ],
  "opportunities": [
    "Депозитные продукты могут дать повышенную доходность на свободные средства"
  ],
  "recommended_actions": [
    "Пересмотреть график рефинансирования на Q4 2026",
    "Оценить доходность депозитов на свободные средства"
  ],
  "attribution": {
    "bank_view": {
      "text": "Период быстрого удешевления кредитов приостановлен",
      "chunk_id": "cb_key_rate_14::p2::c1",
      "doc_title": "Ключевая ставка ЦБ РФ: ставка без изменения на 14,0%, риторика стала жестче",
      "page": 2
    },
    "model_inference": "Финансовая нагрузка на компанию не снизится в ближайший квартал — вывод модели на основе сигнала credit_dependency=high и позиции банка."
  },
  "sources": [
    {"type": "news", "id": 1001},
    {"type": "analytics", "chunk_id": "cb_key_rate_14::p2::c1"},
    {"type": "client_signal", "id": "credit_dependency"}
  ],
  "confidence": 0.82
}
```

---

## Публичный API

| Функция | Назначение |
|---|---|
| `interpret(input_json, *, api_key=None, model=None, base_url=None, temperature=0.0, max_retries=1, timeout=60.0) -> dict` | Основная функция. Возвращает полный `output.json`. Гарантирует валидность (или fallback) |
| `fallback_output(input_json, interpretation_id, reason) -> dict` | Минимально валидный выход, если LLM не справилась |
| `new_interpretation_id() -> int` | Уникальный int-id интерпретации |
| `strip_json_fence(text) -> str` | Убирает ` ```json ... ``` ` обёртку |
| `ALLOWED_MODELS` | frozenset разрешённых моделей |
| `DEFAULT_MODEL`, `DEFAULT_BASE_URL` | значения по умолчанию (из `.env` или константы) |
| `SYSTEM_PROMPT`, `LLM_SCHEMA` | промпт и схема для внешнего использования |

### Параметры `interpret()`

| Параметр      | Тип         | По умолчанию | Описание                         |
| ------------- | ----------- | ------------ | -------------------------------- |
| `input_json`  | dict        | —            | входной JSON (см. выше)          |
| `api_key`     | str \| None | из `.env`    | переопределяет `LLM_API_KEY`     |
| `model`       | str \| None | из `.env`    | переопределяет `LLM_MODEL`       |
| `base_url`    | str \| None | из `.env`    | переопределяет `LLM_BASE_URL`    |
| `temperature` | float       | `0.0`        | для стабильности модели          |
| `max_retries` | int         | `1`          | один ретрай при ошибке валидации |
| `timeout`     | float       | `60.0`       | таймаут HTTP-запроса, сек        |

---

## Контракт с LLM

LLM **не возвращает** метаданные. Она возвращает только:

```json
{
  "what_happened": "str",
  "why_it_matters": "str",
  "risks": ["str"],
  "opportunities": ["str"],
  "recommended_actions": ["str"],
  "bank_view_text": "str",
  "model_inference": "str",
  "used_chunk_id": "str",
  "used_signals": ["credit_dependency"],
  "confidence": 0.0
}
```

Валидация (`_validate_llm_output`):

1. `jsonschema.validate` по `schema.json`.
2. `used_chunk_id ∈ {analytics[].chunk_id}` — иначе ошибка.
3. `used_signals ⊆ keys(client.signals)` — иначе ошибка.

Если валидация не прошла — один ретрай с текстом ошибки в промпте.
Если и это не помогло — `fallback_output()` с `confidence: 0.0`.

---

## Разрешённые модели

```
google/gemma-4-26b-a4b-it
z-ai/glm-5.3-flash            (по умолчанию)
qwen/qwen3.6-35b-a3b          
deepseek/deepseek-v4.1-flash
qwen/qwen3-vl-30b-a3b-instruct
moonshotai/kimi-k2.6
```

Другие модели — `ValueError("model '...' не входит в разрешённый список")`.

---

## Ограничения и допущения

- **Один вызов LLM = одна новость** (Single). Для ленты — N вызовов.
- **`analytics` не пустой.** Если пуст — `interpret()` сразу возвращает fallback
  с причиной `analytics is empty`, без вызова LLM.
- **Хост `changellenge.up.railway.app`** может отдавать `502/503/504`
  или таймауты. Модуль ловит их как `RuntimeError`; тест помечает `[SKIP]`.

---

## Ошибки

| Ситуация | Исключение |
|---|---|
| Нет `LLM_API_KEY` | `ValueError("LLM_API_KEY не задан...")` |
| Модель вне allow-list | `ValueError("model '...' не входит в разрешённый список")` |
| Невалидный вход | `ValueError("во входе отсутствует ключ: ...")` |
| LLM вернула не-JSON | ретрай, затем fallback |
| LLM вернула невалидный JSON | ретрай, затем fallback |
| `used_chunk_id` не из `analytics` | ретрай, затем fallback |
| Сетевая ошибка | `RuntimeError` (тест → `[SKIP]`) |

---

## Проверка

Тесты — в соседней папке `tests/` (не входят в поставку модуля):

```bash
python tests/test_interpreter.py
```

- офлайн-тесты — без сети;
- онлайн-тесты — `[SKIP]`, если хост недоступен;
- полный лог — `tests/test_results.log`.