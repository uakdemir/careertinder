import asyncio
from abc import abstractmethod

import httpx
from pydantic import BaseModel

from jobhunter.config.schema import SecretsConfig
from jobhunter.scrapers.base import BaseScraper, RawJobData
from jobhunter.scrapers.exceptions import ScraperError, ScraperQuotaError, ScraperTimeoutError


class ApifyBaseScraper(BaseScraper):
    """Shared base for Apify REST API scrapers (C2c, C2d).

    Implements the full Apify actor run lifecycle:
    1. POST /v2/acts/{actorId}/runs — start actor with input params
    2. GET /v2/actor-runs/{runId} — poll until SUCCEEDED or FAILED
    3. GET /v2/datasets/{datasetId}/items — retrieve results
    """

    APIFY_BASE_URL = "https://api.apify.com"
    POLL_INTERVAL_SECONDS = 5.0
    POLL_MAX_WAIT_SECONDS = 300.0

    def __init__(self, config: BaseModel, secrets: SecretsConfig) -> None:
        super().__init__(config, secrets)
        self._actor_id: str = config.apify_actor_id  # type: ignore[attr-defined]
        self._max_results: int = config.max_results  # type: ignore[attr-defined]
        self._client: httpx.AsyncClient | None = None

    async def scrape(self) -> list[RawJobData]:
        """Execute the full Apify actor lifecycle."""
        token = self._secrets.apify_api_token
        if not token:
            raise ScraperQuotaError(self.scraper_name, "APIFY_API_TOKEN not set in .env")

        async with httpx.AsyncClient(
            base_url=self.APIFY_BASE_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        ) as client:
            self._client = client
            run_id = await self._start_actor_run()
            dataset_id = await self._poll_until_complete(run_id)
            items = await self._get_dataset_items(dataset_id)
            results = []
            for item in items:
                parsed = self._parse_item(item)
                if parsed is not None:
                    results.append(parsed)
            return results

    async def _start_actor_run(self) -> str:
        """POST /v2/acts/{actorId}/runs. Returns run ID."""
        assert self._client is not None
        actor_input = self._build_actor_input()
        resp = await self._client.post(
            f"/v2/acts/{self._actor_id}/runs",
            json=actor_input,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        run_id: str = data["id"]
        self._logger.info("Actor run started: %s (run_id=%s)", self._actor_id, run_id)
        return run_id

    async def _poll_until_complete(self, run_id: str) -> str:
        """Poll run status with exponential backoff. Returns dataset ID."""
        assert self._client is not None
        elapsed = 0.0
        interval = self.POLL_INTERVAL_SECONDS

        while elapsed < self.POLL_MAX_WAIT_SECONDS:
            await asyncio.sleep(interval)
            elapsed += interval

            resp = await self._client.get(f"/v2/actor-runs/{run_id}")
            resp.raise_for_status()
            data = resp.json()["data"]
            status = data["status"]

            if status == "SUCCEEDED":
                dataset_id = data.get("defaultDatasetId")
                if not dataset_id:
                    raise ScraperError(
                        self.scraper_name,
                        f"Actor run succeeded but defaultDatasetId missing (run={run_id})",
                    )
                self._logger.info("Actor run succeeded (dataset=%s)", dataset_id)
                return str(dataset_id)
            elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise ScraperError(
                    self.scraper_name, f"Actor run {status}: {data.get('statusMessage', '')}"
                )

            # Exponential backoff: 5s, 7.5s, 11.25s, ... capped at 30s
            interval = min(interval * 1.5, 30.0)

        raise ScraperTimeoutError(
            self.scraper_name, f"Actor run {run_id} did not complete within {self.POLL_MAX_WAIT_SECONDS}s"
        )

    async def _get_dataset_items(self, dataset_id: str) -> list[dict]:
        """GET /v2/datasets/{datasetId}/items. Returns raw JSON items."""
        assert self._client is not None
        resp = await self._client.get(
            f"/v2/datasets/{dataset_id}/items",
            params={"limit": self._max_results},
        )
        resp.raise_for_status()
        items: list[dict] = resp.json()
        self._logger.info("Retrieved %d items from dataset %s", len(items), dataset_id)
        return items

    async def health_check(self) -> bool:
        """Check Apify API connectivity and token validity."""
        token = self._secrets.apify_api_token
        if not token:
            return False
        try:
            async with httpx.AsyncClient(
                base_url=self.APIFY_BASE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            ) as client:
                resp = await client.get("/v2/users/me")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    @abstractmethod
    def _build_actor_input(self) -> dict:
        """Build actor-specific input parameters. Implemented by subclass."""

    @abstractmethod
    def _parse_item(self, item: dict) -> RawJobData | None:
        """Parse one Apify result item. Return None to skip invalid items."""
