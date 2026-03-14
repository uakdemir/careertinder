"""C2c — Wellfound (AngelList) job scraper via Apify REST API.

Supports multi-profile search: each WellfoundSearchProfile is run as a
separate actor invocation with weight-based budget allocation.

Dedup is handled at two levels:
  1. In-scraper: track seen job URLs across profiles.
  2. In-orchestrator: fingerprint_hash dedup against the DB (existing flow).
"""

import logging

from pydantic import BaseModel

from jobhunter.config.schema import SecretsConfig, WellfoundConfig, WellfoundSearchProfile
from jobhunter.scrapers.apify_adapters import WellfoundItemAdapter
from jobhunter.scrapers.apify_base import ApifyBaseScraper
from jobhunter.scrapers.base import BaseScraper, RawJobData
from jobhunter.scrapers.exceptions import ScraperError


class _SingleWellfoundScraper(ApifyBaseScraper):
    """Internal: runs one Apify actor invocation for a single search profile.

    Overrides self._max_results with the per-profile allocation so both
    the actor input AND the dataset fetch limit reflect the profile budget.
    """

    def __init__(
        self,
        config: WellfoundConfig,
        secrets: SecretsConfig,
        profile: WellfoundSearchProfile,
        max_results: int,
    ) -> None:
        self._profile = profile
        self._adapter = WellfoundItemAdapter()
        super().__init__(config, secrets)
        # Override inherited total budget with per-profile allocation
        self._max_results = max_results

    @property
    def scraper_name(self) -> str:
        return "wellfound"

    def _build_actor_input(self) -> dict:
        """Build input for shahidirfan/wellfound-jobs-scraper actor.

        The actor requires USA residential proxies to extract data from Wellfound.
        """
        actor_input: dict = {
            "keyword": self._profile.search_keyword,
            "startUrl": self._profile.start_url or "https://wellfound.com/jobs",
            "results_wanted": self._max_results,
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
            },
        }
        return actor_input

    def _parse_item(self, item: dict) -> RawJobData | None:
        """Delegate to WellfoundItemAdapter for field mapping."""
        return self._adapter.to_raw_job(item)


class WellfoundApifyScraper(BaseScraper):
    """C2c — Wellfound job scraper with multi-profile support.

    Iterates through configured search profiles, allocating max_results
    budget by weight. Deduplicates across profiles by job URL.
    """

    def __init__(self, config: BaseModel, secrets: SecretsConfig) -> None:
        self._wellfound_config: WellfoundConfig = config  # type: ignore[assignment]
        self._secrets = secrets
        self._logger = logging.getLogger("jobhunter.scrapers.wellfound")

    @property
    def scraper_name(self) -> str:
        return "wellfound"

    async def scrape(self) -> list[RawJobData]:
        """Run all search profiles and return deduplicated results."""
        profiles = self._wellfound_config.search_profiles
        if not profiles:
            self._logger.warning("No search profiles configured for Wellfound")
            return []

        budgets = self._allocate_budget(profiles, self._wellfound_config.max_results)
        seen_urls: set[str] = set()
        all_results: list[RawJobData] = []

        for i, profile in enumerate(profiles):
            budget = budgets[i]
            if budget == 0:
                self._logger.info("Skipping profile '%s' (budget=0)", profile.label)
                continue

            self._logger.info(
                "Running profile '%s' (budget=%d)", profile.label, budget
            )

            try:
                scraper = _SingleWellfoundScraper(
                    self._wellfound_config, self._secrets, profile, budget
                )
                profile_results = await scraper.scrape()

                new_results = []
                for job in profile_results:
                    if job.source_url in seen_urls:
                        self._logger.debug(
                            "Cross-profile duplicate: %s (profile: %s)",
                            job.source_url, profile.label,
                        )
                        continue
                    seen_urls.add(job.source_url)
                    new_results.append(job)

                all_results.extend(new_results)
                self._logger.info(
                    "Profile '%s': %d results (%d after dedup)",
                    profile.label, len(profile_results), len(new_results),
                )
            except ScraperError as e:
                self._logger.error("Profile '%s' failed: %s", profile.label, e)
                # Continue with other profiles (failure isolation)

        self._logger.info(
            "Wellfound total: %d results from %d profiles",
            len(all_results), len(profiles),
        )
        return all_results

    async def health_check(self) -> bool:
        """Check Apify API connectivity."""
        if not self._wellfound_config.search_profiles:
            return False
        scraper = _SingleWellfoundScraper(
            self._wellfound_config,
            self._secrets,
            self._wellfound_config.search_profiles[0],
            max_results=1,
        )
        return await scraper.health_check()

    @staticmethod
    def _allocate_budget(
        profiles: list[WellfoundSearchProfile], total: int
    ) -> list[int]:
        """Distribute max_results across profiles by weight (index-parallel).

        Invariant: sum(result) <= total.
        Algorithm: floor proportional shares, then distribute remainder
        one-at-a-time to profiles with largest fractional part.
        """
        if not profiles:
            return []
        total_weight = sum(p.weight for p in profiles)
        if total_weight == 0:
            return [0] * len(profiles)

        raw = [(total * p.weight / total_weight) for p in profiles]
        floors = [int(r) for r in raw]
        remainders = [(r - f, i) for i, (r, f) in enumerate(zip(raw, floors, strict=True))]

        leftover = total - sum(floors)
        remainders.sort(key=lambda x: x[0], reverse=True)
        for j in range(leftover):
            floors[remainders[j][1]] += 1

        return floors
