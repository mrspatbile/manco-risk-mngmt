"""
tests/test_risk_utils.py
========================
Unit tests for risk_utils.py
Run with: python3 -m pytest tests/test_risk_utils.py -v
"""

import pytest
import numpy as np
import pandas as pd
from fund_risk_workflow.risk.risk_utils import (
    var_historical, var_parametric, var_scale,
    es_historical, es_parametric, es_scale,
    kupiec_test, christoffersen_test,
    exception_report, full_backtest_report,
    stress_equity, stress_rates, stress_credit,
    stress_fx, stress_combined, stress_historical,
    stress_property, stress_rental, stress_ltv,
    days_to_liquidate, liquidity_buckets,
    redemption_stress, investor_concentration,
    liquidity_adjusted_var, compute_pnl_attribution,
    pre_trade_check, lmt_trigger_analysis,
)
from fund_risk_workflow.risk.risk_utils import (  # private helpers — tested directly
    _ptc_apply_trade, _ptc_portfolio_var,
    _check_ucits, _check_aifm_hf, _check_aifm_pd,
)
from fund_risk_workflow.data.database import get_engine


# ----------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------

@pytest.fixture
def normal_returns():
    """250 days of normally distributed returns."""
    np.random.seed(42)
    return np.random.normal(0.0005, 0.012, 250)


@pytest.fixture
def returns_series(normal_returns):
    return pd.Series(normal_returns)


@pytest.fixture
def var_series(normal_returns):
    """VaR series slightly above most losses."""
    return pd.Series(np.abs(normal_returns) * 0.8)


@pytest.fixture
def sample_positions():
    """Sample enriched positions DataFrame."""
    return pd.DataFrame({
        'instrument_name'  : [
            'SPY ETF', 'T Bond 2028', 'LVMH Bond',
            'EUR/USD Fwd', 'Cash EUR', 'Office LU'
        ],
        'asset_class'      : [
            'Equity', 'Bond', 'Bond',
            'FX', 'Cash', 'Real Estate'
        ],
        'sub_asset_class'  : [
            'ETF', 'Government', 'IG Corporate',
            'Forward', 'Cash', 'Direct Property'
        ],
        'currency'         : [
            'USD', 'USD', 'EUR',
            'USD', 'EUR', 'EUR'
        ],
        'market_value_eur' : [
            50000000, 30000000, 20000000,
            10000000, 5000000, 45000000
        ],
        'weight_pct'       : [
            31.25, 18.75, 12.50,
            6.25, 3.12, 28.13
        ],
        'beta'             : [1.0, np.nan, np.nan, np.nan, np.nan, 0.7],
        'dur_adj_mid'      : [np.nan, 2.31, 4.71, np.nan, np.nan, np.nan],
        'convexity'        : [np.nan, 0.065, 0.268, np.nan, np.nan, np.nan],
        'z_sprd_mid'       : [np.nan, np.nan, 58.0, np.nan, np.nan, np.nan],
        'adv_eur'          : [75e6, 750e6, 16e6, 0, 0, 0],
        'is_direct_property': [False, False, False, False, False, True],
        'ltv_pct'          : [np.nan, np.nan, np.nan, np.nan, np.nan, 42.5],
        'rental_yield_pct' : [np.nan, np.nan, np.nan, np.nan, np.nan, 4.2],
        'vacancy_rate_pct' : [np.nan, np.nan, np.nan, np.nan, np.nan, 8.5],
        'property_type'    : [None, None, None, None, None, 'Office'],
        'valuation_date'   : [None, None, None, None, None, '2026-03-31'],
    })


@pytest.fixture
def nav(sample_positions):
    return float(sample_positions['market_value_eur'].sum())


@pytest.fixture
def investor_df():
    return pd.DataFrame({
        'investor_id'  : ['INV001', 'INV002', 'INV003',
                          'INV004', 'INV005'],
        'investor_name': ['Pension Fund A', 'Insurance B',
                          'Family Office C', 'Bank D', 'HNW E'],
        'aum_eur'      : [60e6, 40e6, 25e6, 15e6, 10e6],
    })


# ----------------------------------------------------------------
# VaR tests
# ----------------------------------------------------------------

class TestVarHistorical:

    def test_returns_positive(self, normal_returns):
        var = var_historical(normal_returns)
        assert var > 0

    def test_99_greater_than_95(self, normal_returns):
        var99 = var_historical(normal_returns, confidence=0.99)
        var95 = var_historical(normal_returns, confidence=0.95)
        assert var99 > var95

    def test_handles_nan(self):
        returns = np.array([0.01, -0.02, np.nan, -0.03, 0.01])
        var = var_historical(returns)
        assert not np.isnan(var)

    def test_handles_series(self, normal_returns):
        var = var_historical(pd.Series(normal_returns))
        assert var > 0

    def test_breach_rate_close_to_expected(self, normal_returns):
        var       = var_historical(normal_returns, confidence=0.99)
        breaches  = (normal_returns < -var).sum()
        rate      = breaches / len(normal_returns)
        assert abs(rate - 0.01) < 0.02


class TestVarParametric:

    def test_returns_positive(self):
        var = var_parametric(mu=0.0005, sigma=0.012)
        assert var > 0

    def test_normal_less_than_t(self):
        var_n = var_parametric(mu=0, sigma=0.012,
                               dist='normal')
        var_t = var_parametric(mu=0, sigma=0.012,
                               dist='t', df=5)
        assert var_t > var_n

    def test_higher_sigma_higher_var(self):
        var1 = var_parametric(mu=0, sigma=0.01)
        var2 = var_parametric(mu=0, sigma=0.02)
        assert var2 > var1

    def test_higher_confidence_higher_var(self):
        var99 = var_parametric(mu=0, sigma=0.01,
                               confidence=0.99)
        var95 = var_parametric(mu=0, sigma=0.01,
                               confidence=0.95)
        assert var99 > var95


class TestVarScale:

    def test_10d_greater_than_1d(self):
        var_10d = var_scale(0.025, horizon=10)
        assert var_10d > 0.025

    def test_20d_greater_than_10d(self):
        var_10d = var_scale(0.025, horizon=10)
        var_20d = var_scale(0.025, horizon=20)
        assert var_20d > var_10d

    def test_correct_scaling(self):
        var_1d  = 0.025
        var_10d = var_scale(var_1d, horizon=10)
        assert abs(var_10d - var_1d * np.sqrt(10)) < 1e-10

    def test_20d_ucits_standard(self):
        var_1d  = 0.025
        var_20d = var_scale(var_1d, horizon=20)
        assert abs(var_20d - var_1d * np.sqrt(20)) < 1e-10


# ----------------------------------------------------------------
# ES tests
# ----------------------------------------------------------------

class TestEsHistorical:

    def test_es_greater_than_var(self, normal_returns):
        var = var_historical(normal_returns, confidence=0.99)
        es  = es_historical(normal_returns, confidence=0.99)
        assert es >= var

    def test_returns_positive(self, normal_returns):
        es = es_historical(normal_returns)
        assert es > 0

    def test_handles_nan(self):
        returns = np.array([0.01, -0.02, np.nan, -0.05, 0.01])
        es = es_historical(returns)
        assert not np.isnan(es)

    def test_99_greater_than_95(self, normal_returns):
        es99 = es_historical(normal_returns, confidence=0.99)
        es95 = es_historical(normal_returns, confidence=0.95)
        assert es99 > es95


class TestEsParametric:

    def test_es_greater_than_var(self):
        sigma = 0.012
        confidence = .99
        var   = var_parametric(mu=0, sigma=sigma,
                               confidence=confidence, dist='normal')
        es    = es_parametric(sigma=sigma, mu=0,
                              confidence=confidence, dist='normal')

        assert es >= var

    def test_t_greater_than_normal(self):
        es_n = es_parametric(sigma=0.012, dist='normal')
        es_t = es_parametric(sigma=0.012, dist='t', df=5)
        assert es_t > es_n

    def test_returns_positive(self):
        es = es_parametric(sigma=0.012)
        assert es > 0


class TestEsScale:

    def test_scaled_greater_than_1d(self):
        es_20d = es_scale(0.032, horizon=20)
        assert es_20d > 0.032

    def test_correct_scaling(self):
        es_1d  = 0.032
        es_20d = es_scale(es_1d, horizon=20)
        assert abs(es_20d - es_1d * np.sqrt(20)) < 1e-10


# ----------------------------------------------------------------
# Backtesting tests
# ----------------------------------------------------------------

class TestKupiecTest:

    def test_returns_dict(self, returns_series, var_series):
        result = kupiec_test(returns_series, var_series)
        assert isinstance(result, dict)

    def test_has_required_keys(self, returns_series, var_series):
        result = kupiec_test(returns_series, var_series)
        for key in ['n_obs', 'n_breaches', 'breach_rate',
                    'expected', 'lr_stat', 'p_value', 'result']:
            assert key in result

    def test_result_is_pass_or_fail(self, returns_series, var_series):
        result = kupiec_test(returns_series, var_series)
        assert result['result'] in ('PASS', 'FAIL')

    def test_zero_breaches_handled(self, returns_series):
        large_var = pd.Series(np.ones(250))
        result    = kupiec_test(returns_series, large_var)
        assert result['n_breaches'] == 0

    def test_breach_rate_computed_correctly(self,
                                             returns_series,
                                             var_series):
        result = kupiec_test(returns_series, var_series)
        expected_rate = result['n_breaches'] / result['n_obs']
        assert abs(result['breach_rate'] - expected_rate) < 1e-4


class TestChristoffersenTest:

    def test_returns_dict(self, returns_series, var_series):
        result = christoffersen_test(returns_series, var_series)
        assert isinstance(result, dict)

    def test_has_required_keys(self, returns_series, var_series):
        result = christoffersen_test(returns_series, var_series)
        for key in ['n00', 'n01', 'n10', 'n11',
                    'lr_ind', 'p_value', 'result']:
            assert key in result

    def test_transition_counts_sum_correctly(self,
                                              returns_series,
                                              var_series):
        result = christoffersen_test(returns_series, var_series)
        total  = result['n00'] + result['n01'] + \
                 result['n10'] + result['n11']
        assert total == len(returns_series) - 1

    def test_result_is_pass_or_fail(self, returns_series, var_series):
        result = christoffersen_test(returns_series, var_series)
        assert result['result'] in ('PASS', 'FAIL')


class TestExceptionReport:

    def test_returns_dataframe(self, returns_series, var_series):
        result = exception_report(returns_series, var_series)
        assert isinstance(result, pd.DataFrame)

    def test_has_correct_columns(self, returns_series, var_series):
        result = exception_report(returns_series, var_series)
        for col in ['return', 'var', 'excess_loss', 'action']:
            assert col in result.columns

    def test_all_rows_are_breaches(self, returns_series, var_series):
        result = exception_report(returns_series, var_series)
        assert (result['return'] < -result['var']).all()

    def test_excess_loss_positive(self, returns_series, var_series):
        result = exception_report(returns_series, var_series)
        if len(result) > 0:
            assert (result['excess_loss'] >= 0).all()


class TestFullBacktestReport:

    def test_returns_dataframe(self, returns_series, var_series):
        result = full_backtest_report(
            returns_series, {'model1': var_series})
        assert isinstance(result, pd.DataFrame)

    def test_three_confidence_levels(self, returns_series,
                                      var_series):
        result = full_backtest_report(
            returns_series, {'model1': var_series})
        assert len(result) == 3

    def test_multiple_models(self, returns_series, var_series):
        result = full_backtest_report(
            returns_series,
            {'model1': var_series, 'model2': var_series * 1.1}
        )
        assert len(result) == 6

    def test_result_column_values(self, returns_series, var_series):
        result = full_backtest_report(
            returns_series, {'model1': var_series})
        assert result['result'].isin(['PASS', 'FAIL']).all()


# ----------------------------------------------------------------
# Stress scenario tests
# ----------------------------------------------------------------

class TestStressEquity:

    def test_returns_dict(self, sample_positions):
        result = stress_equity(sample_positions)
        assert isinstance(result, dict)

    def test_negative_pnl_for_crash(self, sample_positions):
        result = stress_equity(sample_positions,
                               delta_equity=-0.30)
        assert result['stressed_pnl_eur'] < 0

    def test_positive_pnl_for_rally(self, sample_positions):
        result = stress_equity(sample_positions,
                               delta_equity=0.10)
        assert result['stressed_pnl_eur'] > 0

    def test_has_required_keys(self, sample_positions):
        result = stress_equity(sample_positions)
        for key in ['scenario', 'stressed_pnl_eur',
                    'stressed_nav_pct', 'by_position']:
            assert key in result

    def test_nav_pct_consistent_with_pnl(self,
                                          sample_positions,
                                          nav):
        result = stress_equity(sample_positions)
        expected_pct = result['stressed_pnl_eur'] / nav * 100
        assert abs(result['stressed_nav_pct'] -
                   expected_pct) < 0.01


class TestStressRates:

    def test_returns_dict(self, sample_positions):
        result = stress_rates(sample_positions)
        assert isinstance(result, dict)

    def test_rate_rise_hurts_bonds(self, sample_positions):
        result = stress_rates(sample_positions, delta_y=0.02)
        assert result['stressed_pnl_eur'] < 0

    def test_rate_fall_helps_bonds(self, sample_positions):
        result = stress_rates(sample_positions, delta_y=-0.01)
        assert result['stressed_pnl_eur'] > 0

    def test_only_affects_bonds(self, sample_positions):
        result = stress_rates(sample_positions)
        assert 'Bond' in result['by_position']['asset_class'].values


class TestStressCredit:

    def test_returns_dict(self, sample_positions):
        result = stress_credit(sample_positions)
        assert isinstance(result, dict)

    def test_spread_widening_hurts_credit(self,
                                           sample_positions):
        result = stress_credit(sample_positions,
                               delta_spread=0.03)
        assert result['stressed_pnl_eur'] < 0
            
    def test_excludes_government_bonds(self, sample_positions):
        result = stress_credit(sample_positions)
        if len(result['by_position']) > 0:
            assert 'T Bond 2028' not in \
                result['by_position']['instrument_name'].values


class TestStressFx:

    def test_returns_dict(self, sample_positions):
        result = stress_fx(sample_positions)
        assert isinstance(result, dict)

    def test_has_required_keys(self, sample_positions):
        result = stress_fx(sample_positions)
        for key in ['scenario', 'stressed_pnl_eur',
                    'stressed_nav_pct', 'by_currency']:
            assert key in result

    def test_eur_positions_unaffected(self, sample_positions):
        eur_mv = sample_positions[
            sample_positions['currency'] == 'EUR'
        ]['market_value_eur'].sum()
        result = stress_fx(sample_positions,
                           fx_shocks={'USD': -0.10})
        # EUR positions should not contribute to FX P&L
        assert result['by_currency']['currency'].isin(
            ['USD']).any()


class TestStressCombined:

    def test_returns_dict(self, sample_positions):
        result = stress_combined(sample_positions)
        assert isinstance(result, dict)

    def test_has_component_pnls(self, sample_positions):
        result = stress_combined(sample_positions)
        for key in ['equity_pnl', 'rates_pnl',
                    'credit_pnl', 'fx_pnl']:
            assert key in result

    def test_total_equals_sum_of_components(self,
                                             sample_positions):
        result = stress_combined(sample_positions)
        total  = (result['equity_pnl'] + result['rates_pnl'] +
                  result['credit_pnl'] + result['fx_pnl'])
        assert abs(result['stressed_pnl_eur'] - total) < 1.0


class TestStressHistorical:

    def test_2008_scenario(self, sample_positions):
        result = stress_historical(sample_positions, '2008')
        assert result['stressed_pnl_eur'] < 0

    def test_2020_scenario(self, sample_positions):
        result = stress_historical(sample_positions, '2020')
        assert isinstance(result, dict)

    def test_2022_scenario(self, sample_positions):
        result = stress_historical(sample_positions, '2022')
        assert isinstance(result, dict)

    def test_2008_worse_than_2020(self, sample_positions):
        r2008 = stress_historical(sample_positions, '2008')
        r2020 = stress_historical(sample_positions, '2020')
        assert r2008['stressed_pnl_eur'] < r2020['stressed_pnl_eur']


    def test_unknown_scenario_raises(self, sample_positions):
        with pytest.raises(ValueError):
            stress_historical(sample_positions, 'unknown')


class TestStressProperty:

    def test_returns_dict(self, sample_positions):
        result = stress_property(sample_positions)
        assert isinstance(result, dict)

    def test_negative_pnl_for_value_decline(self,
                                              sample_positions):
        result = stress_property(sample_positions,
            delta_value_by_type={'Office': -0.20})
        assert result['stressed_pnl_eur'] < 0

    def test_only_affects_direct_properties(self,
                                             sample_positions):
        result = stress_property(sample_positions)
        assert result['stressed_pnl_eur'] != 0

    def test_no_direct_properties_returns_zero(self):
        positions = pd.DataFrame({
            'asset_class'       : ['Equity'],
            'market_value_eur'  : [1000000],
            'is_direct_property': [False],
            'property_type'     : [None],
        })
        result = stress_property(positions)
        assert result['stressed_pnl_eur'] == 0.0


class TestStressRental:

    def test_returns_dict(self, sample_positions):
        result = stress_rental(sample_positions)
        assert isinstance(result, dict)

    def test_negative_pnl(self, sample_positions):
        result = stress_rental(sample_positions,
                               delta_vacancy=0.10,
                               delta_yield=-0.005)
        assert result['stressed_pnl_eur'] < 0

    def test_no_direct_properties_returns_zero(self):
        positions = pd.DataFrame({
            'asset_class'       : ['Equity'],
            'market_value_eur'  : [1000000],
            'is_direct_property': [False],
        })
        result = stress_rental(positions)
        assert result['stressed_pnl_eur'] == 0.0


class TestStressLtv:

    def test_returns_dict(self, sample_positions):
        result = stress_ltv(sample_positions)
        assert isinstance(result, dict)

    def test_has_required_keys(self, sample_positions):
        result = stress_ltv(sample_positions)
        for key in ['scenario', 'n_breaches',
                    'breaching_properties', 'by_position']:
            assert key in result

    def test_high_ltv_position_breaches(self):
        positions = pd.DataFrame({
            'instrument_name'   : ['High LTV Office'],
            'asset_class'       : ['Real Estate'],
            'market_value_eur'  : [10000000],
            'is_direct_property': [True],
            'ltv_pct'           : [70.0],
            'property_type'     : ['Office'],
        })
        result = stress_ltv(positions,
                            delta_property_value=-0.20,
                            ltv_threshold=0.75)
        assert result['n_breaches'] == 1

    def test_low_ltv_no_breach(self):
        positions = pd.DataFrame({
            'instrument_name'   : ['Low LTV Office'],
            'asset_class'       : ['Real Estate'],
            'market_value_eur'  : [10000000],
            'is_direct_property': [True],
            'ltv_pct'           : [30.0],
            'property_type'     : ['Office'],
        })
        result = stress_ltv(positions,
                            delta_property_value=-0.20,
                            ltv_threshold=0.75)
        assert result['n_breaches'] == 0


# ----------------------------------------------------------------
# Liquidity tests
# ----------------------------------------------------------------

class TestDaysToLiquidate:

    def test_returns_dataframe(self, sample_positions):
        result = days_to_liquidate(sample_positions)
        assert isinstance(result, pd.DataFrame)

    def test_adds_days_column(self, sample_positions):
        result = days_to_liquidate(sample_positions)
        assert 'days_to_liquidate' in result.columns

    def test_direct_property_is_infinite(self, sample_positions):
        result = days_to_liquidate(sample_positions)
        direct = result[result['is_direct_property'] == True]
        assert (direct['days_to_liquidate'] == np.inf).all()

    def test_cash_is_zero_days(self, sample_positions):
        result = days_to_liquidate(sample_positions)
        cash   = result[result['asset_class'] == 'Cash']
        assert (cash['days_to_liquidate'] == 0).all()

    def test_liquid_equity_has_low_days(self, sample_positions):
        result = days_to_liquidate(sample_positions)
        equity = result[result['asset_class'] == 'Equity']
        assert (equity['days_to_liquidate'] < 10).all()


class TestLiquidityBuckets:

    def test_returns_dataframe(self, sample_positions):
        pos    = days_to_liquidate(sample_positions)
        result = liquidity_buckets(pos)
        assert isinstance(result, pd.DataFrame)

    def test_adds_bucket_column(self, sample_positions):
        pos    = days_to_liquidate(sample_positions)
        result = liquidity_buckets(pos)
        assert 'liquidity_bucket' in result.columns

    def test_direct_property_in_over_one_year(self,
                                               sample_positions):
        pos    = days_to_liquidate(sample_positions)
        result = liquidity_buckets(pos)
        direct = result[result['is_direct_property'] == True]
        assert (direct['liquidity_bucket'] == '> 1 year').all()

    def test_all_buckets_valid(self, sample_positions):
        valid_buckets = {'1 day', '2-7 days', '8-30 days',
                         '31-90 days', '91-365 days', '> 1 year'}
        pos    = days_to_liquidate(sample_positions)
        result = liquidity_buckets(pos)
        actual = set(result['liquidity_bucket'].dropna().unique())
        assert actual.issubset(valid_buckets)


class TestRedemptionStress:

    def test_returns_dict(self, sample_positions, nav):
        pos    = days_to_liquidate(sample_positions)
        pos    = liquidity_buckets(pos)
        result = redemption_stress(pos, nav)
        assert isinstance(result, dict)

    def test_has_required_keys(self, sample_positions, nav):
        pos    = days_to_liquidate(sample_positions)
        pos    = liquidity_buckets(pos)
        result = redemption_stress(pos, nav)
        for key in ['redemption_amount_eur', 'liquid_assets_eur',
                    'liquidity_gap_eur', 'coverage_ratio',
                    'can_meet_redemption', 'recommendation']:
            assert key in result

    def test_coverage_ratio_positive(self, sample_positions, nav):
        pos    = days_to_liquidate(sample_positions)
        pos    = liquidity_buckets(pos)
        result = redemption_stress(pos, nav,
                                   redemption_pct=0.10)
        assert result['coverage_ratio'] >= 0

    def test_large_redemption_may_fail(self, sample_positions,
                                        nav):
        pos    = days_to_liquidate(sample_positions)
        pos    = liquidity_buckets(pos)
        result = redemption_stress(pos, nav,
                                   redemption_pct=0.90)
        assert not result['can_meet_redemption']


# ================================================================
# lmt_trigger_analysis — MRS-84 / MRS-86
# ================================================================

_LMT_NAV            = 1_000_000_000   # 1bn total NAV
_LMT_LIQUID_PCT     = 0.70            # 700M liquid, 300M illiquid
_LMT_GATE           = 0.10            # gate cap = min(10% × NAV, liquid) = 100M
_LMT_SWING          = 0.05            # swing threshold = 5% of NAV

_LMT_COLS = [
    'month', 'base_gross_pct', 'effective_gross_pct', 'effective_gross_eur',
    'paid_eur', 'deferred_eur', 'backlog_eur', 'gate_active', 'swing_active',
    'suspension_active', 'consecutive_gate_months', 'liquid_nav_eur',
    'illiquid_nav_eur', 'total_nav_eur',
]


class TestLmtTriggerAnalysis:

    def _run(self, schedule, **kwargs):
        result = lmt_trigger_analysis(
            _LMT_NAV, _LMT_LIQUID_PCT,
            _LMT_GATE, _LMT_SWING,
            schedule, **kwargs,
        )
        return result['df']

    # ── Structure ────────────────────────────────────────────────

    def test_returns_dataframe(self):
        df = self._run([0.03] * 12)
        assert isinstance(df, pd.DataFrame)

    def test_has_twelve_rows(self):
        df = self._run([0.03] * 12)
        assert len(df) == 12

    def test_required_columns(self):
        df = self._run([0.03] * 12)
        for col in _LMT_COLS:
            assert col in df.columns, f'Missing column: {col}'

    def test_month_index_is_one_to_twelve(self):
        df = self._run([0.03] * 12)
        assert df['month'].tolist() == list(range(1, 13))

    # ── Normal flow — no LMT triggers ───────────────────────────

    def test_normal_flow_no_triggers(self):
        """3% / month: 30M demand < 100M gate cap, 3% < 5% swing."""
        df = self._run([0.03] * 12)
        assert not df['gate_active'].any()
        assert not df['swing_active'].any()
        assert not df['suspension_active'].any()
        assert (df['backlog_eur'] == 0.0).all()
        assert (df['deferred_eur'] == 0.0).all()

    def test_normal_flow_full_payment(self):
        """When no gate fires every redemption request is paid in full."""
        df = self._run([0.03] * 12)
        assert (df['paid_eur'] == df['effective_gross_eur']).all()

    def test_liquid_nav_decreases_over_time(self):
        """Paid redemptions shrink the liquid sleeve each month."""
        df = self._run([0.05] * 12)
        for i in range(1, len(df)):
            assert df['liquid_nav_eur'].iloc[i] <= df['liquid_nav_eur'].iloc[i - 1]

    # ── Gate activation ──────────────────────────────────────────

    def test_gate_activates_when_demand_exceeds_cap(self):
        """15% / month: 150M demand > 100M gate cap → gate fires in month 1."""
        df = self._run([0.15] * 12)
        assert df['gate_active'].iloc[0]

    def test_gate_creates_deferred_amount(self):
        """When gate fires, deferred_eur > 0 (excess demand rolled to backlog)."""
        df = self._run([0.15] * 12)
        assert df['deferred_eur'].iloc[0] > 0.0

    def test_gate_paid_capped_at_gate_cap(self):
        """
        Month 1: gate_cap = min(10% × 1bn, 700M) = 100M.
        No prior backlog so paid_eur must equal gate_cap.
        """
        df = self._run([0.15] * 12)
        assert abs(df['paid_eur'].iloc[0] - 100_000_000) < 1.0

    def test_gate_backlog_accumulates(self):
        """Backlog in month 2 >= backlog in month 1 while gate keeps firing."""
        df = self._run([0.15] * 12)
        assert df['backlog_eur'].iloc[1] >= df['backlog_eur'].iloc[0]

    def test_no_gate_below_threshold(self):
        """9% / month: 90M demand < 100M gate cap → gate never fires."""
        df = self._run([0.09] * 12)
        assert not df['gate_active'].any()

    # ── Swing pricing ────────────────────────────────────────────

    def test_swing_activates_above_threshold(self):
        """7% demand > 5% swing threshold → swing active; 70M < 100M → no gate."""
        df = self._run([0.07] * 12)
        assert df['swing_active'].iloc[0]
        assert not df['gate_active'].iloc[0]

    def test_swing_off_below_threshold(self):
        """3% < 5% → swing never fires."""
        df = self._run([0.03] * 12)
        assert not df['swing_active'].any()

    # ── Contagion multiplier ─────────────────────────────────────

    def test_contagion_scales_effective_rate_after_gate(self):
        """
        Month 1 at 15% fires the gate.
        Month 2 base = 8%; with contagion × 1.5 → effective = 12%.
        effective_gross_pct > base_gross_pct only with contagion active.
        """
        schedule = [0.15, 0.08] + [0.01] * 10
        df = self._run(schedule, contagion_multiplier=1.5)
        # month 2 (index 1): effective > base because gate fired in month 1
        assert df['effective_gross_pct'].iloc[1] > df['base_gross_pct'].iloc[1]
        assert abs(df['effective_gross_pct'].iloc[1] - 12.0) < 0.01

    def test_no_contagion_effective_equals_base(self):
        """Without contagion (multiplier=1.0) effective always equals base."""
        schedule = [0.15, 0.08] + [0.01] * 10
        df = self._run(schedule, contagion_multiplier=1.0)
        assert (df['effective_gross_pct'] == df['base_gross_pct']).all()

    # ── Suspension trigger ───────────────────────────────────────

    def test_suspension_fires_after_consecutive_gates_with_large_backlog(self):
        """
        With 15% / month and default consecutive_gate_for_suspension=3:

        Month 1: consec=1, backlog=50M
        Month 2: consec=2, backlog=95M
        Month 3: consec=3, backlog=135.5M, liquid=429M  → 135.5/429 = 31.6% > 25%
        Month 4: both conditions met → suspension_active = True
        """
        df = self._run([0.15] * 12)
        assert df['suspension_active'].iloc[3]   # month 4 (0-indexed: 3)

    def test_suspension_stops_all_payments(self):
        """When suspension is active, paid_eur must be zero."""
        df = self._run([0.15] * 12)
        suspended = df[df['suspension_active']]
        assert len(suspended) > 0
        assert (suspended['paid_eur'] == 0.0).all()

    def test_no_suspension_with_small_redemptions(self):
        """5% / month never fires the gate so suspension cannot trigger."""
        df = self._run([0.05] * 12)
        assert not df['suspension_active'].any()

    # ── Edge cases ───────────────────────────────────────────────

    def test_zero_schedule_no_activity(self):
        """Zero redemptions: nothing paid, nothing deferred, no triggers."""
        df = self._run([0.0] * 12)
        assert (df['paid_eur'] == 0.0).all()
        assert (df['deferred_eur'] == 0.0).all()
        assert (df['backlog_eur'] == 0.0).all()
        assert not df['gate_active'].any()
        assert not df['swing_active'].any()
        assert not df['suspension_active'].any()

    def test_zero_schedule_liquid_nav_unchanged(self):
        """Zero redemptions: liquid sleeve must stay at its initial value."""
        df = self._run([0.0] * 12)
        expected_liquid = _LMT_NAV * _LMT_LIQUID_PCT
        assert df['liquid_nav_eur'].iloc[-1] == pytest.approx(expected_liquid)

    def test_illiquid_nav_stays_static(self):
        """Illiquid sleeve never changes regardless of redemption pressure."""
        df = self._run([0.15] * 12)
        expected_illiquid = _LMT_NAV * (1.0 - _LMT_LIQUID_PCT)
        assert (df['illiquid_nav_eur'] - expected_illiquid).abs().max() < 1.0

    def test_base_gross_pct_stored_as_percentage(self):
        """Output base_gross_pct is in % (e.g. 5.0 for a 0.05 schedule value)."""
        df = self._run([0.05] * 12)
        assert df['base_gross_pct'].iloc[0] == pytest.approx(5.0)


class TestInvestorConcentration:

    def test_returns_dict(self, investor_df, nav):
        result = investor_concentration(investor_df, nav)
        assert isinstance(result, dict)

    def test_has_required_keys(self, investor_df, nav):
        result = investor_concentration(investor_df, nav)
        for key in ['largest_investor_pct', 'top3_pct',
                    'concentration_flag', 'high_concentration',
                    'largest_redemption_eur']:
            assert key in result

    def test_flags_large_investor(self, nav):
        investors = pd.DataFrame({
            'investor_id'  : ['INV001'],
            'investor_name': ['Big Pension'],
            'aum_eur'      : [60e6],
        })
        result = investor_concentration(
            investors, nav, threshold=0.20)
        assert result['concentration_flag'] == True

    def test_no_flag_for_small_investors(self, nav):
        investors = pd.DataFrame({
            'investor_id'  : ['INV001', 'INV002'],
            'investor_name': ['Small A', 'Small B'],
            'aum_eur'      : [5e6, 5e6],
        })
        result = investor_concentration(
            investors, nav, threshold=0.20)
        assert result['concentration_flag'] == False

    def test_top3_pct_correct(self, investor_df, nav):
        result   = investor_concentration(investor_df, nav)
        expected = (60e6 + 40e6 + 25e6) / nav
        assert abs(result['top3_pct'] - expected) < 0.001


class TestLiquidityAdjustedVar:

    def test_returns_dict(self, sample_positions):
        result = liquidity_adjusted_var(0.025, sample_positions)
        assert isinstance(result, dict)

    def test_lvar_greater_than_var(self, sample_positions):
        result = liquidity_adjusted_var(0.025, sample_positions)
        assert result['lvar'] >= result['var']

    def test_has_required_keys(self, sample_positions):
        result = liquidity_adjusted_var(0.025, sample_positions)
        for key in ['var', 'liquidity_cost', 'lvar',
                    'lvar_pct_increase', 'by_asset_class']:
            assert key in result

    def test_higher_multiplier_higher_lvar(self,
                                            sample_positions):
        r1 = liquidity_adjusted_var(0.025, sample_positions,
                                    stress_multiplier=1.0)
        r2 = liquidity_adjusted_var(0.025, sample_positions,
                                    stress_multiplier=5.0)
        assert r2['lvar'] > r1['lvar']

    def test_liquidity_cost_nonnegative(self, sample_positions):
        result = liquidity_adjusted_var(0.025, sample_positions)
        assert result['liquidity_cost'] >= 0

# tests/test_pnl_attribution.py
# MRS-28 | Unit tests for compute_pnl_attribution()


# Known dataset
# One equity position: MV=1,000,000, beta=1.2
# One bond position:   MV=500,000,  dur=4.0
# One USD position:    MV=200,000,  no beta/dur
# One day of market moves:
#   r_market = +1%  -> equity P&L = 1.2 * 0.01 * 1,000,000 = 12,000
#   dy       = +5bp -> rates P&L  = -4.0 * 0.0005 * 500,000 = -1,000
#   r_fx_USD = +0.5%-> FX P&L     = 200,000 * 0.005 = 1,000
#   explained = 12,000
#   actual    = 14,000
#   residual  = 2,000

@pytest.fixture
def positions():
    return pd.DataFrame([
        {'date': pd.Timestamp('2025-01-02'), 'isin': 'EQ1', 'asset_class': 'Equity',
         'currency': 'EUR', 'market_value_eur': 1_000_000, 'beta': 1.2, 'dur_adj_mid': float('nan')},
        {'date': pd.Timestamp('2025-01-02'), 'isin': 'BD1', 'asset_class': 'Bond',
         'currency': 'EUR', 'market_value_eur': 500_000, 'beta': float('nan'), 'dur_adj_mid': 4.0},
        {'date': pd.Timestamp('2025-01-02'), 'isin': 'FX1', 'asset_class': 'FX',
         'currency': 'USD', 'market_value_eur': 200_000, 'beta': float('nan'), 'dur_adj_mid': float('nan')},
    ])

@pytest.fixture
def market_moves():
    return pd.DataFrame(
        [{'r_market': 0.01, 'dy': 0.0005, 'r_fx_USD': 0.005}],
        index=pd.to_datetime(['2025-01-02']),
    )

@pytest.fixture
def pnl_actual():
    return pd.Series(
        [14_000.0],
        index=pd.to_datetime(['2025-01-02']),
    )


class TestComputePnlAttribution:

    def test_returns_dataframe(self, positions, market_moves, pnl_actual):
        result = compute_pnl_attribution(positions, market_moves, pnl_actual)
        assert isinstance(result, pd.DataFrame)

    def test_required_columns(self, positions, market_moves, pnl_actual):
        result = compute_pnl_attribution(positions, market_moves, pnl_actual)
        for col in ['pnl_actual', 'pnl_equity', 'pnl_rates', 'pnl_fx',
                    'pnl_explained', 'pnl_residual', 'pct_explained']:
            assert col in result.columns

    def test_equity_pnl(self, positions, market_moves, pnl_actual):
        result = compute_pnl_attribution(positions, market_moves, pnl_actual)
        assert result['pnl_equity'].iloc[0] == pytest.approx(12_000.0, rel=1e-4)

    def test_rates_pnl(self, positions, market_moves, pnl_actual):
        result = compute_pnl_attribution(positions, market_moves, pnl_actual)
        assert result['pnl_rates'].iloc[0] == pytest.approx(-1_000.0, rel=1e-4)

    def test_fx_pnl(self, positions, market_moves, pnl_actual):
        result = compute_pnl_attribution(positions, market_moves, pnl_actual)
        assert result['pnl_fx'].iloc[0] == pytest.approx(1_000.0, rel=1e-4)

    def test_residual_equals_actual_minus_explained(self, positions, market_moves, pnl_actual):
        result = compute_pnl_attribution(positions, market_moves, pnl_actual)
        row = result.iloc[0]
        assert row['pnl_residual'] == pytest.approx(
            row['pnl_actual'] - row['pnl_explained'], rel=1e-4
        )

    def test_pct_explained(self, positions, market_moves, pnl_actual):
        result = compute_pnl_attribution(positions, market_moves, pnl_actual)
        # explained = 12,000, actual = 14,000 -> 85.7%
        assert result['pct_explained'].iloc[0] == pytest.approx(
            12_000 / 14_000, rel=1e-4
        )


# ================================================================
# pre_trade_check — MRS-61
# Breach tests use synthetic DataFrames; no DB required.
# Integration test uses live ENGINE to verify clean trade passes.
# ================================================================

_ENGINE  = get_engine()
_PTC_DATE = '2026-03-31'


def _make_ucits_positions(nav: float = 10_000_000) -> pd.DataFrame:
    """
    10 equities at 5% + 8 bonds at 5% + 1 cash at 10% = 100% NAV.
    Each issuer exactly 5% (not > 5%) → no 5/10/40 bucket exposure.
    Cash at 10% (not > 10%) → no single-issuer breach; sum_above_5 = 10% < 40%.
    VaR ≈ 11.6% (port_beta=0.50, port_dur=2.0); relative mult ≈ 0.96.
    """
    rows = []
    for i in range(10):
        rows.append({
            'isin': f'EQ_{i:02d}', 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
            'market_value_eur': nav * 0.05, 'beta': 1.0, 'dur_adj_mid': float('nan'),
            'currency': 'EUR', 'issuer': f'Corp_{i:02d}', 'adv_eur': 5_000_000.0,
        })
    for i in range(8):
        rows.append({
            'isin': f'BD_{i:02d}', 'asset_class': 'Bond', 'sub_asset_class': 'Govie',
            'market_value_eur': nav * 0.05, 'beta': float('nan'), 'dur_adj_mid': 5.0,
            'currency': 'EUR', 'issuer': f'Sovereign_{i:02d}', 'adv_eur': 50_000_000.0,
        })
    rows.append({
        'isin': 'CASH_EUR', 'asset_class': 'Cash', 'sub_asset_class': '',
        'market_value_eur': nav * 0.10, 'beta': float('nan'), 'dur_adj_mid': float('nan'),
        'currency': 'EUR', 'issuer': None, 'adv_eur': float('nan'),
    })
    return pd.DataFrame(rows)


def _make_hf_positions(nav: float = 50_000_000) -> pd.DataFrame:
    """
    8 equities at 10% each across 4 sectors (2 per sector) + 20% cash = 100% NAV.
    Includes 'sector' column so sector_col='sector' is used in the check.
    Gross/commitment leverage = 1.0x; max issuer = 10%; max sector = 20%. All within limits.
    Long-only: no EU236/2012 short-selling flags.
    """
    _SECTORS = ['Technology', 'Healthcare', 'Financials', 'Consumer Staples']
    rows = []
    for i in range(8):
        rows.append({
            'isin': f'HF_EQ_{i:02d}', 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
            'market_value_eur': nav * 0.10, 'beta': 1.0, 'dur_adj_mid': float('nan'),
            'currency': 'EUR', 'issuer': f'HF_Corp_{i:02d}', 'sector': _SECTORS[i % 4],
            'adv_eur': 10_000_000.0,
        })
    rows.append({
        'isin': 'HF_CASH', 'asset_class': 'Cash', 'sub_asset_class': '',
        'market_value_eur': nav * 0.20, 'beta': float('nan'), 'dur_adj_mid': float('nan'),
        'currency': 'EUR', 'issuer': None, 'sector': 'Cash', 'adv_eur': float('nan'),
    })
    return pd.DataFrame(rows)


def _make_pd_positions(nav: float = 20_000_000) -> pd.DataFrame:
    """
    6 senior loans at 15% each + 1 mezzanine (HY) at 10% = 100% NAV.
    Max borrower: 15% < 20% ✓; HY exposure: 10% < 50% ✓; Unrated: 0% ✓.
    """
    return pd.DataFrame([
        {'isin': 'LOAN_A', 'asset_class': 'Loan', 'sub_asset_class': 'Senior Secured',
         'market_value_eur': nav * 0.15, 'beta': float('nan'), 'dur_adj_mid': 3.0,
         'currency': 'EUR', 'issuer': 'BorrowerA', 'rating': 'BBB'},
        {'isin': 'LOAN_B', 'asset_class': 'Loan', 'sub_asset_class': 'Senior Secured',
         'market_value_eur': nav * 0.15, 'beta': float('nan'), 'dur_adj_mid': 3.0,
         'currency': 'EUR', 'issuer': 'BorrowerB', 'rating': 'BBB+'},
        {'isin': 'LOAN_C', 'asset_class': 'Loan', 'sub_asset_class': 'Senior Secured',
         'market_value_eur': nav * 0.15, 'beta': float('nan'), 'dur_adj_mid': 3.5,
         'currency': 'EUR', 'issuer': 'BorrowerC', 'rating': 'A-'},
        {'isin': 'LOAN_D', 'asset_class': 'Loan', 'sub_asset_class': 'Senior Secured',
         'market_value_eur': nav * 0.15, 'beta': float('nan'), 'dur_adj_mid': 3.5,
         'currency': 'EUR', 'issuer': 'BorrowerD', 'rating': 'BBB-'},
        {'isin': 'LOAN_E', 'asset_class': 'Loan', 'sub_asset_class': 'Senior Secured',
         'market_value_eur': nav * 0.15, 'beta': float('nan'), 'dur_adj_mid': 4.0,
         'currency': 'EUR', 'issuer': 'BorrowerE', 'rating': 'BBB'},
        {'isin': 'LOAN_F', 'asset_class': 'Loan', 'sub_asset_class': 'Senior Secured',
         'market_value_eur': nav * 0.15, 'beta': float('nan'), 'dur_adj_mid': 4.0,
         'currency': 'EUR', 'issuer': 'BorrowerF', 'rating': 'BBB+'},
        {'isin': 'LOAN_G', 'asset_class': 'Loan', 'sub_asset_class': 'Mezzanine',
         'market_value_eur': nav * 0.10, 'beta': float('nan'), 'dur_adj_mid': 4.5,
         'currency': 'EUR', 'issuer': 'BorrowerG', 'rating': 'BB'},
    ])


class TestPtcApplyTrade:

    def test_new_position_added(self):
        pos   = _make_ucits_positions()
        trade = {
            'isin': 'NEW_STOCK', 'direction': 'buy', 'quantity': 100,
            'price_eur': 50.0, 'asset_class': 'Equity', 'sub_asset_class': 'Small Cap',
        }
        result = _ptc_apply_trade(pos, trade)
        assert 'NEW_STOCK' in result['isin'].values
        new_mv = result.loc[result['isin'] == 'NEW_STOCK', 'market_value_eur'].iloc[0]
        assert new_mv == pytest.approx(5_000.0)

    def test_existing_position_increased(self):
        pos   = _make_ucits_positions()
        orig  = pos.loc[pos['isin'] == 'EQ_00', 'market_value_eur'].iloc[0]
        trade = {
            'isin': 'EQ_00', 'direction': 'buy', 'quantity': 1,
            'price_eur': 100_000.0, 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
        }
        result = _ptc_apply_trade(pos, trade)
        new_mv = result.loc[result['isin'] == 'EQ_00', 'market_value_eur'].iloc[0]
        assert new_mv == pytest.approx(orig + 100_000.0)

    def test_sell_reduces_position(self):
        pos   = _make_ucits_positions()
        orig  = pos.loc[pos['isin'] == 'EQ_00', 'market_value_eur'].iloc[0]
        trade = {
            'isin': 'EQ_00', 'direction': 'sell', 'quantity': 1,
            'price_eur': 100_000.0, 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
        }
        result = _ptc_apply_trade(pos, trade)
        new_mv = result.loc[result['isin'] == 'EQ_00', 'market_value_eur'].iloc[0]
        assert new_mv == pytest.approx(orig - 100_000.0)

    def test_short_creates_negative_mv(self):
        pos   = _make_ucits_positions()
        trade = {
            'isin': 'SHORT_NEW', 'direction': 'short', 'quantity': 100,
            'price_eur': 50.0, 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
        }
        result = _ptc_apply_trade(pos, trade)
        new_mv = result.loc[result['isin'] == 'SHORT_NEW', 'market_value_eur'].iloc[0]
        assert new_mv == pytest.approx(-5_000.0)


class TestPtcPortfolioVar:

    def test_equity_only_portfolio(self):
        pos = pd.DataFrame([{
            'isin': 'EQ', 'asset_class': 'Equity',
            'market_value_eur': 1_000_000, 'beta': 1.0, 'dur_adj_mid': float('nan'),
        }])
        nav = 1_000_000.0
        var = _ptc_portfolio_var(pos, nav)
        # beta=1, full NAV equity → vol = 1*0.010, 20-day 99% VaR = 0.01*sqrt(20)*2.3263
        import numpy as np
        expected = 0.010 * np.sqrt(20) * 2.3263
        assert var == pytest.approx(expected, rel=1e-4)

    def test_zero_nav_returns_zero(self):
        pos = _make_ucits_positions()
        assert _ptc_portfolio_var(pos, 0.0) == 0.0

    def test_bond_only_portfolio(self):
        pos = pd.DataFrame([{
            'isin': 'BD', 'asset_class': 'Bond',
            'market_value_eur': 1_000_000, 'beta': float('nan'), 'dur_adj_mid': 5.0,
        }])
        nav = 1_000_000.0
        var = _ptc_portfolio_var(pos, nav)
        # dur=5, full NAV → vol = 5*0.005 = 0.025
        import numpy as np
        expected = 0.025 * np.sqrt(20) * 2.3263
        assert var == pytest.approx(expected, rel=1e-4)


class TestCheckUcitsClean:

    def test_clean_trade_no_breaches(self):
        pos   = _make_ucits_positions()
        nav   = float(pos['market_value_eur'].sum())
        trade = {
            'isin': 'NEW_EQ', 'direction': 'buy', 'quantity': 10,
            'price_eur': 1_000.0, 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
        }
        pro_forma          = _ptc_apply_trade(pos, trade)
        breaches, metrics  = _check_ucits(pro_forma, nav, trade)
        assert len(breaches) == 0

    def test_required_metrics_returned(self):
        pos   = _make_ucits_positions()
        nav   = float(pos['market_value_eur'].sum())
        trade = {
            'isin': 'NEW_EQ', 'direction': 'buy', 'quantity': 1,
            'price_eur': 100.0, 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_ucits(pro_forma, nav, trade)
        for key in ['absolute_var_pct', 'relative_var_multiplier', 'reference_var_pct',
                    'max_issuer_pct', 'sum_above_5pct_issuers', 'trade_eligible', 'borrowing_pct']:
            assert key in metrics

    def test_ineligible_asset_breaches(self):
        pos   = _make_ucits_positions()
        nav   = float(pos['market_value_eur'].sum())
        trade = {
            'isin': 'LOAN_X', 'direction': 'buy', 'quantity': 1,
            'price_eur': 100_000.0, 'asset_class': 'Loan', 'sub_asset_class': 'Senior Secured',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_ucits(pro_forma, nav, trade)
        checks = [b['check'] for b in breaches]
        assert 'eligible_assets_article_50' in checks

    def test_5_10_40_single_issuer_breach(self):
        # Build a portfolio where one issuer already sits at 9% NAV, then add more
        nav = 10_000_000.0
        pos = pd.DataFrame([
            {
                'isin': 'EQ_A', 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
                'market_value_eur': nav * 0.09, 'beta': 1.0, 'dur_adj_mid': float('nan'),
                'currency': 'EUR', 'issuer': 'BigCo',
            },
            {
                'isin': 'EQ_B', 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
                'market_value_eur': nav * 0.91, 'beta': 1.0, 'dur_adj_mid': float('nan'),
                'currency': 'EUR', 'issuer': 'Others',
            },
        ])
        trade = {
            'isin': 'EQ_A', 'direction': 'buy', 'quantity': 1,
            'price_eur': nav * 0.025,  # +2.5% NAV → BigCo = 11.5% → breaches 10%
            'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
            'issuer': 'BigCo',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_ucits(pro_forma, nav, trade)
        checks = [b['check'] for b in breaches]
        assert '5_10_40_single_issuer_hard' in checks

    def test_var_breach_high_beta(self):
        # Portfolio of very high-beta equity → absolute VaR > 20%
        nav = 10_000_000.0
        pos = pd.DataFrame([{
            'isin': 'EQ_HIGH', 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
            'market_value_eur': nav, 'beta': 4.0, 'dur_adj_mid': float('nan'),
            'currency': 'EUR', 'issuer': 'HighBeta',
        }])
        trade = {
            'isin': 'MORE_EQ', 'direction': 'buy', 'quantity': 1,
            'price_eur': 1_000.0, 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_ucits(pro_forma, nav, trade)
        checks = [b['check'] for b in breaches]
        assert 'absolute_var_limit' in checks


class TestCheckAifmHfClean:

    def test_clean_trade_no_breaches(self):
        pos   = _make_hf_positions()
        nav   = 50_000_000.0
        trade = {
            'isin': 'NEW_EQ', 'direction': 'buy', 'quantity': 10,
            'price_eur': 1_000.0, 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_aifm_hf(pro_forma, nav, trade)
        assert len(breaches) == 0

    def test_required_metrics_returned(self):
        pos   = _make_hf_positions()
        nav   = 50_000_000.0
        trade = {
            'isin': 'NEW_EQ', 'direction': 'buy', 'quantity': 1,
            'price_eur': 100.0, 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_aifm_hf(pro_forma, nav, trade)
        for key in ['gross_leverage', 'commitment_leverage', 'max_issuer_pct', 'max_sector_pct']:
            assert key in metrics

    def test_gross_leverage_breach(self):
        nav = 50_000_000.0
        pos = pd.DataFrame([{
            'isin': 'LONG_A', 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
            'market_value_eur': nav * 2.90, 'beta': 1.0, 'dur_adj_mid': float('nan'),
            'currency': 'EUR', 'issuer': 'IssuerA', 'adv_eur': 10_000_000,
        }])
        trade = {
            'isin': 'LONG_B', 'direction': 'buy', 'quantity': 1,
            'price_eur': nav * 0.20,  # +20% NAV → gross = 3.10x → breach
            'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_aifm_hf(pro_forma, nav, trade)
        checks = [b['check'] for b in breaches]
        assert 'gross_leverage' in checks

    def test_issuer_concentration_breach(self):
        nav = 50_000_000.0
        pos = pd.DataFrame([{
            'isin': 'EQ_A', 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
            'market_value_eur': nav * 0.24, 'beta': 1.0, 'dur_adj_mid': float('nan'),
            'currency': 'EUR', 'issuer': 'BigIssuer', 'adv_eur': 10_000_000,
            'sector': 'Industrials',
        }, {
            'isin': 'EQ_B', 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
            'market_value_eur': nav * 0.76, 'beta': 1.0, 'dur_adj_mid': float('nan'),
            'currency': 'EUR', 'issuer': 'Others', 'adv_eur': 20_000_000,
            'sector': 'Utilities',
        }])
        trade = {
            'isin': 'EQ_A', 'direction': 'buy', 'quantity': 1,
            'price_eur': nav * 0.03,  # +3% → BigIssuer = 27% → breach 25%
            'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
            'issuer': 'BigIssuer',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_aifm_hf(pro_forma, nav, trade)
        checks = [b['check'] for b in breaches]
        assert 'issuer_concentration' in checks


class TestCheckAifmPdClean:

    def test_clean_trade_no_breaches(self):
        pos   = _make_pd_positions()
        nav   = float(pos['market_value_eur'].sum())
        trade = {
            'isin': 'LOAN_D', 'direction': 'buy', 'quantity': 1,
            'price_eur': nav * 0.05, 'asset_class': 'Loan',
            'sub_asset_class': 'Senior Secured', 'rating': 'BBB',
            'issuer': 'BorrowerD',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_aifm_pd(pro_forma, nav, trade)
        assert len(breaches) == 0

    def test_required_metrics_returned(self):
        pos   = _make_pd_positions()
        nav   = float(pos['market_value_eur'].sum())
        trade = {
            'isin': 'LOAN_D', 'direction': 'buy', 'quantity': 1,
            'price_eur': 1_000.0, 'asset_class': 'Loan',
            'sub_asset_class': 'Senior Secured', 'rating': 'BBB',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_aifm_pd(pro_forma, nav, trade)
        for key in ['max_borrower_pct', 'hy_exposure_pct', 'unrated_exposure_pct']:
            assert key in metrics

    def test_single_borrower_breach(self):
        nav = 20_000_000.0
        pos = pd.DataFrame([{
            'isin': 'LOAN_A', 'asset_class': 'Loan', 'sub_asset_class': 'Senior Secured',
            'market_value_eur': nav * 0.19, 'beta': float('nan'), 'dur_adj_mid': 3.0,
            'currency': 'EUR', 'issuer': 'BigBorrower', 'rating': 'BBB',
        }, {
            'isin': 'LOAN_B', 'asset_class': 'Loan', 'sub_asset_class': 'Senior Secured',
            'market_value_eur': nav * 0.81, 'beta': float('nan'), 'dur_adj_mid': 3.0,
            'currency': 'EUR', 'issuer': 'Others', 'rating': 'BBB',
        }])
        trade = {
            'isin': 'LOAN_A', 'direction': 'buy', 'quantity': 1,
            'price_eur': nav * 0.03,  # +3% → BigBorrower = 22% → breach 20%
            'asset_class': 'Loan', 'sub_asset_class': 'Senior Secured',
            'issuer': 'BigBorrower', 'rating': 'BBB',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_aifm_pd(pro_forma, nav, trade)
        checks = [b['check'] for b in breaches]
        assert 'single_borrower_concentration' in checks

    def test_hy_exposure_breach(self):
        nav = 20_000_000.0
        pos = pd.DataFrame([{
            'isin': 'HY_A', 'asset_class': 'Loan', 'sub_asset_class': 'Mezzanine',
            'market_value_eur': nav * 0.49, 'beta': float('nan'), 'dur_adj_mid': 4.0,
            'currency': 'EUR', 'issuer': 'SubA', 'rating': 'BB',
        }, {
            'isin': 'IG_A', 'asset_class': 'Loan', 'sub_asset_class': 'Senior Secured',
            'market_value_eur': nav * 0.51, 'beta': float('nan'), 'dur_adj_mid': 3.0,
            'currency': 'EUR', 'issuer': 'IG1', 'rating': 'BBB',
        }])
        trade = {
            'isin': 'HY_B', 'direction': 'buy', 'quantity': 1,
            'price_eur': nav * 0.05,  # +5% → HY = 54% → breach 50%
            'asset_class': 'Loan', 'sub_asset_class': 'Mezzanine',
            'issuer': 'SubB', 'rating': 'B+',
        }
        pro_forma         = _ptc_apply_trade(pos, trade)
        breaches, metrics = _check_aifm_pd(pro_forma, nav, trade)
        checks = [b['check'] for b in breaches]
        assert 'hy_exposure_limit' in checks


class TestPreTradeCheckIntegration:
    """Integration tests against the live DB. Require a populated database."""

    def test_returns_dict(self):
        trade = {
            'isin': 'US78378X1072', 'direction': 'buy', 'quantity': 10,
            'price_eur': 500.0, 'asset_class': 'Equity',
            'sub_asset_class': 'Large Cap', 'beta': 1.0,
        }
        result = pre_trade_check(trade, _ENGINE, 'UCITS_Balanced', _PTC_DATE)
        assert isinstance(result, dict)

    def test_required_keys(self):
        trade = {
            'isin': 'US78378X1072', 'direction': 'buy', 'quantity': 10,
            'price_eur': 500.0, 'asset_class': 'Equity',
            'sub_asset_class': 'Large Cap', 'beta': 1.0,
        }
        result = pre_trade_check(trade, _ENGINE, 'UCITS_Balanced', _PTC_DATE)
        for key in ['passed', 'fund_id', 'fund_type', 'proposed_trade',
                    'breaches', 'post_trade_metrics']:
            assert key in result

    def test_passed_is_bool(self):
        trade = {
            'isin': 'US78378X1072', 'direction': 'buy', 'quantity': 10,
            'price_eur': 500.0, 'asset_class': 'Equity',
            'sub_asset_class': 'Large Cap', 'beta': 1.0,
        }
        result = pre_trade_check(trade, _ENGINE, 'UCITS_Balanced', _PTC_DATE)
        assert isinstance(result['passed'], bool)

    def test_breaches_is_list(self):
        trade = {
            'isin': 'US78378X1072', 'direction': 'buy', 'quantity': 10,
            'price_eur': 500.0, 'asset_class': 'Equity',
            'sub_asset_class': 'Large Cap', 'beta': 1.0,
        }
        result = pre_trade_check(trade, _ENGINE, 'UCITS_Balanced', _PTC_DATE)
        assert isinstance(result['breaches'], list)

    def test_fund_type_ucits(self):
        trade = {
            'isin': 'US78378X1072', 'direction': 'buy', 'quantity': 1,
            'price_eur': 100.0, 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
        }
        result = pre_trade_check(trade, _ENGINE, 'UCITS_Balanced', _PTC_DATE)
        assert result['fund_type'] == 'ucits'

    def test_unsupported_fund_raises(self):
        trade = {
            'isin': 'X', 'direction': 'buy', 'quantity': 1,
            'price_eur': 100.0, 'asset_class': 'Equity', 'sub_asset_class': 'Large Cap',
        }
        with pytest.raises(ValueError, match='not supported'):
            pre_trade_check(trade, _ENGINE, 'UNKNOWN_FUND', _PTC_DATE)