"""Scraper-specific test fixtures."""

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from jobhunter.config.schema import (
    LinkedInConfig,
    LinkedInSearchProfile,
    RemoteIoConfig,
    RemoteRocketshipConfig,
    SecretsConfig,
    WellfoundConfig,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def remote_io_config() -> RemoteIoConfig:
    return RemoteIoConfig(enabled=True, base_url="https://remote.io/remote-jobs", max_pages=2, delay_seconds=0)


@pytest.fixture
def remote_rocketship_config() -> RemoteRocketshipConfig:
    return RemoteRocketshipConfig(
        enabled=True, base_url="https://www.remoterocketship.com", max_pages=2, delay_seconds=0
    )


@pytest.fixture
def wellfound_config() -> WellfoundConfig:
    return WellfoundConfig(
        enabled=True,
        apify_actor_id="shahidirfan/wellfound-jobs-scraper",
        max_results=50,
        search_keyword="software engineer",
        location_filter="remote",
    )


@pytest.fixture
def linkedin_search_profile() -> LinkedInSearchProfile:
    return LinkedInSearchProfile(
        label="Test Architect Remote",
        job_titles=["Software Architect"],
        locations=["Remote"],
        workplace_type=["remote"],
        experience_level=["mid-senior", "director"],
        weight=1,
    )


@pytest.fixture
def linkedin_config(linkedin_search_profile: LinkedInSearchProfile) -> LinkedInConfig:
    return LinkedInConfig(
        enabled=True,
        apify_actor_id="harvestapi/linkedin-job-search",
        max_results=50,
        search_profiles=[linkedin_search_profile],
    )


@pytest.fixture
def secrets_with_apify() -> SecretsConfig:
    with patch.dict(os.environ, {"APIFY_API_TOKEN": "test-token-123"}, clear=False):
        return SecretsConfig(apify_api_token="test-token-123")


@pytest.fixture
def secrets_no_apify() -> SecretsConfig:
    with patch.dict(os.environ, {}, clear=False):
        return SecretsConfig(apify_api_token=None)


@pytest.fixture
def remote_io_listing_html() -> str:
    return (FIXTURES_DIR / "remote_io_listing.html").read_text(encoding="utf-8")


@pytest.fixture
def remote_io_detail_html() -> str:
    return (FIXTURES_DIR / "remote_io_detail.html").read_text(encoding="utf-8")


@pytest.fixture
def remoterocketship_listing_html() -> str:
    return (FIXTURES_DIR / "remoterocketship_listing.html").read_text(encoding="utf-8")


@pytest.fixture
def remoterocketship_detail_html() -> str:
    return (FIXTURES_DIR / "remoterocketship_detail.html").read_text(encoding="utf-8")


@pytest.fixture
def linkedin_apify_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = json.loads(
        (FIXTURES_DIR / "linkedin_apify_response.json").read_text(encoding="utf-8")
    )
    return items


@pytest.fixture
def wellfound_apify_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = json.loads(
        (FIXTURES_DIR / "wellfound_apify_response.json").read_text(encoding="utf-8")
    )
    return items
