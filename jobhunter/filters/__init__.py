"""Tier 1 Rule-Based Filtering.

Zero-API-cost filtering that eliminates clearly unqualified postings
before any AI evaluation.
"""

from jobhunter.filters.engine import FilterOutcome, RuleEngine
from jobhunter.filters.rules.base import FilterDecision, RuleResult

__all__ = [
    "FilterDecision",
    "FilterOutcome",
    "RuleEngine",
    "RuleResult",
]
