"""Salary extraction and normalization.

Extracts salary information from raw strings and normalizes to annual USD.
Handles a wide variety of formats encountered in job postings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Static exchange rates to USD (updated manually)
EXCHANGE_RATES_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.10,
    "GBP": 1.26,
    "CAD": 0.74,
    "AUD": 0.65,
    "CHF": 1.13,
    "TRY": 0.031,
}

# Hours per year for hourly rate conversion (40 hrs/week * 52 weeks)
HOURS_PER_YEAR = 2080


@dataclass
class ParsedSalary:
    """Parsed salary information normalized to annual USD."""

    min_annual_usd: int | None
    max_annual_usd: int | None
    original_currency: str
    original_period: str  # "year", "month", "hour"
    confidence: float  # 0.0-1.0
    raw_string: str


def _detect_currency(text: str) -> str:
    """Detect currency from text. Defaults to USD."""
    text_upper = text.upper()

    # Check for explicit currency codes
    if "EUR" in text_upper or "€" in text:
        return "EUR"
    if "GBP" in text_upper or "£" in text:
        return "GBP"
    if "CAD" in text_upper:
        return "CAD"
    if "AUD" in text_upper:
        return "AUD"
    if "CHF" in text_upper:
        return "CHF"
    if "TRY" in text_upper or "TL" in text_upper:
        return "TRY"

    # Default to USD (most common)
    return "USD"


def _detect_period(text: str) -> str:
    """Detect salary period from text. Defaults to year."""
    text_lower = text.lower()

    if any(p in text_lower for p in ["/hr", "/hour", "per hour", "hourly", "/h"]):
        return "hour"
    if any(p in text_lower for p in ["/mo", "/month", "per month", "monthly", "/m"]):
        return "month"
    # Default to annual
    return "year"


def _parse_number(text: str) -> int | None:
    """Parse a number from text, handling K/M suffixes and EU number formats."""
    if not text:
        return None

    # Remove currency symbols and whitespace
    cleaned = re.sub(r"[$€£¥]", "", text).strip()

    # Handle "K" suffix (e.g., "120K" -> 120000)
    k_match = re.match(r"^(\d+(?:[.,]\d+)?)\s*[kK]$", cleaned)
    if k_match:
        num_str = k_match.group(1).replace(",", ".")
        try:
            return int(float(num_str) * 1000)
        except ValueError:
            return None

    # Handle "M" suffix (e.g., "1.2M" -> 1200000)
    m_match = re.match(r"^(\d+(?:[.,]\d+)?)\s*[mM]$", cleaned)
    if m_match:
        num_str = m_match.group(1).replace(",", ".")
        try:
            return int(float(num_str) * 1_000_000)
        except ValueError:
            return None

    # Handle EU number format (90.000 = 90000, not 90.0)
    # EU format uses periods as thousand separators
    eu_match = re.match(r"^(\d{1,3})\.(\d{3})(?:\.(\d{3}))?$", cleaned)
    if eu_match:
        parts = [p for p in eu_match.groups() if p]
        return int("".join(parts))

    # Handle US format with commas (90,000)
    us_match = re.match(r"^(\d{1,3}),(\d{3})(?:,(\d{3}))?$", cleaned)
    if us_match:
        parts = [p for p in us_match.groups() if p]
        return int("".join(parts))

    # Simple integer (including large numbers without separators like 90000)
    int_match = re.match(r"^(\d+)$", cleaned)
    if int_match:
        return int(int_match.group(1))

    return None


def _extract_salary_range(text: str) -> tuple[int | None, int | None]:
    """Extract min and max salary values from text."""
    if not text:
        return None, None

    # Range pattern that handles:
    # - "$90,000 - $120,000"
    # - "$90K-$120K"
    # - "$10,000/mo - $12,000/mo"
    # - "90.000€ - 120.000€"
    # Currency can be before or after the number
    range_patterns = [
        # Currency before: $90,000 - $120,000
        r"[\$€£]\s*(\d[\d,\.]*[kKmM]?)\s*(?:/\w+\s*)?(?:-|–|to)\s*[\$€£]?\s*(\d[\d,\.]*[kKmM]?)(?:\s*/\w+)?",
        # Currency after (EU style): 90.000€ - 120.000€
        r"(\d[\d,\.]*[kKmM]?)\s*[€£]?\s*(?:-|–|to)\s*(\d[\d,\.]*[kKmM]?)\s*[€£]?",
        # Plain numbers with USD/EUR: 90000 - 120000 USD
        r"(\d[\d,\.]*[kKmM]?)\s*(?:-|–|to)\s*(\d[\d,\.]*[kKmM]?)\s*(?:USD|EUR|GBP)?",
    ]

    for range_pattern in range_patterns:
        range_match = re.search(range_pattern, text, re.IGNORECASE)
        if range_match:
            min_val = _parse_number(range_match.group(1))
            max_val = _parse_number(range_match.group(2))
            if min_val and max_val and min_val != max_val:
                return min_val, max_val

    # If range patterns matched but min == max, try again with single value
    range_match = None
    for range_pattern in range_patterns:
        range_match = re.search(range_pattern, text, re.IGNORECASE)
    if range_match:
        min_val = _parse_number(range_match.group(1))
        max_val = _parse_number(range_match.group(2))
        if min_val and max_val:
            return min_val, max_val

    # Single value patterns
    # Currency symbol before number: $90,000
    single_patterns = [
        r"[\$€£]\s*(\d[\d,\.]*[kKmM]?)",
        # Currency code before number: GBP 80,000
        r"(?:USD|EUR|GBP|CAD|AUD|CHF)\s+(\d[\d,\.]*[kKmM]?)",
        # Number with currency code after: 90000 USD
        r"(\d[\d,\.]*[kKmM]?)\s*(?:USD|EUR|GBP|CAD)",
        # Number with currency symbol after (EU style): 90.000€
        r"(\d[\d,\.]*)\s*[€£]",
    ]

    for pattern in single_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = _parse_number(match.group(1))
            if val:
                return val, val

    # Last resort: look for any number that looks like a salary (4+ digits)
    fallback_pattern = r"(\d{4,}(?:[.,]\d{3})*(?:[kKmM])?)"
    fallback_match = re.search(fallback_pattern, text)
    if fallback_match:
        val = _parse_number(fallback_match.group(1))
        if val:
            return val, val

    return None, None


def _normalize_to_annual(amount: int | None, period: str) -> int | None:
    """Convert salary to annual amount based on period."""
    if amount is None:
        return None

    if period == "hour":
        return amount * HOURS_PER_YEAR
    if period == "month":
        return amount * 12

    return amount


def _convert_to_usd(amount: int | None, currency: str) -> int | None:
    """Convert amount to USD using static exchange rates."""
    if amount is None:
        return None

    rate = EXCHANGE_RATES_TO_USD.get(currency, 1.0)
    return int(amount * rate)


def parse_salary(raw: str | None) -> ParsedSalary | None:
    """Parse a raw salary string into normalized annual USD.

    Returns None for unparseable or empty salary strings.
    Returns ParsedSalary with low confidence for ambiguous formats.

    Examples:
        - "$90,000" -> min=90000, max=90000
        - "$90K-$120K" -> min=90000, max=120000
        - "$7,500/mo" -> min=90000, max=90000 (annualized)
        - "Competitive" -> None
        - "" or None -> None
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()

    # Skip clearly unparseable values
    skip_patterns = [
        r"^competitive$",
        r"^doe$",
        r"^negotiable$",
        r"^based on experience$",
        r"^tbd$",
        r"^n/a$",
        r"^not specified$",
        r"^unpaid$",
        r"^equity only$",
    ]
    if any(re.match(p, text, re.IGNORECASE) for p in skip_patterns):
        return None

    # Extract components
    currency = _detect_currency(text)
    period = _detect_period(text)
    min_val, max_val = _extract_salary_range(text)

    # If we couldn't parse any numbers, return None
    if min_val is None and max_val is None:
        return None

    # Normalize to annual
    min_annual = _normalize_to_annual(min_val, period)
    max_annual = _normalize_to_annual(max_val, period)

    # Convert to USD
    min_usd = _convert_to_usd(min_annual, currency)
    max_usd = _convert_to_usd(max_annual, currency)

    # Ensure min <= max
    if min_usd is not None and max_usd is not None and min_usd > max_usd:
        min_usd, max_usd = max_usd, min_usd

    # Calculate confidence based on parsing certainty
    confidence = 1.0
    if currency != "USD":
        confidence *= 0.9  # Slight uncertainty in exchange rates
    if period != "year":
        confidence *= 0.95  # Slight uncertainty in period detection
    if min_usd is None or max_usd is None:
        confidence *= 0.8  # Missing data

    return ParsedSalary(
        min_annual_usd=min_usd,
        max_annual_usd=max_usd,
        original_currency=currency,
        original_period=period,
        confidence=confidence,
        raw_string=raw,
    )
