from jobhunter.scrapers.apify_base import ApifyBaseScraper
from jobhunter.scrapers.base import RawJobData


class WellfoundApifyScraper(ApifyBaseScraper):
    """C2c — Wellfound (AngelList) job scraper via Apify REST API."""

    @property
    def scraper_name(self) -> str:
        return "wellfound"

    def _build_actor_input(self) -> dict:
        """Build input for shahidirfan/wellfound-jobs-scraper actor."""
        return {
            "keyword": self._config.search_keyword,  # type: ignore[attr-defined]
            "location": self._config.location_filter,  # type: ignore[attr-defined]
            "maxItems": self._max_results,
        }

    def _parse_item(self, item: dict) -> RawJobData | None:
        """Parse a Wellfound Apify result into RawJobData.

        Wellfound provides startup-specific data (funding stage, team size)
        which we capture in the description for downstream extraction in M2.
        """
        title = item.get("title") or item.get("jobTitle")
        company = item.get("companyName") or item.get("company")
        if not title or not company:
            self._logger.warning("Skipping Wellfound item with missing title/company")
            return None

        source_url = (item.get("url") or "").strip()
        if not source_url:
            self._logger.warning("Skipping Wellfound item with missing URL")
            return None

        # Build enriched description with startup metadata
        description_parts = [item.get("description", "")]
        startup_meta = self._extract_startup_metadata(item)
        if startup_meta:
            description_parts.append(f"\n\n--- Startup Info ---\n{startup_meta}")

        return RawJobData(
            source="wellfound",
            source_url=source_url,
            title=title,
            company=company,
            description="\n".join(description_parts),
            salary_raw=item.get("salary") or item.get("compensation"),
            location_raw=item.get("location"),
            requirements=item.get("requirements"),
            posted_date_raw=item.get("postedAt"),
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
