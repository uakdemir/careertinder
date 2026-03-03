"""Tests for D4: Wellfound Apify scraper (_parse_item, startup metadata)."""

import pytest

from jobhunter.scrapers.wellfound_apify import WellfoundApifyScraper


class TestWellfoundApifyScraper:
    @pytest.fixture
    def scraper(self, wellfound_config, secrets_with_apify):
        return WellfoundApifyScraper(wellfound_config, secrets_with_apify)

    def test_scraper_name(self, scraper) -> None:
        assert scraper.scraper_name == "wellfound"

    def test_build_actor_input(self, scraper) -> None:
        actor_input = scraper._build_actor_input()
        assert actor_input["keyword"] == "software engineer"
        assert actor_input["location"] == "remote"
        assert actor_input["maxItems"] == 50

    def test_parse_item_complete(self, scraper) -> None:
        item = {
            "title": "Head of Platform",
            "companyName": "StartupAlpha",
            "url": "https://wellfound.com/jobs/1",
            "description": "Lead platform team.",
            "salary": "$140K-$190K",
            "location": "Remote",
            "requirements": "10+ years",
            "postedAt": "2025-01-16",
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
        assert result.requirements == "10+ years"

    def test_parse_item_alternative_field_names(self, scraper) -> None:
        """Wellfound actor may use jobTitle/company instead of title/companyName."""
        item = {
            "jobTitle": "Senior Dev",
            "company": "BetaCo",
            "url": "https://wellfound.com/jobs/2",
            "description": "Backend work.",
            "compensation": "$100K + equity",
            "fundingStage": "Seed",
            "teamSize": "10-20",
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert result.title == "Senior Dev"
        assert result.company == "BetaCo"
        assert result.salary_raw == "$100K + equity"
        assert "Funding stage: Seed" in result.description
        assert "Team size: 10-20" in result.description

    def test_parse_item_no_startup_metadata(self, scraper) -> None:
        item = {
            "title": "Engineer",
            "companyName": "PlainCo",
            "url": "https://wellfound.com/jobs/3",
            "description": "Build things.",
        }
        result = scraper._parse_item(item)
        assert result is not None
        assert "--- Startup Info ---" not in result.description

    def test_parse_item_missing_url(self, scraper) -> None:
        item = {"title": "Engineer", "companyName": "Co", "description": "Build things."}
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_item_empty_url(self, scraper) -> None:
        item = {"title": "Engineer", "companyName": "Co", "url": "", "description": "Build things."}
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_item_missing_required(self, scraper) -> None:
        item = {"url": "https://wellfound.com/jobs/invalid", "description": "No title or company."}
        result = scraper._parse_item(item)
        assert result is None

    def test_parse_items_from_fixture(self, scraper, wellfound_apify_items) -> None:
        results = [scraper._parse_item(item) for item in wellfound_apify_items]
        valid = [r for r in results if r is not None]
        assert len(valid) == 2  # 2 valid, 1 skipped (missing title+company)
        assert valid[0].title == "Head of Platform"
        assert valid[1].title == "Senior Backend Developer"

    def test_extract_startup_metadata_tech_stack_string(self, scraper) -> None:
        item = {"techStack": "Python, Go, Rust"}
        result = scraper._extract_startup_metadata(item)
        assert result is not None
        assert "Tech stack: Python, Go, Rust" in result

    def test_extract_startup_metadata_empty(self, scraper) -> None:
        result = scraper._extract_startup_metadata({})
        assert result is None
