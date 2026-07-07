"""Tests for real estate utils, workflow builder, and display functions."""

import pandas as pd
import pytest

import fund_risk_workflow.risk.real_estate_utils as reu
import fund_risk_workflow.ui.real_estate_display as red
from fund_risk_workflow.config import VALUATION_DATE
from fund_risk_workflow.data.database import get_engine
from fund_risk_workflow.data.enrichment import get_risk_ready_df
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg
from fund_risk_workflow.data.reference_data import (
    load_investor_base,
    load_rmp,
    load_tenant_register,
)
from fund_risk_workflow.pipeline.real_estate_workflow import (
    build_real_estate_workflow,
)
from fund_risk_workflow.risk.private_debt_utils import (
    closed_ended_investor_concentration,
)

FUND_ID = 'AIFM_RealEstate'


@pytest.fixture(scope='module')
def engine():
    return get_engine()


@pytest.fixture(scope='module')
def bbg():
    return MockBloomberg()


@pytest.fixture(scope='module')
def risk_df(engine):
    return get_risk_ready_df(engine, FUND_ID, VALUATION_DATE)


@pytest.fixture(scope='module')
def nav(risk_df):
    return float(risk_df['market_value_eur'].sum())


@pytest.fixture(scope='module')
def rmp():
    return load_rmp(FUND_ID)


@pytest.fixture(scope='module')
def tenants():
    return load_tenant_register(FUND_ID)


@pytest.fixture(scope='module')
def workflow(engine, bbg):
    return build_real_estate_workflow(engine, bbg, FUND_ID, VALUATION_DATE)


# ── sleeves and property profile ────────────────────────────────────────────

class TestSleeves:
    def test_sleeve_summary_sums_to_nav(self, risk_df, nav):
        out = reu.sleeve_summary(risk_df, nav)
        assert out['market_value_eur'].sum() == pytest.approx(nav)

    def test_four_sleeves_present(self, risk_df, nav):
        out = reu.sleeve_summary(risk_df, nav)
        assert set(out['sleeve']) == {
            'Direct Property', 'Listed REIT', 'FX Hedge', 'Cash'}

    def test_direct_property_dominates(self, risk_df, nav):
        out = reu.sleeve_summary(risk_df, nav).set_index('sleeve')
        assert out.loc['Direct Property', 'pct_nav'] > 50

    def test_property_profile_weighted_averages(self, risk_df, nav):
        out = reu.direct_property_profile(risk_df, nav)
        props = out['properties']
        mv = props['market_value_eur']
        expected_ltv = (props['ltv_pct'] * mv).sum() / mv.sum()
        assert out['weighted_avg']['ltv_pct'] == pytest.approx(expected_ltv)
        assert len(props) == 4

    def test_effective_yield_formula(self, risk_df, nav):
        out = reu.direct_property_profile(risk_df, nav)['properties']
        row = out.iloc[0]
        expected = row['rental_yield_pct'] * (1 - row['vacancy_rate_pct'] / 100)
        assert row['effective_yield_pct'] == pytest.approx(expected)

    def test_empty_raises(self, risk_df):
        with pytest.raises(ValueError):
            reu.sleeve_summary(risk_df.iloc[0:0], 1.0)


# ── stress ──────────────────────────────────────────────────────────────────

class TestStress:
    def test_assumptions_from_policy(self, rmp):
        out = reu.property_stress_assumptions(rmp)
        values = dict(zip(out['parameter'], out['value']))
        assert values['Retail value shock'] == -0.25
        assert values['Vacancy rate increase'] == 0.10
        assert values['Parallel shift'] == 0.02
        assert values['Capitalisation yield'] == 0.05

    def test_assumptions_missing_raise(self):
        with pytest.raises(ValueError, match='missing'):
            reu.property_stress_assumptions({'stress_scenarios': {}})

    def test_property_stress_hits_direct_only(self, risk_df, nav, rmp):
        out = reu.property_stress_results(risk_df, nav, rmp)
        prop_pnl = out.loc[
            out['scenario'].str.startswith('Property value'),
            'stressed_pnl_eur'].iloc[0]
        # Sum of type shocks applied to the four direct properties
        direct = risk_df[risk_df['is_direct_property'] == True]  # noqa: E712
        shocks = rmp['stress_scenarios']['property_value_shock_by_type']
        expected = sum(shocks[t] * mv for t, mv in
                       zip(direct['property_type'],
                           direct['market_value_eur']))
        assert prop_pnl == pytest.approx(expected)

    def test_historical_scenarios_exclude_direct_properties(
            self, risk_df, nav, rmp):
        out = reu.property_stress_results(risk_df, nav, rmp)
        hist = out[out['scenario'].str.contains('listed sleeve')]
        listed_mv = risk_df[
            risk_df['is_direct_property'] != True  # noqa: E712
        ]['market_value_eur'].abs().sum()
        # A -100% shock on the whole listed sleeve is the absolute bound
        assert (hist['stressed_pnl_eur'].abs() <= listed_mv).all()

    def test_ltv_stress_uses_policy_threshold(self, risk_df, rmp):
        out = reu.ltv_stress_summary(risk_df, rmp)
        assert out['threshold'] == rmp['ltv_monitoring']['ltv_stress_threshold']
        assert out['shock'] == (
            rmp['stress_scenarios']['ltv_stress_property_value_shock'])
        assert out['n_breaches'] == len(out['breaching_properties'])

    def test_ltv_stress_math(self, risk_df, rmp):
        out = reu.ltv_stress_summary(risk_df, rmp)
        row = out['by_position'].iloc[0]
        expected = (row['ltv_pct'] / 100) / (1 + out['shock'])
        assert row['stressed_ltv'] == pytest.approx(expected)


# ── lease register ──────────────────────────────────────────────────────────

class TestLeaseRegister:
    def test_leases_link_to_actual_properties(self, tenants, risk_df):
        direct_isins = set(
            risk_df[risk_df['is_direct_property'] == True]['isin'])  # noqa: E712
        assert set(tenants['property_isin']).issubset(direct_isins)

    def test_rent_reconciles_within_1_pct(self, tenants, risk_df):
        out = reu.reconcile_lease_rents(tenants, risk_df, tolerance_pct=1.0)
        assert (out['deviation_pct'].abs() <= 1.0).all()
        assert len(out) == 4

    def test_unknown_property_raises(self, tenants, risk_df):
        bad = tenants.copy()
        bad.loc[0, 'property_isin'] = 'PROP_XX_999'
        with pytest.raises(ValueError, match='unknown property'):
            reu.reconcile_lease_rents(bad, risk_df)

    def test_tenant_concentration_sums_to_100(self, tenants, nav):
        out = reu.tenant_concentration(tenants, nav)
        assert out['by_tenant']['pct_total_rent'].sum() == pytest.approx(100.0)
        assert out['by_property']['pct_total_rent'].sum() == pytest.approx(100.0)

    def test_tenant_default_stress_math(self, tenants, nav):
        out = reu.tenant_default_stress(tenants, nav,
                                        capitalisation_yield=0.05)
        worst = out['worst']
        top = out['by_tenant'].iloc[0]
        assert worst['income_loss_eur'] == pytest.approx(
            top['annual_rent_eur'])
        assert worst['implied_nav_impact_eur'] == pytest.approx(
            top['annual_rent_eur'] / 0.05)

    def test_tenant_default_bad_yield_raises(self, tenants, nav):
        with pytest.raises(ValueError, match='capitalisation_yield'):
            reu.tenant_default_stress(tenants, nav, capitalisation_yield=0.0)


# ── investor concentration ─────────────────────────────────────────────────

class TestInvestors:
    def test_weights_sum_to_100_pct(self, nav):
        base = load_investor_base(FUND_ID, nav_eur=nav)
        assert base['nav_pct'].sum() == pytest.approx(1.0)
        assert len(base) == 12

    def test_closed_ended_concentration(self, nav):
        base = load_investor_base(FUND_ID, nav_eur=nav)
        out = closed_ended_investor_concentration(base, nav)
        assert out['summary']['largest_investor_pct'] == pytest.approx(0.20)


# ── workflow builder ────────────────────────────────────────────────────────

class TestWorkflowBuilder:
    def test_wrong_fund_id_raises(self, engine, bbg):
        with pytest.raises(ValueError, match='expects'):
            build_real_estate_workflow(engine, bbg,
                                       'AIFM_PrivateDebt', VALUATION_DATE)

    def test_missing_date_raises(self, engine, bbg):
        with pytest.raises(ValueError, match='No positions'):
            build_real_estate_workflow(engine, bbg, FUND_ID, '1999-01-01')

    def test_result_keys_complete(self, workflow):
        required = {
            'rmp', 'positions', 'risk_df', 'nav',
            'sleeve_summary', 'direct_property_profile',
            'leverage', 'granular_leverage',
            'stress_assumptions', 'stress_results', 'ltv_stress',
            'investor_base', 'investor_concentration',
            'tenant_register', 'tenant_concentration',
            'tenant_default_stress', 'esg_df',
        }
        assert required.issubset(workflow.keys())

    def test_nav_matches_positions(self, workflow):
        assert workflow['nav'] == pytest.approx(168_874_400.0)

    def test_esg_reference_scores_for_properties(self, workflow):
        esg = workflow['esg_df']
        lux = esg[esg['instrument_name'] == 'Office Tower Luxembourg City']
        assert lux['esg_score'].iloc[0] == 72


# ── presentation ────────────────────────────────────────────────────────────

class TestDisplay:
    @pytest.fixture(autouse=True)
    def capture(self, monkeypatch):
        self.htmls = []
        real = red.display_dark_table

        def spy(df, **kwargs):
            html = real(df, **kwargs)
            self.htmls.append(html)
            return html

        monkeypatch.setattr(red, 'display_dark_table', spy)
        monkeypatch.setattr(red, 'display', lambda *_a, **_k: None)

    def _assert_dark(self):
        assert self.htmls
        for html in self.htmls:
            assert '<table' in html
            assert '#1a1f2e' in html or '#141929' in html

    def test_sleeve_summary_dark(self, workflow):
        red.display_sleeve_summary(workflow['sleeve_summary'])
        self._assert_dark()
        assert pd.api.types.is_numeric_dtype(
            workflow['sleeve_summary']['market_value_eur'])

    def test_property_profile_dark(self, workflow):
        red.display_direct_property_profile(
            workflow['direct_property_profile'])
        self._assert_dark()

    def test_ltv_stress_dark(self, workflow):
        red.display_ltv_stress(workflow['ltv_stress'])
        self._assert_dark()

    def test_tenant_tables_dark(self, workflow):
        red.display_tenant_concentration(workflow['tenant_concentration'])
        red.display_tenant_default_stress(workflow['tenant_default_stress'])
        self._assert_dark()
        assert len(self.htmls) == 3

    def test_property_plot_uses_dark_style(self, workflow):
        import matplotlib
        matplotlib.use('Agg')
        fig = red.plot_direct_property_metrics(
            workflow['direct_property_profile'], FUND_ID)
        from matplotlib.figure import Figure
        assert isinstance(fig, Figure)
        from fund_risk_workflow.ui.plot_style import C
        import matplotlib.colors as mcolors
        assert mcolors.to_hex(fig.get_facecolor()) == C['bg']
