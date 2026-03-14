"""Tests for D4: Wellfound Apify scraper (adapter delegation, multi-profile)."""

from unittest.mock import AsyncMock, patch

import pytest

from jobhunter.config.schema import WellfoundConfig, WellfoundSearchProfile
from jobhunter.scrapers.wellfound_apify import WellfoundApifyScraper, _SingleWellfoundScraper


class TestSingleWellfoundScraper:
    """Tests for the internal _SingleWellfoundScraper (Apify actor interface)."""

    @pytest.fixture
    def scraper(self, wellfound_config, secrets_with_apify):
        profile = wellfound_config.search_profiles[0]
        return _SingleWellfoundScraper(wellfound_config, secrets_with_apify, profile, max_results=50)

    def test_scraper_name(self, scraper) -> None:
        assert scraper.scraper_name == "wellfound"

    def test_build_actor_input(self, scraper) -> None:
        actor_input = scraper._build_actor_input()
        assert actor_input["keyword"] == "software engineer"
        assert actor_input["startUrl"] == "https://wellfound.com/jobs"
        assert actor_input["results_wanted"] == 50
        assert actor_input["proxyConfiguration"]["useApifyProxy"] is True
        assert "RESIDENTIAL" in actor_input["proxyConfiguration"]["apifyProxyGroups"]
        assert "location" not in actor_input

    def test_build_actor_input_with_custom_start_url(self, wellfound_config, secrets_with_apify) -> None:
        profile = WellfoundSearchProfile(
            label="Custom",
            search_keyword="devops",
            start_url="https://wellfound.com/jobs?role=devops",
        )
        scraper = _SingleWellfoundScraper(wellfound_config, secrets_with_apify, profile, max_results=10)
        actor_input = scraper._build_actor_input()
        assert actor_input["startUrl"] == "https://wellfound.com/jobs?role=devops"

    def test_max_results_override(self, wellfound_config, secrets_with_apify) -> None:
        """_max_results must equal per-profile allocation, not total budget."""
        profile = wellfound_config.search_profiles[0]
        scraper = _SingleWellfoundScraper(wellfound_config, secrets_with_apify, profile, max_results=25)
        assert scraper._max_results == 25  # Not 50 (the total)

    def test_parse_item_delegates_to_adapter(self, scraper) -> None:
        """_parse_item delegates to WellfoundItemAdapter.to_raw_job."""
        item = {
            "title": "Engineer",
            "company": "Co",
            "applyUrl": "https://wellfound.com/jobs/1",
            "description_text": "Build things.",
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert result.source == "wellfound"
        assert result.title == "Engineer"

    def test_parse_item_complete(self, scraper) -> None:
        item = {
            "title": "Head of Platform",
            "company": "StartupAlpha",
            "applyUrl": "https://wellfound.com/jobs/1",
            "description_text": "Lead platform team.",
            "salary": "$140K-$190K",
            "location": "San Francisco",
            "remote": "Yes",
            "postedDate": 1737072000,
            "companyStage": "Series B",
            "companySize": "51-100",
            "techStack": ["Python", "K8s"],
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert result.source == "wellfound"
        assert result.title == "Head of Platform"
        assert result.company == "StartupAlpha"
        assert result.salary_raw == "$140K-$190K"
        assert "Funding stage: Series B" in result.description
        assert "Team size: 51-100" in result.description
        assert "Tech stack: Python, K8s" in result.description
        # Remote flag appended since "remote" not in location
        assert "(Remote)" in result.location_raw  # type: ignore[operator]
        # Unix timestamp converted to ISO
        assert result.posted_date_raw == "2025-01-17"

    def test_parse_item_no_startup_metadata(self, scraper) -> None:
        item = {
            "title": "Engineer",
            "company": "PlainCo",
            "applyUrl": "https://wellfound.com/jobs/3",
            "description_text": "Build things.",
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert "--- Startup Info ---" not in result.description

    def test_parse_item_missing_url(self, scraper) -> None:
        item = {"title": "Engineer", "company": "Co", "description_text": "Build things."}
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_item_empty_url(self, scraper) -> None:
        item = {"title": "Engineer", "company": "Co", "applyUrl": "", "description_text": "Build things."}
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_item_missing_required(self, scraper) -> None:
        item = {"applyUrl": "https://wellfound.com/jobs/invalid", "description_text": "No title or company."}
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_items_from_fixture(self, scraper, wellfound_apify_items) -> None:
        results = [scraper._parse_item(item) for item in wellfound_apify_items]
        valid = [r for r in results if r is not None]
        assert len(valid) == 2  # 2 valid, 1 skipped (missing title+company)
        assert valid[0].title == "Head of Platform"
        assert valid[1].title == "Senior Backend Developer"

    def test_parse_item_url_fallback(self, scraper) -> None:
        """Falls back to 'url' when 'applyUrl' is missing."""
        item = {
            "title": "Dev",
            "company": "Co",
            "url": "https://wellfound.com/jobs/fallback",
            "description_text": "Fallback URL.",
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert result.source_url == "https://wellfound.com/jobs/fallback"


class TestWellfoundApifyScraper:
    """Tests for the multi-profile Wellfound orchestrator."""

    @pytest.fixture
    def scraper(self, wellfound_config, secrets_with_apify):
        return WellfoundApifyScraper(wellfound_config, secrets_with_apify)

    def test_scraper_name(self, scraper) -> None:
        assert scraper.scraper_name == "wellfound"

    def test_budget_allocation_single_profile(self) -> None:
        profiles = [WellfoundSearchProfile(label="A", search_keyword="eng", weight=1)]
        budget = WellfoundApifyScraper._allocate_budget(profiles, 100)
        assert budget == [100]

    def test_budget_allocation_weighted(self) -> None:
        profiles = [
            WellfoundSearchProfile(label="High", search_keyword="eng", weight=3),
            WellfoundSearchProfile(label="Low", search_keyword="arch", weight=1),
        ]
        budget = WellfoundApifyScraper._allocate_budget(profiles, 100)
        assert budget == [75, 25]

    def test_budget_allocation_invariant(self) -> None:
        """sum(budgets) <= total must always hold."""
        profiles = [
            WellfoundSearchProfile(label="A", search_keyword="eng", weight=1),
            WellfoundSearchProfile(label="B", search_keyword="arch", weight=1),
            WellfoundSearchProfile(label="C", search_keyword="mgr", weight=1),
        ]
        budget = WellfoundApifyScraper._allocate_budget(profiles, 10)
        assert sum(budget) <= 10
        assert len(budget) == 3

    def test_budget_fewer_than_profiles(self) -> None:
        """max_results < len(profiles) -> some get 0."""
        profiles = [
            WellfoundSearchProfile(label=f"P{i}", search_keyword=f"kw{i}", weight=1)
            for i in range(5)
        ]
        budget = WellfoundApifyScraper._allocate_budget(profiles, 2)
        assert sum(budget) == 2
        assert budget.count(0) == 3  # 3 of 5 get 0

    def test_budget_empty_profiles(self) -> None:
        budget = WellfoundApifyScraper._allocate_budget([], 100)
        assert budget == []

    @pytest.mark.asyncio
    async def test_scrape_no_profiles(self, secrets_with_apify) -> None:
        config = WellfoundConfig(enabled=True, max_results=50, search_profiles=[])
        scraper = WellfoundApifyScraper(config, secrets_with_apify)
        results = await scraper.scrape()
        assert results == []

    @pytest.mark.asyncio
    async def test_scrape_single_profile(self, scraper) -> None:
        from jobhunter.scrapers.base import RawJobData

        mock_results = [
            RawJobData(
                source="wellfound",
                source_url="https://wellfound.com/jobs/1",
                title="Eng",
                company="Co",
                description="Build things",
            ),
        ]

        with patch.object(_SingleWellfoundScraper, "scrape", new_callable=AsyncMock, return_value=mock_results):
            results = await scraper.scrape()

        assert len(results) == 1
        assert results[0].title == "Eng"

    @pytest.mark.asyncio
    async def test_scrape_cross_profile_dedup(self, secrets_with_apify) -> None:
        from jobhunter.scrapers.base import RawJobData

        profiles = [
            WellfoundSearchProfile(label="P1", search_keyword="eng", weight=1),
            WellfoundSearchProfile(label="P2", search_keyword="arch", weight=1),
        ]
        config = WellfoundConfig(enabled=True, max_results=100, search_profiles=profiles)
        scraper = WellfoundApifyScraper(config, secrets_with_apify)

        shared_job = RawJobData(
            source="wellfound",
            source_url="https://wellfound.com/jobs/999",
            title="Shared",
            company="SharedCo",
            description="Appears in both",
        )
        unique_job = RawJobData(
            source="wellfound",
            source_url="https://wellfound.com/jobs/888",
            title="Unique",
            company="UniqueCo",
            description="Only in P2",
        )

        call_count = 0

        async def mock_scrape(self_inner: _SingleWellfoundScraper) -> list[RawJobData]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [shared_job]
            return [shared_job, unique_job]

        with patch.object(_SingleWellfoundScraper, "scrape", mock_scrape):
            results = await scraper.scrape()

        assert len(results) == 2
        urls = {r.source_url for r in results}
        assert "https://wellfound.com/jobs/999" in urls
        assert "https://wellfound.com/jobs/888" in urls

    @pytest.mark.asyncio
    async def test_scrape_profile_failure_isolation(self, secrets_with_apify) -> None:
        from jobhunter.scrapers.base import RawJobData
        from jobhunter.scrapers.exceptions import ScraperError

        profiles = [
            WellfoundSearchProfile(label="Fails", search_keyword="fail", weight=1),
            WellfoundSearchProfile(label="Works", search_keyword="work", weight=1),
        ]
        config = WellfoundConfig(enabled=True, max_results=100, search_profiles=profiles)
        scraper = WellfoundApifyScraper(config, secrets_with_apify)

        good_job = RawJobData(
            source="wellfound",
            source_url="https://wellfound.com/jobs/555",
            title="Good",
            company="GoodCo",
            description="Working",
        )

        call_count = 0

        async def mock_scrape(self_inner: _SingleWellfoundScraper) -> list[RawJobData]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ScraperError("wellfound", "Actor failed")
            return [good_job]

        with patch.object(_SingleWellfoundScraper, "scrape", mock_scrape):
            results = await scraper.scrape()

        assert len(results) == 1
        assert results[0].title == "Good"
