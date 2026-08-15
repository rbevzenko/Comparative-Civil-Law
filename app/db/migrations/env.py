import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.getcwd())

from app.api.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DATABASE_URL is the asyncpg URL used by the app (postgresql+asyncpg://...).
# Alembic runs migrations synchronously, so strip the async driver suffix to
# fall back to the default psycopg2 driver.
database_url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
sync_url = database_url.replace("+asyncpg", "") if database_url else database_url
config.set_main_option("sqlalchemy.url", sync_url or "")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
