"""C2d — LinkedIn job scraper via valig Apify actor.

Supports multi-profile search: each LinkedInSearchProfile is run as a
separate actor invocation with weight-based budget allocation.

The valig actor (valig/linkedin-jobs-scraper) returns full job details
at ~$0.32/1k jobs (3x cheaper than HarvestAPI).

Dedup is handled at two levels:
  1. In-scraper: track seen LinkedIn job IDs across profiles to avoid
     returning the same job from overlapping searches.
  2. In-orchestrator: fingerprint_hash dedup against the DB (existing flow).
"""

import logging

from pydantic import BaseModel

from jobhunter.config.schema import LinkedInConfig, LinkedInSearchProfile, SecretsConfig
from jobhunter.scrapers.apify_adapters import LinkedInItemAdapter
from jobhunter.scrapers.apify_base import ApifyBaseScraper
from jobhunter.scrapers.base import BaseScraper, RawJobData
from jobhunter.scrapers.exceptions import ScraperError

# Mapping from our config values to valig actor values (numeric codes)
_WORKPLACE_MAP: dict[str, str] = {
    "office": "1",
    "remote": "2",
    "hybrid": "3",
}

_EXPERIENCE_MAP: dict[str, str] = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid-senior": "4",
    "director": "5",
    "executive": "6",
}

_DATE_POSTED_MAP: dict[str, str] = {
    "1h": "r86400",
    "24h": "r86400",
    "week": "r604800",
    "month": "r2592000",
}

_CONTRACT_TYPE_MAP: dict[str, str] = {
    "full-time": "F",
    "part-time": "P",
    "contract": "C",
    "temporary": "T",
    "internship": "I",
    "other": "O",
}


class _SingleProfileScraper(ApifyBaseScraper):
    """Internal: runs one valig actor invocation for a single search profile."""

    def __init__(
        self,
        config: LinkedInConfig,
        secrets: SecretsConfig,
        profile: LinkedInSearchProfile,
        max_items: int,
    ) -> None:
        super().__init__(config, secrets)
        self._profile = profile
        self._adapter = LinkedInItemAdapter()
        self._max_items = max_items
        # Override inherited total budget with per-profile allocation
        self._max_results = max_items

    @property
    def scraper_name(self) -> str:
        return "linkedin"

    def _build_actor_input(self) -> dict:
        """Build input for valig/linkedin-jobs-scraper actor.

        Valig input schema:
          - title: string (single search term)
          - location: string (single location)
          - remote: array ["On-site", "Remote", "Hybrid"]
          - experienceLevel: array ["Internship", "Entry level", "Associate", "Mid-Senior", "Director", "Executive"]
          - contractType: array ["Full-time", "Part-time", "Contract", "Temporary", "Internship", "Other"]
          - datePosted: enum "Any time" | "Past month" | "Past week" | "Past 24 hours"
          - limit: int 1-1000
          - urlParam: array of {key, value} for advanced LinkedIn filters
        """
        # Join multiple job titles with OR for broader search
        title = " OR ".join(self._profile.job_titles) if self._profile.job_titles else ""

        # Use first location or empty for worldwide
        location = self._profile.locations[0] if self._profile.locations else ""

        actor_input: dict = {
            "title": title,
            "location": location,
            "limit": self._max_items,
        }

        # Map workplace_type to valig's remote field
        if self._profile.workplace_type:
            remote_values = [
                _WORKPLACE_MAP[wt]
                for wt in self._profile.workplace_type
                if wt in _WORKPLACE_MAP
            ]
            if remote_values:
                actor_input["remote"] = remote_values

        # Map experience_level
        if self._profile.experience_level:
            exp_values = [
                _EXPERIENCE_MAP[exp]
                for exp in self._profile.experience_level
                if exp in _EXPERIENCE_MAP
            ]
            if exp_values:
                actor_input["experienceLevel"] = exp_values

        # Map contract_type to valig codes
        if self._profile.contract_type:
            contract_values = [
                _CONTRACT_TYPE_MAP[ct.lower()]
                for ct in self._profile.contract_type
                if ct.lower() in _CONTRACT_TYPE_MAP
            ]
            if contract_values:
                actor_input["contractType"] = contract_values

        # Map posted_limit to datePosted
        if self._profile.posted_limit and self._profile.posted_limit in _DATE_POSTED_MAP:
            actor_input["datePosted"] = _DATE_POSTED_MAP[self._profile.posted_limit]

        # Build urlParam for advanced filters (job functions, geoId)
        url_params = self._build_url_params()
        if url_params:
            actor_input["urlParam"] = url_params

        return actor_input

    def _build_url_params(self) -> list[dict[str, str]]:
        """Build urlParam array for advanced LinkedIn filters.

        Used for filters not natively supported by valig:
          - f_F: Job functions (it, eng, prjm, etc.)
          - geoId: LinkedIn geographic targeting
        """
        params: list[dict[str, str]] = []

        # Job functions (f_F)
        if self._profile.job_functions:
            params.append({
                "key": "f_F",
                "value": ",".join(self._profile.job_functions),
            })

        # Geographic targeting (geoId)
        if self._profile.geo_id:
            params.append({
                "key": "geoId",
                "value": self._profile.geo_id,
            })

        return params

    def _parse_item(self, item: dict) -> RawJobData | None:
        """Delegate to LinkedInItemAdapter for field mapping."""
        return self._adapter.to_raw_job(item)


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

        budgets = self._allocate_budget(profiles, self._linkedin_config.max_results)
        seen_ids: set[str] = set()
        all_results: list[RawJobData] = []

        for i, profile in enumerate(profiles):
            max_items = budgets[i]
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
    ) -> list[int]:
        """Distribute max_results across profiles by weight (index-parallel).

        Invariant: sum(result) <= total_budget.
        Algorithm: floor proportional shares, then distribute remainder
        one-at-a-time to profiles with largest fractional part.
        """
        if not profiles:
            return []
        total_weight = sum(p.weight for p in profiles)
        if total_weight == 0:
            return [0] * len(profiles)

        raw = [(total_budget * p.weight / total_weight) for p in profiles]
        floors = [int(r) for r in raw]
        remainders = [(r - f, i) for i, (r, f) in enumerate(zip(raw, floors, strict=True))]

        leftover = total_budget - sum(floors)
        remainders.sort(key=lambda x: x[0], reverse=True)
        for j in range(leftover):
            floors[remainders[j][1]] += 1

        return floors

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
