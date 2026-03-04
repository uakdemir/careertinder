"""Rule engine for Tier 1 filtering.

Central orchestrator that loads filter rules from configuration,
applies them in sequence, and produces a final decision with full audit trail.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from jobhunter.filters.rules.base import FilterDecision, FilterRule, RuleResult
from jobhunter.filters.rules.company import CompanyRule
from jobhunter.filters.rules.keyword import KeywordRule
from jobhunter.filters.rules.location import LocationRule
from jobhunter.filters.rules.salary import SalaryRule
from jobhunter.filters.rules.title import TitleBlacklistRule, TitleWhitelistRule

if TYPE_CHECKING:
    from jobhunter.config.schema import FilteringConfig
    from jobhunter.db.models import RawJobPosting

logger = logging.getLogger(__name__)


@dataclass
class FilterOutcome:
    """Complete result of filtering a job through all rules."""

    final_decision: FilterDecision
    rule_results: list[RuleResult] = field(default_factory=list)
    failed_rules: list[str] = field(default_factory=list)
    passed_rules: list[str] = field(default_factory=list)
    ambiguous_rules: list[str] = field(default_factory=list)


class RuleEngine:
    """Applies ordered filter rules to raw job postings.

    Rules are applied in order of computational cost (cheapest first).
    Short-circuits on company whitelist (immediate PASS) and
    company/title blacklist (immediate FAIL).

    Per C3 architecture: rule errors degrade to AMBIGUOUS rather than
    crashing the pipeline.
    """

    def __init__(self, config: FilteringConfig) -> None:
        """Initialize engine with filtering config.

        Args:
            config: FilteringConfig with thresholds and patterns
        """
        self.config = config
        self.rules: list[FilterRule] = self._load_rules()

    def _load_rules(self) -> list[FilterRule]:
        """Load rules in order of computational cost (cheapest first)."""
        return [
            CompanyRule(),  # O(1) set lookup
            TitleBlacklistRule(),  # Fast regex
            TitleWhitelistRule(),  # Fast regex
            LocationRule(),  # String search
            KeywordRule(),  # String search
            SalaryRule(),  # Regex extraction + comparison
        ]

    def filter(self, job: RawJobPosting) -> FilterOutcome:
        """Apply all rules to a job and return the outcome.

        Args:
            job: Raw job posting to filter

        Returns:
            FilterOutcome with final decision and rule-by-rule results
        """
        results: list[RuleResult] = []

        for rule in self.rules:
            try:
                result = rule.evaluate(job, self.config)
            except Exception as e:
                # Per C3: degrade to AMBIGUOUS on rule error, log and continue
                logger.exception(
                    "Rule '%s' raised exception for job raw_id=%s: %s",
                    rule.name,
                    job.raw_id,
                    e,
                )
                result = RuleResult(
                    rule_name=rule.name,
                    decision=FilterDecision.AMBIGUOUS,
                    reason=f"Rule error: {type(e).__name__}: {e}",
                    details={"error": str(e), "error_type": type(e).__name__},
                )
            results.append(result)

            # Short-circuit on company whitelist (immediate PASS)
            if (
                result.decision == FilterDecision.PASS
                and result.rule_name == "company_whitelist"
            ):
                logger.debug(
                    "Job raw_id=%s short-circuited to PASS by company whitelist",
                    job.raw_id,
                )
                return FilterOutcome(
                    final_decision=FilterDecision.PASS,
                    rule_results=results,
                    failed_rules=[],
                    passed_rules=[result.rule_name],
                    ambiguous_rules=[],
                )

            # Short-circuit on company blacklist or title blacklist (immediate FAIL)
            if result.decision == FilterDecision.FAIL and rule.name in (
                "company_blacklist",
                "title_blacklist",
            ):
                logger.debug(
                    "Job raw_id=%s short-circuited to FAIL by %s",
                    job.raw_id,
                    rule.name,
                )
                # Still include the result in the outcome
                return self._build_outcome(results)

        return self._build_outcome(results)

    def _build_outcome(self, results: list[RuleResult]) -> FilterOutcome:
        """Build final outcome from rule results.

        Decision priority:
        - Any FAIL → FAIL
        - Any AMBIGUOUS (no FAIL) → AMBIGUOUS
        - All PASS → PASS
        """
        failed = [r for r in results if r.decision == FilterDecision.FAIL]
        ambiguous = [r for r in results if r.decision == FilterDecision.AMBIGUOUS]
        passed = [r for r in results if r.decision == FilterDecision.PASS]

        if failed:
            final = FilterDecision.FAIL
        elif ambiguous:
            final = FilterDecision.AMBIGUOUS
        else:
            final = FilterDecision.PASS

        return FilterOutcome(
            final_decision=final,
            rule_results=results,
            failed_rules=[r.rule_name for r in failed],
            passed_rules=[r.rule_name for r in passed],
            ambiguous_rules=[r.rule_name for r in ambiguous],
        )
