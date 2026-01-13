"""Tests for GDV calculator validation functions."""
from datetime import datetime, timedelta

import pytest

from src.analysis.gdv_calculator import (
    sanity_check_gdv,
    validate_unit_value_against_rent,
)
from src.data_sources.land_registry import ComparableSale


class TestValidateUnitValueAgainstRent:
    """Tests for rental yield validation."""

    def test_valid_yield_within_range(self):
        """Value is reasonable when yield is 5-10%."""
        # £85,000 value with £436/month rent = 6.2% yield
        result = validate_unit_value_against_rent(
            estimated_value=85000,
            monthly_rent=436,
        )
        assert result["valid"] is True
        assert 6.0 <= result["implied_yield"] <= 6.5

    def test_value_too_high_low_yield(self):
        """Detects when value is too high (yield too low)."""
        # £345,000 value with £436/month rent = 1.5% yield - WAY too low!
        result = validate_unit_value_against_rent(
            estimated_value=345000,
            monthly_rent=436,
        )
        assert result["valid"] is False
        assert result["issue"] == "value_too_high"
        assert result["implied_yield"] < 5.0
        # Should suggest a corrected value around £100k
        assert 80000 <= result["corrected_value"] <= 110000

    def test_conservative_valuation_high_yield(self):
        """Accepts conservative valuations (yield too high)."""
        # £50,000 value with £436/month rent = 10.5% yield - conservative
        result = validate_unit_value_against_rent(
            estimated_value=50000,
            monthly_rent=436,
        )
        assert result["valid"] is True
        assert result.get("note") == "conservative_valuation"
        assert result["implied_yield"] > 10.0

    def test_missing_rent_data_skipped(self):
        """Skips validation when rent data is missing."""
        result = validate_unit_value_against_rent(
            estimated_value=100000,
            monthly_rent=0,
        )
        assert result["valid"] is True
        assert result["skipped"] is True

    def test_missing_value_data_skipped(self):
        """Skips validation when value data is missing."""
        result = validate_unit_value_against_rent(
            estimated_value=0,
            monthly_rent=500,
        )
        assert result["valid"] is True
        assert result["skipped"] is True

    def test_custom_yield_range(self):
        """Allows custom yield range for different markets."""
        # In a high-yield area, 8% might be the minimum
        result = validate_unit_value_against_rent(
            estimated_value=75000,
            monthly_rent=500,  # 8% yield
            min_yield=0.08,
            max_yield=0.12,
        )
        assert result["valid"] is True


class TestSanityCheckGDV:
    """Tests for GDV sanity checks."""

    def _make_comparable(
        self,
        price: int,
        property_type: str = "F",
        days_ago: int = 30,
    ) -> ComparableSale:
        """Helper to create a ComparableSale."""
        return ComparableSale(
            address="Test Address",
            postcode="PR9 0NP",
            price=price,
            sale_date=datetime.now() - timedelta(days=days_ago),
            property_type=property_type,
            new_build=False,
            estate_type="L",
            transaction_category="standard",
            raw_data={},
        )

    def test_valid_gdv_passes(self):
        """Reasonable GDV passes all checks."""
        # 6 units at £85k each = £510k GDV on £319k asking
        comparables = [self._make_comparable(80000) for _ in range(5)]
        result = sanity_check_gdv(
            total_gdv=510000,
            asking_price=319500,
            num_units=6,
            comparables=comparables,
        )
        assert result["passed"] is True
        assert len(result["issues"]) == 0

    def test_unit_exceeds_block_price_fails(self):
        """Fails when single unit value > block asking price."""
        # 6 units at £345k each = £2.07M GDV on £319k asking - WRONG!
        comparables = [self._make_comparable(345000) for _ in range(5)]
        result = sanity_check_gdv(
            total_gdv=2070000,
            asking_price=319500,
            num_units=6,
            comparables=comparables,
        )
        assert result["passed"] is False
        assert any(i["check"] == "unit_exceeds_block_price" for i in result["issues"])

    def test_extreme_gdv_ratio_fails(self):
        """Fails when GDV > 5x asking price."""
        result = sanity_check_gdv(
            total_gdv=2000000,
            asking_price=300000,
            num_units=6,
            comparables=[],
        )
        assert result["passed"] is False
        assert any(i["check"] == "gdv_ratio_extreme" for i in result["issues"])

    def test_high_gdv_ratio_warns(self):
        """Warns when GDV is 3-5x asking price."""
        result = sanity_check_gdv(
            total_gdv=1000000,
            asking_price=300000,
            num_units=6,
            comparables=[],
        )
        assert result["passed"] is True  # Passes but with warning
        assert any(w["check"] == "gdv_ratio_high" for w in result["warnings"])

    def test_mixed_property_types_warns(self):
        """Warns when comparables include non-flat properties."""
        comparables = [
            self._make_comparable(80000, "F"),
            self._make_comparable(80000, "F"),
            self._make_comparable(200000, "T"),  # Terraced house
            self._make_comparable(250000, "S"),  # Semi-detached
        ]
        result = sanity_check_gdv(
            total_gdv=500000,
            asking_price=300000,
            num_units=6,
            comparables=comparables,
        )
        assert any(w["check"] == "mixed_property_types" for w in result["warnings"])

    def test_comparable_price_mismatch_fails(self):
        """Fails when average comparable is way higher than per-unit asking."""
        # Block asking £300k for 6 units = £50k per unit
        # But comparables average £300k - clearly using houses!
        comparables = [
            self._make_comparable(300000, "F"),
            self._make_comparable(320000, "F"),
            self._make_comparable(280000, "F"),
        ]
        result = sanity_check_gdv(
            total_gdv=1800000,  # 6 x £300k
            asking_price=300000,
            num_units=6,
            comparables=comparables,
        )
        assert result["passed"] is False
        assert any(i["check"] == "comparable_price_mismatch" for i in result["issues"])

    def test_flats_only_no_warning(self):
        """No warning when all comparables are flats."""
        comparables = [
            self._make_comparable(80000, "F"),
            self._make_comparable(85000, "F"),
            self._make_comparable(90000, "F"),
        ]
        result = sanity_check_gdv(
            total_gdv=500000,
            asking_price=300000,
            num_units=6,
            comparables=comparables,
        )
        assert not any(w["check"] == "mixed_property_types" for w in result["warnings"])


class TestRealWorldScenario:
    """Test the exact scenario from the bug report."""

    def _make_comparable(
        self,
        price: int,
        property_type: str = "F",
    ) -> ComparableSale:
        return ComparableSale(
            address="Test Address",
            postcode="PR9 0NP",
            price=price,
            sale_date=datetime.now() - timedelta(days=60),
            property_type=property_type,
            new_build=False,
            estate_type="L",
            transaction_category="standard",
            raw_data={},
        )

    def test_southport_block_wrong_valuations_detected(self):
        """
        The actual bug: 6-flat block in Southport valued at £2.07M instead of ~£510k.

        Actual property:
        - 6 apartments in converted Victorian building
        - Guide price: £319,500 for WHOLE BLOCK
        - Rental income: £31,428/year (~£436/month per unit)

        Bug showed:
        - Each unit valued at £345,000 (house prices!)
        - Total GDV: £2,070,000

        Correct valuations:
        - Each flat worth ~£75k-£90k
        - Total GDV: ~£510,000
        """
        # The WRONG comparables that were being used (house prices)
        wrong_comparables = [
            self._make_comparable(345000, "D"),  # Detached house
            self._make_comparable(320000, "S"),  # Semi-detached
            self._make_comparable(350000, "T"),  # Terraced house
        ]

        wrong_gdv = 6 * 345000  # £2,070,000

        # Sanity check should catch this
        result = sanity_check_gdv(
            total_gdv=wrong_gdv,
            asking_price=319500,
            num_units=6,
            comparables=wrong_comparables,
        )

        # Should fail multiple checks
        assert result["passed"] is False
        assert len(result["issues"]) >= 1

        # Should detect unit > block price
        assert any(i["check"] == "unit_exceeds_block_price" for i in result["issues"])

        # Rental yield check should also catch it
        yield_result = validate_unit_value_against_rent(
            estimated_value=345000,  # Wrong value
            monthly_rent=436,  # Actual rent
        )
        assert yield_result["valid"] is False
        assert yield_result["issue"] == "value_too_high"
        # Corrected value should be around £85k-£105k
        assert 80000 <= yield_result["corrected_value"] <= 110000

    def test_southport_block_correct_valuations_pass(self):
        """Correct valuations for the Southport block should pass."""
        # CORRECT comparables (flat prices)
        correct_comparables = [
            self._make_comparable(78000, "F"),
            self._make_comparable(85000, "F"),
            self._make_comparable(82000, "F"),
            self._make_comparable(90000, "F"),
            self._make_comparable(75000, "F"),
        ]

        correct_gdv = 6 * 85000  # £510,000

        result = sanity_check_gdv(
            total_gdv=correct_gdv,
            asking_price=319500,
            num_units=6,
            comparables=correct_comparables,
        )

        # Should pass all checks
        assert result["passed"] is True
        assert len(result["issues"]) == 0

        # Rental yield should be reasonable
        yield_result = validate_unit_value_against_rent(
            estimated_value=85000,
            monthly_rent=436,
        )
        assert yield_result["valid"] is True
        assert 5.0 <= yield_result["implied_yield"] <= 7.0
