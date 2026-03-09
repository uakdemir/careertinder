"""Tests for M5.1 multi-profile schema models and legacy migration."""

from typing import Any

from jobhunter.config.schema import (
    RemoteIoConfig,
    RemoteIoSearchProfile,
    RemoteRocketshipConfig,
    WellfoundConfig,
    WellfoundSearchProfile,
)


class TestRemoteIoSearchProfile:
    def test_model_defaults(self) -> None:
        profile = RemoteIoSearchProfile(label="Test", url="https://remote.io/python")
        assert profile.max_pages == 5  # default
        assert profile.label == "Test"
        assert profile.url == "https://remote.io/python"

    def test_model_validation(self) -> None:
        profile = RemoteIoSearchProfile(label="Custom", url="https://remote.io/devops", max_pages=20)
        assert profile.max_pages == 20


class TestRemoteIoConfigLegacyMigration:
    def test_legacy_base_url_migrated(self) -> None:
        """Old DB format with base_url is auto-migrated to search_profiles."""
        data: dict[str, Any] = {
            "enabled": True, "base_url": "https://remote.io/jobs", "max_pages": 3, "delay_seconds": 1,
        }
        config = RemoteIoConfig(**data)
        assert len(config.search_profiles) == 1
        assert config.search_profiles[0].label == "Default"
        assert config.search_profiles[0].url == "https://remote.io/jobs"
        assert config.search_profiles[0].max_pages == 3

    def test_new_format_not_migrated(self) -> None:
        """New format with search_profiles is not double-migrated."""
        data: dict[str, Any] = {
            "enabled": True,
            "delay_seconds": 1,
            "search_profiles": [{"label": "A", "url": "https://remote.io/a", "max_pages": 2}],
        }
        config = RemoteIoConfig(**data)
        assert len(config.search_profiles) == 1
        assert config.search_profiles[0].label == "A"

    def test_default_config_has_seeded_profile(self) -> None:
        """Fresh config has one Default profile."""
        config = RemoteIoConfig()
        assert len(config.search_profiles) == 1
        assert config.search_profiles[0].label == "Default"
        assert config.search_profiles[0].url == "https://remote.io/remote-jobs"


class TestRemoteRocketshipConfigLegacyMigration:
    def test_legacy_base_url_migrated(self) -> None:
        data: dict[str, Any] = {"enabled": True, "base_url": "https://rrs.com/jobs", "max_pages": 5, "delay_seconds": 2}
        config = RemoteRocketshipConfig(**data)
        assert len(config.search_profiles) == 1
        assert config.search_profiles[0].url == "https://rrs.com/jobs"
        assert config.search_profiles[0].max_pages == 5


class TestWellfoundConfigLegacyMigration:
    def test_legacy_keyword_migrated(self) -> None:
        """Old DB format with search_keyword is auto-migrated to search_profiles."""
        data: dict[str, Any] = {
            "enabled": True,
            "apify_actor_id": "actor/test",
            "max_results": 50,
            "search_keyword": "platform engineer",
            "location_filter": "europe",
        }
        config = WellfoundConfig(**data)
        assert len(config.search_profiles) == 1
        assert config.search_profiles[0].label == "Default"
        assert config.search_profiles[0].search_keyword == "platform engineer"
        assert config.search_profiles[0].location_filter == "europe"

    def test_default_config_has_seeded_profile(self) -> None:
        config = WellfoundConfig()
        assert len(config.search_profiles) == 1
        assert config.search_profiles[0].search_keyword == "software engineer"


class TestWellfoundSearchProfile:
    def test_source_url_optional(self) -> None:
        profile = WellfoundSearchProfile(label="Test", search_keyword="eng")
        assert profile.source_url is None

    def test_source_url_preserved(self) -> None:
        profile = WellfoundSearchProfile(
            label="Test", search_keyword="eng", source_url="https://wellfound.com/search/eng"
        )
        assert profile.source_url == "https://wellfound.com/search/eng"
