"""Title matching rules (blacklist/whitelist)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from jobhunter.filters.rules.base import FilterDecision, RuleResult

if TYPE_CHECKING:
    from jobhunter.config.schema import FilteringConfig
    from jobhunter.db.models import RawJobPosting


# Common abbreviation expansions for fuzzy matching
ABBREVIATIONS: dict[str, list[str]] = {
    "sr": ["senior", "sr"],
    "snr": ["senior", "snr"],
    "jr": ["junior", "jr"],
    "eng": ["engineer", "engineering", "eng"],
    "mgr": ["manager", "mgr"],
    "dir": ["director", "dir"],
    "dev": ["developer", "dev"],
    "sw": ["software", "sw"],
}


def _normalize_title(title: str) -> str:
    """Normalize title for matching.

    - Lowercase
    - Expand common abbreviations
    - Normalize whitespace
    """
    normalized = title.lower().strip()

    # Expand abbreviations
    for abbr, expansions in ABBREVIATIONS.items():
        # Match abbreviation with word boundaries and optional period
        pattern = rf"\b{re.escape(abbr)}\.?\b"
        for expansion in expansions:
            if expansion != abbr and re.search(pattern, normalized):
                # Add expanded form for matching
                normalized = re.sub(pattern, expansion, normalized, count=1)
                break

    return normalized


def _pattern_matches(pattern: str, title: str) -> bool:
    """Check if pattern matches title using word boundaries."""
    # Escape special regex chars in pattern, then add word boundaries
    escaped = re.escape(pattern.lower())
    regex = rf"\b{escaped}\b"
    return bool(re.search(regex, title.lower()))


class TitleBlacklistRule:
    """Reject jobs with blacklisted title patterns.

    This is a hard fail - any blacklist match results in FAIL.
    """

    name = "title_blacklist"

    def evaluate(self, job: RawJobPosting, config: FilteringConfig) -> RuleResult:
        """Check title against blacklist patterns."""
        title_normalized = _normalize_title(job.title)

        for pattern in config.title_blacklist:
            if _pattern_matches(pattern, title_normalized):
                return RuleResult(
                    rule_name="title_blacklist",
                    decision=FilterDecision.FAIL,
                    reason=f"Title contains blacklisted term: '{pattern}'",
                    details={
                        "title": job.title,
                        "normalized": title_normalized,
                        "matched_pattern": pattern,
                    },
                )

        return RuleResult(
            rule_name="title_blacklist",
            decision=FilterDecision.PASS,
            reason="Title does not match any blacklist patterns",
            details={"title": job.title, "normalized": title_normalized},
        )


class TitleWhitelistRule:
    """Require at least one whitelist pattern to match.

    No whitelist match results in AMBIGUOUS (not FAIL).
    """

    name = "title_whitelist"

    def evaluate(self, job: RawJobPosting, config: FilteringConfig) -> RuleResult:
        """Check title against whitelist patterns."""
        title_normalized = _normalize_title(job.title)
        matched_patterns: list[str] = []

        for pattern in config.title_whitelist:
            if _pattern_matches(pattern, title_normalized):
                matched_patterns.append(pattern)

        if matched_patterns:
            return RuleResult(
                rule_name="title_whitelist",
                decision=FilterDecision.PASS,
                reason=f"Title matches whitelist patterns: {matched_patterns}",
                details={
                    "title": job.title,
                    "normalized": title_normalized,
                    "matched_patterns": matched_patterns,
                },
            )

        # No whitelist match - AMBIGUOUS, not FAIL
        return RuleResult(
            rule_name="title_whitelist",
            decision=FilterDecision.AMBIGUOUS,
            reason="Title does not match any whitelist patterns",
            details={
                "title": job.title,
                "normalized": title_normalized,
                "whitelist": config.title_whitelist,
            },
        )
