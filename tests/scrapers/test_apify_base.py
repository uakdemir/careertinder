"""Tests for D2: ApifyBaseScraper lifecycle (start, poll, retrieve)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from jobhunter.scrapers.apify_base import ApifyBaseScraper
from jobhunter.scrapers.base import RawJobData
from jobhunter.scrapers.exceptions import ScraperError, ScraperQuotaError, ScraperTimeoutError


class ConcreteApifyScraper(ApifyBaseScraper):
    """Concrete implementation for testing the ABC."""

    @property
    def scraper_name(self) -> str:
        return "test_apify"

    def _build_actor_input(self) -> dict:
        return {"keyword": "test", "maxItems": 10}

    def _parse_item(self, item: dict) -> RawJobData | None:
        title = item.get("title")
        company = item.get("company")
        if not title or not company:
            return None
        return RawJobData(
            source="test_apify",
            source_url=item.get("url", ""),
            title=title,
            company=company,
            description=item.get("description", ""),
        )


def _make_response(json_data: dict | list, status_code: int = 200) -> httpx.Response:
    """Create a mock httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "https://api.apify.com/test"),
    )


class TestApifyBaseScraper:
    @pytest.fixture
    def scraper(self, wellfound_config, secrets_with_apify):
        return ConcreteApifyScraper(wellfound_config, secrets_with_apify)

    @pytest.mark.asyncio
    async def test_scrape_without_token(self, wellfound_config, secrets_no_apify) -> None:
        scraper = ConcreteApifyScraper(wellfound_config, secrets_no_apify)
        with pytest.raises(ScraperQuotaError, match="APIFY_API_TOKEN"):
            await scraper.scrape()

    @pytest.mark.asyncio
    async def test_start_actor_run_success(self, scraper) -> None:
        mock_client = AsyncMock()
        mock_client.post.return_value = _make_response({"data": {"id": "run123"}})
        scraper._client = mock_client

        run_id = await scraper._start_actor_run()
        assert run_id == "run123"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_until_complete_success(self, scraper) -> None:
        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            _make_response({"data": {"status": "RUNNING"}}),
            _make_response({"data": {"status": "RUNNING"}}),
            _make_response({"data": {"status": "SUCCEEDED", "defaultDatasetId": "ds456"}}),
        ]
        scraper._client = mock_client

        with patch("jobhunter.scrapers.apify_base.asyncio.sleep", new_callable=AsyncMock):
            dataset_id = await scraper._poll_until_complete("run123")

        assert dataset_id == "ds456"

    @pytest.mark.asyncio
    async def test_poll_until_complete_missing_dataset_id(self, scraper) -> None:
        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(
            {"data": {"status": "SUCCEEDED", "defaultDatasetId": None}}
        )
        scraper._client = mock_client

        with patch("jobhunter.scrapers.apify_base.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ScraperError, match="defaultDatasetId missing"):
                await scraper._poll_until_complete("run123")

    @pytest.mark.asyncio
    async def test_poll_until_complete_failed(self, scraper) -> None:
        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(
            {"data": {"status": "FAILED", "statusMessage": "Actor crashed"}}
        )
        scraper._client = mock_client

        with patch("jobhunter.scrapers.apify_base.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ScraperError, match="FAILED"):
                await scraper._poll_until_complete("run123")

    @pytest.mark.asyncio
    async def test_poll_until_complete_timeout(self, scraper) -> None:
        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response({"data": {"status": "RUNNING"}})
        scraper._client = mock_client
        scraper.POLL_MAX_WAIT_SECONDS = 1.0
        scraper.POLL_INTERVAL_SECONDS = 0.5

        with patch("jobhunter.scrapers.apify_base.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ScraperTimeoutError, match="did not complete"):
                await scraper._poll_until_complete("run123")

    @pytest.mark.asyncio
    async def test_get_dataset_items(self, scraper) -> None:
        items = [{"title": "Job1", "company": "Co1"}, {"title": "Job2", "company": "Co2"}]
        mock_client = AsyncMock()
        mock_client.get.return_value = _make_response(items)
        scraper._client = mock_client

        result = await scraper._get_dataset_items("ds456")
        assert len(result) == 2
        assert result[0]["title"] == "Job1"

    @pytest.mark.asyncio
    async def test_health_check_valid_token(self, scraper) -> None:
        with patch("jobhunter.scrapers.apify_base.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = _make_response({"data": {"username": "test"}})
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await scraper.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_invalid_token(self, scraper) -> None:
        with patch("jobhunter.scrapers.apify_base.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = _make_response({"error": "Unauthorized"}, status_code=401)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await scraper.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_health_check_no_token(self, wellfound_config, secrets_no_apify) -> None:
        scraper = ConcreteApifyScraper(wellfound_config, secrets_no_apify)
        result = await scraper.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_scrape_end_to_end(self, scraper) -> None:
        """Full lifecycle: start → poll → retrieve → parse."""
        items = [
            {"title": "Eng", "company": "Co", "url": "https://example.com/1", "description": "Build things"},
            {"title": None, "company": "Co", "url": "https://example.com/2", "description": "Skip me"},
        ]

        with patch.object(scraper, "_start_actor_run", new_callable=AsyncMock, return_value="run1"):
            with patch.object(scraper, "_poll_until_complete", new_callable=AsyncMock, return_value="ds1"):
                with patch.object(scraper, "_get_dataset_items", new_callable=AsyncMock, return_value=items):
                    # Need to set _client to something non-None for the context manager
                    with patch("jobhunter.scrapers.apify_base.httpx.AsyncClient") as mock_cls:
                        mock_client = AsyncMock()
                        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                        mock_client.__aexit__ = AsyncMock(return_value=False)
                        mock_cls.return_value = mock_client

                        results = await scraper.scrape()

        assert len(results) == 1
        assert results[0].title == "Eng"
        assert results[0].company == "Co"
