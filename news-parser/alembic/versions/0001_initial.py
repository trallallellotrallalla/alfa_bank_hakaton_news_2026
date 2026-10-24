"""Начальная схема: события, статьи, аналитика Альфа-Банка, журнал LLM.

Revision ID: 0001
Revises:
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

from alembic import op
from news_parser.core.settings import get_settings

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

settings = get_settings()
SCHEMA = settings.db_schema
DIM = settings.embedding_dim


def _arr(name: str) -> sa.Column:
    return sa.Column(name, pg.ARRAY(sa.String()), nullable=False, server_default="{}")


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("horizon", sa.String(16), nullable=False),
        _arr("macro_factors"),
        _arr("industries"),
        _arr("okved"),
        _arr("regions"),
        _arr("countries"),
        sa.Column("entities", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("embedding", Vector(DIM), nullable=True),
        sa.Column("main_article_id", sa.BigInteger(), nullable=True),
        sa.Column("is_structured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("n_articles", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("n_sources", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_trust", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_events_last_seen_at", "events", ["last_seen_at"], schema=SCHEMA)
    for col in ("macro_factors", "industries", "okved", "regions", "countries"):
        op.create_index(f"ix_events_{col}", "events", [col], schema=SCHEMA, postgresql_using="gin")
    op.create_index(
        "ix_events_embedding",
        "events",
        ["embedding"],
        schema=SCHEMA,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "articles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("trust", sa.Float(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("extraction", pg.JSONB(), nullable=True),
        sa.Column("extraction_meta", pg.JSONB(), nullable=True),
        sa.Column("embedding", Vector(DIM), nullable=True),
        sa.Column(
            "event_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.events.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("cluster_similarity", sa.Float(), nullable=True),
        schema=SCHEMA,
    )
    for col in ("source_id", "url", "content_hash", "status", "event_id"):
        op.create_index(f"ix_articles_{col}", "articles", [col], schema=SCHEMA)

    op.create_table(
        "analytics_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("doc_id", sa.String(64), nullable=False),
        sa.Column("doc_title", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_from", sa.Integer(), nullable=True),
        sa.Column("page_to", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        _arr("macro_factors"),
        _arr("industries"),
        sa.Column("origin", sa.String(32), nullable=False, server_default="alfa_bank"),
        sa.Column("embedding", Vector(DIM), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("doc_id", "chunk_index"),
        schema=SCHEMA,
    )
    op.create_index("ix_analytics_chunks_doc_id", "analytics_chunks", ["doc_id"], schema=SCHEMA)
    op.create_index(
        "ix_analytics_chunks_embedding",
        "analytics_chunks",
        ["embedding"],
        schema=SCHEMA,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_llm_calls_created_at", "llm_calls", ["created_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("llm_calls", schema=SCHEMA)
    op.drop_table("analytics_chunks", schema=SCHEMA)
    op.drop_table("articles", schema=SCHEMA)
    op.drop_table("events", schema=SCHEMA)
