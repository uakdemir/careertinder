"""Salary gate rule."""

from __future__ import annotations

from typing import TYPE_CHECKING

from jobhunter.filters.parsers.salary_parser import parse_salary
from jobhunter.filters.rules.base import FilterDecision, RuleResult

if TYPE_CHECKING:
    from jobhunter.config.schema import FilteringConfig
    from jobhunter.db.models import RawJobPosting


class SalaryRule:
    """Check if salary meets minimum threshold.

    Missing salary results in AMBIGUOUS (conservative filtering).
    Salary below threshold results in FAIL.
    Salary at or above threshold results in PASS.
    """

    name = "salary"

    def evaluate(self, job: RawJobPosting, config: FilteringConfig) -> RuleResult:
        """Evaluate salary against minimum threshold."""
        parsed = parse_salary(job.salary_raw)

        # Missing or unparseable salary - AMBIGUOUS, not FAIL
        if parsed is None:
            return RuleResult(
                rule_name="salary",
                decision=FilterDecision.AMBIGUOUS,
                reason="Salary not specified or unparseable",
                details={
                    "salary_raw": job.salary_raw,
                    "threshold_usd": config.salary_min_usd,
                },
            )

        # Check minimum salary meets threshold
        min_salary = parsed.min_annual_usd

        if min_salary is None:
            return RuleResult(
                rule_name="salary",
                decision=FilterDecision.AMBIGUOUS,
                reason="Could not determine minimum salary",
                details={
                    "salary_raw": job.salary_raw,
                    "parsed": {
                        "min": parsed.min_annual_usd,
                        "max": parsed.max_annual_usd,
                        "currency": parsed.original_currency,
                        "period": parsed.original_period,
                    },
                    "threshold_usd": config.salary_min_usd,
                },
            )

        if min_salary < config.salary_min_usd:
            return RuleResult(
                rule_name="salary",
                decision=FilterDecision.FAIL,
                reason=f"Salary ${min_salary:,} below threshold ${config.salary_min_usd:,}",
                details={
                    "salary_raw": job.salary_raw,
                    "parsed_min_usd": min_salary,
                    "parsed_max_usd": parsed.max_annual_usd,
                    "threshold_usd": config.salary_min_usd,
                    "currency": parsed.original_currency,
                    "confidence": parsed.confidence,
                },
            )

        # Salary meets or exceeds threshold
        return RuleResult(
            rule_name="salary",
            decision=FilterDecision.PASS,
            reason=f"Salary ${min_salary:,} meets threshold ${config.salary_min_usd:,}",
            details={
                "salary_raw": job.salary_raw,
                "parsed_min_usd": min_salary,
                "parsed_max_usd": parsed.max_annual_usd,
                "threshold_usd": config.salary_min_usd,
                "currency": parsed.original_currency,
                "confidence": parsed.confidence,
            },
        )
