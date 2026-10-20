# Образ модуля news-parser. Сборка: docker build -t news-parser .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    EMBEDDING_CACHE_DIR=/models \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.13.4

WORKDIR /app

# Сначала только зависимости — этот слой кешируется, пока не меняется uv.lock
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini docker-entrypoint.sh ./
RUN uv sync --frozen --no-dev && chmod +x docker-entrypoint.sh

# Модель эмбеддингов скачивается при сборке, а не при старте контейнера:
# старт быстрый и не зависит от доступа к HuggingFace.
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
ARG EMBEDDING_DIM=768
RUN EMBEDDING_MODEL=$EMBEDDING_MODEL EMBEDDING_DIM=$EMBEDDING_DIM python -m news_parser.cli warmup

RUN useradd --create-home --uid 1000 app && chown -R app /app /models
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["./docker-entrypoint.sh"]
