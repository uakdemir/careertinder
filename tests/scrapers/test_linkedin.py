"""Tests for LinkedIn valig scraper (multi-profile, structured queries)."""

from unittest.mock import AsyncMock, patch

import pytest

from jobhunter.config.schema import LinkedInConfig, LinkedInSearchProfile
from jobhunter.scrapers.linkedin_apify import LinkedInApifyScraper, _SingleProfileScraper


class TestSingleProfileScraper:
    """Tests for the internal _SingleProfileScraper (valig actor interface)."""

    @pytest.fixture
    def profile(self, linkedin_search_profile):
        return linkedin_search_profile

    @pytest.fixture
    def scraper(self, linkedin_config, secrets_with_apify, profile):
        return _SingleProfileScraper(linkedin_config, secrets_with_apify, profile, max_items=50)

    def test_scraper_name(self, scraper) -> None:
        assert scraper.scraper_name == "linkedin"

    def test_build_actor_input(self, scraper) -> None:
        """Test mapping from our config format to valig actor input."""
        actor_input = scraper._build_actor_input()
        # valig uses single title string (we join with OR)
        assert actor_input["title"] == "Software Architect"
        assert actor_input["limit"] == 50
        # valig uses "location" as string
        assert actor_input["location"] == "Remote"
        # valig uses "remote" array with numeric codes (1=On-site, 2=Remote, 3=Hybrid)
        assert actor_input["remote"] == ["2"]
        # valig uses "experienceLevel" with numeric codes (4=Mid-Senior, 5=Director)
        assert actor_input["experienceLevel"] == ["4", "5"]
        # No salary/datePosted set in fixture
        assert "salary" not in actor_input  # valig doesn't support salary filter
        assert "datePosted" not in actor_input

    def test_build_actor_input_with_posted_limit(self, linkedin_config, secrets_with_apify) -> None:
        """Test datePosted mapping."""
        profile = LinkedInSearchProfile(
            label="Test",
            job_titles=["Engineer"],
            posted_limit="week",
        )
        scraper = _SingleProfileScraper(linkedin_config, secrets_with_apify, profile, max_items=10)
        actor_input = scraper._build_actor_input()
        # salary is NOT in actor_input (valig doesn't support it)
        assert "salary" not in actor_input
        # posted_limit maps to datePosted (r604800 = past week in seconds)
        assert actor_input["datePosted"] == "r604800"

    def test_build_actor_input_multiple_titles(self, linkedin_config, secrets_with_apify) -> None:
        """Multiple job titles joined with OR."""
        profile = LinkedInSearchProfile(
            label="Test",
            job_titles=["Engineering Manager", "Director of Engineering"],
        )
        scraper = _SingleProfileScraper(linkedin_config, secrets_with_apify, profile, max_items=10)
        actor_input = scraper._build_actor_input()
        assert actor_input["title"] == "Engineering Manager OR Director of Engineering"

    def test_parse_item_complete(self, scraper) -> None:
        """Test parsing valig output format."""
        item = {
            "id": "4227647589",
            "title": "VP of Engineering",
            "url": "https://www.linkedin.com/jobs/view/4227647589",
            "description": "Lead engineering org.",
            "descriptionHtml": "<p>Lead engineering org.</p>",
            "companyName": "MegaTech",
            "companyUrl": "https://www.linkedin.com/company/megatech",
            "salary": "$180K-$250K",
            "location": "Remote - Worldwide",
            "postedDate": "2025-01-15",
            "postedTimeAgo": "2 days ago",
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert result.source == "linkedin"
        assert result.title == "VP of Engineering"
        assert result.company == "MegaTech"
        assert result.salary_raw == "$180K-$250K"
        assert result.location_raw == "Remote - Worldwide"
        assert result.posted_date_raw == "2025-01-15"
        assert result.source_url == "https://www.linkedin.com/jobs/view/4227647589"
        assert result.raw_html == "<p>Lead engineering org.</p>"

    def test_parse_item_null_salary(self, scraper) -> None:
        """Null salary is preserved."""
        item = {
            "title": "Architect",
            "url": "https://www.linkedin.com/jobs/view/123",
            "description": "Build things.",
            "companyName": "Co",
            "salary": None,
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert result.salary_raw is None

    def test_parse_item_posted_time_ago_fallback(self, scraper) -> None:
        """Falls back to postedTimeAgo if postedDate is missing."""
        item = {
            "title": "Architect",
            "url": "https://www.linkedin.com/jobs/view/123",
            "description": "Build things.",
            "companyName": "Co",
            "postedTimeAgo": "3 days ago",
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert result.posted_date_raw == "3 days ago"

    def test_parse_item_missing_title(self, scraper) -> None:
        item = {
            "companyName": "SomeCo",
            "url": "https://www.linkedin.com/jobs/view/123",
        }
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_item_missing_company(self, scraper) -> None:
        item = {
            "title": "Engineer",
            "url": "https://www.linkedin.com/jobs/view/123",
            "companyName": None,
        }
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_item_missing_url(self, scraper) -> None:
        item = {
            "title": "Architect",
            "companyName": "Co",
            "description": "Build things.",
        }
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_item_empty_url(self, scraper) -> None:
        item = {
            "title": "Architect",
            "companyName": "Co",
            "url": "",
            "description": "Build things.",
        }
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_items_from_fixture(self, scraper, linkedin_apify_items) -> None:
        results = [scraper._parse_item(item) for item in linkedin_apify_items]
        valid = [r for r in results if r is not None]
        assert len(valid) == 2  # 2 valid, 2 skipped (missing title, missing company)
        assert valid[0].title == "VP of Engineering"
        assert valid[1].title == "Solutions Architect"
        assert valid[1].salary_raw is None  # salary was null in fixture


class TestLinkedInApifyScraper:
    """Tests for the multi-profile LinkedIn scraper."""

    @pytest.fixture
    def scraper(self, linkedin_config, secrets_with_apify):
        return LinkedInApifyScraper(linkedin_config, secrets_with_apify)

    def test_scraper_name(self, scraper) -> None:
        assert scraper.scraper_name == "linkedin"

    def test_budget_allocation_single_profile(self) -> None:
        profiles = [
            LinkedInSearchProfile(label="A", job_titles=["Eng"], weight=1),
        ]
        budget = LinkedInApifyScraper._allocate_budget(profiles, 100)
        assert budget == [100]

    def test_budget_allocation_equal_weights(self) -> None:
        profiles = [
            LinkedInSearchProfile(label="A", job_titles=["Eng"], weight=1),
            LinkedInSearchProfile(label="B", job_titles=["Arch"], weight=1),
        ]
        budget = LinkedInApifyScraper._allocate_budget(profiles, 100)
        assert budget == [50, 50]

    def test_budget_allocation_weighted(self) -> None:
        profiles = [
            LinkedInSearchProfile(label="High", job_titles=["Eng"], weight=3),
            LinkedInSearchProfile(label="Low", job_titles=["Arch"], weight=1),
        ]
        budget = LinkedInApifyScraper._allocate_budget(profiles, 100)
        assert budget == [75, 25]

    def test_budget_allocation_invariant(self) -> None:
        """sum(budgets) <= total_budget invariant must hold."""
        profiles = [
            LinkedInSearchProfile(label="A", job_titles=["Eng"], weight=1),
            LinkedInSearchProfile(label="B", job_titles=["Arch"], weight=10),
        ]
        budget = LinkedInApifyScraper._allocate_budget(profiles, 10)
        assert sum(budget) <= 10
        assert len(budget) == 2

    def test_extract_job_id(self) -> None:
        assert LinkedInApifyScraper._extract_job_id(
            "https://www.linkedin.com/jobs/view/4227647589"
        ) == "4227647589"

    def test_extract_job_id_trailing_slash(self) -> None:
        assert LinkedInApifyScraper._extract_job_id(
            "https://www.linkedin.com/jobs/view/4227647589/"
        ) == "4227647589"

    def test_extract_job_id_with_query_params(self) -> None:
        assert LinkedInApifyScraper._extract_job_id(
            "https://www.linkedin.com/jobs/view/4227647589?trk=public_jobs"
        ) == "4227647589"

    def test_extract_job_id_invalid_url(self) -> None:
        assert LinkedInApifyScraper._extract_job_id("https://example.com/foo") is None

    def test_extract_job_id_empty(self) -> None:
        assert LinkedInApifyScraper._extract_job_id("") is None

    @pytest.mark.asyncio
    async def test_scrape_no_profiles(self, secrets_with_apify) -> None:
        config = LinkedInConfig(
            enabled=True,
            apify_actor_id="valig/linkedin-jobs-scraper",
            max_results=50,
            search_profiles=[],
        )
        scraper = LinkedInApifyScraper(config, secrets_with_apify)
        results = await scraper.scrape()
        assert results == []

    @pytest.mark.asyncio
    async def test_scrape_single_profile(self, scraper) -> None:
        """Full flow: one profile -> mocked actor -> results."""
        from jobhunter.scrapers.base import RawJobData

        mock_results = [
            RawJobData(
                source="linkedin",
                source_url="https://www.linkedin.com/jobs/view/111",
                title="Eng",
                company="Co",
                description="Build things",
            ),
            RawJobData(
                source="linkedin",
                source_url="https://www.linkedin.com/jobs/view/222",
                title="Arch",
                company="Co2",
                description="Design things",
            ),
        ]

        with patch.object(_SingleProfileScraper, "scrape", new_callable=AsyncMock, return_value=mock_results):
            results = await scraper.scrape()

        assert len(results) == 2
        assert results[0].title == "Eng"
        assert results[1].title == "Arch"

    @pytest.mark.asyncio
    async def test_scrape_cross_profile_dedup(self, secrets_with_apify) -> None:
        """Same job ID from two profiles should only appear once."""
        from jobhunter.scrapers.base import RawJobData

        profiles = [
            LinkedInSearchProfile(label="P1", job_titles=["Eng"], weight=1),
            LinkedInSearchProfile(label="P2", job_titles=["Arch"], weight=1),
        ]
        config = LinkedInConfig(
            enabled=True,
            apify_actor_id="valig/linkedin-jobs-scraper",
            max_results=100,
            search_profiles=profiles,
        )
        scraper = LinkedInApifyScraper(config, secrets_with_apify)

        # Both profiles return the same job
        shared_job = RawJobData(
            source="linkedin",
            source_url="https://www.linkedin.com/jobs/view/999",
            title="Shared Job",
            company="SharedCo",
            description="Appears in both searches",
        )
        unique_job = RawJobData(
            source="linkedin",
            source_url="https://www.linkedin.com/jobs/view/888",
            title="Unique Job",
            company="UniqueCo",
            description="Only in P2",
        )

        call_count = 0

        async def mock_scrape(self_inner: _SingleProfileScraper) -> list[RawJobData]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [shared_job]
            return [shared_job, unique_job]

        with patch.object(_SingleProfileScraper, "scrape", mock_scrape):
            results = await scraper.scrape()

        assert len(results) == 2  # shared_job + unique_job (not 3)
        urls = {r.source_url for r in results}
        assert "https://www.linkedin.com/jobs/view/999" in urls
        assert "https://www.linkedin.com/jobs/view/888" in urls

    @pytest.mark.asyncio
    async def test_scrape_profile_failure_isolation(self, secrets_with_apify) -> None:
        """One profile failing shouldn't prevent others from returning results."""
        from jobhunter.scrapers.base import RawJobData
        from jobhunter.scrapers.exceptions import ScraperError

        profiles = [
            LinkedInSearchProfile(label="Fails", job_titles=["Fails"], weight=1),
            LinkedInSearchProfile(label="Works", job_titles=["Works"], weight=1),
        ]
        config = LinkedInConfig(
            enabled=True,
            apify_actor_id="valig/linkedin-jobs-scraper",
            max_results=100,
            search_profiles=profiles,
        )
        scraper = LinkedInApifyScraper(config, secrets_with_apify)

        good_job = RawJobData(
            source="linkedin",
            source_url="https://www.linkedin.com/jobs/view/555",
            title="Good Job",
            company="GoodCo",
            description="From the working profile",
        )

        call_count = 0

        async def mock_scrape(self_inner: _SingleProfileScraper) -> list[RawJobData]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ScraperError("linkedin", "Actor failed")
            return [good_job]

        with patch.object(_SingleProfileScraper, "scrape", mock_scrape):
            results = await scraper.scrape()

        assert len(results) == 1
        assert results[0].title == "Good Job"

    def test_allocate_budget_duplicate_labels(self) -> None:
        """Two profiles with same label get independent allocations."""
        profiles = [
            LinkedInSearchProfile(label="Same", job_titles=["Eng"], weight=1),
            LinkedInSearchProfile(label="Same", job_titles=["Arch"], weight=1),
        ]
        budget = LinkedInApifyScraper._allocate_budget(profiles, 100)
        assert budget == [50, 50]  # Index-based, not label-keyed

    def test_dataset_fetch_uses_profile_budget(self, linkedin_config, secrets_with_apify) -> None:
        """_SingleProfileScraper._max_results equals per-profile allocation, not total."""
        profile = linkedin_config.search_profiles[0]
        scraper = _SingleProfileScraper(linkedin_config, secrets_with_apify, profile, max_items=25)
        assert scraper._max_results == 25  # Not 50 (the total config.max_results)
