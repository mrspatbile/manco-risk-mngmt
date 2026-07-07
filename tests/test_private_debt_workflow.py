"""Tests for private debt utils, workflow builder, and display functions."""

import pandas as pd
import pytest

import fund_risk_workflow.risk.private_debt_utils as pdu
import fund_risk_workflow.ui.private_debt_display as pdd
from fund_risk_workflow.config import VALUATION_DATE
from fund_risk_workflow.data.database import get_engine
from fund_risk_workflow.data.enrichment import get_risk_ready_df
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg
from fund_risk_workflow.data.reference_data import load_investor_base, load_rmp
from fund_risk_workflow.pipeline.private_debt_workflow import (
    build_private_debt_workflow,
)

FUND_ID = 'AIFM_PrivateDebt'


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
def workflow(engine, bbg):
    return build_private_debt_workflow(engine, bbg, FUND_ID, VALUATION_DATE)


# ── aggregation ─────────────────────────────────────────────────────────────

class TestAggregation:
    def test_rating_profile_sums_to_nav(self, risk_df, nav):
        out = pdu.rating_profile(risk_df, nav)
        assert out['market_value_eur'].sum() == pytest.approx(nav)
        assert out['pct_nav'].sum() == pytest.approx(100.0)

    def test_rating_profile_sorted_strongest_first(self, risk_df, nav):
        out = pdu.rating_profile(risk_df, nav)
        assert out['rating'].iloc[0] == 'AAA'
        assert out['rating'].iloc[-1] == 'NR'

    def test_seniority_profile_sums_to_nav(self, risk_df, nav):
        out = pdu.seniority_profile(risk_df, nav)
        assert out['market_value_eur'].sum() == pytest.approx(nav)

    def test_sector_profile_labels_cash(self, risk_df, nav):
        out = pdu.sector_profile(risk_df, nav)
        assert 'Cash & Equivalents' in out['sector'].values

    def test_country_profile_sums_to_nav(self, risk_df, nav):
        out = pdu.country_profile(risk_df, nav)
        assert out['market_value_eur'].sum() == pytest.approx(nav)

    def test_borrower_concentration_excludes_cash(self, risk_df, nav):
        out = pdu.borrower_concentration(risk_df, nav)
        assert 'Cash EUR' not in out['instrument_name'].values
        assert len(out) == 9  # 11 positions minus cash and MMF
        assert (out['exposure_eur'] > 0).all()

    def test_borrower_label_is_instrument_name(self, risk_df, nav):
        out = pdu.borrower_concentration(risk_df, nav)
        assert out['instrument_name'].iloc[0] in risk_df['instrument_name'].values

    def test_maturity_ladder_sums_to_nav(self, risk_df, nav):
        out = pdu.maturity_ladder(risk_df, nav, VALUATION_DATE)
        assert out['market_value_eur'].sum() == pytest.approx(nav)
        assert set(out['bucket']).issubset(set(pdu.MATURITY_BUCKETS))

    def test_maturity_ladder_cash_has_no_stated_maturity(self, risk_df, nav):
        out = pdu.maturity_ladder(risk_df, nav, VALUATION_DATE)
        no_mat = out[out['bucket'] == 'No stated maturity']
        assert no_mat['n_positions'].iloc[0] == 2  # cash + MMF

    def test_empty_positions_raise(self, risk_df):
        with pytest.raises(ValueError, match='empty'):
            pdu.rating_profile(risk_df.iloc[0:0], 1.0)

    def test_nonpositive_nav_raises(self, risk_df):
        with pytest.raises(ValueError, match='NAV'):
            pdu.rating_profile(risk_df, 0.0)


# ── stress ──────────────────────────────────────────────────────────────────

class TestStress:
    def test_assumptions_from_policy(self):
        rmp = load_rmp(FUND_ID)
        out = pdu.credit_stress_assumptions(rmp)
        assert len(out) == 3
        values = dict(zip(out['parameter'], out['value']))
        assert values['Rate shock (parallel shift)'] == 0.02
        assert values['Credit spread widening'] == 0.015
        assert values['Senior secured recovery rate'] == 0.40

    def test_assumptions_missing_params_raise(self):
        with pytest.raises(ValueError, match='missing'):
            pdu.credit_stress_assumptions({'stress_scenarios': {}})

    def test_stress_results_shape(self, risk_df, nav):
        out = pdu.credit_stress_results(risk_df, nav,
                                        delta_y=0.02, delta_spread=0.015)
        assert len(out) >= 3  # rate, credit, combined + historical
        assert pd.api.types.is_numeric_dtype(out['stressed_pnl_eur'])
        assert pd.api.types.is_numeric_dtype(out['pct_nav'])

    def test_rate_and_credit_stress_are_losses(self, risk_df, nav):
        out = pdu.credit_stress_results(risk_df, nav,
                                        delta_y=0.02, delta_spread=0.015)
        assert out['stressed_pnl_eur'].iloc[0] < 0  # rate shock
        assert out['stressed_pnl_eur'].iloc[1] < 0  # credit widening

    def test_borrower_default_loss_uses_recovery(self, risk_df, nav):
        out = pdu.borrower_default_stress(risk_df, nav, recovery_rate=0.40)
        top = out['by_borrower'].iloc[0]
        assert top['loss_eur'] == pytest.approx(top['exposure_eur'] * 0.60)
        assert out['worst']['borrower'] == top['borrower']

    def test_borrower_default_invalid_recovery_raises(self, risk_df, nav):
        with pytest.raises(ValueError, match='recovery_rate'):
            pdu.borrower_default_stress(risk_df, nav, recovery_rate=1.5)


# ── investor concentration ─────────────────────────────────────────────────

class TestInvestorConcentration:
    def test_weights_sum_to_100_pct(self, nav):
        base = load_investor_base(FUND_ID, nav_eur=nav)
        assert base['nav_pct'].sum() == pytest.approx(1.0)
        assert len(base) == 8

    def test_closed_ended_outputs(self, nav):
        base = load_investor_base(FUND_ID, nav_eur=nav)
        out = pdu.closed_ended_investor_concentration(base, nav)
        assert out['summary']['largest_investor_pct'] == pytest.approx(0.35)
        assert out['summary']['top3_pct'] == pytest.approx(0.70)
        assert out['summary']['concentration_flag'] is True
        assert out['summary']['high_concentration'] is True
        assert out['by_type']['pct_nav'].sum() == pytest.approx(100.0)

    def test_no_redemption_outputs(self, nav):
        base = load_investor_base(FUND_ID, nav_eur=nav)
        out = pdu.closed_ended_investor_concentration(base, nav)
        assert 'redemption' not in ' '.join(out.keys()).lower()

    def test_bad_weights_raise(self, nav):
        base = load_investor_base(FUND_ID, nav_eur=nav)
        bad = base.copy()
        bad.loc[0, 'nav_pct'] = 0.99
        with pytest.raises(ValueError, match='100%'):
            pdu.closed_ended_investor_concentration(bad, nav)

    def test_empty_base_raises(self, nav):
        with pytest.raises(ValueError, match='empty'):
            pdu.closed_ended_investor_concentration(pd.DataFrame(), nav)


# ── workflow builder ────────────────────────────────────────────────────────

class TestWorkflowBuilder:
    def test_wrong_fund_id_raises(self, engine, bbg):
        with pytest.raises(ValueError, match='expects'):
            build_private_debt_workflow(engine, bbg,
                                        'AIFM_HedgeFund', VALUATION_DATE)

    def test_missing_date_raises(self, engine, bbg):
        with pytest.raises(ValueError, match='No positions'):
            build_private_debt_workflow(engine, bbg, FUND_ID, '1999-01-01')

    def test_result_keys_complete(self, workflow):
        required = {
            'rmp', 'positions', 'risk_df', 'nav',
            'credit_profile', 'concentration', 'maturity_profile',
            'leverage', 'granular_leverage',
            'stress_assumptions', 'stress_results', 'borrower_default',
            'investor_base', 'investor_concentration', 'esg_df',
        }
        assert required.issubset(workflow.keys())

    def test_nav_matches_positions(self, workflow):
        assert workflow['nav'] == pytest.approx(48_769_000.0)

    def test_esg_uses_reference_scores_for_clos(self, workflow):
        esg = workflow['esg_df']
        clo = esg[esg['instrument_name'] == 'Cairn CLO AAA 2024-1']
        assert clo['esg_score'].iloc[0] == 57

    def test_leverage_within_policy(self, workflow):
        assert 0 < workflow['leverage']['gross_leverage'] < 2.0


# ── presentation ────────────────────────────────────────────────────────────

class TestDisplay:
    @pytest.fixture(autouse=True)
    def capture(self, monkeypatch):
        self.htmls = []
        self.dfs = []
        real = pdd.display_dark_table

        def spy(df, **kwargs):
            self.dfs.append(df)
            html = real(df, **kwargs)
            self.htmls.append(html)
            return html

        monkeypatch.setattr(pdd, 'display_dark_table', spy)
        monkeypatch.setattr(pdd, 'display', lambda *_a, **_k: None)

    def _assert_dark(self):
        assert self.htmls, 'display function rendered no table'
        for html in self.htmls:
            assert '<table' in html
            assert '#1a1f2e' in html or '#141929' in html  # dark row colors

    def test_rating_table_dark_and_numeric(self, workflow):
        rating = workflow['credit_profile']['rating']
        pdd.display_rating_profile(rating)
        self._assert_dark()
        # input must stay numeric — formatting is display-only
        assert pd.api.types.is_numeric_dtype(rating['market_value_eur'])
        assert pd.api.types.is_numeric_dtype(self.dfs[0]['market_value_eur'])

    def test_stress_results_dark(self, workflow):
        pdd.display_stress_results(workflow['stress_results'])
        self._assert_dark()
        assert pd.api.types.is_numeric_dtype(
            workflow['stress_results']['stressed_pnl_eur'])

    def test_borrower_default_dark(self, workflow):
        pdd.display_borrower_default(workflow['borrower_default'])
        self._assert_dark()

    def test_investor_concentration_dark(self, workflow):
        pdd.display_investor_concentration_closed_ended(
            workflow['investor_concentration'])
        self._assert_dark()
        assert len(self.htmls) == 2  # register + type breakdown

    def test_maturity_ladder_dark(self, workflow):
        pdd.display_maturity_ladder(workflow['maturity_profile'])
        self._assert_dark()
