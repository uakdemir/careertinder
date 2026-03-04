"""Keyword inclusion/exclusion filter."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from jobhunter.filters.rules.base import FilterDecision, RuleResult

if TYPE_CHECKING:
    from jobhunter.config.schema import FilteringConfig
    from jobhunter.db.models import RawJobPosting


def _keyword_matches(keyword: str, text: str) -> bool:
    """Match keyword with word boundaries for single words, substring for phrases.

    Single-word tokens (e.g., "go", "aws") use word boundaries to avoid
    false positives like "good" matching "go" or "draws" matching "aws".
    Multi-word phrases use normalized substring matching.
    """
    keyword_lower = keyword.lower()
    text_lower = text.lower()

    if " " in keyword_lower:
        # Multi-word phrase: substring match
        return keyword_lower in text_lower
    else:
        # Single word: use word boundaries
        pattern = rf"\b{re.escape(keyword_lower)}\b"
        return bool(re.search(pattern, text_lower))


class KeywordRule:
    """Filter by required and excluded keywords.

    - Excluded keyword found → FAIL
    - No required keyword found → AMBIGUOUS
    - Otherwise → PASS
    """

    name = "keyword"

    def evaluate(self, job: RawJobPosting, config: FilteringConfig) -> RuleResult:
        """Check for required and excluded keywords in title and description."""
        text = f"{job.title} {job.description}"

        # Check excluded keywords first (hard fail)
        for keyword in config.excluded_keywords:
            if _keyword_matches(keyword, text):
                return RuleResult(
                    rule_name="keyword_exclusion",
                    decision=FilterDecision.FAIL,
                    reason=f"Excluded keyword found: '{keyword}'",
                    details={
                        "keyword": keyword,
                        "excluded_keywords": config.excluded_keywords,
                    },
                )

        # Check required keywords (at least one must be present)
        if config.required_keywords:
            found = [kw for kw in config.required_keywords if _keyword_matches(kw, text)]
            if not found:
                return RuleResult(
                    rule_name="keyword_requirement",
                    decision=FilterDecision.AMBIGUOUS,
                    reason="No required keywords found",
                    details={
                        "required_keywords": config.required_keywords,
                        "found_keywords": [],
                    },
                )
            # Found at least one required keyword
            return RuleResult(
                rule_name="keyword",
                decision=FilterDecision.PASS,
                reason=f"Required keywords found: {found}",
                details={
                    "found_keywords": found,
                    "required_keywords": config.required_keywords,
                },
            )

        # No required keywords configured - pass
        return RuleResult(
            rule_name="keyword",
            decision=FilterDecision.PASS,
            reason="No keyword requirements configured",
            details={},
        )
