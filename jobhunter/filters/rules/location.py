"""Location/remote policy rule."""

from __future__ import annotations

from typing import TYPE_CHECKING

from jobhunter.filters.parsers.location_parser import LocationPolicy, parse_location
from jobhunter.filters.rules.base import FilterDecision, RuleResult

if TYPE_CHECKING:
    from jobhunter.config.schema import FilteringConfig
    from jobhunter.db.models import RawJobPosting


class LocationRule:
    """Check location/remote policy for remote-from-Turkey feasibility.

    Uses config keywords to customize detection.
    Geo-restricted positions (US only, etc.) are rejected.
    Unclear locations are marked AMBIGUOUS.
    """

    name = "location"

    def evaluate(self, job: RawJobPosting, config: FilteringConfig) -> RuleResult:
        """Evaluate location/remote policy."""
        parsed = parse_location(job.location_raw, job.description)

        # Build custom keywords from config
        # Note: The parser uses default keywords, but config can override
        # For now, use parsed results directly

        if parsed.policy == LocationPolicy.REMOTE_WORLDWIDE:
            return RuleResult(
                rule_name="location",
                decision=FilterDecision.PASS,
                reason="Remote worldwide position",
                details={
                    "policy": parsed.policy.value,
                    "indicators": parsed.remote_indicators_found,
                    "confidence": parsed.confidence,
                },
            )

        if parsed.policy == LocationPolicy.REMOTE_REGIONAL:
            # Check if explicitly allowed regions include Turkey/Europe/EMEA
            allowed_lower = [r.lower() for r in parsed.allowed_regions]
            turkey_compatible = any(
                r in allowed_lower for r in ["turkey", "europe", "emea", "eu"]
            )
            if turkey_compatible:
                return RuleResult(
                    rule_name="location",
                    decision=FilterDecision.PASS,
                    reason=f"Regional remote includes Turkey-compatible regions: {parsed.allowed_regions}",
                    details={
                        "policy": parsed.policy.value,
                        "allowed_regions": parsed.allowed_regions,
                        "confidence": parsed.confidence,
                    },
                )
            # Regional but not sure about Turkey
            return RuleResult(
                rule_name="location",
                decision=FilterDecision.AMBIGUOUS,
                reason="Regional remote - Turkey eligibility unclear",
                details={
                    "policy": parsed.policy.value,
                    "indicators": parsed.remote_indicators_found,
                    "confidence": parsed.confidence,
                },
            )

        if parsed.policy == LocationPolicy.REMOTE_COUNTRY_SPECIFIC:
            return RuleResult(
                rule_name="location",
                decision=FilterDecision.FAIL,
                reason=f"Country-specific restriction: {parsed.excluded_regions}",
                details={
                    "policy": parsed.policy.value,
                    "excluded_regions": parsed.excluded_regions,
                    "restriction_indicators": parsed.restriction_indicators_found,
                },
            )

        if parsed.policy == LocationPolicy.HYBRID:
            return RuleResult(
                rule_name="location",
                decision=FilterDecision.FAIL,
                reason="Hybrid position requires office presence",
                details={
                    "policy": parsed.policy.value,
                    "indicators": parsed.remote_indicators_found,
                },
            )

        if parsed.policy == LocationPolicy.ONSITE:
            return RuleResult(
                rule_name="location",
                decision=FilterDecision.FAIL,
                reason="On-site only position",
                details={
                    "policy": parsed.policy.value,
                    "restriction_indicators": parsed.restriction_indicators_found,
                },
            )

        # UNCLEAR - let Tier 2 decide
        return RuleResult(
            rule_name="location",
            decision=FilterDecision.AMBIGUOUS,
            reason="Remote policy unclear",
            details={
                "policy": parsed.policy.value,
                "location_raw": job.location_raw,
                "confidence": parsed.confidence,
            },
        )
