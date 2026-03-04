"""Tests for location parser."""

import pytest

from jobhunter.filters.parsers.location_parser import LocationPolicy, parse_location


class TestParseLocation:
    """Test location and remote policy parsing."""

    @pytest.mark.parametrize(
        "location_raw,description,expected_policy",
        [
            # Worldwide remote indicators
            ("Remote - Worldwide", "", LocationPolicy.REMOTE_WORLDWIDE),
            ("Remote (Worldwide)", "", LocationPolicy.REMOTE_WORLDWIDE),
            ("Work from anywhere", "", LocationPolicy.REMOTE_WORLDWIDE),
            ("", "We are a fully distributed team, work from anywhere!", LocationPolicy.REMOTE_WORLDWIDE),
            ("", "Location independent position", LocationPolicy.REMOTE_WORLDWIDE),
            ("Global", "Remote position", LocationPolicy.REMOTE_WORLDWIDE),
        ],
    )
    def test_remote_worldwide(
        self, location_raw: str, description: str, expected_policy: LocationPolicy
    ) -> None:
        """Test detection of worldwide remote positions."""
        result = parse_location(location_raw, description)
        assert result.policy == expected_policy
        assert result.confidence >= 0.9

    @pytest.mark.parametrize(
        "location_raw,description,expected_policy",
        [
            # Generic remote without worldwide indicator
            ("Remote", "", LocationPolicy.REMOTE_REGIONAL),
            # Remote with "US" but no "only" restriction
            ("Remote - Americas", "", LocationPolicy.REMOTE_REGIONAL),
        ],
    )
    def test_remote_regional(
        self, location_raw: str, description: str, expected_policy: LocationPolicy
    ) -> None:
        """Test detection of regional remote positions."""
        result = parse_location(location_raw, description)
        assert result.policy == expected_policy

    @pytest.mark.parametrize(
        "location_raw,description,expected_policy",
        [
            # Europe/EMEA mentions are positive signals (Turkey included)
            ("Remote - US/EU", "", LocationPolicy.REMOTE_WORLDWIDE),
            ("Remote (Europe preferred)", "", LocationPolicy.REMOTE_WORLDWIDE),
        ],
    )
    def test_europe_remote_as_worldwide(
        self, location_raw: str, description: str, expected_policy: LocationPolicy
    ) -> None:
        """Test that Europe/EU mentions are classified as worldwide (Turkey-compatible)."""
        result = parse_location(location_raw, description)
        assert result.policy == expected_policy

    @pytest.mark.parametrize(
        "location_raw,description,expected_policy",
        [
            # US-only restrictions
            ("Remote - US only", "", LocationPolicy.REMOTE_COUNTRY_SPECIFIC),
            ("", "Must be located in United States", LocationPolicy.REMOTE_COUNTRY_SPECIFIC),
            ("Remote", "US work authorization required", LocationPolicy.REMOTE_COUNTRY_SPECIFIC),
            ("Remote", "This position is US only", LocationPolicy.REMOTE_COUNTRY_SPECIFIC),
            # Canada only
            ("Remote - Canada only", "", LocationPolicy.REMOTE_COUNTRY_SPECIFIC),
        ],
    )
    def test_geo_restricted(
        self, location_raw: str, description: str, expected_policy: LocationPolicy
    ) -> None:
        """Test detection of geo-restricted remote positions."""
        result = parse_location(location_raw, description)
        assert result.policy == expected_policy
        assert len(result.restriction_indicators_found) > 0

    @pytest.mark.parametrize(
        "location_raw,description,expected_policy",
        [
            # Hybrid indicators
            ("Hybrid - NYC", "", LocationPolicy.HYBRID),
            ("Hybrid", "2 days in office per week", LocationPolicy.HYBRID),
            ("San Francisco (Hybrid)", "", LocationPolicy.HYBRID),
            ("Flexible", "We require 3 days in office", LocationPolicy.HYBRID),
        ],
    )
    def test_hybrid(
        self, location_raw: str, description: str, expected_policy: LocationPolicy
    ) -> None:
        """Test detection of hybrid positions."""
        result = parse_location(location_raw, description)
        assert result.policy == expected_policy

    @pytest.mark.parametrize(
        "location_raw,description,expected_policy",
        [
            # Onsite only
            ("San Francisco, CA", "On-site required", LocationPolicy.ONSITE),
            ("NYC Office", "No remote", LocationPolicy.ONSITE),
            ("London", "In-office only position", LocationPolicy.ONSITE),
            ("", "Must be able to commute to our office", LocationPolicy.ONSITE),
            ("Austin, TX", "Onsite only, no remote work", LocationPolicy.ONSITE),
        ],
    )
    def test_onsite(
        self, location_raw: str, description: str, expected_policy: LocationPolicy
    ) -> None:
        """Test detection of onsite-only positions."""
        result = parse_location(location_raw, description)
        assert result.policy == expected_policy

    @pytest.mark.parametrize(
        "location_raw,description,expected_policy",
        [
            # Unclear/ambiguous
            ("San Francisco", "", LocationPolicy.UNCLEAR),
            ("", "Join our team!", LocationPolicy.UNCLEAR),
            ("", "", LocationPolicy.UNCLEAR),
        ],
    )
    def test_unclear(
        self, location_raw: str, description: str, expected_policy: LocationPolicy
    ) -> None:
        """Test detection of unclear location policies."""
        result = parse_location(location_raw, description)
        assert result.policy == expected_policy
        assert result.confidence <= 0.6

    def test_turkey_europe_explicit_mention(self) -> None:
        """Test that explicit Turkey/Europe mentions are strong positive signals."""
        result = parse_location("Remote", "We're open to candidates from Turkey and Europe")
        assert result.policy == LocationPolicy.REMOTE_WORLDWIDE
        assert "Turkey" in result.allowed_regions or any(
            kw in result.remote_indicators_found for kw in ["turkey", "europe"]
        )

    def test_emea_mention(self) -> None:
        """Test EMEA region mention."""
        result = parse_location("Remote - EMEA", "")
        # EMEA includes Turkey, should be positive
        assert result.policy == LocationPolicy.REMOTE_WORLDWIDE
        assert "emea" in result.remote_indicators_found

    def test_exclusion_overrides_inclusion(self) -> None:
        """Test that exclusion keywords override inclusion keywords."""
        # Location says remote, but description says US only
        result = parse_location("Remote", "This position is US only")
        assert result.policy == LocationPolicy.REMOTE_COUNTRY_SPECIFIC
        assert "US" in result.excluded_regions

    def test_description_trumps_location_field(self) -> None:
        """Test that restrictions in description are detected even if location looks good."""
        result = parse_location(
            "Remote - Worldwide",
            "Note: Must be authorized to work in the US. US work authorization required."
        )
        # Description has US restriction, should detect it
        assert result.policy == LocationPolicy.REMOTE_COUNTRY_SPECIFIC

    def test_confidence_high_for_clear_worldwide(self) -> None:
        """Test high confidence for clear worldwide indicators."""
        result = parse_location("Remote - Worldwide", "Work from anywhere in the world")
        assert result.confidence >= 0.9

    def test_confidence_lower_for_generic_remote(self) -> None:
        """Test lower confidence for generic 'remote' without clarification."""
        result = parse_location("Remote", "")
        assert result.confidence < 0.8  # Could be regionally restricted

    def test_remote_indicators_captured(self) -> None:
        """Test that found remote indicators are captured."""
        result = parse_location("Fully remote, work from anywhere", "Distributed team")
        assert len(result.remote_indicators_found) >= 2

    def test_restriction_indicators_captured(self) -> None:
        """Test that found restriction indicators are captured."""
        result = parse_location("", "US only, must be located in US")
        assert len(result.restriction_indicators_found) >= 1
