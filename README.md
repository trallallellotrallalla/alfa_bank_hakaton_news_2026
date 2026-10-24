# alfa_bank_hakaton_news_2026

Команда **DeleteSystem32** — проект «Новостная аналитика для принятия бизнес-решений» (Альфа Хак 2026).

---

## Архитектура и связь модулей

Проект объединяет три модуля в единый пайплайн:

```
┌──────────────────┐     ┌────────────────────────────────────────┐     ┌─────────────────────────────┐
│   data_loader    │────▶│              news-parser               │────▶│         interpreter         │
│ профиль и связи  │     │ парсер, префильтр, LLM-классификатор,  │     │ LLM-интерпретатор: генерация│
│ клиента из БД    │     │ жесткий фильтр + векторный RAG-подбор  │     │ выводов, рисков и действий  │
└──────────────────┘     └────────────────────────────────────────┘     └─────────────────────────────┘
                                    │ пакеты {client, news, analytics}             │
                                    └──────────────────────────────────────────────┘
```

1. **`data_loader/`** — загрузка данных о клиентах и контрагентах (`schema.sql`, `data/clients/*.csv`) и сборка карточки клиента `get_client_info(client_id)`.
2. **`news-parser/`** ([подробный README](news-parser/README.md)) — фоновый сбор новостей (СМИ, ЦБ РФ, MOEX) и аналитики Альфа-Банка (`data/alfa`), очистка, дедупликация, префильтр, LLM-классификация, эмбеддинги и формирование пакетов `{client, news, analytics}` для конкретного клиента (`get_packets`).
3. **`interpreter/`** ([подробный README](interpreter/interpreter/README.md)) — принимает пакет `{client, news, analytics}` от парсера и генерирует персонализированную интерпретацию события для клиента (`interpret`), валидируя ответ по JSON-схеме и проверяя ссылки на чанки аналитики и сигналы клиента.

---

## Быстрый старт (Docker)

Все сервисы запускаются из корня проекта через единый `docker-compose.yml` и единый `.env`:

```bash
cp .env.example .env   # укажите LLM_API_KEY
docker compose up -d --build
```

Контейнер `news-parser` включает в себя `news-parser`, `data_loader` и `interpreter`.

### Вызов сквозного пайплайна (`news-parser` → `interpreter`)

**Через CLI контейнера:**

```bash
# Сквозной пайплайн: отбор релевантных клиенту новостей и аналитики -> LLM-интерпретация каждого пакета
docker compose exec news-parser python -m news_parser.cli interpret U_176 --limit 5

# Только пакеты от парсера (вход для интерпретатора)
docker compose exec news-parser python -m news_parser.cli packets U_176 --limit 5
```

**Из Python:**

```python
from news_parser import interpret_client, get_packets, interpret

# 1. В один вызов (парсер + классификатор -> интерпретатор):
interpretations = interpret_client("U_176", limit=5)

# 2. Пошагово:
packets = get_packets("U_176", limit=5)
for packet in packets:
    result = interpret(packet)
```

---

## Структура репозитория

```
.
├── data/                  # аналитика Альфа-Банка (data/alfa) и CSV клиентов (data/clients)
├── data_loader/           # загрузка клиентских данных в БД и get_client_info()
├── news-parser/           # модуль парсера, классификатора и подбора (news_parser)
├── interpreter/           # модуль LLM-интерпретации пакета (interpreter)
├── schema.sql             # схема таблиц клиентских данных (public)
├── docker-compose.yml     # единый Docker Compose (PostgreSQL + pgvector и рабочий контейнер)
├── .dockerignore          # контекст сборки единого образа
└── .env.example           # шаблон единого файла переменных окружения
```
