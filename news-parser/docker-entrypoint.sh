#!/bin/sh
set -e

# Создать/обновить таблицы модуля (идемпотентно)
alembic upgrade head

# Воркер: фоновый сбор и обработка по расписанию. HTTP-сервера нет — функции модуля
# вызываются напрямую (news_parser.interface) или через CLI: python -m news_parser.cli ...
exec python -m news_parser.worker
