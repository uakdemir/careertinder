import asyncio
import json
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

from jobhunter.config.schema import RemoteRocketshipSearchProfile
from jobhunter.scrapers.base import BaseScraper, RawJobData
from jobhunter.scrapers.exceptions import ScraperTimeoutError
from jobhunter.scrapers.rate_limiter import RateLimiter

_BASE_URL = "https://www.remoterocketship.com"


class RemoteRocketshipScraper(BaseScraper):
    """C2b — RemoteRocketship scraper using Playwright browser automation.

    Supports multi-profile search: each profile has its own URL and max_pages.
    Single browser instance shared across all profiles.

    Extracts job data from Next.js __NEXT_DATA__ JSON embedded in the page,
    which is more reliable than CSS selectors on this site.
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
        """Scrape a single search profile by paginating through search results.

        Navigates page-by-page (using ?page=N param), extracts job listings
        from __NEXT_DATA__ JSON on each page, then visits detail pages for
        full descriptions.
        """
        job_infos: list[dict] = []
        rate_limiter = RateLimiter(self._config.delay_seconds)  # type: ignore[attr-defined]

        for page_num in range(1, profile.max_pages + 1):
            page_url = self._set_page_param(profile.url, page_num)
            await self._navigate_with_retry(page, page_url)

            page_jobs = await self._extract_jobs_from_json(page)
            if not page_jobs:
                self._logger.info(
                    "Profile '%s' page %d: no jobs found, stopping pagination",
                    profile.label,
                    page_num,
                )
                break

            job_infos.extend(page_jobs)
            self._logger.info(
                "Profile '%s' page %d: %d jobs", profile.label, page_num, len(page_jobs)
            )
            await rate_limiter.wait()

        if not job_infos:
            self._logger.warning(
                "Profile '%s': no jobs found across %d pages",
                profile.label,
                profile.max_pages,
            )
            return []

        # Visit detail pages for full descriptions
        results: list[RawJobData] = []
        for info in job_infos:
            await rate_limiter.wait()
            detail = await self._scrape_detail_page(page, info)
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

    @staticmethod
    def _set_page_param(url: str, page_num: int) -> str:
        """Set or replace the ?page=N parameter in a URL."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        params["page"] = [str(page_num)]
        new_query = urlencode(params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    async def _extract_jobs_from_json(self, page: Page) -> list[dict]:
        """Extract job listings from the __NEXT_DATA__ JSON embedded in the page.

        Returns a list of dicts with keys: title, company, detail_url,
        salary_raw, location_raw, summary.
        """
        try:
            raw_json: str | None = await page.evaluate(
                "(() => {"
                "  const el = document.getElementById('__NEXT_DATA__');"
                "  return el ? el.textContent : null;"
                "})()"
            )
        except Exception as e:
            self._logger.warning("Failed to extract __NEXT_DATA__: %s", e)
            return []

        if not raw_json:
            self._logger.warning("No __NEXT_DATA__ found on page")
            return []

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            self._logger.warning("Failed to parse __NEXT_DATA__ JSON: %s", e)
            return []

        # Navigate the Next.js data structure to find job listings
        jobs_raw = self._find_jobs_in_next_data(data)
        if not jobs_raw:
            return []

        results: list[dict] = []
        for job in jobs_raw:
            title = job.get("roleTitle") or job.get("title")
            company_obj = job.get("company") or {}
            company_name = company_obj.get("name") if isinstance(company_obj, dict) else str(company_obj)
            company_slug = company_obj.get("slug", "") if isinstance(company_obj, dict) else ""
            slug = job.get("slug", "")

            if not title or not company_name or not slug:
                continue

            detail_url = f"{_BASE_URL}/company/{company_slug}/jobs/{slug}/"

            # Build salary string from salaryRange
            salary_raw = self._extract_salary(job)

            # Location
            location = job.get("location") or ""
            location_type = job.get("locationType") or ""
            if location_type:
                location = f"{location} – {location_type}".strip(" –")

            # Summary (used as fallback description if detail page fails)
            summary = (
                job.get("jobDescriptionSummary")
                or job.get("twoLineJobDescriptionSummary")
                or ""
            )

            results.append({
                "title": title.strip(),
                "company": company_name.strip(),
                "detail_url": detail_url,
                "salary_raw": salary_raw,
                "location_raw": location or None,
                "summary": summary,
            })

        return results

    def _find_jobs_in_next_data(self, data: dict) -> list[dict]:
        """Locate the job listings array within __NEXT_DATA__.

        The structure varies but is typically at:
        props.pageProps.jobs or props.pageProps.dehydratedState.queries[*].state.data
        """
        try:
            page_props = data.get("props", {}).get("pageProps", {})

            # Direct jobs array
            if "jobs" in page_props and isinstance(page_props["jobs"], list):
                return page_props["jobs"]

            # Dehydrated React Query state
            dehydrated = page_props.get("dehydratedState", {})
            for query in dehydrated.get("queries", []):
                state_data = query.get("state", {}).get("data", {})
                if isinstance(state_data, list):
                    # Check if items look like jobs
                    if state_data and isinstance(state_data[0], dict) and "roleTitle" in state_data[0]:
                        return state_data
                # Paginated response with items/data key
                if isinstance(state_data, dict):
                    for key in ("items", "data", "jobs", "results"):
                        candidate = state_data.get(key)
                        if isinstance(candidate, list) and candidate:
                            if isinstance(candidate[0], dict) and (
                                "roleTitle" in candidate[0] or "title" in candidate[0]
                            ):
                                return candidate

            # Fallback: search all pageProps values for a list of job-like dicts
            for value in page_props.values():
                if isinstance(value, list) and len(value) > 0:
                    if isinstance(value[0], dict) and (
                        "roleTitle" in value[0] or "slug" in value[0]
                    ):
                        return value

        except (KeyError, TypeError, IndexError) as e:
            self._logger.warning("Unexpected __NEXT_DATA__ structure: %s", e)

        return []

    @staticmethod
    def _extract_salary(job: dict) -> str | None:
        """Extract a human-readable salary string from a job dict."""
        salary_range = job.get("salaryRange")
        if salary_range:
            if isinstance(salary_range, str):
                return salary_range
            if isinstance(salary_range, dict):
                lo = salary_range.get("min") or salary_range.get("minValue")
                hi = salary_range.get("max") or salary_range.get("maxValue")
                currency = salary_range.get("currency", "USD")
                if lo and hi:
                    return f"${lo:,} - ${hi:,} / year ({currency})"
                if lo:
                    return f"${lo:,}+ / year ({currency})"
        return None

    async def _scrape_detail_page(self, page: Page, job_info: dict) -> RawJobData | None:
        """Navigate to detail page and extract full description."""
        detail_url = job_info["detail_url"]
        try:
            await self._navigate_with_retry(page, detail_url)

            # Try __NEXT_DATA__ first for structured description
            description = await self._extract_description_from_json(page)

            # Fallback to CSS selectors for description
            if not description:
                description_el = await page.query_selector(
                    "article, .job-description, .description, "
                    "[data-testid='description'], [class*='description']"
                )
                description = await description_el.inner_text() if description_el else ""

            # Final fallback to summary from search page
            if not description:
                description = job_info.get("summary", "")

            raw_html = await page.content()

            return RawJobData(
                source="remote_rocketship",
                source_url=detail_url,
                title=job_info["title"],
                company=job_info["company"],
                description=description.strip(),
                salary_raw=job_info.get("salary_raw"),
                location_raw=job_info.get("location_raw"),
                raw_html=raw_html,
            )
        except ScraperTimeoutError:
            self._logger.warning("Timeout on detail page %s — skipping", detail_url)
            return None
        except Exception as e:
            self._logger.error("Error scraping detail %s: %s", detail_url, e)
            return None

    async def _extract_description_from_json(self, page: Page) -> str:
        """Try to extract job description from detail page __NEXT_DATA__."""
        try:
            raw_json: str | None = await page.evaluate(
                "(() => {"
                "  const el = document.getElementById('__NEXT_DATA__');"
                "  return el ? el.textContent : null;"
                "})()"
            )
            if not raw_json:
                return ""

            data = json.loads(raw_json)
            page_props = data.get("props", {}).get("pageProps", {})

            # Common locations for job description on detail pages
            for key in ("job", "jobPosting", "posting"):
                job_obj = page_props.get(key)
                if isinstance(job_obj, dict):
                    for desc_key in ("description", "jobDescription", "fullDescription"):
                        desc = job_obj.get(desc_key)
                        if desc and isinstance(desc, str) and len(desc) > 50:
                            return str(desc)

            # Check top-level pageProps
            for desc_key in ("description", "jobDescription"):
                desc = page_props.get(desc_key)
                if desc and isinstance(desc, str) and len(desc) > 50:
                    return str(desc)

        except Exception:
            pass
        return ""

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
