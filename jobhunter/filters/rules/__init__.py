"""Filter rules for Tier 1 rule-based filtering."""

from jobhunter.filters.rules.base import FilterDecision, FilterRule, RuleResult
from jobhunter.filters.rules.company import CompanyRule
from jobhunter.filters.rules.keyword import KeywordRule
from jobhunter.filters.rules.location import LocationRule
from jobhunter.filters.rules.salary import SalaryRule
from jobhunter.filters.rules.title import TitleBlacklistRule, TitleWhitelistRule

__all__ = [
    "CompanyRule",
    "FilterDecision",
    "FilterRule",
    "KeywordRule",
    "LocationRule",
    "RuleResult",
    "SalaryRule",
    "TitleBlacklistRule",
    "TitleWhitelistRule",
]
