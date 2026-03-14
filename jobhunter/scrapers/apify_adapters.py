"""Adapter pattern for Apify actor response parsing.

Each Apify actor (Wellfound, LinkedIn) returns actor-specific field names.
Adapters decouple field mapping from scraper orchestration so that actor
schema changes only require updating the adapter, not scraper business logic.

Flow: Apify actor response (dict) -> Adapter.to_raw_job(item) -> RawJobData | None
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from jobhunter.scrapers.base import RawJobData

logger = logging.getLogger(__name__)


class ApifyItemAdapter(ABC):
    """Adapts Apify actor response items to RawJobData."""

    source_name: str  # e.g. "wellfound", "linkedin"

    @abstractmethod
    def to_raw_job(self, item: dict) -> RawJobData | None:
        """Convert one actor response item to RawJobData. None = skip."""

    def _first_of(self, item: dict, *keys: str) -> str | None:
        """Return first non-empty string value from multiple candidate keys."""
        for key in keys:
            val = item.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return None


class WellfoundItemAdapter(ApifyItemAdapter):
    """Adapts shahidirfan/wellfound-jobs-scraper output to RawJobData.

    Actual actor output fields:
      title, company, applyUrl, companyUrl, description_text, description_html,
      salary, location, remote, companySize, companyStage/fundingStage,
      techStack, jobType, primaryRoleTitle, postedDate (unix ts),
      acceptedRemoteLocationNames
    """

    source_name = "wellfound"

    def to_raw_job(self, item: dict) -> RawJobData | None:
        title = item.get("title")
        company = item.get("company")
        if not title or not company:
            logger.warning("Skipping Wellfound item with missing title/company")
            return None

        source_url = (
            self._first_of(item, "applyUrl", "url") or ""
        )
        if not source_url:
            logger.warning("Skipping Wellfound item with missing URL")
            return None

        # Description: prefer text, fall back to HTML, then generic
        description = (
            item.get("description_text")
            or item.get("description_html")
            or item.get("description")
            or ""
        )

        # Enrich with startup metadata
        description_parts = [description]
        startup_meta = self._extract_startup_metadata(item)
        if startup_meta:
            description_parts.append(f"\n\n--- Startup Info ---\n{startup_meta}")

        # Location: combine location + remote flag
        location = item.get("location") or ""
        remote_flag = item.get("remote")
        if remote_flag and str(remote_flag).lower() == "yes" and "remote" not in location.lower():
            if location:
                location = f"{location} (Remote)"
            else:
                location = "Remote"

        # Posted date: convert unix timestamp to ISO string
        posted_date_raw = self._parse_posted_date(item.get("postedDate"))

        return RawJobData(
            source="wellfound",
            source_url=source_url,
            title=title,
            company=company,
            description="\n".join(description_parts),
            salary_raw=item.get("salary"),
            location_raw=location or None,
            posted_date_raw=posted_date_raw,
        )

    def _extract_startup_metadata(self, item: dict) -> str | None:
        """Extract and format Wellfound startup-specific fields."""
        parts: list[str] = []
        if stage := item.get("companyStage") or item.get("fundingStage"):
            parts.append(f"Funding stage: {stage}")
        if size := item.get("companySize") or item.get("teamSize"):
            parts.append(f"Team size: {size}")
        if tech := item.get("techStack"):
            if isinstance(tech, list):
                tech = ", ".join(tech)
            parts.append(f"Tech stack: {tech}")
        return "\n".join(parts) if parts else None

    @staticmethod
    def _parse_posted_date(posted_ts: int | float | str | None) -> str | None:
        """Convert unix timestamp or string to ISO date string."""
        if posted_ts is None:
            return None
        if isinstance(posted_ts, (int, float)):
            return datetime.fromtimestamp(posted_ts, tz=UTC).strftime("%Y-%m-%d")
        if isinstance(posted_ts, str) and posted_ts.strip():
            return posted_ts.strip()
        return None


class LinkedInItemAdapter(ApifyItemAdapter):
    """Adapts valig/linkedin-jobs-scraper output to RawJobData.

    Valig output schema:
      id, url, title, location, companyName, companyUrl,
      recruiterName, recruiterUrl, experienceLevel, contractType,
      workType, sector, salary, applyType, applyUrl,
      postedTimeAgo, postedDate, applicationsCount,
      description, descriptionHtml
    """

    source_name = "linkedin"

    def to_raw_job(self, item: dict) -> RawJobData | None:
        title = item.get("title")
        company = item.get("companyName")
        if not title or not company:
            logger.warning(
                "Skipping LinkedIn item with missing title/company: %s",
                item.get("id"),
            )
            return None

        source_url = (item.get("url") or "").strip()
        if not source_url:
            logger.warning(
                "Skipping LinkedIn item with missing URL: %s", item.get("id")
            )
            return None

        # Prefer plain text description, fall back to HTML
        description = item.get("description") or item.get("descriptionHtml") or ""

        return RawJobData(
            source="linkedin",
            source_url=source_url,
            title=title,
            company=company,
            description=description,
            salary_raw=item.get("salary"),
            location_raw=item.get("location"),
            requirements=None,
            posted_date_raw=item.get("postedDate") or item.get("postedTimeAgo"),
            raw_html=item.get("descriptionHtml"),
        )
