"""Base classes and types for filter rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from jobhunter.config.schema import FilteringConfig
    from jobhunter.db.models import RawJobPosting


class FilterDecision(Enum):
    """Outcome of a filter rule evaluation."""

    PASS = "pass"
    FAIL = "fail"
    AMBIGUOUS = "ambiguous"


@dataclass
class RuleResult:
    """Result of evaluating a single rule against a job."""

    rule_name: str
    decision: FilterDecision
    reason: str
    details: dict | None = field(default=None)


class FilterRule(Protocol):
    """Protocol for filter rules.

    Each rule evaluates a single aspect of job eligibility.
    Rules should be stateless and idempotent.
    """

    name: str

    def evaluate(self, job: RawJobPosting, config: FilteringConfig) -> RuleResult:
        """Evaluate a job against this rule.

        Args:
            job: The raw job posting to evaluate
            config: Filtering configuration with thresholds and patterns

        Returns:
            RuleResult with decision and reasoning
        """
        ...
