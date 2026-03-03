import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel

from jobhunter.config.schema import SecretsConfig


@dataclass(frozen=True)
class RawJobData:
    """Scraper output DTO — not an ORM model.
    Mapped to DS1 RawJobPosting by the orchestrator.
    """

    source: str
    source_url: str
    title: str
    company: str
    description: str
    salary_raw: str | None = None
    location_raw: str | None = None
    requirements: str | None = None
    raw_html: str | None = None
    posted_date_raw: str | None = None


class BaseScraper(ABC):
    """Abstract base for all job scrapers (C2a-C2d)."""

    def __init__(self, config: BaseModel, secrets: SecretsConfig) -> None:
        self._config = config
        self._secrets = secrets
        self._logger = logging.getLogger(f"jobhunter.scrapers.{self.scraper_name}")

    @property
    @abstractmethod
    def scraper_name(self) -> str:
        """Return the canonical scraper name.
        One of: 'remote_io', 'remote_rocketship', 'wellfound', 'linkedin'.
        """

    @abstractmethod
    async def scrape(self) -> list[RawJobData]:
        """Execute the scrape and return raw job data.
        Raises ScraperError on unrecoverable failure.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Quick connectivity check. Returns True if the source is reachable."""
