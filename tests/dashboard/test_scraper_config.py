"""Tests for M5.1 dashboard scraper config — source_url round-trip."""

from jobhunter.db.settings import CATEGORY_SCRAPING, get_scraping_config, seed_defaults, update_settings


class TestLinkedInSourceUrlDashboardRoundtrip:
    """Verify source_url survives the DB save/reload cycle."""

    def test_source_url_survives_save_reload(self, db_session_with_settings) -> None:
        """Import URL → save → reload → source_url still present."""
        session = db_session_with_settings

        # Seed defaults first
        seed_defaults(session)
        session.commit()

        # Simulate what the dashboard does: save config with source_url
        config_data = {
            "timeout_seconds": 600,
            "linkedin": {
                "enabled": True,
                "apify_actor_id": "valig/linkedin-jobs-scraper",
                "max_results": 100,
                "search_profiles": [
                    {
                        "label": "Architect Turkey",
                        "job_titles": ["Software Architect"],
                        "locations": ["Remote"],
                        "geo_id": "102105699",
                        "workplace_type": ["remote"],
                        "experience_level": ["mid-senior", "director"],
                        "job_functions": [],
                        "contract_type": [],
                        "posted_limit": None,
                        "source_url": "https://www.linkedin.com/jobs/search/?keywords=architect&f_WT=2&geoId=102105699",
                        "weight": 1,
                    }
                ],
            },
            "wellfound": {
                "enabled": False,
                "apify_actor_id": "shahidirfan/wellfound-jobs-scraper",
                "max_results": 100,
                "search_profiles": [
                    {
                        "label": "Default",
                        "search_keyword": "software engineer",
                        "location_filter": "remote",
                    }
                ],
            },
            "remote_io": {
                "enabled": True,
                "delay_seconds": 2,
                "search_profiles": [
                    {"label": "Default", "url": "https://remote.io/remote-jobs", "max_pages": 10}
                ],
            },
            "remote_rocketship": {
                "enabled": True,
                "delay_seconds": 2,
                "search_profiles": [
                    {"label": "Default", "url": "https://www.remoterocketship.com", "max_pages": 10}
                ],
            },
        }

        update_settings(session, CATEGORY_SCRAPING, config_data)
        session.commit()

        # Reload and verify source_url survived
        config = get_scraping_config(session)
        assert len(config.linkedin.search_profiles) == 1
        profile = config.linkedin.search_profiles[0]
        assert profile.source_url == "https://www.linkedin.com/jobs/search/?keywords=architect&f_WT=2&geoId=102105699"
        assert profile.label == "Architect Turkey"

    def test_source_url_none_by_default(self, db_session_with_settings) -> None:
        """Profiles without source_url get None."""
        session = db_session_with_settings
        seed_defaults(session)
        session.commit()

        config = get_scraping_config(session)
        # Default LinkedIn has no profiles (empty list default)
        # But Wellfound should have a seeded default with source_url=None
        assert len(config.wellfound.search_profiles) == 1
        assert config.wellfound.search_profiles[0].source_url is None
