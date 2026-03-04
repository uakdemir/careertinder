"""Location and remote-work policy detection.

Parses location strings and job descriptions to determine remote work feasibility,
particularly for "remote from Turkey" scenarios.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class LocationPolicy(Enum):
    """Normalized remote-work classification."""

    REMOTE_WORLDWIDE = "remote_worldwide"
    REMOTE_REGIONAL = "remote_regional"  # e.g., "US/EU only"
    REMOTE_COUNTRY_SPECIFIC = "remote_country_specific"  # e.g., "US only"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNCLEAR = "unclear"


@dataclass
class ParsedLocation:
    """Parsed location information from job posting."""

    policy: LocationPolicy
    allowed_regions: list[str] = field(default_factory=list)
    excluded_regions: list[str] = field(default_factory=list)
    remote_indicators_found: list[str] = field(default_factory=list)
    restriction_indicators_found: list[str] = field(default_factory=list)
    confidence: float = 1.0


# Inclusion keywords that indicate remote-friendly positions
INCLUSION_KEYWORDS: list[str] = [
    # Remote work indicators
    "remote",
    "remote-friendly",
    "fully remote",
    "100% remote",
    "work from home",
    "wfh",
    # Global indicators
    "worldwide",
    "anywhere",
    "global",
    "location independent",
    "work from anywhere",
    # Distributed team indicators
    "distributed team",
    "distributed",
    "async-first",
    "async first",
    # Turkey/Europe positive signals
    "turkey",
    "türkiye",
    "europe",
    "emea",
    "eu",
    "european",
]

# Exclusion keywords that indicate geo-restrictions
EXCLUSION_KEYWORDS: list[str] = [
    # US-only restrictions
    "us only",
    "usa only",
    "u.s. only",
    "united states only",
    "us-based only",
    "us based only",
    "must be located in us",
    "must be located in the us",
    "must be located in united states",
    "us citizens only",
    "us work authorization required",
    "us work authorization",
    # Canada restrictions
    "canada only",
    "canadian only",
    # UK restrictions
    "uk only",
    "united kingdom only",
    # No remote
    "no remote",
    "not remote",
    "on-site required",
    "onsite required",
    "onsite only",
    "on-site only",
    "in-office only",
    "in office only",
    "office-based",
    "office based",
    # Relocation requirements
    "must be able to commute",
    "commute to",
    "relocate to",
    "relocation required",
    "willing to relocate",
]

# Hybrid indicators
HYBRID_KEYWORDS: list[str] = [
    "hybrid",
    "flexible",
    "2 days in office",
    "3 days in office",
    "days per week in office",
    "office days",
]


def _find_keywords(text: str, keywords: list[str]) -> list[str]:
    """Find which keywords appear in the text."""
    text_lower = text.lower()
    found = []
    for keyword in keywords:
        # Use word boundary matching for short keywords to avoid false positives
        if len(keyword) <= 3:
            pattern = rf"\b{re.escape(keyword)}\b"
            if re.search(pattern, text_lower):
                found.append(keyword)
        elif keyword in text_lower:
            found.append(keyword)
    return found


def _detect_regional_restriction(text: str) -> list[str]:
    """Detect specific regional restrictions mentioned."""
    regions = []
    text_lower = text.lower()

    # Common region patterns
    region_patterns = [
        (r"\bus\b|\busa\b|united states", "US"),
        (r"\bcanada\b|\bcanadian\b", "Canada"),
        (r"\buk\b|united kingdom", "UK"),
        (r"\bgermany\b", "Germany"),
        (r"\beurope\b|\beu\b|\bemea\b", "Europe"),
        (r"\basia\b|\bapac\b", "Asia-Pacific"),
    ]

    for pattern, region in region_patterns:
        if re.search(pattern, text_lower):
            # Check if this region is mentioned as a restriction
            # Look for patterns like "X only", "based in X", "must be in X"
            restriction_patterns = [
                rf"{pattern}\s+only",
                rf"based\s+in\s+.*{pattern}",
                rf"must\s+be\s+(in|located\s+in)\s+.*{pattern}",
            ]
            for rp in restriction_patterns:
                if re.search(rp, text_lower):
                    regions.append(region)
                    break

    return regions


def parse_location(location_raw: str | None, description: str) -> ParsedLocation:
    """Parse location from raw string and description text.

    Checks both location field and full description to catch
    geo-restrictions often buried in job descriptions.

    Args:
        location_raw: The location field from the job posting
        description: The full job description text

    Returns:
        ParsedLocation with policy classification and confidence
    """
    # Combine location and description for analysis
    combined_text = f"{location_raw or ''} {description}"

    # Find indicators
    inclusion_found = _find_keywords(combined_text, INCLUSION_KEYWORDS)
    exclusion_found = _find_keywords(combined_text, EXCLUSION_KEYWORDS)
    hybrid_found = _find_keywords(combined_text, HYBRID_KEYWORDS)

    # Detect regional restrictions
    restricted_regions = _detect_regional_restriction(combined_text)

    # Determine policy based on indicators
    # Priority: exclusion > hybrid > inclusion

    # Check for hard exclusions first
    if exclusion_found:
        # Onsite-only keywords (no remote possible)
        onsite_keywords = {"no remote", "not remote", "on-site required", "onsite required",
                          "onsite only", "on-site only", "in-office only", "in office only",
                          "office-based", "office based", "must be able to commute",
                          "commute to", "relocate to", "relocation required", "willing to relocate"}
        if any(kw in exclusion_found for kw in onsite_keywords):
            return ParsedLocation(
                policy=LocationPolicy.ONSITE,
                restriction_indicators_found=exclusion_found,
                confidence=0.9,
            )

        # Country-specific restrictions
        if restricted_regions:
            return ParsedLocation(
                policy=LocationPolicy.REMOTE_COUNTRY_SPECIFIC,
                excluded_regions=restricted_regions,
                restriction_indicators_found=exclusion_found,
                confidence=0.85,
            )

        # General regional restriction
        return ParsedLocation(
            policy=LocationPolicy.REMOTE_REGIONAL,
            restriction_indicators_found=exclusion_found,
            confidence=0.8,
        )

    # Check for hybrid
    if hybrid_found:
        return ParsedLocation(
            policy=LocationPolicy.HYBRID,
            remote_indicators_found=hybrid_found,
            confidence=0.85,
        )

    # Check for positive remote indicators
    if inclusion_found:
        # Check for worldwide indicators
        worldwide_keywords = {"worldwide", "anywhere", "global", "work from anywhere",
                             "location independent"}
        if any(kw in inclusion_found for kw in worldwide_keywords):
            return ParsedLocation(
                policy=LocationPolicy.REMOTE_WORLDWIDE,
                remote_indicators_found=inclusion_found,
                confidence=0.95,
            )

        # Turkey/Europe specific mentions are strong positive signals
        turkey_keywords = {"turkey", "türkiye", "europe", "emea", "eu"}
        if any(kw in inclusion_found for kw in turkey_keywords):
            return ParsedLocation(
                policy=LocationPolicy.REMOTE_WORLDWIDE,
                remote_indicators_found=inclusion_found,
                allowed_regions=["Turkey", "Europe"],
                confidence=0.9,
            )

        # Generic "remote" without other context
        return ParsedLocation(
            policy=LocationPolicy.REMOTE_REGIONAL,
            remote_indicators_found=inclusion_found,
            confidence=0.7,  # Lower confidence - could be regionally restricted
        )

    # No clear indicators
    return ParsedLocation(
        policy=LocationPolicy.UNCLEAR,
        confidence=0.5,
    )
