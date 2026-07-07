"""
Tests for liquidity calibration weight computation and merging.

Tests the compute_liquidity_calibration_weights() helper function
that maps investor registry types to calibration types and computes weights.
Also tests merging computed weights into calibration investor assumptions.
"""

import pytest
from fund_risk_workflow.data.reference_data import (
    compute_liquidity_calibration_weights,
    merge_computed_weights_into_investors,
    build_lmt_parameters,
)


class TestLiquidityCalibrationWeights:
    """Test suite for weight computation from investor registry."""

    def test_pension_plan_maps_to_institutional(self):
        """Pension Plan investor type maps to Institutional calibration type."""
        investor_records = [
            {"investor_type": "Pension Plan", "nav_pct": 0.5},
            {"investor_type": "Retail", "nav_pct": 0.5},
        ]
        investor_type_mapping = {
            "Pension Plan": "Institutional",
            "Retail": "Retail",
        }
        calibration_investors = [
            {"type": "Institutional", "base_redemption_rate": 0.04},
            {"type": "Retail", "base_redemption_rate": 0.03},
        ]

        weights = compute_liquidity_calibration_weights(
            investor_records,
            investor_type_mapping,
            calibration_investors,
        )

        assert weights["Institutional"] == pytest.approx(0.5)
        assert weights["Retail"] == pytest.approx(0.5)

    def test_multiple_types_map_to_institutional_and_sum(self):
        """Platform, Insurance, and Pension Plan all map to Institutional and sum correctly."""
        investor_records = [
            {"investor_type": "Pension Plan", "nav_pct": 0.20},
            {"investor_type": "Platform", "nav_pct": 0.15},
            {"investor_type": "Insurance", "nav_pct": 0.10},
            {"investor_type": "Retail", "nav_pct": 0.55},
        ]
        investor_type_mapping = {
            "Pension Plan": "Institutional",
            "Platform": "Institutional",
            "Insurance": "Institutional",
            "Retail": "Retail",
        }
        calibration_investors = [
            {"type": "Institutional", "base_redemption_rate": 0.04},
            {"type": "Retail", "base_redemption_rate": 0.03},
        ]

        weights = compute_liquidity_calibration_weights(
            investor_records,
            investor_type_mapping,
            calibration_investors,
        )

        assert weights["Institutional"] == pytest.approx(0.45)
        assert weights["Retail"] == pytest.approx(0.55)
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_retail_stays_retail(self):
        """Retail investor type remains mapped to Retail calibration type."""
        investor_records = [
            {"investor_type": "Retail", "nav_pct": 1.0}
        ]
        investor_type_mapping = {"Retail": "Retail"}
        calibration_investors = [
            {"type": "Retail", "base_redemption_rate": 0.03}
        ]

        weights = compute_liquidity_calibration_weights(
            investor_records,
            investor_type_mapping,
            calibration_investors,
        )

        assert weights == {"Retail": 1.0}

    def test_family_office_mapping(self):
        """Family Office investor type maps to Family Office calibration type."""
        investor_records = [
            {"investor_type": "Family Office", "nav_pct": 0.30},
            {"investor_type": "Retail", "nav_pct": 0.70},
        ]
        investor_type_mapping = {
            "Family Office": "Family Office",
            "Retail": "Retail",
        }
        calibration_investors = [
            {"type": "Family Office", "base_redemption_rate": 0.02},
            {"type": "Retail", "base_redemption_rate": 0.03},
        ]

        weights = compute_liquidity_calibration_weights(
            investor_records,
            investor_type_mapping,
            calibration_investors,
        )

        assert weights["Family Office"] == pytest.approx(0.30)
        assert weights["Retail"] == pytest.approx(0.70)

    def test_unmapped_investor_type_raises_error(self):
        """Unmapped investor type raises clear ValueError."""
        investor_records = [
            {"investor_type": "UnknownType", "nav_pct": 1.0}
        ]
        investor_type_mapping = {"Retail": "Retail"}
        calibration_investors = [
            {"type": "Retail", "base_redemption_rate": 0.03}
        ]

        with pytest.raises(ValueError) as exc_info:
            compute_liquidity_calibration_weights(
                investor_records,
                investor_type_mapping,
                calibration_investors,
            )

        assert "UnknownType" in str(exc_info.value)
        assert "not found in investor_type_mapping" in str(exc_info.value)

    def test_mapped_type_missing_from_calibration_raises_error(self):
        """Mapped calibration type not in assumptions raises clear ValueError."""
        investor_records = [
            {"investor_type": "Pension Plan", "nav_pct": 1.0}
        ]
        investor_type_mapping = {
            "Pension Plan": "Institutional"
        }
        calibration_investors = [
            {"type": "Retail", "base_redemption_rate": 0.03}
            # Institutional NOT in calibration
        ]

        with pytest.raises(ValueError) as exc_info:
            compute_liquidity_calibration_weights(
                investor_records,
                investor_type_mapping,
                calibration_investors,
            )

        assert "Institutional" in str(exc_info.value)
        assert "not found in calibration investor types" in str(exc_info.value)

    def test_total_nav_pct_too_low_raises_error(self):
        """Total nav_pct < 0.95 raises ValueError."""
        investor_records = [
            {"investor_type": "Retail", "nav_pct": 0.90}
            # Sum = 0.90, which is < 0.95
        ]
        investor_type_mapping = {"Retail": "Retail"}
        calibration_investors = [
            {"type": "Retail", "base_redemption_rate": 0.03}
        ]

        with pytest.raises(ValueError) as exc_info:
            compute_liquidity_calibration_weights(
                investor_records,
                investor_type_mapping,
                calibration_investors,
            )

        assert "Total investor nav_pct" in str(exc_info.value)
        assert "expected close to 1.0" in str(exc_info.value)

    def test_total_nav_pct_too_high_raises_error(self):
        """Total nav_pct > 1.05 raises ValueError."""
        investor_records = [
            {"investor_type": "Retail", "nav_pct": 1.10}
            # Sum = 1.10, which is > 1.05
        ]
        investor_type_mapping = {"Retail": "Retail"}
        calibration_investors = [
            {"type": "Retail", "base_redemption_rate": 0.03}
        ]

        with pytest.raises(ValueError) as exc_info:
            compute_liquidity_calibration_weights(
                investor_records,
                investor_type_mapping,
                calibration_investors,
            )

        assert "Total investor nav_pct" in str(exc_info.value)
        assert "expected close to 1.0" in str(exc_info.value)

    def test_total_nav_pct_exactly_one_passes(self):
        """Total nav_pct = 1.0 exactly passes validation."""
        investor_records = [
            {"investor_type": "Institutional", "nav_pct": 0.45},
            {"investor_type": "Retail", "nav_pct": 0.55},
        ]
        investor_type_mapping = {
            "Institutional": "Institutional",
            "Retail": "Retail",
        }
        calibration_investors = [
            {"type": "Institutional", "base_redemption_rate": 0.04},
            {"type": "Retail", "base_redemption_rate": 0.03},
        ]

        weights = compute_liquidity_calibration_weights(
            investor_records,
            investor_type_mapping,
            calibration_investors,
        )

        assert weights["Institutional"] == pytest.approx(0.45)
        assert weights["Retail"] == pytest.approx(0.55)

    def test_missing_nav_pct_defaults_to_zero(self):
        """Investor record without nav_pct defaults to 0.0."""
        investor_records = [
            {"investor_type": "Retail"},  # No nav_pct key
            {"investor_type": "Retail", "nav_pct": 1.0},
        ]
        investor_type_mapping = {"Retail": "Retail"}
        calibration_investors = [
            {"type": "Retail", "base_redemption_rate": 0.03}
        ]

        weights = compute_liquidity_calibration_weights(
            investor_records,
            investor_type_mapping,
            calibration_investors,
        )

        assert weights["Retail"] == pytest.approx(1.0)

    def test_three_calibration_types_with_mixed_mapping(self):
        """Complex mix of registry types mapping to all three calibration types."""
        investor_records = [
            {"investor_type": "Pension Plan", "nav_pct": 0.20},
            {"investor_type": "Fund of Funds", "nav_pct": 0.10},
            {"investor_type": "Retail", "nav_pct": 0.40},
            {"investor_type": "Family Office", "nav_pct": 0.30},
        ]
        investor_type_mapping = {
            "Pension Plan": "Institutional",
            "Fund of Funds": "Institutional",
            "Retail": "Retail",
            "Family Office": "Family Office",
        }
        calibration_investors = [
            {"type": "Institutional", "base_redemption_rate": 0.04},
            {"type": "Retail", "base_redemption_rate": 0.03},
            {"type": "Family Office", "base_redemption_rate": 0.02},
        ]

        weights = compute_liquidity_calibration_weights(
            investor_records,
            investor_type_mapping,
            calibration_investors,
        )

        assert weights["Institutional"] == pytest.approx(0.30)
        assert weights["Retail"] == pytest.approx(0.40)
        assert weights["Family Office"] == pytest.approx(0.30)
        assert sum(weights.values()) == pytest.approx(1.0)


class TestMergeWeightsIntoInvestors:
    """Test suite for merging computed weights into calibration investors."""

    def test_merge_adds_weight_field(self):
        """Merge adds 'weight' field to calibration investors."""
        calibration_investors = [
            {"type": "Retail", "base_redemption_rate": 0.03, "stress_redemption_rate": 0.12},
            {"type": "Institutional", "base_redemption_rate": 0.04, "stress_redemption_rate": 0.18},
        ]
        computed_weights = {"Retail": 0.60, "Institutional": 0.40}

        result = merge_computed_weights_into_investors(calibration_investors, computed_weights)

        assert len(result) == 2
        assert result[0]["type"] == "Retail"
        assert result[0]["weight"] == 0.60
        assert result[0]["base_redemption_rate"] == 0.03
        assert result[1]["type"] == "Institutional"
        assert result[1]["weight"] == 0.40
        assert result[1]["base_redemption_rate"] == 0.04

    def test_merge_preserves_all_fields(self):
        """Merge preserves all existing fields from calibration investors."""
        calibration_investors = [
            {
                "type": "Retail",
                "base_redemption_rate": 0.03,
                "stress_redemption_rate": 0.12,
                "custom_field": "value",
            },
        ]
        computed_weights = {"Retail": 1.0}

        result = merge_computed_weights_into_investors(calibration_investors, computed_weights)

        assert result[0]["custom_field"] == "value"
        assert result[0]["weight"] == 1.0

    def test_merge_sets_weight_to_zero_for_missing_types(self):
        """Merge sets weight to 0.0 if calibration type not in computed weights."""
        calibration_investors = [
            {"type": "Retail", "base_redemption_rate": 0.03},
            {"type": "Institutional", "base_redemption_rate": 0.04},
            {"type": "Family Office", "base_redemption_rate": 0.02},
        ]
        computed_weights = {
            "Retail": 0.95,
            "Institutional": 0.05,
            # Family Office missing
        }

        result = merge_computed_weights_into_investors(calibration_investors, computed_weights)

        assert len(result) == 3
        assert result[0]["weight"] == 0.95
        assert result[1]["weight"] == 0.05
        assert result[2]["weight"] == 0.0  # Missing type gets zero weight

    def test_merge_raises_if_computed_weight_type_not_in_calibration(self):
        """Merge raises if computed weight type not in calibration investors."""
        calibration_investors = [
            {"type": "Retail", "base_redemption_rate": 0.03},
        ]
        computed_weights = {"Retail": 0.5, "UnknownType": 0.5}

        with pytest.raises(ValueError) as exc_info:
            merge_computed_weights_into_investors(calibration_investors, computed_weights)

        assert "UnknownType" in str(exc_info.value)
        assert "not found in calibration investor types" in str(exc_info.value)


class TestBuildLMTParametersWithComputedWeights:
    """Integration tests for build_lmt_parameters with computed weights."""

    def test_build_lmt_parameters_computes_and_merges_weights(self):
        """build_lmt_parameters computes weights from registry and merges them."""
        # This is an integration test using actual fund data
        from fund_risk_workflow.data.reference_data import load_investor_and_calibration_data

        data = load_investor_and_calibration_data('UCITS_Balanced')

        lmt_params = build_lmt_parameters(
            'UCITS_Balanced',
            data['calibration_inputs'],
            data['calibration_config'],
        )

        # Verify enriched investors are included
        assert 'investors_enriched' in lmt_params
        enriched = lmt_params['investors_enriched']

        # Verify weights are present
        for inv in enriched:
            assert 'weight' in inv
            assert 'type' in inv
            assert 'base_redemption_rate' in inv
            assert 'stress_redemption_rate' in inv
            assert isinstance(inv['weight'], (int, float))
            assert 0 <= inv['weight'] <= 1.0

        # Verify weights sum to approximately 1.0
        total_weight = sum(inv['weight'] for inv in enriched)
        assert 0.95 <= total_weight <= 1.05

    def test_build_lmt_parameters_schedule_uses_enriched_investors(self):
        """Redemption schedule is built using enriched investors with weights."""
        from fund_risk_workflow.data.reference_data import load_investor_and_calibration_data

        data = load_investor_and_calibration_data('UCITS_Balanced')

        lmt_params = build_lmt_parameters(
            'UCITS_Balanced',
            data['calibration_inputs'],
            data['calibration_config'],
        )

        # Verify schedule was built (it will use the enriched investors internally)
        assert 'schedule' in lmt_params
        schedule = lmt_params['schedule']
        assert len(schedule) == 12  # 12-month schedule

        # All schedule values should be between 0 and 1
        for rate in schedule:
            assert 0 <= rate <= 1.0

    def test_build_redemption_schedule_with_weights(self):
        """build_redemption_schedule works when investors have weights."""
        from fund_risk_workflow.computation.liquidity_calibration import build_redemption_schedule

        calibration_config = {
            'investors': [
                {'type': 'Retail', 'weight': 0.60, 'base_redemption_rate': 0.03, 'stress_redemption_rate': 0.12},
                {'type': 'Institutional', 'weight': 0.40, 'base_redemption_rate': 0.04, 'stress_redemption_rate': 0.18},
            ],
            'stress_months': [3, 4],
            'redemption_concentration': 6.0,
            'seed': 42,
        }

        schedule = build_redemption_schedule(calibration_config, n_months=12)

        assert len(schedule) == 12
        for rate in schedule:
            assert 0 <= rate <= 1.0
