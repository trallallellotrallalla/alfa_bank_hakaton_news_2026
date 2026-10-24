"""Чанки статей с векторами — контекст для агента вместо URL.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op
from news_parser.core.settings import get_settings

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

settings = get_settings()
SCHEMA = settings.db_schema
DIM = settings.embedding_dim


def upgrade() -> None:
    op.create_table(
        "article_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "article_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.events.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(DIM), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("article_id", "chunk_index"),
        schema=SCHEMA,
    )
    op.create_index("ix_article_chunks_article_id", "article_chunks", ["article_id"], schema=SCHEMA)
    op.create_index("ix_article_chunks_event_id", "article_chunks", ["event_id"], schema=SCHEMA)
    op.create_index(
        "ix_article_chunks_embedding",
        "article_chunks",
        ["embedding"],
        schema=SCHEMA,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("article_chunks", schema=SCHEMA)
