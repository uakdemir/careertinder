import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from jobhunter.config.schema import DatabaseConfig

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def create_engine(config: DatabaseConfig):
    """Create and configure the SQLAlchemy engine."""
    global _engine, _SessionLocal

    db_path = Path(config.path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _engine = sa_create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=config.echo_sql,
    )

    @event.listens_for(_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    _SessionLocal = sessionmaker(bind=_engine)
    logger.info("Database engine created for %s", db_path)
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
