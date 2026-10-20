# THIRD_PARTY_NOTICES — модуль news-parser

## Библиотеки (точные версии — в uv.lock)

| Компонент | Назначение | Лицензия |
|---|---|---|
| FastAPI | HTTP API | MIT |
| Uvicorn | ASGI-сервер | BSD-3-Clause |
| Pydantic, pydantic-settings | схемы и валидация, конфигурация | MIT |
| SQLAlchemy | ORM / SQL | MIT |
| Alembic | миграции БД | MIT |
| psycopg 3 | драйвер PostgreSQL | LGPL-3.0 |
| pgvector-python | тип vector для SQLAlchemy | MIT |
| httpx | HTTP-клиент | BSD-3-Clause |
| feedparser | разбор RSS/Atom | BSD-2-Clause |
| trafilatura | извлечение основного текста из HTML | Apache-2.0 |
| APScheduler | фоновые задачи | MIT |
| pypdf | извлечение текста из PDF | BSD-3-Clause |
| fastembed (+ onnxruntime) | локальные эмбеддинги | Apache-2.0 (onnxruntime — MIT) |
| PyYAML | конфиги | MIT |
| NumPy | нормализация векторов | BSD-3-Clause |
| pytest | тесты (только dev) | MIT |

## Инфраструктура

| Компонент | Назначение | Лицензия |
|---|---|---|
| PostgreSQL | хранилище | PostgreSQL License |
| pgvector (расширение) | векторный поиск | PostgreSQL License |
| python:3.12-slim (Docker) | базовый образ | PSF / Debian |

## Модели

| Модель | Назначение | Лицензия |
|---|---|---|
| sentence-transformers/paraphrase-multilingual-mpnet-base-v2 | эмбеддинги (по умолчанию, локально) | Apache-2.0 |
| Gemma 4 26B A4B (через API организаторов) | извлечение и классификация | из списка разрешённых моделей кейса |

## Источники данных

Используются только общедоступные ленты и API. Учитываются robots.txt и паузы между
запросами, антибот-защита не обходится. Права на тексты принадлежат издателям:
в выдаче модуль показывает краткую разметку и ссылку на первоисточник.

| Источник | Доступ |
|---|---|
| РБК, Интерфакс, Коммерсантъ, Ведомости, ТАСС | публичные RSS-ленты |
| Банк России | RSS пресс-релизов, XML официальных курсов (cbr.ru) |
| Московская биржа | MOEX ISS API (история индексов) |
| Аналитические материалы Альфа-Банка | материалы кейса (Приложение 2 ТЗ) |
