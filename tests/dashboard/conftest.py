"""Dashboard-specific test fixtures."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobhunter.db.models import Base
from jobhunter.db.settings import SettingsEntry  # noqa: F401 — ensures table is registered


@pytest.fixture
def db_session_with_settings():
    """In-memory SQLite database with all tables including settings.

    Fresh for each test. Imports SettingsEntry so its table is in metadata.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()
