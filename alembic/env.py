"""Alembic migration environment supporting SQLite and PostgreSQL."""

from logging.config import fileConfig
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import engine_from_config, pool

from alembic import context
from jobhunter.config.loader import load_config
from jobhunter.config.schema import SecretsConfig
from jobhunter.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Build database URL from config.yaml, with env var overrides for PostgreSQL."""
    app_config = load_config(Path("config.yaml"))
    db_config = app_config.database

    if db_config.driver == "sqlite":
        db_path = Path(db_config.path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path}"

    elif db_config.driver == "postgresql":
        # Env vars override config.yaml values
        secrets = SecretsConfig()
        host = secrets.database_host or db_config.host
        port = secrets.database_port or db_config.port
        name = secrets.database_name or db_config.name
        user = secrets.database_user or db_config.user
        password = secrets.database_password or ""

        encoded_password = quote_plus(password)
        return f"postgresql://{user}:{encoded_password}@{host}:{port}/{name}"

    else:
        raise ValueError(f"Unsupported database driver: {db_config.driver}")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Override the URL from alembic.ini with our dynamic URL
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
