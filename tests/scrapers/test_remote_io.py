"""Tests for D5: Remote.io Playwright scraper."""

from unittest.mock import AsyncMock, patch

import pytest

from jobhunter.scrapers.exceptions import ScraperTimeoutError
from jobhunter.scrapers.remote_io import RemoteIoScraper


class TestRemoteIoScraper:
    @pytest.fixture
    def scraper(self, remote_io_config, secrets_no_apify):
        return RemoteIoScraper(remote_io_config, secrets_no_apify)

    def test_scraper_name(self, scraper) -> None:
        assert scraper.scraper_name == "remote_io"

    def test_build_listing_url_page1(self, scraper) -> None:
        url = scraper._build_listing_url(1)
        assert url == "https://remote.io/remote-jobs"
        assert "?page=" not in url

    def test_build_listing_url_page2(self, scraper) -> None:
        url = scraper._build_listing_url(2)
        assert url == "https://remote.io/remote-jobs?page=2"

    def test_build_listing_url_page5(self, scraper) -> None:
        url = scraper._build_listing_url(5)
        assert url == "https://remote.io/remote-jobs?page=5"

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

    @pytest.mark.asyncio
    async def test_extract_job_cards(self, scraper) -> None:
        """Mock Playwright page with job card elements."""

        def _make_card(title: str, company: str, href: str, salary: str | None = None):
            card = AsyncMock()

            title_el = AsyncMock()
            title_el.inner_text = AsyncMock(return_value=title)
            company_el = AsyncMock()
            company_el.inner_text = AsyncMock(return_value=company)
            link_el = AsyncMock()
            link_el.get_attribute = AsyncMock(return_value=href)

            if salary:
                salary_el = AsyncMock()
                salary_el.inner_text = AsyncMock(return_value=salary)
            else:
                salary_el = None

            # Map selectors to elements using ordered checks
            selector_map: list[tuple[str, AsyncMock | None]] = []
            # Title selectors
            selector_map.append(("h2", title_el))
            # Company selectors
            selector_map.append(("company-name", company_el))
            # Link selectors
            selector_map.append(("href", link_el))
            # Salary selectors
            selector_map.append(("salary", salary_el))

            async def _qs(selector):
                for key, el in selector_map:
                    if key in selector:
                        return el
                return None

            card.query_selector = _qs
            return card

        cards = [
            _make_card("Senior Architect", "TechCo", "/job/senior-architect", "$150K"),
            _make_card("Lead Dev", "StartupCo", "https://remote.io/job/lead-dev"),
        ]

        mock_page = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=cards)

        result = await scraper._extract_job_cards(mock_page)
        assert len(result) == 2
        assert result[0]["title"] == "Senior Architect"
        assert result[0]["company"] == "TechCo"
        assert result[0]["detail_url"] == "https://remote.io/job/senior-architect"
        assert result[1]["detail_url"] == "https://remote.io/job/lead-dev"

    @pytest.mark.asyncio
    async def test_extract_job_cards_empty(self, scraper) -> None:
        mock_page = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[])

        result = await scraper._extract_job_cards(mock_page)
        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_detail_page_success(self, scraper) -> None:
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        desc_el = AsyncMock()
        desc_el.inner_text = AsyncMock(return_value="Full job description here.")
        mock_page.query_selector = AsyncMock(return_value=desc_el)
        mock_page.content = AsyncMock(return_value="<html>raw</html>")

        card = {
            "title": "Engineer",
            "company": "Co",
            "detail_url": "https://remote.io/job/1",
            "salary_raw": "$100K",
            "location_raw": "Remote",
        }

        result = await scraper._scrape_detail_page(mock_page, card)
        assert result is not None
        assert result.source == "remote_io"
        assert result.title == "Engineer"
        assert result.description == "Full job description here."
        assert result.raw_html == "<html>raw</html>"

    @pytest.mark.asyncio
    async def test_scrape_detail_page_timeout(self, scraper) -> None:
        mock_page = AsyncMock()

        with patch.object(
            scraper, "_navigate_with_retry", new_callable=AsyncMock,
            side_effect=ScraperTimeoutError("remote_io", "timeout"),
        ):
            card = {"title": "Eng", "company": "Co", "detail_url": "https://remote.io/job/1"}
            result = await scraper._scrape_detail_page(mock_page, card)

        assert result is None
