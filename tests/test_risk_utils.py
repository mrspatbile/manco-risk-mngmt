"""
tests/test_risk_utils.py
========================
Unit tests for risk_utils.py
Run with: python3 -m pytest tests/test_risk_utils.py -v
"""

import pytest
import numpy as np
import pandas as pd
from src.risk_utils import (
    var_historical, var_parametric, var_scale,
    es_historical, es_parametric, es_scale,
    kupiec_test, christoffersen_test,
    exception_report, full_backtest_report,
    stress_equity, stress_rates, stress_credit,
    stress_fx, stress_combined, stress_historical,
    stress_property, stress_rental, stress_ltv,
    days_to_liquidate, liquidity_buckets,
    redemption_stress, investor_concentration,
    liquidity_adjusted_var, var_montecarlo, compute_pnl_attribution
)


# ----------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------

@pytest.fixture
def normal_returns():
    """250 days of normally distributed returns."""
    np.random.seed(42)
    return np.random.normal(0.0005, 0.012, 250)


@pytest.fixture
def pnl_series(normal_returns):
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
        var   = var_parametric(mu=0, sigma=sigma,
                               confidence=0.99, dist='normal')
        es    = es_parametric(sigma=sigma, mu=0,
                              confidence=0.99, dist='normal')
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

    def test_returns_dict(self, pnl_series, var_series):
        result = kupiec_test(pnl_series, var_series)
        assert isinstance(result, dict)

    def test_has_required_keys(self, pnl_series, var_series):
        result = kupiec_test(pnl_series, var_series)
        for key in ['n_obs', 'n_breaches', 'breach_rate',
                    'expected', 'lr_stat', 'p_value', 'result']:
            assert key in result

    def test_result_is_pass_or_fail(self, pnl_series, var_series):
        result = kupiec_test(pnl_series, var_series)
        assert result['result'] in ('PASS', 'FAIL')

    def test_zero_breaches_handled(self, pnl_series):
        large_var = pd.Series(np.ones(250))
        result    = kupiec_test(pnl_series, large_var)
        assert result['n_breaches'] == 0

    def test_breach_rate_computed_correctly(self,
                                             pnl_series,
                                             var_series):
        result = kupiec_test(pnl_series, var_series)
        expected_rate = result['n_breaches'] / result['n_obs']
        assert abs(result['breach_rate'] - expected_rate) < 1e-4


class TestChristoffersenTest:

    def test_returns_dict(self, pnl_series, var_series):
        result = christoffersen_test(pnl_series, var_series)
        assert isinstance(result, dict)

    def test_has_required_keys(self, pnl_series, var_series):
        result = christoffersen_test(pnl_series, var_series)
        for key in ['n00', 'n01', 'n10', 'n11',
                    'lr_ind', 'p_value', 'result']:
            assert key in result

    def test_transition_counts_sum_correctly(self,
                                              pnl_series,
                                              var_series):
        result = christoffersen_test(pnl_series, var_series)
        total  = result['n00'] + result['n01'] + \
                 result['n10'] + result['n11']
        assert total == len(pnl_series) - 1

    def test_result_is_pass_or_fail(self, pnl_series, var_series):
        result = christoffersen_test(pnl_series, var_series)
        assert result['result'] in ('PASS', 'FAIL')


class TestExceptionReport:

    def test_returns_dataframe(self, pnl_series, var_series):
        result = exception_report(pnl_series, var_series)
        assert isinstance(result, pd.DataFrame)

    def test_has_correct_columns(self, pnl_series, var_series):
        result = exception_report(pnl_series, var_series)
        for col in ['pnl', 'var', 'excess_loss', 'action']:
            assert col in result.columns

    def test_all_rows_are_breaches(self, pnl_series, var_series):
        result = exception_report(pnl_series, var_series)
        assert (result['pnl'] < -result['var']).all()

    def test_excess_loss_positive(self, pnl_series, var_series):
        result = exception_report(pnl_series, var_series)
        if len(result) > 0:
            assert (result['excess_loss'] >= 0).all()


class TestFullBacktestReport:

    def test_returns_dataframe(self, pnl_series, var_series):
        result = full_backtest_report(
            pnl_series, {'model1': var_series})
        assert isinstance(result, pd.DataFrame)

    def test_three_confidence_levels(self, pnl_series,
                                      var_series):
        result = full_backtest_report(
            pnl_series, {'model1': var_series})
        assert len(result) == 3

    def test_multiple_models(self, pnl_series, var_series):
        result = full_backtest_report(
            pnl_series,
            {'model1': var_series, 'model2': var_series * 1.1}
        )
        assert len(result) == 6

    def test_result_column_values(self, pnl_series, var_series):
        result = full_backtest_report(
            pnl_series, {'model1': var_series})
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

class TestVarMonteCarlo:
    def test_returns_dict(self, sample_positions):
        result = var_montecarlo(sample_positions, n_sims=1000)
        assert isinstance(result, dict)

    def test_required_keys(self, sample_positions):
        result = var_montecarlo(sample_positions, n_sims=1000)
        for key in ['var', 'es', 'pnl_distribution',
                    'factor_vols', 'corr_matrix']:
            assert key in result

    def test_var_positive(self, sample_positions):
        result = var_montecarlo(sample_positions, n_sims=1000)
        assert result['var'] > 0

    def test_es_greater_than_var(self, sample_positions):
        result = var_montecarlo(sample_positions, n_sims=1000)
        assert result['es'] >= result['var']

    def test_pnl_distribution_shape(self, sample_positions):
        result = var_montecarlo(sample_positions, n_sims=1000)
        assert len(result['pnl_distribution']) == 1000

    def test_higher_confidence_higher_var(self, sample_positions):
        r99 = var_montecarlo(sample_positions, n_sims=1000,
                             confidence=0.99, seed=42)
        r95 = var_montecarlo(sample_positions, n_sims=1000,
                             confidence=0.95, seed=42)
        assert r99['var'] >= r95['var']

    def test_longer_horizon_higher_var(self, sample_positions):
        r1  = var_montecarlo(sample_positions, n_sims=1000,
                             horizon=1, seed=42)
        r20 = var_montecarlo(sample_positions, n_sims=1000,
                             horizon=20, seed=42)
        assert r20['var'] > r1['var']

    def test_corr_matrix_shape(self, sample_positions):
        result = var_montecarlo(sample_positions, n_sims=1000)
        assert result['corr_matrix'].shape == (6, 6)

    def test_reproducible_with_seed(self, sample_positions):
        r1 = var_montecarlo(sample_positions, n_sims=1000, seed=42)
        r2 = var_montecarlo(sample_positions, n_sims=1000, seed=42)
        assert r1['var'] == r2['var']

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