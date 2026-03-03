"""Tests for LinkedIn URL parser (convenience tool for structured queries)."""

from jobhunter.scrapers.linkedin_url_parser import build_linkedin_url, parse_linkedin_url


class TestParseLinkedInUrl:
    def test_full_url(self) -> None:
        url = "https://www.linkedin.com/jobs/search/?keywords=software+architect&location=Remote&f_WT=2&f_E=4,5&f_TPR=r604800"
        result = parse_linkedin_url(url, label="My Search")
        assert result is not None
        assert result.label == "My Search"
        assert result.job_titles == ["software architect"]
        assert result.locations == ["Remote"]
        assert result.workplace_type == ["remote"]
        assert result.experience_level == ["mid-senior", "director"]
        assert result.posted_limit == "week"

    def test_keywords_only(self) -> None:
        url = "https://www.linkedin.com/jobs/search/?keywords=engineering+manager"
        result = parse_linkedin_url(url)
        assert result is not None
        assert result.job_titles == ["engineering manager"]
        assert result.workplace_type == ["remote"]  # default

    def test_auto_label(self) -> None:
        url = "https://www.linkedin.com/jobs/search/?keywords=architect&location=Europe"
        result = parse_linkedin_url(url)
        assert result is not None
        assert "architect" in result.label
        assert "Europe" in result.label

    def test_auto_label_no_location(self) -> None:
        url = "https://www.linkedin.com/jobs/search/?keywords=architect&f_WT=2"
        result = parse_linkedin_url(url)
        assert result is not None
        assert "Remote" in result.label

    def test_office_workplace_type(self) -> None:
        url = "https://www.linkedin.com/jobs/search/?keywords=engineer&f_WT=1"
        result = parse_linkedin_url(url)
        assert result is not None
        assert result.workplace_type == ["office"]

    def test_hybrid_workplace_type(self) -> None:
        url = "https://www.linkedin.com/jobs/search/?keywords=engineer&f_WT=3"
        result = parse_linkedin_url(url)
        assert result is not None
        assert result.workplace_type == ["hybrid"]

    def test_time_posted_24h(self) -> None:
        url = "https://www.linkedin.com/jobs/search/?keywords=engineer&f_TPR=r86400"
        result = parse_linkedin_url(url)
        assert result is not None
        assert result.posted_limit == "24h"

    def test_time_posted_month(self) -> None:
        url = "https://www.linkedin.com/jobs/search/?keywords=engineer&f_TPR=r2592000"
        result = parse_linkedin_url(url)
        assert result is not None
        assert result.posted_limit == "month"

    def test_not_linkedin_url(self) -> None:
        result = parse_linkedin_url("https://example.com/jobs")
        assert result is None

    def test_malformed_url(self) -> None:
        result = parse_linkedin_url("not-a-url")
        assert result is None

    def test_empty_url(self) -> None:
        result = parse_linkedin_url("")
        assert result is None

    def test_no_keywords(self) -> None:
        url = "https://www.linkedin.com/jobs/search/?f_WT=2"
        result = parse_linkedin_url(url)
        assert result is not None
        assert result.job_titles == []


class TestBuildLinkedInUrl:
    def test_roundtrip_basic(self) -> None:
        url = "https://www.linkedin.com/jobs/search/?keywords=architect&f_WT=2&f_E=4,5"
        profile = parse_linkedin_url(url)
        assert profile is not None
        rebuilt = build_linkedin_url(profile)
        assert "keywords=architect" in rebuilt
        assert "f_WT=2" in rebuilt
        assert "f_E=" in rebuilt

    def test_build_with_posted_limit(self) -> None:
        from jobhunter.config.schema import LinkedInSearchProfile

        profile = LinkedInSearchProfile(
            label="Test",
            job_titles=["VP Engineering"],
            locations=["New York"],
            posted_limit="week",
        )
        url = build_linkedin_url(profile)
        assert "keywords=VP Engineering" in url
        assert "location=New York" in url
        assert "f_TPR=r604800" in url
