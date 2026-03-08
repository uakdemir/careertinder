"""Tests for M3.5 dashboard components — status actions, score display, pipeline runner."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobhunter.db.models import (
    ApplicationStatus,
    Base,
    Company,
    ProcessedJob,
    RawJobPosting,
)
from jobhunter.db.settings import SettingsEntry  # noqa: F401


@pytest.fixture
def db_session():
    """In-memory SQLite database with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


def _create_raw_job(session: Session, title: str = "Engineer", company: str = "Acme") -> RawJobPosting:
    """Helper to create a raw job posting."""
    raw = RawJobPosting(
        source="linkedin",
        source_url="https://example.com/job",
        title=title,
        company=company,
        description="Test job description",
        fingerprint_hash=f"hash_{title}_{company}_{id(session)}",
    )
    session.add(raw)
    session.flush()
    return raw


def _create_company(session: Session, name: str = "Acme Corp") -> Company:
    """Helper to create a company."""
    company = Company(name=name)
    session.add(company)
    session.flush()
    return company


def _create_processed_job(
    session: Session,
    raw: RawJobPosting,
    company: Company,
    status: str = "new",
) -> ProcessedJob:
    """Helper to create a processed job."""
    job = ProcessedJob(
        company_id=company.company_id,
        raw_id=raw.raw_id,
        title=raw.title,
        location_policy="remote_worldwide",
        description_clean="Clean description",
        application_url=raw.source_url,
        source_site=raw.source,
        fingerprint_hash=raw.fingerprint_hash,
        status=status,
    )
    session.add(job)
    session.flush()
    return job


# ---------------------------------------------------------------------------
# Status Actions Tests
# ---------------------------------------------------------------------------


class TestTransitionJobStatus:
    """Tests for transition_job_status()."""

    def test_creates_ds7_record(self, db_session: Session) -> None:
        from jobhunter.dashboard.components.status_actions import transition_job_status

        raw = _create_raw_job(db_session)
        company = _create_company(db_session)
        job = _create_processed_job(db_session, raw, company, status="evaluated")

        transition_job_status(db_session, job.job_id, "shortlisted")

        records = db_session.query(ApplicationStatus).filter_by(job_id=job.job_id).all()
        assert len(records) == 1
        assert records[0].status == "shortlisted"
        assert records[0].updated_by == "user"

    def test_append_only(self, db_session: Session) -> None:
        """Multiple transitions create multiple records."""
        from jobhunter.dashboard.components.status_actions import transition_job_status

        raw = _create_raw_job(db_session)
        company = _create_company(db_session)
        job = _create_processed_job(db_session, raw, company, status="evaluated")

        transition_job_status(db_session, job.job_id, "shortlisted")
        transition_job_status(db_session, job.job_id, "rejected_by_user")

        records = db_session.query(ApplicationStatus).filter_by(job_id=job.job_id).all()
        assert len(records) == 2

    def test_with_notes(self, db_session: Session) -> None:
        from jobhunter.dashboard.components.status_actions import transition_job_status

        raw = _create_raw_job(db_session)
        company = _create_company(db_session)
        job = _create_processed_job(db_session, raw, company, status="evaluated")

        transition_job_status(db_session, job.job_id, "shortlisted", notes="Great match")

        record = db_session.query(ApplicationStatus).filter_by(job_id=job.job_id).first()
        assert record is not None
        assert record.notes == "Great match"


class TestGetCurrentStatus:
    """Tests for get_current_status()."""

    def test_returns_none_when_no_records(self, db_session: Session) -> None:
        from jobhunter.dashboard.components.status_actions import get_current_status

        raw = _create_raw_job(db_session)
        company = _create_company(db_session)
        job = _create_processed_job(db_session, raw, company)

        assert get_current_status(db_session, job.job_id) is None

    def test_returns_latest_status(self, db_session: Session) -> None:
        from jobhunter.dashboard.components.status_actions import (
            get_current_status,
            transition_job_status,
        )

        raw = _create_raw_job(db_session)
        company = _create_company(db_session)
        job = _create_processed_job(db_session, raw, company, status="evaluated")

        transition_job_status(db_session, job.job_id, "shortlisted")
        transition_job_status(db_session, job.job_id, "rejected_by_user")

        assert get_current_status(db_session, job.job_id) == "rejected_by_user"

    def test_shortlist_skip_shortlist_returns_shortlisted(self, db_session: Session) -> None:
        """Shortlist → Skip → Shortlist should return shortlisted."""
        from jobhunter.dashboard.components.status_actions import (
            get_current_status,
            transition_job_status,
        )

        raw = _create_raw_job(db_session)
        company = _create_company(db_session)
        job = _create_processed_job(db_session, raw, company, status="evaluated")

        transition_job_status(db_session, job.job_id, "shortlisted")
        transition_job_status(db_session, job.job_id, "rejected_by_user")
        transition_job_status(db_session, job.job_id, "shortlisted")

        assert get_current_status(db_session, job.job_id) == "shortlisted"


# ---------------------------------------------------------------------------
# Score Display Tests
# ---------------------------------------------------------------------------


class TestScoreDisplay:
    """Tests for score_display module."""

    def test_score_color_green(self) -> None:
        from jobhunter.dashboard.components.score_display import score_color

        assert score_color(75) == "green"
        assert score_color(100) == "green"

    def test_score_color_orange(self) -> None:
        from jobhunter.dashboard.components.score_display import score_color

        assert score_color(60) == "orange"
        assert score_color(74) == "orange"

    def test_score_color_red(self) -> None:
        from jobhunter.dashboard.components.score_display import score_color

        assert score_color(0) == "red"
        assert score_color(59) == "red"

    def test_score_badge(self) -> None:
        from jobhunter.dashboard.components.score_display import score_badge

        assert ":green[92]" in score_badge(92)
        assert ":orange[65]" in score_badge(65)
        assert ":red[30]" in score_badge(30)

    def test_fit_category_label(self) -> None:
        from jobhunter.dashboard.components.score_display import fit_category_label

        assert fit_category_label("exceptional_match") == "Exceptional"
        assert fit_category_label("strong_match") == "Strong Match"
        assert fit_category_label("moderate_match") == "Moderate"
        assert fit_category_label(None) == "—"
        assert fit_category_label("unknown") == "unknown"


# ---------------------------------------------------------------------------
# Formatting Tests
# ---------------------------------------------------------------------------


class TestFormatting:
    """Tests for formatting utilities."""

    def test_format_relative_time_none(self) -> None:
        from jobhunter.dashboard.components.formatting import format_relative_time

        assert format_relative_time(None) == "Never"

    def test_format_relative_time_recent(self) -> None:
        from jobhunter.dashboard.components.formatting import format_relative_time

        assert format_relative_time(datetime.now(UTC)) == "just now"


# ---------------------------------------------------------------------------
# Pipeline Runner Tests
# ---------------------------------------------------------------------------


class TestPipelineRunner:
    """Tests for pipeline_runner module."""

    def test_run_simple_command(self) -> None:
        """run_pipeline_command with --help returns 0."""
        from unittest.mock import MagicMock

        from jobhunter.dashboard.components.pipeline_runner import run_pipeline_command

        placeholder = MagicMock()
        placeholder.code = MagicMock()

        exit_code = run_pipeline_command(["--help"], placeholder)
        assert exit_code == 0
        # Placeholder should have been called at least once with output
        assert placeholder.code.call_count > 0
