"""Tests for salary parser."""

import pytest

from jobhunter.filters.parsers.salary_parser import parse_salary


class TestParseSalary:
    """Test salary parsing for various formats."""

    @pytest.mark.parametrize(
        "raw,expected_min,expected_max",
        [
            # Simple USD formats
            ("$90,000", 90000, 90000),
            ("$90000", 90000, 90000),
            ("$90K", 90000, 90000),
            ("$90k", 90000, 90000),
            # USD ranges
            ("$90,000 - $120,000", 90000, 120000),
            ("$90K-$120K", 90000, 120000),
            ("$90k - $120k", 90000, 120000),
            ("90k-120k USD", 90000, 120000),
            ("90,000-120,000 USD", 90000, 120000),
            ("USD 90,000 - 120,000", 90000, 120000),
            # With 'to' separator
            ("$90,000 to $120,000", 90000, 120000),
            # En-dash separator
            ("$90K–$120K", 90000, 120000),
        ],
    )
    def test_usd_salary_formats(self, raw: str, expected_min: int, expected_max: int) -> None:
        """Test various USD salary formats."""
        result = parse_salary(raw)
        assert result is not None
        assert result.min_annual_usd == expected_min
        assert result.max_annual_usd == expected_max
        assert result.original_currency == "USD"

    @pytest.mark.parametrize(
        "raw,expected_min,expected_max",
        [
            # Monthly to annual conversion (x12)
            ("$7,500/mo", 90000, 90000),
            ("$7500/month", 90000, 90000),
            ("$7,500 per month", 90000, 90000),
            ("$10,000/mo - $12,000/mo", 120000, 144000),
        ],
    )
    def test_monthly_salary_conversion(self, raw: str, expected_min: int, expected_max: int) -> None:
        """Test monthly salary to annual conversion."""
        result = parse_salary(raw)
        assert result is not None
        assert result.min_annual_usd == expected_min
        assert result.max_annual_usd == expected_max
        assert result.original_period == "month"

    @pytest.mark.parametrize(
        "raw,expected_min,expected_max",
        [
            # Hourly to annual conversion (x2080)
            ("$45/hr", 93600, 93600),
            ("$45-$55/hr", 93600, 114400),
            ("$50 per hour", 104000, 104000),
            ("$50/hour", 104000, 104000),
        ],
    )
    def test_hourly_salary_conversion(self, raw: str, expected_min: int, expected_max: int) -> None:
        """Test hourly salary to annual conversion."""
        result = parse_salary(raw)
        assert result is not None
        assert result.min_annual_usd == expected_min
        assert result.max_annual_usd == expected_max
        assert result.original_period == "hour"

    @pytest.mark.parametrize(
        "raw,currency,expected_min_approx,expected_max_approx",
        [
            # EUR (rate ~1.10)
            ("€80,000/year", "EUR", 88000, 88000),
            ("EUR 80,000 - 100,000", "EUR", 88000, 110000),
            # GBP (rate ~1.26)
            ("£70K - £90K", "GBP", 88200, 113400),
            ("GBP 80,000", "GBP", 100800, 100800),
        ],
    )
    def test_currency_conversion(
        self, raw: str, currency: str, expected_min_approx: int, expected_max_approx: int
    ) -> None:
        """Test currency conversion to USD."""
        result = parse_salary(raw)
        assert result is not None
        assert result.original_currency == currency
        # Allow 1% tolerance for float conversion
        assert result.min_annual_usd is not None
        assert result.max_annual_usd is not None
        assert abs(result.min_annual_usd - expected_min_approx) < expected_min_approx * 0.01
        assert abs(result.max_annual_usd - expected_max_approx) < expected_max_approx * 0.01

    @pytest.mark.parametrize(
        "raw",
        [
            # EU number format (periods as thousand separators)
            "90.000€ - 120.000€",
            "90.000 - 120.000 EUR",
        ],
    )
    def test_eu_number_format(self, raw: str) -> None:
        """Test EU number format parsing (periods as thousand separators)."""
        result = parse_salary(raw)
        assert result is not None
        # 90.000 EUR = 90000 * 1.10 = 99000 USD
        # 120.000 EUR = 120000 * 1.10 = 132000 USD
        assert result.min_annual_usd == 99000
        assert result.max_annual_usd == 132000
        assert result.original_currency == "EUR"

    @pytest.mark.parametrize(
        "raw",
        [
            "Competitive",
            "competitive",
            "DOE",
            "doe",
            "Negotiable",
            "Based on experience",
            "TBD",
            "N/A",
            "Not specified",
            "Unpaid",
            "Equity only",
            "",
            None,
            "   ",
        ],
    )
    def test_unparseable_returns_none(self, raw: str | None) -> None:
        """Test that unparseable salary strings return None."""
        result = parse_salary(raw)
        assert result is None

    def test_confidence_high_for_standard_usd(self) -> None:
        """Test high confidence for standard USD annual salary."""
        result = parse_salary("$100,000 - $150,000")
        assert result is not None
        assert result.confidence >= 0.9

    def test_confidence_lower_for_currency_conversion(self) -> None:
        """Test slightly lower confidence when currency conversion is applied."""
        result = parse_salary("€100,000")
        assert result is not None
        # Currency conversion reduces confidence by 0.9 factor
        assert result.confidence < 1.0

    def test_confidence_lower_for_period_conversion(self) -> None:
        """Test slightly lower confidence when period conversion is applied."""
        result = parse_salary("$10,000/month")
        assert result is not None
        # Period conversion reduces confidence by 0.95 factor
        assert result.confidence < 1.0

    def test_min_max_swapped_if_needed(self) -> None:
        """Test that min/max are swapped if provided in wrong order."""
        # This shouldn't normally happen, but parser should handle it
        result = parse_salary("$120K - $90K")
        assert result is not None
        assert result.min_annual_usd == 90000
        assert result.max_annual_usd == 120000

    def test_raw_string_preserved(self) -> None:
        """Test that original raw string is preserved in result."""
        raw = "$90,000 - $120,000 USD"
        result = parse_salary(raw)
        assert result is not None
        assert result.raw_string == raw
