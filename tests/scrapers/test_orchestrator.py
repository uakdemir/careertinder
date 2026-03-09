"""Tests for D7: Scraper orchestrator (dedup, audit, failure isolation)."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobhunter.config.schema import AppConfig, ScrapingConfig, SecretsConfig
from jobhunter.db.models import Base, RawJobPosting, ScraperRun
from jobhunter.scrapers.base import BaseScraper, RawJobData
from jobhunter.scrapers.exceptions import ScraperError, ScraperStructureError
from jobhunter.scrapers.orchestrator import ScraperOrchestrator


class FakeScraper(BaseScraper):
    """Fake scraper for testing orchestrator logic."""

    def __init__(self, name: str, jobs: list[RawJobData] | None = None, error: Exception | None = None):
        self._name = name
        self._jobs = jobs or []
        self._error = error
        self._logger = MagicMock()

    @property
    def scraper_name(self) -> str:
        return self._name

    async def scrape(self) -> list[RawJobData]:
        if self._error:
            raise self._error
        return self._jobs

    async def health_check(self) -> bool:
        return True


@pytest.fixture
def orch_session():
    """In-memory SQLite database for orchestrator tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def config():
    return AppConfig()


@pytest.fixture
def secrets():
    return SecretsConfig(_env_file=None)


def _make_job(title: str = "Engineer", company: str = "TechCo", source: str = "remote_io") -> RawJobData:
    return RawJobData(
        source=source,
        source_url=f"https://example.com/{title.lower().replace(' ', '-')}",
        title=title,
        company=company,
        description=f"Description for {title} at {company}.",
    )


class TestScraperOrchestrator:
    @pytest.mark.asyncio
    async def test_run_all_success(self, config, secrets, orch_session) -> None:
        jobs1 = [_make_job("Engineer", "Co1", "remote_io")]
        jobs2 = [_make_job("Architect", "Co2", "linkedin")]
        scraper1 = FakeScraper("remote_io", jobs=jobs1)
        scraper2 = FakeScraper("linkedin", jobs=jobs2)

        orchestrator = ScraperOrchestrator(config, secrets, orch_session)
        with patch.object(orchestrator, "_build_enabled_scrapers", return_value=[scraper1, scraper2]):
            result = await orchestrator.run_all()

        assert len(result.results) == 2
        assert result.total_jobs_found == 2
        assert result.total_jobs_new == 2
        assert all(r.status == "success" for r in result.results)

        # Verify DB records
        postings = orch_session.query(RawJobPosting).all()
        assert len(postings) == 2
        runs = orch_session.query(ScraperRun).all()
        assert len(runs) == 2

    @pytest.mark.asyncio
    async def test_run_all_one_fails(self, config, secrets, orch_session) -> None:
        """First scraper fails, second succeeds — isolation."""
        scraper1 = FakeScraper("remote_io", error=ScraperError("remote_io", "boom"))
        scraper2 = FakeScraper("linkedin", jobs=[_make_job("Dev", "Co", "linkedin")])

        orchestrator = ScraperOrchestrator(config, secrets, orch_session)
        with patch.object(orchestrator, "_build_enabled_scrapers", return_value=[scraper1, scraper2]):
            result = await orchestrator.run_all()

        assert len(result.results) == 2
        assert result.results[0].status == "failed"
        assert result.results[0].error_message is not None
        assert result.results[1].status == "success"
        assert result.results[1].jobs_new == 1

        # Failed scraper still has a DS9 record
        runs = orch_session.query(ScraperRun).all()
        assert len(runs) == 2
        failed_run = [r for r in runs if r.scraper_name == "remote_io"][0]
        assert failed_run.status == "failed"
        assert failed_run.error_message is not None

    @pytest.mark.asyncio
    async def test_dedup_same_fingerprint(self, config, secrets, orch_session) -> None:
        """Running with same job twice → second time is update, not new."""
        job = _make_job("Engineer", "TechCo", "remote_io")
        scraper = FakeScraper("remote_io", jobs=[job])

        orchestrator = ScraperOrchestrator(config, secrets, orch_session)

        # First run
        with patch.object(orchestrator, "_build_enabled_scrapers", return_value=[scraper]):
            result1 = await orchestrator.run_all()
        assert result1.total_jobs_new == 1

        # Second run — same job
        scraper2 = FakeScraper("remote_io", jobs=[job])
        with patch.object(orchestrator, "_build_enabled_scrapers", return_value=[scraper2]):
            result2 = await orchestrator.run_all()

        assert result2.results[0].jobs_new == 0
        assert result2.results[0].jobs_updated == 1
        # Still only 1 posting in DB
        postings = orch_session.query(RawJobPosting).all()
        assert len(postings) == 1

    @pytest.mark.asyncio
    async def test_dedup_cross_source(self, config, secrets, orch_session) -> None:
        """Same company+title from different sources → dedup."""
        job_a = _make_job("Engineer", "TechCo", "remote_io")
        job_b = _make_job("Engineer", "TechCo", "linkedin")

        orchestrator = ScraperOrchestrator(config, secrets, orch_session)

        # First source
        scraper1 = FakeScraper("remote_io", jobs=[job_a])
        with patch.object(orchestrator, "_build_enabled_scrapers", return_value=[scraper1]):
            result1 = await orchestrator.run_all()
        assert result1.total_jobs_new == 1

        # Second source, same company+title
        scraper2 = FakeScraper("linkedin", jobs=[job_b])
        with patch.object(orchestrator, "_build_enabled_scrapers", return_value=[scraper2]):
            result2 = await orchestrator.run_all()
        assert result2.results[0].jobs_new == 0
        assert result2.results[0].jobs_updated == 1

    @pytest.mark.asyncio
    async def test_ds9_audit_record_created(self, config, secrets, orch_session) -> None:
        scraper = FakeScraper("remote_io", jobs=[_make_job()])

        orchestrator = ScraperOrchestrator(config, secrets, orch_session)
        with patch.object(orchestrator, "_build_enabled_scrapers", return_value=[scraper]):
            await orchestrator.run_all()

        runs = orch_session.query(ScraperRun).all()
        assert len(runs) == 1
        run = runs[0]
        assert run.scraper_name == "remote_io"
        assert run.status == "success"
        assert run.jobs_found == 1
        assert run.jobs_new == 1
        assert run.completed_at is not None
        assert run.duration_seconds is not None
        assert run.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_ds9_captures_error_traceback(self, config, secrets, orch_session) -> None:
        scraper = FakeScraper("linkedin", error=ScraperError("linkedin", "crash"))

        orchestrator = ScraperOrchestrator(config, secrets, orch_session)
        with patch.object(orchestrator, "_build_enabled_scrapers", return_value=[scraper]):
            await orchestrator.run_all()

        runs = orch_session.query(ScraperRun).all()
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "failed"
        assert run.error_traceback is not None
        assert "ScraperError" in run.error_traceback

    @pytest.mark.asyncio
    async def test_run_single_valid_name(self, config, secrets, orch_session) -> None:
        orchestrator = ScraperOrchestrator(config, secrets, orch_session)

        fake = FakeScraper("linkedin", jobs=[_make_job("Dev", "Co", "linkedin")])
        with patch.object(orchestrator, "_build_scraper", return_value=fake):
            result = await orchestrator.run_single("linkedin")

        assert result.scraper_name == "linkedin"
        assert result.status == "success"
        assert result.jobs_new == 1

    @pytest.mark.asyncio
    async def test_run_single_invalid_name(self, config, secrets, orch_session) -> None:
        orchestrator = ScraperOrchestrator(config, secrets, orch_session)
        with pytest.raises(ValueError, match="Unknown scraper"):
            await orchestrator.run_single("nonexistent")

    @pytest.mark.asyncio
    async def test_enabled_scrapers_respect_config(self, secrets, orch_session) -> None:
        config = AppConfig(
            scraping=ScrapingConfig(
                remote_io={"enabled": False},  # type: ignore[arg-type]
                remote_rocketship={"enabled": False},  # type: ignore[arg-type]
                wellfound={"enabled": False},  # type: ignore[arg-type]
                linkedin={"enabled": True},  # type: ignore[arg-type]
            )
        )
        orchestrator = ScraperOrchestrator(config, secrets, orch_session)
        scrapers = orchestrator._build_enabled_scrapers()
        assert len(scrapers) == 1
        assert scrapers[0].scraper_name == "linkedin"

    @pytest.mark.asyncio
    async def test_timeout_enforcement(self, secrets, orch_session) -> None:
        """Scraper exceeding timeout → timeout status."""
        import asyncio

        config = AppConfig(scraping=ScrapingConfig(timeout_seconds=1))

        async def slow_scrape() -> list[RawJobData]:
            await asyncio.sleep(10)
            return []

        scraper = FakeScraper("remote_io")
        scraper.scrape = slow_scrape  # type: ignore[assignment]

        orchestrator = ScraperOrchestrator(config, secrets, orch_session)
        with patch.object(orchestrator, "_build_enabled_scrapers", return_value=[scraper]):
            result = await orchestrator.run_all()

        assert result.results[0].status == "timeout"
        assert result.results[0].error_message is not None
        assert "timeout" in result.results[0].error_message.lower()

    @pytest.mark.asyncio
    async def test_structure_error_sets_blocked_status(self, config, secrets, orch_session) -> None:
        """ScraperStructureError → run_record.status = 'blocked'."""
        scraper = FakeScraper(
            "remote_io",
            error=ScraperStructureError("remote_io", "No job cards found on page 1"),
        )

        orchestrator = ScraperOrchestrator(config, secrets, orch_session)
        with patch.object(orchestrator, "_build_enabled_scrapers", return_value=[scraper]):
            result = await orchestrator.run_all()

        assert result.results[0].status == "blocked"
        assert "No job cards" in (result.results[0].error_message or "")

        # Verify DS9 record
        runs = orch_session.query(ScraperRun).all()
        assert len(runs) == 1
        assert runs[0].status == "blocked"
        assert runs[0].error_message is not None
