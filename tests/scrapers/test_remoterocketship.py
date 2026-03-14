"""Tests for RemoteRocketship Playwright scraper (multi-profile, __NEXT_DATA__ extraction)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from jobhunter.config.schema import RemoteRocketshipConfig, RemoteRocketshipSearchProfile
from jobhunter.scrapers.exceptions import ScraperTimeoutError
from jobhunter.scrapers.remoterocketship import RemoteRocketshipScraper


class TestRemoteRocketshipScraper:
    @pytest.fixture
    def scraper(self, remote_rocketship_config, secrets_no_apify):
        return RemoteRocketshipScraper(remote_rocketship_config, secrets_no_apify)

    def test_scraper_name(self, scraper) -> None:
        assert scraper.scraper_name == "remote_rocketship"

    # --- URL page parameter ---

    def test_set_page_param_adds_page(self) -> None:
        url = "https://www.remoterocketship.com/?sort=DateAdded&minSalary=90000"
        result = RemoteRocketshipScraper._set_page_param(url, 3)
        assert "page=3" in result
        assert "sort=DateAdded" in result

    def test_set_page_param_replaces_existing(self) -> None:
        url = "https://www.remoterocketship.com/?page=1&sort=DateAdded"
        result = RemoteRocketshipScraper._set_page_param(url, 5)
        assert "page=5" in result
        assert "page=1" not in result

    # --- __NEXT_DATA__ extraction ---

    @pytest.mark.asyncio
    async def test_extract_jobs_from_json_success(self, scraper) -> None:
        """Extracts jobs from __NEXT_DATA__ pageProps.jobs array."""
        next_data = {
            "props": {
                "pageProps": {
                    "jobs": [
                        {
                            "roleTitle": "Senior Engineer",
                            "slug": "senior-engineer-remote",
                            "location": "United States",
                            "locationType": "remote",
                            "salaryRange": None,
                            "jobDescriptionSummary": "Build cool stuff.",
                            "company": {
                                "name": "Acme Corp",
                                "slug": "acme-corp",
                            },
                        },
                    ]
                }
            }
        }
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=json.dumps(next_data))

        results = await scraper._extract_jobs_from_json(mock_page)
        assert len(results) == 1
        assert results[0]["title"] == "Senior Engineer"
        assert results[0]["company"] == "Acme Corp"
        assert results[0]["detail_url"] == (
            "https://www.remoterocketship.com/company/acme-corp/jobs/senior-engineer-remote/"
        )
        assert results[0]["location_raw"] == "United States – remote"
        assert results[0]["summary"] == "Build cool stuff."

    @pytest.mark.asyncio
    async def test_extract_jobs_from_json_no_next_data(self, scraper) -> None:
        """Returns empty list when __NEXT_DATA__ script tag is missing."""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=None)

        results = await scraper._extract_jobs_from_json(mock_page)
        assert results == []

    @pytest.mark.asyncio
    async def test_extract_jobs_from_json_dehydrated_state(self, scraper) -> None:
        """Finds jobs in dehydratedState.queries fallback path."""
        next_data = {
            "props": {
                "pageProps": {
                    "dehydratedState": {
                        "queries": [
                            {
                                "state": {
                                    "data": [
                                        {
                                            "roleTitle": "DevOps Lead",
                                            "slug": "devops-lead-remote",
                                            "company": {"name": "Cloud Inc", "slug": "cloud-inc"},
                                            "location": "Remote",
                                            "locationType": "remote",
                                            "salaryRange": None,
                                            "jobDescriptionSummary": "Lead DevOps.",
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                }
            }
        }
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=json.dumps(next_data))

        results = await scraper._extract_jobs_from_json(mock_page)
        assert len(results) == 1
        assert results[0]["title"] == "DevOps Lead"

    # --- Salary extraction ---

    def test_extract_salary_none(self) -> None:
        assert RemoteRocketshipScraper._extract_salary({}) is None
        assert RemoteRocketshipScraper._extract_salary({"salaryRange": None}) is None

    def test_extract_salary_string(self) -> None:
        result = RemoteRocketshipScraper._extract_salary({"salaryRange": "$100K - $150K"})
        assert result == "$100K - $150K"

    def test_extract_salary_dict(self) -> None:
        job = {"salaryRange": {"min": 100000, "max": 150000, "currency": "USD"}}
        result = RemoteRocketshipScraper._extract_salary(job)
        assert result is not None
        assert "100,000" in result
        assert "150,000" in result

    # --- Detail page ---

    @pytest.mark.asyncio
    async def test_scrape_detail_page_success(self, scraper) -> None:
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html>detail</html>")

        # __NEXT_DATA__ extraction returns empty (force CSS fallback)
        with patch.object(
            scraper, "_extract_description_from_json",
            new_callable=AsyncMock, return_value="",
        ):
            desc_el = AsyncMock()
            desc_el.inner_text = AsyncMock(return_value="Job description text.")
            mock_page.query_selector = AsyncMock(return_value=desc_el)

            with patch.object(scraper, "_navigate_with_retry", new_callable=AsyncMock):
                job_info = {
                    "title": "Principal Engineer",
                    "company": "RocketCo",
                    "detail_url": "https://www.remoterocketship.com/company/rocketco/jobs/principal/",
                    "salary_raw": "$150K",
                    "location_raw": "Remote",
                    "summary": "Fallback summary.",
                }
                result = await scraper._scrape_detail_page(mock_page, job_info)

        assert result is not None
        assert result.source == "remote_rocketship"
        assert result.title == "Principal Engineer"
        assert result.description == "Job description text."
        assert result.location_raw == "Remote"
        assert result.raw_html == "<html>detail</html>"

    @pytest.mark.asyncio
    async def test_scrape_detail_page_timeout(self, scraper) -> None:
        mock_page = AsyncMock()

        with patch.object(
            scraper, "_navigate_with_retry", new_callable=AsyncMock,
            side_effect=ScraperTimeoutError("remote_rocketship", "timeout"),
        ):
            job_info = {
                "title": "Eng",
                "company": "Co",
                "detail_url": "https://www.remoterocketship.com/company/co/jobs/eng/",
            }
            result = await scraper._scrape_detail_page(mock_page, job_info)

        assert result is None

    @pytest.mark.asyncio
    async def test_scrape_detail_page_fallback_to_summary(self, scraper) -> None:
        """Falls back to search-page summary when no description found."""
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)  # No CSS description
        mock_page.content = AsyncMock(return_value="<html></html>")

        with (
            patch.object(scraper, "_navigate_with_retry", new_callable=AsyncMock),
            patch.object(
                scraper, "_extract_description_from_json",
                new_callable=AsyncMock, return_value="",
            ),
        ):
            job_info = {
                "title": "Eng",
                "company": "Co",
                "detail_url": "https://example.com/job/1",
                "summary": "Summary from search page.",
            }
            result = await scraper._scrape_detail_page(mock_page, job_info)

        assert result is not None
        assert result.description == "Summary from search page."

    # --- Profile / scrape integration ---

    @pytest.mark.asyncio
    async def test_scrape_no_profiles(self, secrets_no_apify) -> None:
        """Empty profiles list returns empty results."""
        config = RemoteRocketshipConfig(enabled=True, delay_seconds=0, search_profiles=[])
        scraper = RemoteRocketshipScraper(config, secrets_no_apify)
        results = await scraper.scrape()
        assert results == []

    @pytest.mark.asyncio
    async def test_scrape_profile_no_jobs(self, scraper, caplog) -> None:
        """No jobs from __NEXT_DATA__ → returns empty (no longer raises)."""
        mock_page = AsyncMock()

        with (
            patch.object(scraper, "_navigate_with_retry", new_callable=AsyncMock),
            patch.object(
                scraper, "_extract_jobs_from_json",
                new_callable=AsyncMock, return_value=[],
            ),
        ):
            profile = RemoteRocketshipSearchProfile(
                label="Empty", url="https://rrs.com/empty", max_pages=1
            )
            results = await scraper._scrape_profile(mock_page, profile)
            assert results == []
            assert "no jobs found" in caplog.text

    @pytest.mark.asyncio
    async def test_multi_profile_dedup(self, secrets_no_apify) -> None:
        """Same job from two profiles is deduplicated by source_url."""
        from jobhunter.scrapers.base import RawJobData

        profiles = [
            RemoteRocketshipSearchProfile(label="P1", url="https://rrs.com/python", max_pages=1),
            RemoteRocketshipSearchProfile(label="P2", url="https://rrs.com/devops", max_pages=1),
        ]
        config = RemoteRocketshipConfig(enabled=True, delay_seconds=0, search_profiles=profiles)
        scraper = RemoteRocketshipScraper(config, secrets_no_apify)

        shared_job = RawJobData(
            source="remote_rocketship",
            source_url="https://rrs.com/job/shared",
            title="Shared",
            company="Co",
            description="Shared job",
        )
        unique_job = RawJobData(
            source="remote_rocketship",
            source_url="https://rrs.com/job/unique",
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
            patch("jobhunter.scrapers.remoterocketship.async_playwright") as mock_pw,
        ):
            mock_chromium = AsyncMock(launch=AsyncMock(return_value=mock_browser))
            mock_pw.return_value.__aenter__ = AsyncMock(
                return_value=AsyncMock(chromium=mock_chromium)
            )
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await scraper.scrape()

        assert len(results) == 2
        urls = {r.source_url for r in results}
        assert "https://rrs.com/job/shared" in urls
        assert "https://rrs.com/job/unique" in urls
