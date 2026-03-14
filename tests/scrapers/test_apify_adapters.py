"""Focused unit tests for Apify item adapters (field mapping, fallbacks, conversions)."""

import pytest

from jobhunter.scrapers.apify_adapters import (
    LinkedInItemAdapter,
    WellfoundItemAdapter,
)


class TestWellfoundItemAdapter:
    """Tests for WellfoundItemAdapter field mapping and enrichment."""

    @pytest.fixture
    def adapter(self) -> WellfoundItemAdapter:
        return WellfoundItemAdapter()

    def test_source_name(self, adapter: WellfoundItemAdapter) -> None:
        assert adapter.source_name == "wellfound"

    def test_complete_item(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "title": "Head of Platform",
            "company": "StartupAlpha",
            "applyUrl": "https://wellfound.com/jobs/1",
            "description_text": "Lead platform team.",
            "salary": "$140K-$190K",
            "location": "New York",
            "remote": "Yes",
            "postedDate": 1737072000,
            "companyStage": "Series B",
            "companySize": "51-100",
            "techStack": ["Python", "K8s"],
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.source == "wellfound"
        assert result.title == "Head of Platform"
        assert result.company == "StartupAlpha"
        assert result.source_url == "https://wellfound.com/jobs/1"
        assert result.salary_raw == "$140K-$190K"
        assert result.posted_date_raw == "2025-01-17"
        assert "Lead platform team." in result.description
        assert "Funding stage: Series B" in result.description
        assert "Team size: 51-100" in result.description
        assert "Tech stack: Python, K8s" in result.description

    def test_missing_title_returns_none(self, adapter: WellfoundItemAdapter) -> None:
        item = {"company": "Co", "applyUrl": "https://wellfound.com/jobs/1"}
        assert adapter.to_raw_job(item) is None

    def test_missing_company_returns_none(self, adapter: WellfoundItemAdapter) -> None:
        item = {"title": "Eng", "applyUrl": "https://wellfound.com/jobs/1"}
        assert adapter.to_raw_job(item) is None

    def test_missing_url_returns_none(self, adapter: WellfoundItemAdapter) -> None:
        item = {"title": "Eng", "company": "Co"}
        assert adapter.to_raw_job(item) is None

    def test_empty_url_returns_none(self, adapter: WellfoundItemAdapter) -> None:
        item = {"title": "Eng", "company": "Co", "applyUrl": "  "}
        assert adapter.to_raw_job(item) is None

    # --- URL fallback ---

    def test_url_fallback_from_apply_url(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "title": "Eng",
            "company": "Co",
            "applyUrl": "https://wellfound.com/apply/1",
            "url": "https://wellfound.com/jobs/1",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.source_url == "https://wellfound.com/apply/1"

    def test_url_fallback_to_url(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "title": "Eng",
            "company": "Co",
            "url": "https://wellfound.com/jobs/1",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.source_url == "https://wellfound.com/jobs/1"

    # --- Description fallbacks ---

    def test_description_prefers_text(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "title": "Eng",
            "company": "Co",
            "applyUrl": "https://wellfound.com/jobs/1",
            "description_text": "Plain text desc",
            "description_html": "<p>HTML desc</p>",
            "description": "Generic desc",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert "Plain text desc" in result.description

    def test_description_falls_back_to_html(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "title": "Eng",
            "company": "Co",
            "applyUrl": "https://wellfound.com/jobs/1",
            "description_html": "<p>HTML desc</p>",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert "<p>HTML desc</p>" in result.description

    def test_description_falls_back_to_generic(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "title": "Eng",
            "company": "Co",
            "applyUrl": "https://wellfound.com/jobs/1",
            "description": "Generic desc",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert "Generic desc" in result.description

    # --- Remote flag ---

    def test_remote_flag_appended_to_location(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "title": "Eng",
            "company": "Co",
            "applyUrl": "https://wellfound.com/jobs/1",
            "location": "New York",
            "remote": "Yes",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert "Remote" in result.location_raw  # type: ignore[operator]
        assert "New York" in result.location_raw  # type: ignore[operator]

    def test_remote_flag_not_duplicated(self, adapter: WellfoundItemAdapter) -> None:
        """Don't append '(Remote)' if location already contains 'remote'."""
        item = {
            "title": "Eng",
            "company": "Co",
            "applyUrl": "https://wellfound.com/jobs/1",
            "location": "Remote - US",
            "remote": "Yes",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.location_raw == "Remote - US"

    def test_remote_flag_no_location(self, adapter: WellfoundItemAdapter) -> None:
        """Remote=Yes with no location -> 'Remote'."""
        item = {
            "title": "Eng",
            "company": "Co",
            "applyUrl": "https://wellfound.com/jobs/1",
            "remote": "Yes",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.location_raw == "Remote"

    def test_remote_flag_no(self, adapter: WellfoundItemAdapter) -> None:
        """Remote=No should not add Remote to location."""
        item = {
            "title": "Eng",
            "company": "Co",
            "applyUrl": "https://wellfound.com/jobs/1",
            "location": "New York",
            "remote": "No",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.location_raw == "New York"

    # --- Posted date conversion ---

    def test_posted_date_unix_timestamp(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "title": "Eng",
            "company": "Co",
            "applyUrl": "https://wellfound.com/jobs/1",
            "postedDate": 1737072000,  # 2025-01-17 00:00:00 UTC
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.posted_date_raw == "2025-01-17"

    def test_posted_date_string_passthrough(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "title": "Eng",
            "company": "Co",
            "applyUrl": "https://wellfound.com/jobs/1",
            "postedDate": "2025-01-15",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.posted_date_raw == "2025-01-15"

    def test_posted_date_none(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "title": "Eng",
            "company": "Co",
            "applyUrl": "https://wellfound.com/jobs/1",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.posted_date_raw is None

    # --- Startup metadata ---

    def test_startup_metadata_all_fields(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "companyStage": "Series A",
            "companySize": "20-50",
            "techStack": ["Go", "Rust"],
        }
        meta = adapter._extract_startup_metadata(item)
        assert meta is not None
        assert "Funding stage: Series A" in meta
        assert "Team size: 20-50" in meta
        assert "Tech stack: Go, Rust" in meta

    def test_startup_metadata_funding_stage_fallback(self, adapter: WellfoundItemAdapter) -> None:
        item = {"fundingStage": "Seed"}
        meta = adapter._extract_startup_metadata(item)
        assert meta is not None
        assert "Funding stage: Seed" in meta

    def test_startup_metadata_team_size_fallback(self, adapter: WellfoundItemAdapter) -> None:
        item = {"teamSize": "5-10"}
        meta = adapter._extract_startup_metadata(item)
        assert meta is not None
        assert "Team size: 5-10" in meta

    def test_startup_metadata_tech_stack_string(self, adapter: WellfoundItemAdapter) -> None:
        item = {"techStack": "Python, Go, Rust"}
        meta = adapter._extract_startup_metadata(item)
        assert meta is not None
        assert "Tech stack: Python, Go, Rust" in meta

    def test_startup_metadata_empty(self, adapter: WellfoundItemAdapter) -> None:
        assert adapter._extract_startup_metadata({}) is None

    def test_no_startup_metadata_in_description(self, adapter: WellfoundItemAdapter) -> None:
        item = {
            "title": "Eng",
            "company": "PlainCo",
            "applyUrl": "https://wellfound.com/jobs/1",
            "description_text": "Build things.",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert "--- Startup Info ---" not in result.description


class TestLinkedInItemAdapter:
    """Tests for LinkedInItemAdapter field mapping."""

    @pytest.fixture
    def adapter(self) -> LinkedInItemAdapter:
        return LinkedInItemAdapter()

    def test_source_name(self, adapter: LinkedInItemAdapter) -> None:
        assert adapter.source_name == "linkedin"

    def test_complete_item(self, adapter: LinkedInItemAdapter) -> None:
        item = {
            "id": "4227647589",
            "title": "VP of Engineering",
            "url": "https://www.linkedin.com/jobs/view/4227647589",
            "description": "Lead engineering org.",
            "descriptionHtml": "<p>Lead engineering org.</p>",
            "companyName": "MegaTech",
            "salary": "$180K-$250K",
            "location": "Remote - Worldwide",
            "postedDate": "2025-01-15",
            "postedTimeAgo": "2 days ago",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.source == "linkedin"
        assert result.title == "VP of Engineering"
        assert result.company == "MegaTech"
        assert result.source_url == "https://www.linkedin.com/jobs/view/4227647589"
        assert result.salary_raw == "$180K-$250K"
        assert result.location_raw == "Remote - Worldwide"
        assert result.posted_date_raw == "2025-01-15"
        assert result.raw_html == "<p>Lead engineering org.</p>"
        assert result.description == "Lead engineering org."

    def test_missing_title_returns_none(self, adapter: LinkedInItemAdapter) -> None:
        item = {
            "companyName": "Co",
            "url": "https://www.linkedin.com/jobs/view/123",
        }
        assert adapter.to_raw_job(item) is None

    def test_missing_company_returns_none(self, adapter: LinkedInItemAdapter) -> None:
        item = {
            "title": "Eng",
            "url": "https://www.linkedin.com/jobs/view/123",
            "companyName": None,
        }
        assert adapter.to_raw_job(item) is None

    def test_missing_url_returns_none(self, adapter: LinkedInItemAdapter) -> None:
        item = {"title": "Eng", "companyName": "Co"}
        assert adapter.to_raw_job(item) is None

    def test_empty_url_returns_none(self, adapter: LinkedInItemAdapter) -> None:
        item = {"title": "Eng", "companyName": "Co", "url": "  "}
        assert adapter.to_raw_job(item) is None

    def test_null_salary(self, adapter: LinkedInItemAdapter) -> None:
        item = {
            "title": "Eng",
            "companyName": "Co",
            "url": "https://www.linkedin.com/jobs/view/123",
            "description": "Build.",
            "salary": None,
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.salary_raw is None

    def test_posted_date_preferred_over_time_ago(self, adapter: LinkedInItemAdapter) -> None:
        item = {
            "title": "Eng",
            "companyName": "Co",
            "url": "https://www.linkedin.com/jobs/view/123",
            "description": "Build.",
            "postedDate": "2025-01-15",
            "postedTimeAgo": "2 days ago",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.posted_date_raw == "2025-01-15"

    def test_posted_time_ago_fallback(self, adapter: LinkedInItemAdapter) -> None:
        item = {
            "title": "Eng",
            "companyName": "Co",
            "url": "https://www.linkedin.com/jobs/view/123",
            "description": "Build.",
            "postedTimeAgo": "3 days ago",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.posted_date_raw == "3 days ago"

    def test_description_fallback_to_html(self, adapter: LinkedInItemAdapter) -> None:
        item = {
            "title": "Eng",
            "companyName": "Co",
            "url": "https://www.linkedin.com/jobs/view/123",
            "descriptionHtml": "<p>HTML desc</p>",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.description == "<p>HTML desc</p>"
        assert result.raw_html == "<p>HTML desc</p>"

    def test_raw_html_preserved(self, adapter: LinkedInItemAdapter) -> None:
        item = {
            "title": "Eng",
            "companyName": "Co",
            "url": "https://www.linkedin.com/jobs/view/123",
            "description": "Plain text",
            "descriptionHtml": "<p>HTML</p>",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.description == "Plain text"
        assert result.raw_html == "<p>HTML</p>"

    def test_requirements_always_none(self, adapter: LinkedInItemAdapter) -> None:
        """LinkedIn adapter sets requirements=None (parsed elsewhere)."""
        item = {
            "title": "Eng",
            "companyName": "Co",
            "url": "https://www.linkedin.com/jobs/view/123",
            "description": "Build.",
        }
        result = adapter.to_raw_job(item)
        assert result is not None
        assert result.requirements is None


class TestFirstOfHelper:
    """Tests for the _first_of helper method."""

    def test_returns_first_match(self) -> None:
        adapter = WellfoundItemAdapter()
        item = {"a": "val_a", "b": "val_b"}
        assert adapter._first_of(item, "a", "b") == "val_a"

    def test_skips_none(self) -> None:
        adapter = WellfoundItemAdapter()
        item = {"a": None, "b": "val_b"}
        assert adapter._first_of(item, "a", "b") == "val_b"

    def test_skips_empty_string(self) -> None:
        adapter = WellfoundItemAdapter()
        item = {"a": "  ", "b": "val_b"}
        assert adapter._first_of(item, "a", "b") == "val_b"

    def test_returns_none_when_no_match(self) -> None:
        adapter = WellfoundItemAdapter()
        assert adapter._first_of({}, "a", "b") is None

    def test_strips_whitespace(self) -> None:
        adapter = WellfoundItemAdapter()
        item = {"a": "  hello  "}
        assert adapter._first_of(item, "a") == "hello"
