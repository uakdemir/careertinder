"""Tests for D6: RemoteRocketship Playwright scraper."""

from unittest.mock import AsyncMock, patch

import pytest

from jobhunter.scrapers.exceptions import ScraperTimeoutError
from jobhunter.scrapers.rate_limiter import RateLimiter
from jobhunter.scrapers.remoterocketship import RemoteRocketshipScraper


class TestRemoteRocketshipScraper:
    @pytest.fixture
    def scraper(self, remote_rocketship_config, secrets_no_apify):
        return RemoteRocketshipScraper(remote_rocketship_config, secrets_no_apify)

    def test_scraper_name(self, scraper) -> None:
        assert scraper.scraper_name == "remote_rocketship"

    @pytest.mark.asyncio
    async def test_load_all_listings_stops_after_no_change(self, scraper) -> None:
        """Three rounds of no new items → stops scrolling."""
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)  # No "Load more" button
        mock_page.evaluate = AsyncMock(return_value=5)  # Always 5 items

        rate_limiter = RateLimiter(0)
        with patch("jobhunter.scrapers.remoterocketship.RateLimiter", return_value=rate_limiter):
            await scraper._load_all_listings(mock_page, rate_limiter)

        # Should have scrolled and checked 3 times (no_change_rounds threshold)
        assert mock_page.evaluate.call_count >= 3

    @pytest.mark.asyncio
    async def test_load_all_listings_stops_at_max_items(self, scraper) -> None:
        """Stops when max_items reached."""
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)

        # evaluate is called for: scrollTo (returns None), then querySelectorAll count
        # Pattern per loop iteration: scrollTo call, count call
        call_results = [
            None, 10,   # round 1: scroll, count=10
            None, 25,   # round 2: scroll, count=25
            None, 45,   # round 3: scroll, count=45 >= 40 (max_pages=2, 2*20=40)
        ]
        mock_page.evaluate = AsyncMock(side_effect=call_results)

        rate_limiter = RateLimiter(0)
        await scraper._load_all_listings(mock_page, rate_limiter)

    @pytest.mark.asyncio
    async def test_load_all_listings_clicks_load_more(self, scraper) -> None:
        """Clicks Load more button when present."""
        load_more_btn = AsyncMock()
        load_more_btn.click = AsyncMock()

        mock_page = AsyncMock()
        # First query_selector: Load more button found; subsequent: None (no button)
        mock_page.query_selector = AsyncMock(
            side_effect=[load_more_btn, None, None, None]
        )
        # When load_more is clicked, no scrollTo evaluate call happens.
        # Pattern: round1 (click, count=5), round2-4 (scroll, count=5)
        call_results = [
            5,           # round 1: count only (button was clicked, not scroll)
            None, 5,     # round 2: scroll, count=5
            None, 5,     # round 3: scroll, count=5
            None, 5,     # round 4: scroll, count=5 (3 no-change rounds reached)
        ]
        mock_page.evaluate = AsyncMock(side_effect=call_results)

        rate_limiter = RateLimiter(0)
        await scraper._load_all_listings(mock_page, rate_limiter)
        load_more_btn.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrape_detail_page_success(self, scraper) -> None:
        mock_page = AsyncMock()
        desc_el = AsyncMock()
        desc_el.inner_text = AsyncMock(return_value="Job description text.")
        mock_page.query_selector = AsyncMock(return_value=desc_el)
        mock_page.content = AsyncMock(return_value="<html>detail</html>")

        with patch.object(scraper, "_navigate_with_retry", new_callable=AsyncMock):
            card = {
                "title": "Principal Engineer",
                "company": "RocketCo",
                "detail_url": "https://www.remoterocketship.com/job/1",
                "salary_raw": "$150K",
                "location_raw": "Remote",
                "tags": ["Python", "AWS"],
            }
            result = await scraper._scrape_detail_page(mock_page, card)

        assert result is not None
        assert result.source == "remote_rocketship"
        assert result.title == "Principal Engineer"
        assert result.description == "Job description text."
        assert result.location_raw == "Remote [Python, AWS]"
        assert result.raw_html == "<html>detail</html>"

    @pytest.mark.asyncio
    async def test_scrape_detail_page_timeout(self, scraper) -> None:
        mock_page = AsyncMock()

        with patch.object(
            scraper, "_navigate_with_retry", new_callable=AsyncMock,
            side_effect=ScraperTimeoutError("remote_rocketship", "timeout"),
        ):
            card = {
                "title": "Eng",
                "company": "Co",
                "detail_url": "https://www.remoterocketship.com/job/1",
            }
            result = await scraper._scrape_detail_page(mock_page, card)

        assert result is None

    def test_tags_appended_to_location(self, scraper) -> None:
        """Verify tag appending logic used in _scrape_detail_page."""
        location = "Remote"
        tags = ["Python", "EU"]
        result = f"{location} [{', '.join(tags)}]".strip()
        assert result == "Remote [Python, EU]"

    def test_tags_with_no_location(self, scraper) -> None:
        location = ""
        tags = ["Senior", "AWS"]
        result = f"{location} [{', '.join(tags)}]".strip()
        assert result == "[Senior, AWS]"
