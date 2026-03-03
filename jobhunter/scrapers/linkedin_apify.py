"""C2d — LinkedIn job scraper via HarvestAPI Apify actor.

Supports multi-profile search: each LinkedInSearchProfile is run as a
separate actor invocation with weight-based budget allocation.

The actor returns full job details in one pass (~$1/1k jobs).
Dedup is handled at two levels:
  1. In-scraper: track seen LinkedIn job IDs across profiles to avoid
     returning the same job from overlapping searches.
  2. In-orchestrator: fingerprint_hash dedup against the DB (existing flow).
"""

import logging

from pydantic import BaseModel

from jobhunter.config.schema import LinkedInConfig, LinkedInSearchProfile, SecretsConfig
from jobhunter.scrapers.apify_base import ApifyBaseScraper
from jobhunter.scrapers.base import BaseScraper, RawJobData
from jobhunter.scrapers.exceptions import ScraperError


class _SingleProfileScraper(ApifyBaseScraper):
    """Internal: runs one HarvestAPI actor invocation for a single search profile."""

    def __init__(
        self,
        config: LinkedInConfig,
        secrets: SecretsConfig,
        profile: LinkedInSearchProfile,
        max_items: int,
    ) -> None:
        super().__init__(config, secrets)
        self._profile = profile
        self._max_items = max_items

    @property
    def scraper_name(self) -> str:
        return "linkedin"

    def _build_actor_input(self) -> dict:
        """Build input for harvestapi/linkedin-job-search actor."""
        actor_input: dict = {
            "jobTitles": self._profile.job_titles,
            "maxItems": self._max_items,
            "sortBy": "date",
        }

        if self._profile.locations:
            actor_input["locations"] = self._profile.locations

        if self._profile.workplace_type:
            actor_input["workplaceType"] = self._profile.workplace_type

        if self._profile.experience_level:
            actor_input["experienceLevel"] = self._profile.experience_level

        if self._profile.salary:
            actor_input["salary"] = [self._profile.salary]

        if self._profile.posted_limit:
            actor_input["postedLimit"] = self._profile.posted_limit

        return actor_input

    def _parse_item(self, item: dict) -> RawJobData | None:
        """Parse a HarvestAPI result into RawJobData.

        HarvestAPI output uses nested objects:
          - company.name (not flat companyName)
          - linkedinUrl (not url)
          - descriptionText (not description)
          - salary.text / salary.min / salary.max
          - location.linkedinText
        """
        title = item.get("title")
        company_obj = item.get("company") or {}
        company = company_obj.get("name") if isinstance(company_obj, dict) else None
        if not title or not company:
            self._logger.warning(
                "Skipping item with missing title/company: %s", item.get("id")
            )
            return None

        source_url = (item.get("linkedinUrl") or "").strip()
        if not source_url:
            self._logger.warning(
                "Skipping LinkedIn item with missing URL: %s", item.get("id")
            )
            return None

        # Extract salary — structured object with text, min, max, currency
        salary_raw = self._extract_salary(item.get("salary"))

        # Extract location — structured object with linkedinText
        location_obj = item.get("location") or {}
        location_raw = (
            location_obj.get("linkedinText")
            if isinstance(location_obj, dict)
            else str(location_obj) if location_obj else None
        )

        # Prefer plain text description, fall back to HTML
        description = item.get("descriptionText") or item.get("descriptionHtml") or ""

        return RawJobData(
            source="linkedin",
            source_url=source_url,
            title=title,
            company=company,
            description=description,
            salary_raw=salary_raw,
            location_raw=location_raw,
            requirements=None,
            posted_date_raw=item.get("postedDate"),
            raw_html=item.get("descriptionHtml"),
        )

    @staticmethod
    def _extract_salary(salary_obj: object) -> str | None:
        """Extract a salary string from the HarvestAPI salary object."""
        if salary_obj is None:
            return None
        if isinstance(salary_obj, str):
            return salary_obj
        if isinstance(salary_obj, dict):
            # Prefer the display text
            if text := salary_obj.get("text"):
                return str(text)
            # Fall back to min-max range
            sal_min = salary_obj.get("min")
            sal_max = salary_obj.get("max")
            currency = salary_obj.get("currency", "USD")
            if sal_min and sal_max:
                return f"{currency} {sal_min:,} - {sal_max:,}"
            if sal_min:
                return f"{currency} {sal_min:,}+"
        return None


class LinkedInApifyScraper(BaseScraper):
    """C2d — LinkedIn job scraper with multi-profile support.

    Iterates through configured search profiles, allocating max_results
    budget by weight. Deduplicates across profiles by LinkedIn job ID.
    """

    def __init__(self, config: BaseModel, secrets: SecretsConfig) -> None:
        self._linkedin_config: LinkedInConfig = config  # type: ignore[assignment]
        self._secrets = secrets
        self._logger = logging.getLogger("jobhunter.scrapers.linkedin")

    @property
    def scraper_name(self) -> str:
        return "linkedin"

    async def scrape(self) -> list[RawJobData]:
        """Run all search profiles and return deduplicated results."""
        profiles = self._linkedin_config.search_profiles
        if not profiles:
            self._logger.warning("No search profiles configured for LinkedIn")
            return []

        budget_map = self._allocate_budget(profiles, self._linkedin_config.max_results)
        seen_ids: set[str] = set()
        all_results: list[RawJobData] = []

        for profile in profiles:
            max_items = budget_map[profile.label]
            self._logger.info(
                "Running profile '%s' (budget=%d)", profile.label, max_items
            )

            try:
                scraper = _SingleProfileScraper(
                    self._linkedin_config, self._secrets, profile, max_items
                )
                profile_results = await scraper.scrape()

                # Cross-profile dedup by LinkedIn job ID (extracted from URL)
                new_results = []
                for job in profile_results:
                    job_id = self._extract_job_id(job.source_url)
                    if job_id and job_id in seen_ids:
                        self._logger.debug("Cross-profile duplicate: %s", job_id)
                        continue
                    if job_id:
                        seen_ids.add(job_id)
                    new_results.append(job)

                all_results.extend(new_results)
                self._logger.info(
                    "Profile '%s': %d results (%d after cross-profile dedup)",
                    profile.label,
                    len(profile_results),
                    len(new_results),
                )
            except ScraperError as e:
                self._logger.error("Profile '%s' failed: %s", profile.label, e)
                # Continue with other profiles (failure isolation)

        self._logger.info(
            "LinkedIn total: %d results from %d profiles",
            len(all_results),
            len(profiles),
        )
        return all_results

    async def health_check(self) -> bool:
        """Check Apify API connectivity."""
        if not self._linkedin_config.search_profiles:
            return False
        # Delegate to the base Apify health check
        scraper = _SingleProfileScraper(
            self._linkedin_config,
            self._secrets,
            self._linkedin_config.search_profiles[0],
            max_items=1,
        )
        return await scraper.health_check()

    @staticmethod
    def _allocate_budget(
        profiles: list[LinkedInSearchProfile], total_budget: int
    ) -> dict[str, int]:
        """Distribute max_results across profiles proportionally by weight.

        Each profile gets at least 1 result if total_budget >= len(profiles).
        """
        total_weight = sum(p.weight for p in profiles)
        budget: dict[str, int] = {}
        for profile in profiles:
            share = max(1, round(total_budget * profile.weight / total_weight))
            budget[profile.label] = share
        return budget

    @staticmethod
    def _extract_job_id(url: str) -> str | None:
        """Extract LinkedIn job ID from a URL like https://www.linkedin.com/jobs/view/1234567."""
        try:
            parts = url.rstrip("/").split("/")
            # URL pattern: .../jobs/view/{id}
            if "view" in parts:
                idx = parts.index("view")
                if idx + 1 < len(parts):
                    candidate = parts[idx + 1].split("?")[0]
                    if candidate.isdigit():
                        return candidate
        except (ValueError, IndexError):
            pass
        return None
