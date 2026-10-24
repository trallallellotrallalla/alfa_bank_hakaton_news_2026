# Образ модуля news-parser. Собирается из КОРНЯ репозитория (рядом лежит data_loader):
#   docker build -f news-parser/Dockerfile -t news-parser .
# Работает и на классическом сборщике, и на BuildKit (buildx не обязателен).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    EMBEDDING_CACHE_DIR=/models \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

# Пользователь и папка модели создаются сразу: без `chown -R` в конце, который
# копирует в новый слой все библиотеки и модель (+1.6 ГБ к образу).
RUN pip install --no-cache-dir uv==0.13.4 \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /models && chown app /models

WORKDIR /app

# Порядок слоёв — от редко меняющихся к часто меняющимся, чтобы правка кода
# не пересобирала зависимости и не скачивала модель заново.

# 1. Зависимости — пересобираются только при изменении uv.lock
COPY news-parser/pyproject.toml news-parser/uv.lock news-parser/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# 2. Модель эмбеддингов — скачивается при сборке, а не при старте контейнера
#    (старт быстрый и не зависит от HuggingFace); пересобирается только при смене модели
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
USER app
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBEDDING_MODEL}', cache_dir='/models')"
USER root

# 3. Код — меняется чаще всего
COPY news-parser/src ./src
# библиотека модуля клиентских данных (get_client_info) — из корня репо
COPY data_loader ./data_loader
COPY news-parser/alembic ./alembic
COPY news-parser/alembic.ini news-parser/docker-entrypoint.sh ./
# sed: если репозиторий клонирован на Windows, Git мог заменить переводы строк на CRLF —
# с ними скрипт в Linux не запустится («not found» / «bad interpreter»)
RUN uv sync --frozen --no-dev && sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

USER app

# HTTP нет: здоровье = доступна ли БД (код выхода CLI-команды health)
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD python -m news_parser.cli health > /dev/null || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
