from logging.config import fileConfig

from sqlalchemy import create_engine, text

from alembic import context
from news_parser.settings import get_settings
from news_parser.storage.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()


def run_migrations_online() -> None:
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        # схема и расширение нужны до того, как alembic создаст свою таблицу версий
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"'))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            include_schemas=True,
            version_table_schema=settings.db_schema,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
