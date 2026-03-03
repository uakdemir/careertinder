class ScraperError(Exception):
    """Base exception for all scraper errors."""

    def __init__(self, scraper_name: str, message: str) -> None:
        self.scraper_name = scraper_name
        super().__init__(f"[{scraper_name}] {message}")


class ScraperTimeoutError(ScraperError):
    """Page load or API poll exceeded timeout."""


class ScraperStructureError(ScraperError):
    """Site HTML structure changed — selectors return no results.
    Not a transient error; requires developer attention.
    """


class ScraperBlockedError(ScraperError):
    """Anti-bot detection triggered (CAPTCHA, interstitial, IP block)."""


class ScraperQuotaError(ScraperError):
    """Apify quota exhausted or API token invalid."""


class ScraperNetworkError(ScraperError):
    """Network-level failure (DNS, connection reset, etc.)."""
