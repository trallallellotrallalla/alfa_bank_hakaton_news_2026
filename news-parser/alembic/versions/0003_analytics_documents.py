"""Документы аналитики: выжимка, позиция банка, теги, дата — для подбора в два шага.

Старые фрагменты аналитики удаляются: при следующем запуске воркер загрузит документы
заново уже с профилем (тексты страниц берутся из кеша рядом с PDF, если он есть).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

from alembic import op
from news_parser.core.settings import get_settings

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

settings = get_settings()
SCHEMA = settings.db_schema
DIM = settings.embedding_dim


def upgrade() -> None:
    op.create_table(
        "analytics_documents",
        sa.Column("doc_id", sa.String(64), primary_key=True),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published_date", sa.Date(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("stance", sa.String(16), nullable=True),
        sa.Column("macro_factors", pg.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("industries", pg.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("text_method", sa.String(32), nullable=False),
        sa.Column("profile_method", sa.String(16), nullable=False),
        sa.Column("embedding", Vector(DIM), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema=SCHEMA,
    )
    for col in ("macro_factors", "industries"):
        op.create_index(f"ix_analytics_documents_{col}", "analytics_documents", [col], schema=SCHEMA, postgresql_using="gin")
    op.execute(f'DELETE FROM "{SCHEMA}".analytics_chunks')


def downgrade() -> None:
    op.drop_table("analytics_documents", schema=SCHEMA)
