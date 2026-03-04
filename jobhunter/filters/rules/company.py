"""Company blacklist/whitelist rule."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from jobhunter.filters.rules.base import FilterDecision, RuleResult

if TYPE_CHECKING:
    from jobhunter.config.schema import FilteringConfig
    from jobhunter.db.models import RawJobPosting


def normalize_company_name(name: str) -> str:
    """Normalize company name for comparison.

    - Lowercase
    - Strip whitespace
    - Remove common suffixes (Inc., LLC, Ltd., Corp., GmbH, etc.)
    - Remove special characters
    """
    normalized = name.lower().strip()

    # Remove common company suffixes
    suffixes = [
        r",?\s*inc\.?$",
        r",?\s*llc\.?$",
        r",?\s*ltd\.?$",
        r",?\s*corp\.?$",
        r",?\s*corporation$",
        r",?\s*gmbh$",
        r",?\s*plc$",
        r",?\s*limited$",
        r",?\s*co\.?$",
        r",?\s*company$",
    ]
    for suffix in suffixes:
        normalized = re.sub(suffix, "", normalized, flags=re.IGNORECASE)

    # Remove special characters but keep alphanumeric and spaces
    normalized = re.sub(r"[^\w\s]", "", normalized)

    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


class CompanyRule:
    """Check company against blacklist and whitelist.

    Whitelist takes precedence - whitelisted companies always pass.
    Blacklisted companies always fail.
    Other companies pass this rule.
    """

    name = "company"

    def evaluate(self, job: RawJobPosting, config: FilteringConfig) -> RuleResult:
        """Evaluate company against whitelist and blacklist."""
        company_normalized = normalize_company_name(job.company)

        # Build normalized sets for comparison
        whitelist_normalized = {normalize_company_name(c) for c in config.company_whitelist}
        blacklist_normalized = {normalize_company_name(c) for c in config.company_blacklist}

        # Whitelist check first (dream companies)
        if company_normalized in whitelist_normalized:
            return RuleResult(
                rule_name="company_whitelist",
                decision=FilterDecision.PASS,
                reason=f"Company '{job.company}' is on whitelist",
                details={"company": job.company, "normalized": company_normalized},
            )

        # Blacklist check
        if company_normalized in blacklist_normalized:
            return RuleResult(
                rule_name="company_blacklist",
                decision=FilterDecision.FAIL,
                reason=f"Company '{job.company}' is blacklisted",
                details={"company": job.company, "normalized": company_normalized},
            )

        # Not on either list - pass this rule
        return RuleResult(
            rule_name="company",
            decision=FilterDecision.PASS,
            reason="Company not on blacklist",
            details={"company": job.company, "normalized": company_normalized},
        )
