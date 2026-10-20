#!/bin/sh
set -e

# Создать/обновить таблицы модуля (идемпотентно)
alembic upgrade head

# Один процесс: внутри живёт планировщик сбора (несколько воркеров = несколько сборов)
exec uvicorn news_parser.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
