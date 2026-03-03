"""Tests for D1: Scraper framework (BaseScraper, RawJobData, exceptions, rate limiter)."""

import dataclasses
from unittest.mock import AsyncMock, patch

import pytest

from jobhunter.scrapers.base import RawJobData
from jobhunter.scrapers.exceptions import (
    ScraperBlockedError,
    ScraperError,
    ScraperNetworkError,
    ScraperQuotaError,
    ScraperStructureError,
    ScraperTimeoutError,
)
from jobhunter.scrapers.rate_limiter import RateLimiter


class TestRawJobData:
    def test_required_fields(self) -> None:
        job = RawJobData(
            source="linkedin",
            source_url="https://example.com/job/1",
            title="Software Architect",
            company="TechCorp",
            description="Build systems.",
        )
        assert job.source == "linkedin"
        assert job.title == "Software Architect"
        assert job.company == "TechCorp"

    def test_defaults_are_none(self) -> None:
        job = RawJobData(
            source="remote_io",
            source_url="https://example.com",
            title="Dev",
            company="Co",
            description="Desc",
        )
        assert job.salary_raw is None
        assert job.location_raw is None
        assert job.requirements is None
        assert job.raw_html is None
        assert job.posted_date_raw is None

    def test_frozen(self) -> None:
        job = RawJobData(
            source="remote_io",
            source_url="https://example.com",
            title="Dev",
            company="Co",
            description="Desc",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            job.title = "Changed"  # type: ignore[misc]


class TestScraperErrorHierarchy:
    def test_all_subclasses_are_scraper_error(self) -> None:
        errors = [
            ScraperTimeoutError("test", "timeout"),
            ScraperStructureError("test", "structure changed"),
            ScraperBlockedError("test", "blocked"),
            ScraperQuotaError("test", "quota"),
            ScraperNetworkError("test", "network"),
        ]
        for err in errors:
            assert isinstance(err, ScraperError)

    def test_error_includes_scraper_name(self) -> None:
        err = ScraperError("linkedin", "connection failed")
        assert "linkedin" in str(err)
        assert "connection failed" in str(err)
        assert err.scraper_name == "linkedin"

    def test_timeout_error_message(self) -> None:
        err = ScraperTimeoutError("remote_io", "page load exceeded 30s")
        assert "[remote_io]" in str(err)
        assert "page load exceeded 30s" in str(err)


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_delay_within_jitter_range(self) -> None:
        limiter = RateLimiter(2.0, jitter_fraction=0.3)
        with patch("jobhunter.scrapers.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await limiter.wait()
            mock_sleep.assert_called_once()
            sleep_time = mock_sleep.call_args[0][0]
            assert 1.4 <= sleep_time <= 2.6

    @pytest.mark.asyncio
    async def test_zero_delay_returns_immediately(self) -> None:
        limiter = RateLimiter(0)
        with patch("jobhunter.scrapers.rate_limiter.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await limiter.wait()
            # With delay=0 and jitter=0.3, jitter is 0*0.3*rand = 0, sleep_time = max(0, 0) = 0
            # sleep is not called when sleep_time is 0 due to the > 0 check
            if mock_sleep.called:
                sleep_time = mock_sleep.call_args[0][0]
                assert sleep_time == 0.0
