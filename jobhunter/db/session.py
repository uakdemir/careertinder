"""Database session management supporting SQLite and PostgreSQL."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from jobhunter.config.schema import DatabaseConfig, SecretsConfig

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def _build_connection_url(config: DatabaseConfig, secrets: SecretsConfig | None = None) -> str:
    """Build SQLAlchemy connection URL based on driver type.

    For PostgreSQL, env vars (via secrets) override config.yaml values.
    """
    if config.driver == "sqlite":
        db_path = Path(config.path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path}"

    elif config.driver == "postgresql":
        # Load secrets if not provided
        if secrets is None:
            secrets = SecretsConfig()

        # Env vars override config.yaml values
        host = secrets.database_host or config.host
        port = secrets.database_port or config.port
        name = secrets.database_name or config.name
        user = secrets.database_user or config.user
        password = secrets.database_password or ""

        if not password:
            logger.warning("DATABASE_PASSWORD not set in environment")

        encoded_password = quote_plus(password)
        return f"postgresql://{user}:{encoded_password}@{host}:{port}/{name}"

    else:
        raise ValueError(f"Unsupported database driver: {config.driver}")


def create_engine(config: DatabaseConfig):
    """Create and configure the SQLAlchemy engine."""
    global _engine, _SessionLocal

    url = _build_connection_url(config)

    # Build engine with driver-specific settings
    if config.driver == "sqlite":
        _engine = sa_create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=config.echo_sql,
        )

        # SQLite-specific pragmas
        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        logger.info("SQLite database engine created for %s", config.path)

    elif config.driver == "postgresql":
        _engine = sa_create_engine(
            url,
            echo=config.echo_sql,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before use
        )
        logger.info(
            "PostgreSQL database engine created for %s@%s:%d/%s",
            config.user, config.host, config.port, config.name
        )

    _SessionLocal = sessionmaker(bind=_engine)
    return _engine


def get_engine():
    """Get the current engine instance."""
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call create_engine() first.")
    return _engine


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional session scope."""
    if _SessionLocal is None:
        raise RuntimeError("Database engine not initialized. Call create_engine() first.")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
