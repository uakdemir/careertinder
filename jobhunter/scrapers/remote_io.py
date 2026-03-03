import asyncio

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

from jobhunter.scrapers.base import BaseScraper, RawJobData
from jobhunter.scrapers.exceptions import ScraperTimeoutError
from jobhunter.scrapers.rate_limiter import RateLimiter


class RemoteIoScraper(BaseScraper):
    """C2a — Remote.io scraper using Playwright browser automation."""

    @property
    def scraper_name(self) -> str:
        return "remote_io"

    async def scrape(self) -> list[RawJobData]:
        """Scrape Remote.io job listings with pagination."""
        results: list[RawJobData] = []
        rate_limiter = RateLimiter(self._config.delay_seconds)  # type: ignore[attr-defined]

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await self._create_context(browser)
            page = await context.new_page()

            try:
                for page_num in range(1, self._config.max_pages + 1):  # type: ignore[attr-defined]
                    url = self._build_listing_url(page_num)
                    self._logger.info("Scraping listing page %d: %s", page_num, url)

                    await self._navigate_with_retry(page, url)
                    job_cards = await self._extract_job_cards(page)

                    if not job_cards:
                        self._logger.info("No job cards found on page %d — stopping pagination", page_num)
                        break

                    for card in job_cards:
                        await rate_limiter.wait()
                        detail = await self._scrape_detail_page(page, card)
                        if detail:
                            results.append(detail)

                    await rate_limiter.wait()
            finally:
                await browser.close()

        self._logger.info("Remote.io scrape complete: %d jobs found", len(results))
        return results

    async def _create_context(self, browser: Browser) -> BrowserContext:
        """Create browser context with realistic settings."""
        return await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )

    def _build_listing_url(self, page_num: int) -> str:
        """Build paginated listing URL."""
        base: str = self._config.base_url  # type: ignore[attr-defined]
        if page_num == 1:
            return base
        return f"{base}?page={page_num}"

    async def _navigate_with_retry(self, page: Page, url: str, max_retries: int = 2) -> None:
        """Navigate to URL with retry on timeout."""
        for attempt in range(max_retries + 1):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                return
            except PlaywrightTimeout:
                if attempt == max_retries:
                    raise ScraperTimeoutError(
                        self.scraper_name, f"Timeout loading {url} after {max_retries + 1} attempts"
                    ) from None
                self._logger.warning("Timeout loading %s (attempt %d/%d)", url, attempt + 1, max_retries + 1)
                await asyncio.sleep(2**attempt)

    async def _extract_job_cards(self, page: Page) -> list[dict]:
        """Extract job card data from listing page.

        NOTE: CSS selectors are placeholders — finalize with live site inspection.
        """
        cards = await page.query_selector_all("[data-testid='job-card'], .job-card, .job-listing")
        results: list[dict] = []

        for card in cards:
            title_el = await card.query_selector("h2, h3, .job-title, [data-testid='job-title']")
            company_el = await card.query_selector(".company-name, [data-testid='company-name']")
            link_el = await card.query_selector("a[href*='/job/'], a[href*='/remote-']")

            title = await title_el.inner_text() if title_el else None
            company = await company_el.inner_text() if company_el else None
            href = await link_el.get_attribute("href") if link_el else None

            if title and company and href:
                salary_el = await card.query_selector(".salary, [data-testid='salary']")
                location_el = await card.query_selector(".location, [data-testid='location']")

                results.append({
                    "title": title.strip(),
                    "company": company.strip(),
                    "salary_raw": (await salary_el.inner_text()).strip() if salary_el else None,
                    "location_raw": (await location_el.inner_text()).strip() if location_el else None,
                    "detail_url": href if href.startswith("http") else f"https://remote.io{href}",
                })

        return results

    async def _scrape_detail_page(self, page: Page, card: dict) -> RawJobData | None:
        """Navigate to job detail page and extract full description."""
        try:
            await self._navigate_with_retry(page, card["detail_url"])

            description_el = await page.query_selector(
                ".job-description, [data-testid='job-description'], article, .description"
            )
            description = await description_el.inner_text() if description_el else ""
            raw_html = await page.content()

            return RawJobData(
                source="remote_io",
                source_url=card["detail_url"],
                title=card["title"],
                company=card["company"],
                description=description.strip(),
                salary_raw=card.get("salary_raw"),
                location_raw=card.get("location_raw"),
                raw_html=raw_html,
            )
        except ScraperTimeoutError:
            self._logger.warning("Timeout on detail page %s — skipping", card["detail_url"])
            return None
        except Exception as e:
            self._logger.error("Error scraping detail page %s: %s", card["detail_url"], e)
            return None

    async def health_check(self) -> bool:
        """Check if Remote.io is reachable."""
        browser = None
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(self._config.base_url, timeout=15000)  # type: ignore[attr-defined]
                title = await page.title()
                return bool(title)
        except Exception:
            return False
        finally:
            if browser:
                await browser.close()
