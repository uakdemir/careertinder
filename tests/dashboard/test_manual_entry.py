"""Tests for D4: Manual job entry — validation, dedup, DB insertion."""

import importlib
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobhunter.db.models import Base, RawJobPosting
from jobhunter.utils.hashing import normalize_and_hash

# The page module starts with a digit, so use importlib to load it
_mod = importlib.import_module("jobhunter.dashboard.pages.14_manual_entry")
_handle_submission = _mod._handle_submission


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


class TestManualEntryValidation:
    """Test _handle_submission validation logic."""

    def test_required_fields_all_empty(self) -> None:
        """All empty required fields produce four error messages."""
        mock_st = MagicMock()
        with patch.object(_mod, "st", mock_st):
            _handle_submission("", "", "", "", "", "", "")

        assert mock_st.error.call_count == 4

    def test_required_fields_partial(self) -> None:
        """Missing one required field produces one error."""
        mock_st = MagicMock()
        with patch.object(_mod, "st", mock_st):
            _handle_submission("Engineer", "Co", "https://x.com", "", "", "", "")

        assert mock_st.error.call_count == 1
        assert "Description" in mock_st.error.call_args[0][0]


class TestManualEntryCreatesPosting:
    """Test successful manual job creation."""

    def test_creates_posting_with_correct_fields(self, db_session: Session) -> None:
        """Valid submission creates RawJobPosting with source='manual'."""
        mock_st = MagicMock()
        with (
            patch.object(_mod, "st", mock_st),
            patch.object(_mod, "get_session") as mock_gs,
        ):
            mock_gs.return_value.__enter__ = MagicMock(return_value=db_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            _handle_submission(
                "Senior Engineer",
                "Acme Corp",
                "https://acme.com/jobs/1",
                "A great job description.",
                "$120K",
                "Remote",
                "5+ years Python",
            )

        posting = db_session.query(RawJobPosting).first()
        assert posting is not None
        assert posting.source == "manual"
        assert posting.title == "Senior Engineer"
        assert posting.company == "Acme Corp"
        assert posting.source_url == "https://acme.com/jobs/1"
        assert posting.description == "A great job description."
        assert posting.salary_raw == "$120K"
        assert posting.location_raw == "Remote"
        assert posting.requirements == "5+ years Python"
        assert posting.raw_html is None
        assert posting.scraper_run_id is None
        assert posting.fingerprint_hash is not None
        mock_st.success.assert_called_once()

    def test_optional_fields_none_when_empty(self, db_session: Session) -> None:
        """Empty optional fields stored as None."""
        mock_st = MagicMock()
        with (
            patch.object(_mod, "st", mock_st),
            patch.object(_mod, "get_session") as mock_gs,
        ):
            mock_gs.return_value.__enter__ = MagicMock(return_value=db_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            _handle_submission(
                "Dev",
                "Co",
                "https://co.com/job",
                "Description text.",
                "",
                "",
                "",
            )

        posting = db_session.query(RawJobPosting).first()
        assert posting is not None
        assert posting.salary_raw is None
        assert posting.location_raw is None
        assert posting.requirements is None


class TestManualEntryDuplicateBlocked:
    """Test duplicate fingerprint blocking."""

    def test_duplicate_blocked(self, db_session: Session) -> None:
        """Submitting a job with the same fingerprint is blocked."""
        fingerprint = normalize_and_hash("Acme Corp", "Senior Engineer")
        existing = RawJobPosting(
            source="linkedin",
            source_url="https://linkedin.com/jobs/1",
            title="Senior Engineer",
            company="Acme Corp",
            description="Existing job.",
            fingerprint_hash=fingerprint,
        )
        db_session.add(existing)
        db_session.commit()

        mock_st = MagicMock()
        with (
            patch.object(_mod, "st", mock_st),
            patch.object(_mod, "get_session") as mock_gs,
        ):
            mock_gs.return_value.__enter__ = MagicMock(return_value=db_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            _handle_submission(
                "Senior Engineer",
                "Acme Corp",
                "https://acme.com/jobs/1",
                "Different description.",
                "",
                "",
                "",
            )

        # Should show error and info, not success
        mock_st.error.assert_called_once()
        assert "already exists" in mock_st.error.call_args[0][0]
        mock_st.info.assert_called_once()
        mock_st.success.assert_not_called()

        # Only the original posting exists
        count = db_session.query(RawJobPosting).count()
        assert count == 1


class TestManualEntryFingerprint:
    """Test fingerprint computation."""

    def test_fingerprint_uses_normalize_and_hash(self, db_session: Session) -> None:
        """Fingerprint computed via normalize_and_hash(company, title)."""
        mock_st = MagicMock()
        with (
            patch.object(_mod, "st", mock_st),
            patch.object(_mod, "get_session") as mock_gs,
        ):
            mock_gs.return_value.__enter__ = MagicMock(return_value=db_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            _handle_submission(
                "Senior Engineer",
                "Acme Corp",
                "https://acme.com/jobs/1",
                "Description.",
                "",
                "",
                "",
            )

        posting = db_session.query(RawJobPosting).first()
        expected = normalize_and_hash("Acme Corp", "Senior Engineer")
        assert posting is not None
        assert posting.fingerprint_hash == expected
