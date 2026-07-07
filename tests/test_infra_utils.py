"""
tests/test_infra_utils.py
=========================
Unit tests for infra_utils.py

Run with: python3 -m pytest tests/test_infra_utils.py -v

Required coverage (MRS-76):
    - DSCR breach detection
    - Concentration flag trigger (sector > 40% NAV)
    - infra_irr returns a float
    - stress_nav returns lower value under positive discount rate shock
"""

import pytest
import pandas as pd
import numpy as np
from fund_risk_workflow.data.database import get_engine
from fund_risk_workflow.risk.infra_utils import (
    fund_nav_timeseries,
    asset_nav_breakdown,
    infra_multiples,
    infra_irr,
    dscr_profile,
    ltv_profile,
    concentration_by_sector,
    cashflow_coverage,
    inflation_sensitivity,
    duration_profile,
    stress_nav,
)

ENGINE  = get_engine()
FUND_ID = 'AIFM_Infra_Core'
QUARTER = '2026-03-31'


# ================================================================
# fund_nav_timeseries
# ================================================================

class TestFundNavTimeseries:

    def test_returns_dataframe(self):
        df = fund_nav_timeseries(ENGINE, FUND_ID)
        assert isinstance(df, pd.DataFrame)

    def test_has_required_columns(self):
        df = fund_nav_timeseries(ENGINE, FUND_ID)
        for col in ['date', 'nav_eur']:
            assert col in df.columns

    def test_sorted_ascending(self):
        df = fund_nav_timeseries(ENGINE, FUND_ID)
        assert df['date'].is_monotonic_increasing

    def test_nav_positive(self):
        df = fund_nav_timeseries(ENGINE, FUND_ID)
        assert (df['nav_eur'] > 0).all()

    def test_at_least_20_quarters(self):
        df = fund_nav_timeseries(ENGINE, FUND_ID)
        assert len(df) >= 20


# ================================================================
# asset_nav_breakdown
# ================================================================

class TestAssetNavBreakdown:

    def test_returns_dataframe(self):
        df = asset_nav_breakdown(ENGINE, FUND_ID, QUARTER)
        assert isinstance(df, pd.DataFrame)

    def test_eight_assets(self):
        df = asset_nav_breakdown(ENGINE, FUND_ID, QUARTER)
        assert len(df) == 8

    def test_nav_pct_sums_to_100(self):
        df = asset_nav_breakdown(ENGINE, FUND_ID, QUARTER)
        assert abs(df['nav_pct'].sum() - 100.0) < 0.1

    def test_has_sector_column(self):
        df = asset_nav_breakdown(ENGINE, FUND_ID, QUARTER)
        assert 'sector' in df.columns
        assert df['sector'].notna().all()

    def test_moic_above_zero(self):
        df = asset_nav_breakdown(ENGINE, FUND_ID, QUARTER)
        assert (df['moic'] > 0).all()


# ================================================================
# infra_multiples
# ================================================================

class TestInfraMultiples:

    def test_returns_dict(self):
        result = infra_multiples(ENGINE, FUND_ID)
        assert isinstance(result, dict)

    def test_required_keys(self):
        result = infra_multiples(ENGINE, FUND_ID)
        for key in ['moic', 'dpi', 'rvpi', 'drawn_capital', 'distributions', 'nav']:
            assert key in result

    def test_moic_equals_dpi_plus_rvpi(self):
        result = infra_multiples(ENGINE, FUND_ID)
        assert abs(result['moic'] - (result['dpi'] + result['rvpi'])) < 0.001

    def test_drawn_capital_positive(self):
        result = infra_multiples(ENGINE, FUND_ID)
        assert result['drawn_capital'] > 0

    def test_nav_positive(self):
        result = infra_multiples(ENGINE, FUND_ID)
        assert result['nav'] > 0


# ================================================================
# infra_irr — required: XIRR output is a float
# ================================================================

class TestInfraIrr:

    def test_returns_float(self):
        """MRS-76 required: XIRR output is a float."""
        result = infra_irr(ENGINE, FUND_ID)
        assert isinstance(result, float)

    def test_irr_positive(self):
        result = infra_irr(ENGINE, FUND_ID)
        assert result > 0

    def test_irr_reasonable_range(self):
        # infrastructure core/core-plus: expect 6–14% net IRR
        result = infra_irr(ENGINE, FUND_ID)
        assert 0.04 < result < 0.20


# ================================================================
# dscr_profile — required: DSCR breach detection
# ================================================================

class TestDscrProfile:

    def test_returns_dataframe(self):
        df = dscr_profile(ENGINE, 'INFRA_003')
        assert isinstance(df, pd.DataFrame)

    def test_has_required_columns(self):
        df = dscr_profile(ENGINE, 'INFRA_003')
        for col in ['date', 'dscr_actual', 'dscr_covenant',
                    'dscr_headroom', 'dscr_breach', 'trend']:
            assert col in df.columns

    def test_dscr_breach_detected(self):
        """MRS-76 required: DSCR breach detection."""
        df = dscr_profile(ENGINE, 'INFRA_003')
        # Toll road INFRA_003 has a COVID breach in Q2 2020
        assert df['dscr_breach'].any(), (
            'Expected at least one DSCR breach for INFRA_003 (COVID Q2 2020)'
        )

    def test_breach_quarter_is_covid(self):
        df = dscr_profile(ENGINE, 'INFRA_003')
        breach_dates = df.loc[df['dscr_breach'] == True, 'date']
        assert any(d.year == 2020 for d in breach_dates)

    def test_trend_column_valid_values(self):
        df = dscr_profile(ENGINE, 'INFRA_001')
        valid = {'improving', 'deteriorating', 'stable', 'insufficient history'}
        assert set(df['trend'].unique()).issubset(valid)

    def test_headroom_consistent_with_actual_and_covenant(self):
        df = dscr_profile(ENGINE, 'INFRA_001').dropna(
            subset=['dscr_actual', 'dscr_covenant', 'dscr_headroom'])
        computed = (df['dscr_actual'] - df['dscr_covenant']).round(3)
        assert (computed == df['dscr_headroom']).all()

    def test_no_breach_for_stable_regulated_asset(self):
        # Regulated water utility (INFRA_001) should have no DSCR breaches
        df = dscr_profile(ENGINE, 'INFRA_001')
        assert not df['dscr_breach'].any()


# ================================================================
# ltv_profile
# ================================================================

class TestLtvProfile:

    def test_returns_dataframe(self):
        df = ltv_profile(ENGINE, 'INFRA_007')
        assert isinstance(df, pd.DataFrame)

    def test_ltv_breach_detected_for_port(self):
        df = ltv_profile(ENGINE, 'INFRA_007')
        # Port INFRA_007 has construction overrun breach in Q3 2023
        assert df['ltv_breach'].any(), (
            'Expected at least one LTV breach for INFRA_007 (construction overrun 2023)'
        )

    def test_breach_quarter_is_2023(self):
        df = ltv_profile(ENGINE, 'INFRA_007')
        breach_dates = df.loc[df['ltv_breach'] == True, 'date']
        assert any(d.year == 2023 for d in breach_dates)

    def test_no_ltv_breach_for_regulated(self):
        # Regulated assets with stable revenues should not breach LTV
        df = ltv_profile(ENGINE, 'INFRA_001')
        assert not df['ltv_breach'].any()


# ================================================================
# concentration_by_sector — required: concentration flag trigger
# ================================================================

class TestConcentrationBySector:

    def test_returns_dataframe(self):
        df = concentration_by_sector(ENGINE, FUND_ID, QUARTER)
        assert isinstance(df, pd.DataFrame)

    def test_has_required_columns(self):
        df = concentration_by_sector(ENGINE, FUND_ID, QUARTER)
        for col in ['sector', 'nav_eur', 'nav_pct', 'concentrated']:
            assert col in df.columns

    def test_nav_pct_sums_to_100(self):
        df = concentration_by_sector(ENGINE, FUND_ID, QUARTER)
        assert abs(df['nav_pct'].sum() - 100.0) < 0.1

    def test_concentration_flag_triggers(self):
        """MRS-76 required: concentration flag trigger."""
        df = concentration_by_sector(ENGINE, FUND_ID, QUARTER)
        # Utilities sector (3 assets) should exceed 40% of total NAV
        assert df['concentrated'].any(), (
            'Expected at least one sector to exceed 40% NAV concentration. '
            'Utilities (3 assets) should trigger this flag.'
        )

    def test_concentrated_sector_over_40pct(self):
        df = concentration_by_sector(ENGINE, FUND_ID, QUARTER)
        concentrated = df[df['concentrated']]
        assert (concentrated['nav_pct'] > 40.0).all()


# ================================================================
# cashflow_coverage
# ================================================================

class TestCashflowCoverage:

    def test_returns_dataframe(self):
        df = cashflow_coverage(ENGINE, FUND_ID)
        assert isinstance(df, pd.DataFrame)

    def test_has_required_columns(self):
        df = cashflow_coverage(ENGINE, FUND_ID)
        for col in ['date', 'distributions', 'management_fees', 'coverage_ratio']:
            assert col in df.columns

    def test_management_fees_non_negative(self):
        df = cashflow_coverage(ENGINE, FUND_ID)
        assert (df['management_fees'] >= 0).all()

    def test_coverage_ratio_non_negative(self):
        df = cashflow_coverage(ENGINE, FUND_ID)
        assert (df['coverage_ratio'] >= 0).all()


# ================================================================
# inflation_sensitivity
# ================================================================

class TestInflationSensitivity:

    def test_returns_dict(self):
        result = inflation_sensitivity(ENGINE, FUND_ID)
        assert isinstance(result, dict)

    def test_required_keys(self):
        result = inflation_sensitivity(ENGINE, FUND_ID)
        for key in ['weighted_avg_linkage', 'pct_fully_linked',
                    'pct_partially_linked', 'pct_unlinked', 'asset_detail']:
            assert key in result

    def test_pct_sums_to_100(self):
        result = inflation_sensitivity(ENGINE, FUND_ID)
        total = (result['pct_fully_linked']
                 + result['pct_partially_linked']
                 + result['pct_unlinked'])
        assert abs(total - 100.0) < 0.5

    def test_weighted_avg_linkage_in_range(self):
        result = inflation_sensitivity(ENGINE, FUND_ID)
        assert 0.0 <= result['weighted_avg_linkage'] <= 1.0

    def test_fund_is_mostly_inflation_linked(self):
        # 6 of 8 assets are regulated or contracted → high linkage expected
        result = inflation_sensitivity(ENGINE, FUND_ID)
        assert result['weighted_avg_linkage'] > 0.55


# ================================================================
# duration_profile
# ================================================================

class TestDurationProfile:

    def test_returns_dataframe(self):
        df = duration_profile(ENGINE, FUND_ID)
        assert isinstance(df, pd.DataFrame)

    def test_has_required_columns(self):
        df = duration_profile(ENGINE, FUND_ID)
        for col in ['asset_id', 'asset_name', 'concession_end',
                    'remaining_years', 'nav_weight', 'near_expiry']:
            assert col in df.columns

    def test_remaining_years_positive(self):
        df = duration_profile(ENGINE, FUND_ID).dropna(subset=['remaining_years'])
        assert (df['remaining_years'] > 0).all()

    def test_weighted_avg_duration_stored(self):
        df = duration_profile(ENGINE, FUND_ID)
        assert 'weighted_avg_remaining_years' in df.attrs

    def test_long_duration_assets(self):
        # All concessions have 12+ years remaining from 2026
        df = duration_profile(ENGINE, FUND_ID).dropna(subset=['remaining_years'])
        assert df['remaining_years'].min() > 12.0


# ================================================================
# stress_nav — required: stress NAV lower under positive dr shock
# ================================================================

class TestStressNav:

    def test_returns_dict(self):
        result = stress_nav(ENGINE, FUND_ID, 100, 0.0)
        assert isinstance(result, dict)

    def test_required_keys(self):
        result = stress_nav(ENGINE, FUND_ID, 100, 0.0)
        for key in ['base_nav', 'stressed_nav', 'nav_change',
                    'nav_change_pct', 'asset_detail']:
            assert key in result

    def test_positive_dr_shock_reduces_nav(self):
        """MRS-76 required: stress NAV returns lower value under positive discount rate shock."""
        result = stress_nav(ENGINE, FUND_ID, discount_rate_shock_bps=100,
                            inflation_shock_pct=0.0)
        assert result['stressed_nav'] < result['base_nav'], (
            'A +100bps discount rate shock should reduce NAV '
            '(yield cap: higher dr → lower EV).'
        )

    def test_nav_change_negative_under_positive_shock(self):
        result = stress_nav(ENGINE, FUND_ID, 100, 0.0)
        assert result['nav_change'] < 0

    def test_larger_shock_larger_impact(self):
        r100 = stress_nav(ENGINE, FUND_ID, 100, 0.0)
        r200 = stress_nav(ENGINE, FUND_ID, 200, 0.0)
        assert r200['stressed_nav'] < r100['stressed_nav']

    def test_negative_dr_shock_increases_nav(self):
        result = stress_nav(ENGINE, FUND_ID, discount_rate_shock_bps=-50,
                            inflation_shock_pct=0.0)
        assert result['stressed_nav'] > result['base_nav']

    def test_inflation_uplift_partially_offsets_dr_shock(self):
        # +100bps dr alone vs +100bps dr with +1% inflation uplift
        r_no_inf = stress_nav(ENGINE, FUND_ID, 100, 0.0)
        r_inf    = stress_nav(ENGINE, FUND_ID, 100, 0.01)
        # inflation linkage should partially offset the dr shock
        assert r_inf['stressed_nav'] > r_no_inf['stressed_nav']

    def test_zero_shock_nav_close_to_base(self):
        result = stress_nav(ENGINE, FUND_ID, 0, 0.0)
        assert abs(result['nav_change_pct']) < 0.01

    def test_asset_detail_has_eight_rows(self):
        result = stress_nav(ENGINE, FUND_ID, 100, 0.0)
        assert len(result['asset_detail']) == 8
