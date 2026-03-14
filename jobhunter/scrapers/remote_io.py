import asyncio
import json
import re

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

from jobhunter.config.schema import RemoteIoSearchProfile
from jobhunter.scrapers.base import BaseScraper, RawJobData
from jobhunter.scrapers.exceptions import ScraperTimeoutError
from jobhunter.scrapers.rate_limiter import RateLimiter

_BASE_URL = "https://remote.io"

# Matches Remote.io job detail URLs:
# /remote-<category>-jobs/<slug>-at-<company>-<id>
_JOB_HREF_RE = re.compile(r"^/remote-[\w-]+-jobs/.+-\d+$")


class RemoteIoScraper(BaseScraper):
    """C2a — Remote.io scraper using Playwright browser automation.

    Supports multi-profile search: each profile has its own URL and max_pages.
    Single browser instance shared across all profiles.

    Extracts job links from listing pages via URL pattern matching,
    then fetches structured data from detail pages using JSON-LD.
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
        """Scrape a single search profile by paginating through results.

        Navigates page-by-page, extracts job links by URL pattern matching,
        then visits detail pages for full data via JSON-LD.
        """
        job_links: list[dict] = []
        rate_limiter = RateLimiter(self._config.delay_seconds)  # type: ignore[attr-defined]

        for page_num in range(1, profile.max_pages + 1):
            url = self._build_listing_url(profile.url, page_num)
            self._logger.info(
                "Scraping '%s' page %d: %s", profile.label, page_num, url
            )

            await self._navigate_with_retry(page, url)
            page_links = await self._extract_job_links(page)

            if not page_links:
                if page_num == 1:
                    self._logger.warning(
                        "No job links found on page 1 for profile '%s'. "
                        "URL pattern may need updating.",
                        profile.label,
                    )
                else:
                    self._logger.info(
                        "No job links on page %d — stopping pagination", page_num
                    )
                break

            job_links.extend(page_links)
            self._logger.info(
                "Profile '%s' page %d: %d job links", profile.label, page_num, len(page_links)
            )
            await rate_limiter.wait()

        if not job_links:
            self._logger.warning(
                "Profile '%s': no jobs found across %d pages",
                profile.label,
                profile.max_pages,
            )
            return []

        # Visit detail pages for full job data
        results: list[RawJobData] = []
        for link_info in job_links:
            await rate_limiter.wait()
            detail = await self._scrape_detail_page(page, link_info)
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

    async def _extract_job_links(self, page: Page) -> list[dict]:
        """Extract job links from a listing page by matching URL patterns.

        Finds all <a> elements whose href matches the Remote.io job URL
        pattern (/remote-*-jobs/*-<id>), then extracts the link text as
        the preliminary title.
        """
        try:
            links: list[dict] = await page.evaluate(
                """(() => {
                    const pattern = /^\\/remote-[\\w-]+-jobs\\/.+-\\d+$/;
                    const seen = new Set();
                    const results = [];
                    for (const a of document.querySelectorAll('a[href]')) {
                        const href = a.getAttribute('href');
                        if (!href || !pattern.test(href) || seen.has(href)) continue;
                        seen.add(href);
                        const text = (a.textContent || '').trim();
                        if (text.length > 0) {
                            results.push({ href: href, text: text });
                        }
                    }
                    return results;
                })()"""
            )
        except Exception as e:
            self._logger.warning("Failed to extract job links: %s", e)
            return []

        results: list[dict] = []
        for link in links:
            href = link["href"]
            detail_url = href if href.startswith("http") else f"{_BASE_URL}{href}"
            # Parse title hint from link text (may be refined from JSON-LD on detail page)
            title_hint = link["text"].split("\n")[0].strip()
            results.append({
                "detail_url": detail_url,
                "title_hint": title_hint,
            })

        return results

    async def _scrape_detail_page(self, page: Page, link_info: dict) -> RawJobData | None:
        """Navigate to job detail page and extract data via JSON-LD."""
        detail_url = link_info["detail_url"]
        try:
            await self._navigate_with_retry(page, detail_url)

            # Primary: JSON-LD structured data
            json_ld = await self._extract_json_ld(page)

            if json_ld:
                title = json_ld.get("title", link_info.get("title_hint", ""))
                org = json_ld.get("hiringOrganization", {})
                company = org.get("name", "") if isinstance(org, dict) else str(org)
                location = self._extract_location_from_json_ld(json_ld)
                posted_date = json_ld.get("datePosted")
            else:
                title = link_info.get("title_hint", "")
                company = self._parse_company_from_url(detail_url)
                location = None
                posted_date = None

            if not title or not company:
                self._logger.warning("Missing title/company for %s — skipping", detail_url)
                return None

            # Description: extract from page content
            description = await self._extract_description(page)
            raw_html = await page.content()

            return RawJobData(
                source="remote_io",
                source_url=detail_url,
                title=title.strip(),
                company=company.strip(),
                description=description.strip() if description else "",
                location_raw=location,
                posted_date_raw=posted_date,
                raw_html=raw_html,
            )
        except ScraperTimeoutError:
            self._logger.warning("Timeout on detail page %s — skipping", detail_url)
            return None
        except Exception as e:
            self._logger.error("Error scraping detail %s: %s", detail_url, e)
            return None

    async def _extract_json_ld(self, page: Page) -> dict | None:
        """Extract schema.org/JobPosting JSON-LD from the page."""
        try:
            json_ld_texts: list[str] = await page.evaluate(
                """(() => {
                    return Array.from(
                        document.querySelectorAll('script[type="application/ld+json"]')
                    ).map(el => el.textContent || '');
                })()"""
            )
        except Exception as e:
            self._logger.debug("Failed to query JSON-LD scripts: %s", e)
            return None

        for text in json_ld_texts:
            try:
                data = json.loads(text)
                if isinstance(data, dict) and data.get("@type") == "JobPosting":
                    return data
                # Handle array of JSON-LD objects
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "JobPosting":
                            return item
            except json.JSONDecodeError:
                continue

        return None

    @staticmethod
    def _extract_location_from_json_ld(json_ld: dict) -> str | None:
        """Build a location string from JSON-LD fields."""
        parts: list[str] = []

        loc_req = json_ld.get("applicantLocationRequirements")
        if isinstance(loc_req, dict):
            name = loc_req.get("name")
            if name:
                parts.append(str(name))
        elif isinstance(loc_req, list):
            for item in loc_req:
                if isinstance(item, dict) and item.get("name"):
                    parts.append(str(item["name"]))

        loc_type = json_ld.get("jobLocationType")
        if loc_type:
            parts.append(str(loc_type))

        return " — ".join(parts) if parts else None

    @staticmethod
    def _parse_company_from_url(url: str) -> str:
        """Best-effort company extraction from the URL slug.

        URL pattern: /remote-*-jobs/<title>-at-<company>-<id>
        """
        match = re.search(r"-at-(.+)-\d+$", url.split("/")[-1])
        if match:
            return match.group(1).replace("-", " ").title()
        return ""

    async def _extract_description(self, page: Page) -> str:
        """Extract job description text from the detail page.

        Tries several selectors that are common for job description content.
        """
        selectors = [
            "article",
            "[class*='description']",
            "[class*='job-content']",
            "[class*='job-detail']",
            "main section",
            ".content",
            "main",
        ]
        for selector in selectors:
            try:
                el = await page.query_selector(selector)
                if el:
                    text = await el.inner_text()
                    if text and len(text.strip()) > 100:
                        return text.strip()
            except Exception:
                continue

        # Fallback: get all text from main content area
        try:
            text = await page.evaluate(
                """(() => {
                    const main = document.querySelector('main') || document.body;
                    return main.innerText || '';
                })()"""
            )
            if text and len(str(text).strip()) > 100:
                return str(text).strip()
        except Exception:
            pass

        return ""

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
