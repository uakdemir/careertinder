import asyncio

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

from jobhunter.config.schema import RemoteIoSearchProfile
from jobhunter.scrapers.base import BaseScraper, RawJobData
from jobhunter.scrapers.exceptions import ScraperStructureError, ScraperTimeoutError
from jobhunter.scrapers.rate_limiter import RateLimiter


class RemoteIoScraper(BaseScraper):
    """C2a — Remote.io scraper using Playwright browser automation.

    Supports multi-profile search: each profile has its own URL and max_pages.
    Single browser instance shared across all profiles.
    """

    @property
    def scraper_name(self) -> str:
        return "remote_io"

    async def scrape(self) -> list[RawJobData]:
        """Scrape all search profiles with a shared browser instance."""
        profiles = self._config.search_profiles  # type: ignore[attr-defined]
        if not profiles:
            self._logger.warning("No search profiles configured for Remote.io")
            return []

        all_results: list[RawJobData] = []
        seen_urls: set[str] = set()

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await self._create_context(browser)
            page = await context.new_page()

            try:
                for profile in profiles:
                    try:
                        profile_results = await self._scrape_profile(page, profile)
                        for job in profile_results:
                            if job.source_url not in seen_urls:
                                seen_urls.add(job.source_url)
                                all_results.append(job)
                            else:
                                self._logger.debug(
                                    "Dedup: %s (profile: %s)", job.source_url, profile.label
                                )
                    except Exception as e:
                        self._logger.error("Profile '%s' failed: %s", profile.label, e)
            finally:
                await browser.close()

        self._logger.info("Remote.io scrape complete: %d jobs found", len(all_results))
        return all_results

    async def _scrape_profile(
        self, page: Page, profile: RemoteIoSearchProfile
    ) -> list[RawJobData]:
        """Scrape a single search profile using a shared browser page."""
        results: list[RawJobData] = []
        rate_limiter = RateLimiter(self._config.delay_seconds)  # type: ignore[attr-defined]

        for page_num in range(1, profile.max_pages + 1):
            url = self._build_listing_url(profile.url, page_num)
            self._logger.info(
                "Scraping '%s' page %d: %s", profile.label, page_num, url
            )

            await self._navigate_with_retry(page, url)
            job_cards = await self._extract_job_cards(page)

            if not job_cards:
                if page_num == 1:
                    raise ScraperStructureError(
                        self.scraper_name,
                        f"No job cards found on page 1 for profile '{profile.label}'. "
                        "CSS selectors may need updating.",
                    )
                self._logger.info(
                    "No job cards found on page %d — stopping pagination", page_num
                )
                break

            for card in job_cards:
                await rate_limiter.wait()
                detail = await self._scrape_detail_page(page, card)
                if detail:
                    results.append(detail)

            await rate_limiter.wait()

        self._logger.info(
            "Profile '%s': %d jobs found", profile.label, len(results)
        )
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

    @staticmethod
    def _build_listing_url(base_url: str, page_num: int) -> str:
        """Build paginated listing URL."""
        if page_num == 1:
            return base_url
        return f"{base_url}?page={page_num}"

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
        profiles = self._config.search_profiles  # type: ignore[attr-defined]
        if not profiles:
            return False
        browser = None
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(profiles[0].url, timeout=15000)
                title = await page.title()
                return bool(title)
        except Exception:
            return False
        finally:
            if browser:
                await browser.close()
