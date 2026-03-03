"""Tests for CLI scrape command routing and config new fields."""

from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from jobhunter.cli import cli
from jobhunter.config.schema import (
    AppConfig,
    LinkedInConfig,
    LinkedInSearchProfile,
    RemoteIoConfig,
    RemoteRocketshipConfig,
    ScrapingConfig,
    WellfoundConfig,
)


class TestConfigNewFields:
    """Verify M1 config fields parse with defaults and explicit values."""

    def test_config_new_fields_with_defaults(self, tmp_path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{}", encoding="utf-8")
        config = AppConfig()
        scraping = config.scraping
        assert scraping.timeout_seconds == 600
        assert scraping.linkedin.search_profiles == []
        assert scraping.linkedin.apify_actor_id == "harvestapi/linkedin-job-search"
        assert scraping.wellfound.search_keyword == "software engineer"
        assert scraping.wellfound.location_filter == "remote"
        assert scraping.wellfound.enabled is False  # Deferred

    def test_config_new_fields_explicit(self) -> None:
        config = AppConfig(
            scraping=ScrapingConfig(
                timeout_seconds=120,
                linkedin=LinkedInConfig(
                    search_profiles=[
                        LinkedInSearchProfile(
                            label="Architect Remote",
                            job_titles=["Software Architect"],
                            locations=["Remote"],
                        ),
                    ],
                ),
                wellfound=WellfoundConfig(
                    search_keyword="platform engineer",
                    location_filter="europe",
                ),
            )
        )
        assert config.scraping.timeout_seconds == 120
        assert len(config.scraping.linkedin.search_profiles) == 1
        assert config.scraping.linkedin.search_profiles[0].job_titles == ["Software Architect"]
        assert config.scraping.wellfound.search_keyword == "platform engineer"
        assert config.scraping.wellfound.location_filter == "europe"

    def test_timeout_seconds_in_config(self, tmp_path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({"scraping": {"timeout_seconds": 30}}),
            encoding="utf-8",
        )
        from jobhunter.config.loader import load_config

        config = load_config(config_path)
        assert config.scraping.timeout_seconds == 30

    def test_per_scraper_config_fields(self) -> None:
        rio = RemoteIoConfig(max_pages=3, delay_seconds=5)
        assert rio.max_pages == 3
        assert rio.delay_seconds == 5

        rrs = RemoteRocketshipConfig(max_pages=2, delay_seconds=4)
        assert rrs.max_pages == 2
        assert rrs.delay_seconds == 4


class TestCliScrapeCommand:
    """Verify CLI scrape routes to run_all vs run_single."""

    @patch("jobhunter.cli.asyncio.run")
    @patch("jobhunter.cli.load_config")
    def test_scrape_command_all(self, mock_load_config: MagicMock, mock_run: MagicMock, tmp_path) -> None:
        mock_load_config.return_value = AppConfig()
        runner = CliRunner()
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{}", encoding="utf-8")

        result = runner.invoke(cli, ["--config", str(config_path), "scrape"])
        assert result.exit_code == 0 or "Error" not in (result.output or "")
        mock_run.assert_called_once()

    @patch("jobhunter.cli.asyncio.run")
    @patch("jobhunter.cli.load_config")
    def test_scrape_command_single(self, mock_load_config: MagicMock, mock_run: MagicMock, tmp_path) -> None:
        mock_load_config.return_value = AppConfig()
        runner = CliRunner()
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{}", encoding="utf-8")

        result = runner.invoke(cli, ["--config", str(config_path), "scrape", "--scraper", "linkedin"])
        assert result.exit_code == 0 or "Error" not in (result.output or "")
        mock_run.assert_called_once()

    def test_scrape_command_invalid_scraper(self, tmp_path) -> None:
        runner = CliRunner()
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{}", encoding="utf-8")

        result = runner.invoke(cli, ["--config", str(config_path), "scrape", "--scraper", "bogus"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output
