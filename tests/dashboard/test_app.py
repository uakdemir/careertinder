"""Tests for the dashboard app module — importability and helper functions."""

from datetime import UTC, datetime, timedelta

import pytest

st = pytest.importorskip("streamlit", reason="Streamlit not installed")


class TestFormatRelativeTime:
    """Tests for app._format_relative_time()."""

    def test_none_returns_never(self) -> None:
        from jobhunter.dashboard.app import _format_relative_time

        assert _format_relative_time(None) == "Never"

    def test_just_now(self) -> None:
        from jobhunter.dashboard.app import _format_relative_time

        result = _format_relative_time(datetime.now(UTC))
        assert result == "just now"

    def test_minutes_ago(self) -> None:
        from jobhunter.dashboard.app import _format_relative_time

        dt = datetime.now(UTC) - timedelta(minutes=15)
        result = _format_relative_time(dt)
        assert "m ago" in result

    def test_hours_ago(self) -> None:
        from jobhunter.dashboard.app import _format_relative_time

        dt = datetime.now(UTC) - timedelta(hours=3)
        result = _format_relative_time(dt)
        assert "h ago" in result

    def test_days_ago(self) -> None:
        from jobhunter.dashboard.app import _format_relative_time

        dt = datetime.now(UTC) - timedelta(days=5)
        result = _format_relative_time(dt)
        assert "d ago" in result

    def test_naive_datetime_handled(self) -> None:
        from jobhunter.dashboard.app import _format_relative_time

        dt = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
        result = _format_relative_time(dt)
        assert "h ago" in result


class TestModuleImports:
    """Verify dashboard modules are importable without Streamlit runtime."""

    def test_import_status_badge(self) -> None:
        from jobhunter.dashboard.components.status_badge import source_badge, status_badge

        assert status_badge("success") == "✓ success"
        assert source_badge("linkedin") == "LI"

    def test_import_settings(self) -> None:
        from jobhunter.db.settings import CATEGORY_SCRAPING, SettingsEntry

        assert CATEGORY_SCRAPING == "scraping"
        assert SettingsEntry.__tablename__ == "settings"
