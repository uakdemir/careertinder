"""Tests for Remote.io Playwright scraper (multi-profile, link-pattern + JSON-LD extraction)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from jobhunter.config.schema import RemoteIoConfig, RemoteIoSearchProfile
from jobhunter.scrapers.exceptions import ScraperTimeoutError
from jobhunter.scrapers.remote_io import RemoteIoScraper


class TestRemoteIoScraper:
    @pytest.fixture
    def scraper(self, remote_io_config, secrets_no_apify):
        return RemoteIoScraper(remote_io_config, secrets_no_apify)

    def test_scraper_name(self, scraper) -> None:
        assert scraper.scraper_name == "remote_io"

    # --- URL building ---

    def test_build_listing_url_page1(self) -> None:
        url = RemoteIoScraper._build_listing_url("https://remote.io/remote-jobs", 1)
        assert url == "https://remote.io/remote-jobs"
        assert "?page=" not in url

    def test_build_listing_url_page2(self) -> None:
        url = RemoteIoScraper._build_listing_url("https://remote.io/remote-jobs", 2)
        assert url == "https://remote.io/remote-jobs?page=2"

    def test_build_listing_url_page5(self) -> None:
        url = RemoteIoScraper._build_listing_url("https://remote.io/remote-python-jobs", 5)
        assert url == "https://remote.io/remote-python-jobs?page=5"

    # --- Company from URL ---

    def test_parse_company_from_url(self) -> None:
        url = "https://remote.io/remote-software-development-jobs/senior-engineer-at-ping-identity-67499"
        result = RemoteIoScraper._parse_company_from_url(url)
        assert result == "Ping Identity"

    def test_parse_company_from_url_single_word(self) -> None:
        url = "https://remote.io/remote-data-jobs/analyst-at-google-12345"
        result = RemoteIoScraper._parse_company_from_url(url)
        assert result == "Google"

    def test_parse_company_from_url_no_match(self) -> None:
        url = "https://remote.io/some-other-page"
        result = RemoteIoScraper._parse_company_from_url(url)
        assert result == ""

    # --- JSON-LD location extraction ---

    def test_extract_location_single(self) -> None:
        json_ld = {
            "applicantLocationRequirements": {"@type": "AdministrativeArea", "name": "Italy"},
            "jobLocationType": "TELECOMMUTE",
        }
        result = RemoteIoScraper._extract_location_from_json_ld(json_ld)
        assert result == "Italy — TELECOMMUTE"

    def test_extract_location_no_requirements(self) -> None:
        json_ld = {"jobLocationType": "TELECOMMUTE"}
        result = RemoteIoScraper._extract_location_from_json_ld(json_ld)
        assert result == "TELECOMMUTE"

    def test_extract_location_empty(self) -> None:
        result = RemoteIoScraper._extract_location_from_json_ld({})
        assert result is None

    def test_extract_location_list(self) -> None:
        json_ld = {
            "applicantLocationRequirements": [
                {"@type": "AdministrativeArea", "name": "US"},
                {"@type": "AdministrativeArea", "name": "Canada"},
            ]
        }
        result = RemoteIoScraper._extract_location_from_json_ld(json_ld)
        assert result == "US — Canada"

    # --- Navigation retry ---

    @pytest.mark.asyncio
    async def test_navigate_with_retry_success_first_try(self, scraper) -> None:
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()

        await scraper._navigate_with_retry(mock_page, "https://example.com")
        mock_page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_with_retry_success_second_try(self, scraper) -> None:
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(
            side_effect=[PlaywrightTimeout("timeout"), None]
        )

        with patch("jobhunter.scrapers.remote_io.asyncio.sleep", new_callable=AsyncMock):
            await scraper._navigate_with_retry(mock_page, "https://example.com")

        assert mock_page.goto.call_count == 2

    @pytest.mark.asyncio
    async def test_navigate_with_retry_all_fail(self, scraper) -> None:
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=PlaywrightTimeout("timeout"))

        with patch("jobhunter.scrapers.remote_io.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ScraperTimeoutError, match="Timeout loading"):
                await scraper._navigate_with_retry(mock_page, "https://example.com")

        assert mock_page.goto.call_count == 3  # initial + 2 retries

    # --- Job link extraction ---

    @pytest.mark.asyncio
    async def test_extract_job_links(self, scraper) -> None:
        """Extracts job links using URL pattern matching."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {"href": "/remote-software-development-jobs/senior-eng-at-acme-12345", "text": "Senior Engineer"},
            {"href": "/remote-data-jobs/data-analyst-at-bigco-67890", "text": "Data Analyst"},
        ])

        result = await scraper._extract_job_links(mock_page)
        assert len(result) == 2
        assert result[0]["detail_url"] == "https://remote.io/remote-software-development-jobs/senior-eng-at-acme-12345"
        assert result[0]["title_hint"] == "Senior Engineer"
        assert result[1]["detail_url"] == "https://remote.io/remote-data-jobs/data-analyst-at-bigco-67890"

    @pytest.mark.asyncio
    async def test_extract_job_links_empty(self, scraper) -> None:
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[])

        result = await scraper._extract_job_links(mock_page)
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_job_links_error(self, scraper) -> None:
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=Exception("JS error"))

        result = await scraper._extract_job_links(mock_page)
        assert result == []

    # --- JSON-LD extraction ---

    @pytest.mark.asyncio
    async def test_extract_json_ld_success(self, scraper) -> None:
        job_posting = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Senior Engineer",
            "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
            "datePosted": "2026-03-10",
        }
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[json.dumps(job_posting)])

        result = await scraper._extract_json_ld(mock_page)
        assert result is not None
        assert result["title"] == "Senior Engineer"
        assert result["hiringOrganization"]["name"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_extract_json_ld_no_job_posting(self, scraper) -> None:
        other_ld = {"@context": "https://schema.org", "@type": "Organization", "name": "Foo"}
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[json.dumps(other_ld)])

        result = await scraper._extract_json_ld(mock_page)
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_json_ld_array_format(self, scraper) -> None:
        """JSON-LD can be an array of objects."""
        job_posting = [
            {"@type": "Organization", "name": "Foo"},
            {"@type": "JobPosting", "title": "Dev"},
        ]
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[json.dumps(job_posting)])

        result = await scraper._extract_json_ld(mock_page)
        assert result is not None
        assert result["title"] == "Dev"

    @pytest.mark.asyncio
    async def test_extract_json_ld_empty(self, scraper) -> None:
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[])

        result = await scraper._extract_json_ld(mock_page)
        assert result is None

    # --- Detail page ---

    @pytest.mark.asyncio
    async def test_scrape_detail_page_with_json_ld(self, scraper) -> None:
        """Full detail page extraction using JSON-LD."""
        json_ld = {
            "@type": "JobPosting",
            "title": "Principal Engineer",
            "hiringOrganization": {"@type": "Organization", "name": "TechCo"},
            "applicantLocationRequirements": {"name": "Remote"},
            "jobLocationType": "TELECOMMUTE",
            "datePosted": "2026-03-10",
        }

        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html>detail</html>")

        with (
            patch.object(scraper, "_navigate_with_retry", new_callable=AsyncMock),
            patch.object(
                scraper, "_extract_json_ld",
                new_callable=AsyncMock, return_value=json_ld,
            ),
            patch.object(
                scraper, "_extract_description",
                new_callable=AsyncMock, return_value="Full job description here.",
            ),
        ):
            link_info = {
                "detail_url": "https://remote.io/remote-software-development-jobs/principal-eng-at-techco-99999",
                "title_hint": "Principal Engineer",
            }
            result = await scraper._scrape_detail_page(mock_page, link_info)

        assert result is not None
        assert result.source == "remote_io"
        assert result.title == "Principal Engineer"
        assert result.company == "TechCo"
        assert result.description == "Full job description here."
        assert result.location_raw == "Remote — TELECOMMUTE"
        assert result.posted_date_raw == "2026-03-10"
        assert result.raw_html == "<html>detail</html>"

    @pytest.mark.asyncio
    async def test_scrape_detail_page_no_json_ld_fallback(self, scraper) -> None:
        """Falls back to URL parsing when JSON-LD is unavailable."""
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html>basic</html>")

        with (
            patch.object(scraper, "_navigate_with_retry", new_callable=AsyncMock),
            patch.object(
                scraper, "_extract_json_ld",
                new_callable=AsyncMock, return_value=None,
            ),
            patch.object(
                scraper, "_extract_description",
                new_callable=AsyncMock, return_value="Some description.",
            ),
        ):
            link_info = {
                "detail_url": "https://remote.io/remote-data-jobs/analyst-at-big-corp-12345",
                "title_hint": "Data Analyst",
            }
            result = await scraper._scrape_detail_page(mock_page, link_info)

        assert result is not None
        assert result.title == "Data Analyst"
        assert result.company == "Big Corp"

    @pytest.mark.asyncio
    async def test_scrape_detail_page_timeout(self, scraper) -> None:
        mock_page = AsyncMock()

        with patch.object(
            scraper, "_navigate_with_retry", new_callable=AsyncMock,
            side_effect=ScraperTimeoutError("remote_io", "timeout"),
        ):
            link_info = {"detail_url": "https://remote.io/remote-jobs/eng-at-co-1", "title_hint": "Eng"}
            result = await scraper._scrape_detail_page(mock_page, link_info)

        assert result is None

    # --- Profile / scrape integration ---

    @pytest.mark.asyncio
    async def test_scrape_no_profiles(self, secrets_no_apify) -> None:
        """Empty profiles list returns empty results."""
        config = RemoteIoConfig(enabled=True, delay_seconds=0, search_profiles=[])
        scraper = RemoteIoScraper(config, secrets_no_apify)
        results = await scraper.scrape()
        assert results == []

    @pytest.mark.asyncio
    async def test_page1_empty_warns(self, scraper, caplog) -> None:
        """Empty page 1 logs warning but continues (failure isolation)."""
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.close = AsyncMock()

        with (
            patch.object(scraper, "_create_context", new_callable=AsyncMock, return_value=mock_context),
            patch.object(scraper, "_navigate_with_retry", new_callable=AsyncMock),
            patch.object(scraper, "_extract_job_links", new_callable=AsyncMock, return_value=[]),
            patch("jobhunter.scrapers.remote_io.async_playwright") as mock_pw,
        ):
            mock_chromium = AsyncMock(launch=AsyncMock(return_value=mock_browser))
            mock_pw.return_value.__aenter__ = AsyncMock(
                return_value=AsyncMock(chromium=mock_chromium)
            )
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await scraper.scrape()
            assert results == []
            assert "No job links found on page 1" in caplog.text

    @pytest.mark.asyncio
    async def test_multi_profile_dedup(self, secrets_no_apify) -> None:
        """Same job from two profiles is deduplicated by source_url."""
        from jobhunter.scrapers.base import RawJobData

        profiles = [
            RemoteIoSearchProfile(label="Python", url="https://remote.io/python", max_pages=1),
            RemoteIoSearchProfile(label="DevOps", url="https://remote.io/devops", max_pages=1),
        ]
        config = RemoteIoConfig(enabled=True, delay_seconds=0, search_profiles=profiles)
        scraper = RemoteIoScraper(config, secrets_no_apify)

        shared_job = RawJobData(
            source="remote_io",
            source_url="https://remote.io/job/shared",
            title="Shared",
            company="Co",
            description="Shared job",
        )
        unique_job = RawJobData(
            source="remote_io",
            source_url="https://remote.io/job/unique",
            title="Unique",
            company="Co2",
            description="Only in P2",
        )

        call_count = 0

        async def mock_scrape_profile(page, profile):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [shared_job]
            return [shared_job, unique_job]

        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.close = AsyncMock()

        with (
            patch.object(scraper, "_create_context", new_callable=AsyncMock, return_value=mock_context),
            patch.object(scraper, "_scrape_profile", side_effect=mock_scrape_profile),
            patch("jobhunter.scrapers.remote_io.async_playwright") as mock_pw,
        ):
            mock_chromium = AsyncMock(launch=AsyncMock(return_value=mock_browser))
            mock_pw.return_value.__aenter__ = AsyncMock(
                return_value=AsyncMock(chromium=mock_chromium)
            )
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await scraper.scrape()

        assert len(results) == 2  # shared + unique, not 3
        urls = {r.source_url for r in results}
        assert "https://remote.io/job/shared" in urls
        assert "https://remote.io/job/unique" in urls

    @pytest.mark.asyncio
    async def test_profile_failure_isolation(self, secrets_no_apify) -> None:
        """One profile failing doesn't stop others."""
        from jobhunter.scrapers.base import RawJobData

        profiles = [
            RemoteIoSearchProfile(label="Fails", url="https://remote.io/fail", max_pages=1),
            RemoteIoSearchProfile(label="Works", url="https://remote.io/work", max_pages=1),
        ]
        config = RemoteIoConfig(enabled=True, delay_seconds=0, search_profiles=profiles)
        scraper = RemoteIoScraper(config, secrets_no_apify)

        good_job = RawJobData(
            source="remote_io",
            source_url="https://remote.io/job/good",
            title="Good",
            company="GoodCo",
            description="Working",
        )

        call_count = 0

        async def mock_scrape_profile(page, profile):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ScraperTimeoutError("remote_io", "Timeout")
            return [good_job]

        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.close = AsyncMock()

        with (
            patch.object(scraper, "_create_context", new_callable=AsyncMock, return_value=mock_context),
            patch.object(scraper, "_scrape_profile", side_effect=mock_scrape_profile),
            patch("jobhunter.scrapers.remote_io.async_playwright") as mock_pw,
        ):
            mock_chromium = AsyncMock(launch=AsyncMock(return_value=mock_browser))
            mock_pw.return_value.__aenter__ = AsyncMock(
                return_value=AsyncMock(chromium=mock_chromium)
            )
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await scraper.scrape()

        assert len(results) == 1
        assert results[0].title == "Good"
