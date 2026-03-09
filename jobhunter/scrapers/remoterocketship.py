import asyncio

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

from jobhunter.config.schema import RemoteRocketshipSearchProfile
from jobhunter.scrapers.base import BaseScraper, RawJobData
from jobhunter.scrapers.exceptions import ScraperStructureError, ScraperTimeoutError
from jobhunter.scrapers.rate_limiter import RateLimiter


class RemoteRocketshipScraper(BaseScraper):
    """C2b — RemoteRocketship scraper using Playwright browser automation.

    Supports multi-profile search: each profile has its own URL and max_pages.
    Single browser instance shared across all profiles.
    """

    @property
    def scraper_name(self) -> str:
        return "remote_rocketship"

    async def scrape(self) -> list[RawJobData]:
        """Scrape all search profiles with a shared browser instance."""
        profiles = self._config.search_profiles  # type: ignore[attr-defined]
        if not profiles:
            self._logger.warning("No search profiles configured for RemoteRocketship")
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

        self._logger.info("RemoteRocketship scrape complete: %d jobs found", len(all_results))
        return all_results

    async def _scrape_profile(
        self, page: Page, profile: RemoteRocketshipSearchProfile
    ) -> list[RawJobData]:
        """Scrape a single search profile using a shared browser page."""
        results: list[RawJobData] = []
        rate_limiter = RateLimiter(self._config.delay_seconds)  # type: ignore[attr-defined]

        await self._navigate_with_retry(page, profile.url)
        await self._load_all_listings(page, rate_limiter, profile.max_pages)
        cards = await self._extract_job_cards(page)

        if not cards:
            raise ScraperStructureError(
                self.scraper_name,
                f"No job cards found for profile '{profile.label}'. "
                "CSS selectors may need updating.",
            )

        for card in cards:
            await rate_limiter.wait()
            detail = await self._scrape_detail_page(page, card)
            if detail:
                results.append(detail)

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

    async def _navigate_with_retry(self, page: Page, url: str, max_retries: int = 2) -> None:
        """Navigate to URL with retry on timeout."""
        for attempt in range(max_retries + 1):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                return
            except PlaywrightTimeout:
                if attempt == max_retries:
                    raise ScraperTimeoutError(self.scraper_name, f"Timeout loading {url}") from None
                self._logger.warning("Timeout %s (attempt %d/%d)", url, attempt + 1, max_retries + 1)
                await asyncio.sleep(2**attempt)

    async def _load_all_listings(
        self, page: Page, rate_limiter: RateLimiter, max_pages: int
    ) -> None:
        """Scroll to load all job listings (infinite scroll / load-more button).

        Stops when:
        - max_pages equivalent of items loaded (max_pages * ~20 items/page)
        - No new items appear after scrolling
        - Load-more button disappears
        """
        max_items: int = max_pages * 20
        prev_count = 0
        no_change_rounds = 0

        while no_change_rounds < 3:
            # Try clicking "Load more" button if present
            load_more = await page.query_selector(
                "button:has-text('Load more'), button:has-text('Show more'), .load-more"
            )
            if load_more:
                await load_more.click()
                await rate_limiter.wait()
            else:
                # Scroll to bottom
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await rate_limiter.wait()

            current_count: int = await page.evaluate(
                "document.querySelectorAll('.job-card, [data-testid=\"job-card\"], .job-listing').length"
            )

            if current_count >= max_items:
                self._logger.info("Reached max items (%d), stopping scroll", max_items)
                break
            elif current_count == prev_count:
                no_change_rounds += 1
            else:
                no_change_rounds = 0

            prev_count = current_count

    async def _extract_job_cards(self, page: Page) -> list[dict]:
        """Extract all visible job cards from the loaded page.

        NOTE: CSS selectors are placeholders — finalize with live site inspection.
        """
        cards = await page.query_selector_all(".job-card, [data-testid='job-card'], .job-listing")
        results: list[dict] = []

        for card in cards:
            title_el = await card.query_selector("h2, h3, .job-title")
            company_el = await card.query_selector(".company-name, .company")
            link_el = await card.query_selector("a[href*='/job/'], a[href*='/remote-']")
            salary_el = await card.query_selector(".salary, .compensation")
            location_el = await card.query_selector(".location, .remote-info")
            tags_el = await card.query_selector_all(".tag, .badge, .label")

            title = await title_el.inner_text() if title_el else None
            company = await company_el.inner_text() if company_el else None
            href = await link_el.get_attribute("href") if link_el else None

            if title and company and href:
                tag_texts = [await t.inner_text() for t in tags_el] if tags_el else []
                results.append({
                    "title": title.strip(),
                    "company": company.strip(),
                    "salary_raw": (await salary_el.inner_text()).strip() if salary_el else None,
                    "location_raw": (await location_el.inner_text()).strip() if location_el else None,
                    "tags": tag_texts,
                    "detail_url": href if href.startswith("http") else f"https://www.remoterocketship.com{href}",
                })

        return results

    async def _scrape_detail_page(self, page: Page, card: dict) -> RawJobData | None:
        """Navigate to detail page and extract full description."""
        try:
            await self._navigate_with_retry(page, card["detail_url"])

            description_el = await page.query_selector(
                ".job-description, .description, article, [data-testid='description']"
            )
            description = await description_el.inner_text() if description_el else ""
            raw_html = await page.content()

            # Append tags to location info if present
            location = card.get("location_raw") or ""
            if card.get("tags"):
                location = f"{location} [{', '.join(card['tags'])}]".strip()

            return RawJobData(
                source="remote_rocketship",
                source_url=card["detail_url"],
                title=card["title"],
                company=card["company"],
                description=description.strip(),
                salary_raw=card.get("salary_raw"),
                location_raw=location or None,
                raw_html=raw_html,
            )
        except ScraperTimeoutError:
            self._logger.warning("Timeout on detail page %s — skipping", card["detail_url"])
            return None
        except Exception as e:
            self._logger.error("Error scraping detail %s: %s", card["detail_url"], e)
            return None

    async def health_check(self) -> bool:
        """Check if RemoteRocketship is reachable."""
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
