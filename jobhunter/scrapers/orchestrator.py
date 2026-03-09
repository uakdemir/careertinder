import asyncio
import logging
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy.orm import Session

from jobhunter.config.schema import AppConfig, SecretsConfig
from jobhunter.db.models import RawJobPosting, ScraperRun
from jobhunter.scrapers.base import BaseScraper, RawJobData
from jobhunter.scrapers.exceptions import ScraperError, ScraperStructureError
from jobhunter.scrapers.linkedin_apify import LinkedInApifyScraper
from jobhunter.scrapers.remote_io import RemoteIoScraper
from jobhunter.scrapers.remoterocketship import RemoteRocketshipScraper
from jobhunter.scrapers.wellfound_apify import WellfoundApifyScraper
from jobhunter.utils.hashing import normalize_and_hash


@dataclass
class ScraperRunResult:
    """Summary of one scraper's execution."""

    scraper_name: str
    status: str  # success | partial_success | failed | timeout | blocked
    jobs_found: int
    jobs_new: int
    jobs_updated: int
    pages_scraped: int
    duration_seconds: float
    error_message: str | None = None


@dataclass
class OrchestratorResult:
    """Summary of all scrapers' execution."""

    results: list[ScraperRunResult]
    total_jobs_found: int
    total_jobs_new: int


class ScraperOrchestrator:
    """C1 — Coordinates all scrapers with isolation, dedup, and audit logging."""

    def __init__(
        self,
        config: AppConfig,
        secrets: SecretsConfig,
        session: Session,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._session = session
        self._logger = logging.getLogger("jobhunter.scrapers.orchestrator")

    async def run_all(self) -> OrchestratorResult:
        """Run all enabled scrapers sequentially with failure isolation."""
        scrapers = self._build_enabled_scrapers()
        results: list[ScraperRunResult] = []

        for scraper in scrapers:
            result = await self._run_single_scraper(scraper)
            results.append(result)

        total_found = sum(r.jobs_found for r in results)
        total_new = sum(r.jobs_new for r in results)
        self._logger.info(
            "Orchestrator complete: %d scrapers, %d found, %d new",
            len(results),
            total_found,
            total_new,
        )
        return OrchestratorResult(results=results, total_jobs_found=total_found, total_jobs_new=total_new)

    async def run_single(self, scraper_name: str) -> ScraperRunResult:
        """Run a specific scraper by name."""
        scraper = self._build_scraper(scraper_name)
        return await self._run_single_scraper(scraper)

    async def _run_single_scraper(self, scraper: BaseScraper) -> ScraperRunResult:
        """Execute one scraper with isolation, dedup, and audit logging."""
        run_record = self._create_run_record(scraper.scraper_name)
        start_time = datetime.now(UTC)

        try:
            raw_jobs = await asyncio.wait_for(
                scraper.scrape(),
                timeout=self._config.scraping.timeout_seconds,
            )

            jobs_new, jobs_updated = self._persist_jobs(raw_jobs, run_record)

            run_record.status = "success"
            run_record.jobs_found = len(raw_jobs)
            run_record.jobs_new = jobs_new
            run_record.jobs_updated = jobs_updated

            result = ScraperRunResult(
                scraper_name=scraper.scraper_name,
                status="success",
                jobs_found=len(raw_jobs),
                jobs_new=jobs_new,
                jobs_updated=jobs_updated,
                pages_scraped=0,
                duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
            )

        except ScraperStructureError as e:
            self._logger.error("Scraper %s: structure change detected: %s", scraper.scraper_name, e)
            run_record.status = "blocked"
            run_record.error_message = str(e)
            result = self._error_result(scraper.scraper_name, "blocked", str(e), start_time)

        except TimeoutError:
            self._logger.error("Scraper %s timed out", scraper.scraper_name)
            run_record.status = "timeout"
            run_record.error_message = f"Exceeded {self._config.scraping.timeout_seconds}s timeout"
            result = self._error_result(scraper.scraper_name, "timeout", run_record.error_message, start_time)

        except ScraperError as e:
            self._logger.error("Scraper %s failed: %s", scraper.scraper_name, e)
            run_record.status = "failed"
            run_record.error_message = str(e)
            run_record.error_traceback = traceback.format_exc()
            result = self._error_result(scraper.scraper_name, "failed", str(e), start_time)

        except Exception as e:
            self._logger.error("Scraper %s unexpected error: %s", scraper.scraper_name, e, exc_info=True)
            run_record.status = "failed"
            run_record.error_message = f"Unexpected: {e}"
            run_record.error_traceback = traceback.format_exc()
            result = self._error_result(scraper.scraper_name, "failed", str(e), start_time)

        finally:
            run_record.completed_at = datetime.now(UTC)
            run_record.duration_seconds = (run_record.completed_at - start_time).total_seconds()
            self._session.commit()

        return result

    def _persist_jobs(self, raw_jobs: list[RawJobData], run_record: ScraperRun) -> tuple[int, int]:
        """Deduplicate and persist raw jobs. Returns (new_count, updated_count)."""
        new_count = 0
        updated_count = 0

        for job_data in raw_jobs:
            fingerprint = normalize_and_hash(job_data.company, job_data.title)

            existing = self._session.query(RawJobPosting).filter_by(fingerprint_hash=fingerprint).first()

            if existing:
                existing.scraped_at = datetime.now(UTC)
                updated_count += 1
                self._logger.debug(
                    "Duplicate: %s @ %s (fingerprint=%s)",
                    job_data.title,
                    job_data.company,
                    fingerprint[:12],
                )
            else:
                raw_posting = RawJobPosting(
                    source=job_data.source,
                    source_url=job_data.source_url,
                    title=job_data.title,
                    company=job_data.company,
                    salary_raw=job_data.salary_raw,
                    location_raw=job_data.location_raw,
                    description=job_data.description,
                    requirements=job_data.requirements,
                    raw_html=job_data.raw_html,
                    fingerprint_hash=fingerprint,
                    scraper_run_id=run_record.run_id,
                )
                self._session.add(raw_posting)
                new_count += 1

        self._session.flush()
        return new_count, updated_count

    def _create_run_record(self, scraper_name: str) -> ScraperRun:
        """Create a DS9 ScraperRun audit record."""
        run_record = ScraperRun(
            scraper_name=scraper_name,
            started_at=datetime.now(UTC),
            status="running",
            jobs_found=0,
            jobs_new=0,
            jobs_updated=0,
            pages_scraped=0,
        )
        self._session.add(run_record)
        self._session.flush()
        return run_record

    def _build_enabled_scrapers(self) -> list[BaseScraper]:
        """Instantiate all enabled scrapers from config."""
        scrapers: list[BaseScraper] = []
        cfg = self._config.scraping

        if cfg.remote_io.enabled:
            scrapers.append(RemoteIoScraper(cfg.remote_io, self._secrets))
        if cfg.remote_rocketship.enabled:
            scrapers.append(RemoteRocketshipScraper(cfg.remote_rocketship, self._secrets))
        if cfg.wellfound.enabled:
            scrapers.append(WellfoundApifyScraper(cfg.wellfound, self._secrets))
        if cfg.linkedin.enabled:
            scrapers.append(LinkedInApifyScraper(cfg.linkedin, self._secrets))

        self._logger.info("Enabled scrapers: %s", [s.scraper_name for s in scrapers])
        return scrapers

    def _build_scraper(self, name: str) -> BaseScraper:
        """Instantiate a single scraper by name."""
        cfg = self._config.scraping
        mapping: dict[str, tuple[type[BaseScraper], BaseModel]] = {
            "remote_io": (RemoteIoScraper, cfg.remote_io),
            "remote_rocketship": (RemoteRocketshipScraper, cfg.remote_rocketship),
            "wellfound": (WellfoundApifyScraper, cfg.wellfound),
            "linkedin": (LinkedInApifyScraper, cfg.linkedin),
        }
        if name not in mapping:
            raise ValueError(f"Unknown scraper: {name}. Valid: {list(mapping.keys())}")
        cls, scraper_cfg = mapping[name]
        return cls(scraper_cfg, self._secrets)

    def _error_result(
        self, name: str, status: str, message: str, start_time: datetime
    ) -> ScraperRunResult:
        return ScraperRunResult(
            scraper_name=name,
            status=status,
            jobs_found=0,
            jobs_new=0,
            jobs_updated=0,
            pages_scraped=0,
            duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
            error_message=message,
        )
