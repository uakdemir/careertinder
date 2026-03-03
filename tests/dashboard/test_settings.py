"""Tests for DS12 settings CRUD and seed_defaults."""

import json

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from jobhunter.config.schema import FilteringConfig, ScrapingConfig
from jobhunter.db.settings import (
    CATEGORY_FILTERING,
    CATEGORY_SCRAPING,
    SettingsEntry,
    get_filtering_config,
    get_scraping_config,
    get_settings,
    seed_defaults,
    update_settings,
)


class TestGetSettings:
    """Tests for get_settings()."""

    def test_returns_defaults_when_category_missing(self, db_session_with_settings: Session) -> None:
        """When no row exists, returns Pydantic defaults."""
        data = get_settings(db_session_with_settings, CATEGORY_SCRAPING)
        expected = ScrapingConfig().model_dump()
        assert data == expected

    def test_returns_stored_json(self, db_session_with_settings: Session) -> None:
        """When a row exists, returns parsed JSON."""
        row = SettingsEntry(
            category=CATEGORY_SCRAPING,
            settings_json=json.dumps({"timeout_seconds": 999}),
        )
        db_session_with_settings.add(row)
        db_session_with_settings.flush()

        data = get_settings(db_session_with_settings, CATEGORY_SCRAPING)
        assert data["timeout_seconds"] == 999

    def test_unknown_category_returns_empty_dict(self, db_session_with_settings: Session) -> None:
        data = get_settings(db_session_with_settings, "nonexistent")
        assert data == {}


class TestUpdateSettings:
    """Tests for update_settings()."""

    def test_creates_row_if_missing(self, db_session_with_settings: Session) -> None:
        """First update creates the settings row."""
        data = ScrapingConfig().model_dump()
        update_settings(db_session_with_settings, CATEGORY_SCRAPING, data)

        row = db_session_with_settings.query(SettingsEntry).filter_by(category=CATEGORY_SCRAPING).first()
        assert row is not None
        assert json.loads(row.settings_json)["timeout_seconds"] == 600

    def test_updates_existing_row(self, db_session_with_settings: Session) -> None:
        """Second update overwrites the existing row."""
        data = ScrapingConfig().model_dump()
        update_settings(db_session_with_settings, CATEGORY_SCRAPING, data)

        data["timeout_seconds"] = 120
        update_settings(db_session_with_settings, CATEGORY_SCRAPING, data)

        row = db_session_with_settings.query(SettingsEntry).filter_by(category=CATEGORY_SCRAPING).first()
        assert row is not None
        assert json.loads(row.settings_json)["timeout_seconds"] == 120

    def test_roundtrip_scraping_config(self, db_session_with_settings: Session) -> None:
        """Write → read produces the same ScrapingConfig."""
        original = ScrapingConfig(timeout_seconds=300)
        update_settings(db_session_with_settings, CATEGORY_SCRAPING, original.model_dump())

        loaded = get_scraping_config(db_session_with_settings)
        assert loaded.timeout_seconds == 300
        assert loaded.remote_io.enabled is True

    def test_roundtrip_filtering_config(self, db_session_with_settings: Session) -> None:
        """Write → read produces the same FilteringConfig."""
        original = FilteringConfig(salary_min_usd=120000)
        update_settings(db_session_with_settings, CATEGORY_FILTERING, original.model_dump())

        loaded = get_filtering_config(db_session_with_settings)
        assert loaded.salary_min_usd == 120000

    def test_rejects_invalid_data(self, db_session_with_settings: Session) -> None:
        """Invalid data raises ValidationError, DB unchanged."""
        with pytest.raises(ValidationError):
            update_settings(
                db_session_with_settings,
                CATEGORY_FILTERING,
                {"salary_min_usd": -100},  # violates gt=0
            )
        # Verify nothing was written
        row = db_session_with_settings.query(SettingsEntry).filter_by(category=CATEGORY_FILTERING).first()
        assert row is None


class TestSeedDefaults:
    """Tests for seed_defaults()."""

    def test_seeds_all_categories(self, db_session_with_settings: Session) -> None:
        """seed_defaults creates rows for all known categories."""
        seed_defaults(db_session_with_settings)

        rows = db_session_with_settings.query(SettingsEntry).all()
        categories = {r.category for r in rows}
        assert "scraping" in categories
        assert "filtering" in categories
        assert "scheduling" in categories
        assert "notifications" in categories

    def test_does_not_overwrite_existing(self, db_session_with_settings: Session) -> None:
        """seed_defaults skips categories that already have a row."""
        custom = ScrapingConfig(timeout_seconds=42).model_dump()
        update_settings(db_session_with_settings, CATEGORY_SCRAPING, custom)

        seed_defaults(db_session_with_settings)

        loaded = get_scraping_config(db_session_with_settings)
        assert loaded.timeout_seconds == 42  # not overwritten to 600

    def test_idempotent(self, db_session_with_settings: Session) -> None:
        """Calling seed_defaults twice produces the same result."""
        seed_defaults(db_session_with_settings)
        count_first = db_session_with_settings.query(SettingsEntry).count()

        seed_defaults(db_session_with_settings)
        count_second = db_session_with_settings.query(SettingsEntry).count()

        assert count_first == count_second
