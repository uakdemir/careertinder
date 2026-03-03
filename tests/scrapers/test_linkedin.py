"""Tests for LinkedIn HarvestAPI scraper (multi-profile, structured queries)."""

from unittest.mock import AsyncMock, patch

import pytest

from jobhunter.config.schema import LinkedInConfig, LinkedInSearchProfile
from jobhunter.scrapers.linkedin_apify import LinkedInApifyScraper, _SingleProfileScraper


class TestSingleProfileScraper:
    """Tests for the internal _SingleProfileScraper (HarvestAPI actor interface)."""

    @pytest.fixture
    def profile(self, linkedin_search_profile):
        return linkedin_search_profile

    @pytest.fixture
    def scraper(self, linkedin_config, secrets_with_apify, profile):
        return _SingleProfileScraper(linkedin_config, secrets_with_apify, profile, max_items=50)

    def test_scraper_name(self, scraper) -> None:
        assert scraper.scraper_name == "linkedin"

    def test_build_actor_input(self, scraper) -> None:
        actor_input = scraper._build_actor_input()
        assert actor_input["jobTitles"] == ["Software Architect"]
        assert actor_input["maxItems"] == 50
        assert actor_input["sortBy"] == "date"
        assert actor_input["locations"] == ["Remote"]
        assert actor_input["workplaceType"] == ["remote"]
        assert actor_input["experienceLevel"] == ["mid-senior", "director"]
        # No salary/postedLimit set in fixture
        assert "salary" not in actor_input
        assert "postedLimit" not in actor_input

    def test_build_actor_input_with_salary_and_posted(self, linkedin_config, secrets_with_apify) -> None:
        profile = LinkedInSearchProfile(
            label="Test",
            job_titles=["Engineer"],
            salary="120k+",
            posted_limit="week",
        )
        scraper = _SingleProfileScraper(linkedin_config, secrets_with_apify, profile, max_items=10)
        actor_input = scraper._build_actor_input()
        assert actor_input["salary"] == ["120k+"]
        assert actor_input["postedLimit"] == "week"

    def test_parse_item_complete(self, scraper) -> None:
        item = {
            "id": "4227647589",
            "title": "VP of Engineering",
            "linkedinUrl": "https://www.linkedin.com/jobs/view/4227647589",
            "descriptionText": "Lead engineering org.",
            "descriptionHtml": "<p>Lead engineering org.</p>",
            "company": {"name": "MegaTech", "employeeCount": 500},
            "salary": {"text": "$180K-$250K", "min": 180000, "max": 250000, "currency": "USD"},
            "location": {"linkedinText": "Remote - Worldwide"},
            "postedDate": "2025-01-15",
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

    def test_parse_item_salary_from_min_max(self, scraper) -> None:
        item = {
            "title": "Architect",
            "linkedinUrl": "https://www.linkedin.com/jobs/view/123",
            "descriptionText": "Build things.",
            "company": {"name": "Co"},
            "salary": {"min": 100000, "max": 150000, "currency": "EUR"},
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert result.salary_raw == "EUR 100,000 - 150,000"

    def test_parse_item_salary_min_only(self, scraper) -> None:
        item = {
            "title": "Architect",
            "linkedinUrl": "https://www.linkedin.com/jobs/view/123",
            "descriptionText": "Build things.",
            "company": {"name": "Co"},
            "salary": {"min": 90000, "currency": "USD"},
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert result.salary_raw == "USD 90,000+"

    def test_parse_item_null_salary(self, scraper) -> None:
        item = {
            "title": "Architect",
            "linkedinUrl": "https://www.linkedin.com/jobs/view/123",
            "descriptionText": "Build things.",
            "company": {"name": "Co"},
            "salary": None,
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert result.salary_raw is None

    def test_parse_item_missing_title(self, scraper) -> None:
        item = {
            "company": {"name": "SomeCo"},
            "linkedinUrl": "https://www.linkedin.com/jobs/view/123",
        }
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_item_missing_company(self, scraper) -> None:
        item = {
            "title": "Engineer",
            "linkedinUrl": "https://www.linkedin.com/jobs/view/123",
            "company": None,
        }
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_item_missing_url(self, scraper) -> None:
        item = {
            "title": "Architect",
            "company": {"name": "Co"},
            "descriptionText": "Build things.",
        }
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_item_empty_url(self, scraper) -> None:
        item = {
            "title": "Architect",
            "company": {"name": "Co"},
            "linkedinUrl": "",
            "descriptionText": "Build things.",
        }
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_item_location_string_fallback(self, scraper) -> None:
        """Location as a plain string instead of structured object."""
        item = {
            "title": "Architect",
            "linkedinUrl": "https://www.linkedin.com/jobs/view/123",
            "descriptionText": "Build things.",
            "company": {"name": "Co"},
            "location": "New York, NY",
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert result.location_raw == "New York, NY"

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
        assert budget["A"] == 100

    def test_budget_allocation_equal_weights(self) -> None:
        profiles = [
            LinkedInSearchProfile(label="A", job_titles=["Eng"], weight=1),
            LinkedInSearchProfile(label="B", job_titles=["Arch"], weight=1),
        ]
        budget = LinkedInApifyScraper._allocate_budget(profiles, 100)
        assert budget["A"] == 50
        assert budget["B"] == 50

    def test_budget_allocation_weighted(self) -> None:
        profiles = [
            LinkedInSearchProfile(label="High", job_titles=["Eng"], weight=3),
            LinkedInSearchProfile(label="Low", job_titles=["Arch"], weight=1),
        ]
        budget = LinkedInApifyScraper._allocate_budget(profiles, 100)
        assert budget["High"] == 75
        assert budget["Low"] == 25

    def test_budget_allocation_minimum_one(self) -> None:
        profiles = [
            LinkedInSearchProfile(label="A", job_titles=["Eng"], weight=1),
            LinkedInSearchProfile(label="B", job_titles=["Arch"], weight=10),
        ]
        budget = LinkedInApifyScraper._allocate_budget(profiles, 10)
        assert budget["A"] >= 1  # At least 1

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
            apify_actor_id="harvestapi/linkedin-job-search",
            max_results=50,
            search_profiles=[],
        )
        scraper = LinkedInApifyScraper(config, secrets_with_apify)
        results = await scraper.scrape()
        assert results == []

    @pytest.mark.asyncio
    async def test_scrape_single_profile(self, scraper) -> None:
        """Full flow: one profile → mocked actor → results."""
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
            apify_actor_id="harvestapi/linkedin-job-search",
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
            apify_actor_id="harvestapi/linkedin-job-search",
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
