"""Tests for PE buyout workflow additions in pe_utils, the builder, and displays."""

import pandas as pd
import pytest

import fund_risk_workflow.risk.pe_utils as peu
import fund_risk_workflow.ui.pe_buyout_display as ped
from fund_risk_workflow.config import QUARTER, VALUATION_DATE
from fund_risk_workflow.data.database import get_engine
from fund_risk_workflow.data.generate_pe_fund import CARRY_RATE, HURDLE_RATE
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg
from fund_risk_workflow.data.reference_data import load_rmp
from fund_risk_workflow.pipeline.pe_buyout_workflow import (
    build_pe_buyout_workflow,
)

FUND_ID = 'AIFM_PE_Buyout'


@pytest.fixture(scope='module')
def engine():
    return get_engine()


@pytest.fixture(scope='module')
def workflow(engine):
    return build_pe_buyout_workflow(engine, MockBloomberg(), FUND_ID,
                                    VALUATION_DATE, QUARTER)


# ── pe_utils additions ──────────────────────────────────────────────────────

class TestPEUtilsAdditions:
    def test_portfolio_overview_shape(self, engine):
        out = peu.pe_portfolio_overview(engine, FUND_ID)
        assert len(out) == 8
        assert out['status'].isin(['Active', 'Exited']).all()
        exited = out[out['status'] == 'Exited']
        assert exited['exit_multiple'].notna().all()

    def test_covenant_summary_headroom(self, engine):
        out = peu.pe_covenant_summary(engine, FUND_ID, QUARTER)
        assert len(out) == 8
        row = out[out['headroom_pct'].notna()].iloc[0]
        expected = ((row['leverage_covenant'] - row['leverage_ratio'])
                    / row['leverage_covenant'] * 100)
        assert row['headroom_pct'] == pytest.approx(expected)

    def test_quarterly_frame_identities(self, engine):
        cf = peu.pe_quarterly_cashflow_frame(engine, FUND_ID)
        assert (cf['ncf'] == cf['distributions'] - cf['capital_called']
                - cf['mgmt_fees']).all()
        assert cf['cncf'].iloc[-1] == pytest.approx(cf['ncf'].sum())
        last = cf.iloc[-1]
        assert last['tvpi'] == pytest.approx(last['dpi'] + last['rvpi'])

    def test_j_curve_has_trough(self, engine):
        cf = peu.pe_quarterly_cashflow_frame(engine, FUND_ID)
        assert cf['cncf'].min() < 0  # capital deployed early

    def test_waterfall_conservation(self, engine):
        wfs = peu.pe_exit_waterfalls(engine, FUND_ID,
                                     hurdle_rate=HURDLE_RATE,
                                     carry_rate=CARRY_RATE)
        assert len(wfs) == 2  # two realised exits
        for wf in wfs:
            total = sum(s['amount_eur'] for s in wf['steps'])
            assert total == pytest.approx(wf['gross_exit_value_eur'])
            assert all(s['amount_eur'] >= 0 for s in wf['steps'])
            parties = {s['party'] for s in wf['steps']}
            assert parties == {'LP', 'GP'}

    def test_commitment_liquidity_coverage(self, engine):
        cl = peu.pe_commitment_liquidity(engine, FUND_ID, VALUATION_DATE,
                                         stress_call_pct=0.30)
        assert cl['unfunded_eur'] == pytest.approx(
            cl['committed_eur'] - cl['drawn_eur'])
        expected_cov = ((cl['cash_eur'] + cl['sub_line_headroom_eur']
                         + cl['distributions_12m_eur'])
                        / (cl['capital_calls_12m_eur'] + cl['fees_12m_eur']))
        assert cl['coverage_ratio'] == pytest.approx(expected_cov)
        buckets = cl['liquidity_buckets']
        assert buckets['abs_exposure'].sum() == pytest.approx(cl['nav_eur'])

    def test_commitment_liquidity_bad_pct_raises(self, engine):
        with pytest.raises(ValueError, match='stress_call_pct'):
            peu.pe_commitment_liquidity(engine, FUND_ID, VALUATION_DATE,
                                        stress_call_pct=0.0)

    def test_lp_cash_flows_first_date(self, engine):
        lp = peu.pe_lp_cash_flows(engine, FUND_ID, VALUATION_DATE)
        assert lp['first_flow_date'] == '2018-06-30'
        assert lp['terminal_nav'] > 0
        assert len(lp['cash_flows']) == len(lp['dates'])

    def test_stress_scenarios_math(self, engine):
        rmp = load_rmp(FUND_ID)
        stress = peu.pe_stress_scenarios(engine, FUND_ID, QUARTER,
                                         params=rmp['stress_scenarios'])
        by_co = stress['by_company']
        base = stress['base_nav_eur']
        s1_total = stress['summary'].loc[
            stress['summary']['scenario'].str.startswith('S1'),
            'delta_nav_eur'].iloc[0]
        assert s1_total == pytest.approx(-0.20 * base)
        # S4 hits Technology only
        tech = by_co[by_co['sector'] == 'Technology']
        non_tech = by_co[by_co['sector'] != 'Technology']
        assert (tech['s4_sector_concentration'] < 0).all()
        assert (non_tech['s4_sector_concentration'] == 0).all()

    def test_stress_missing_params_raise(self, engine):
        with pytest.raises(ValueError, match='missing'):
            peu.pe_stress_scenarios(engine, FUND_ID, QUARTER, params={})


# ── workflow builder ────────────────────────────────────────────────────────

class TestWorkflowBuilder:
    def test_wrong_fund_id_raises(self, engine):
        with pytest.raises(ValueError, match='expects'):
            build_pe_buyout_workflow(engine, MockBloomberg(),
                                     'AIFM_Infra_Core', VALUATION_DATE,
                                     QUARTER)

    def test_result_keys_complete(self, workflow):
        required = {
            'rmp', 'fund', 'portfolio_companies', 'valuations',
            'cash_flows', 'nav_history', 'cash_management',
            'portfolio_overview', 'valuation_monitor',
            'performance', 'j_curve', 'exit_waterfalls',
            'cash_summary', 'value_bridge', 'commitment_liquidity',
            'pme', 'stress_results', 'esg_df',
        }
        assert required.issubset(workflow.keys())

    def test_pme_uses_cached_benchmark(self, workflow):
        pme = workflow['pme']
        assert pme['benchmark'] == 'SX5E Index'
        assert pme['pe_irr'] is not None
        assert pme['pme_irr'] is not None
        assert pme['alpha'] == pytest.approx(
            pme['pe_irr'] - pme['pme_irr'])

    def test_esg_df_populated(self, workflow):
        esg = workflow['esg_df']
        assert len(esg) > 0
        assert 'esg_reporter' in esg.columns

    def test_no_generator_outputs(self, workflow):
        # Data must come from the DB, not regenerated structures
        assert isinstance(workflow['cash_flows'], pd.DataFrame)
        assert len(workflow['cash_flows']) == 47  # populated table row count


# ── presentation ────────────────────────────────────────────────────────────

class TestDisplay:
    @pytest.fixture(autouse=True)
    def capture(self, monkeypatch):
        self.htmls = []
        real = ped.display_dark_table

        def spy(df, **kwargs):
            html = real(df, **kwargs)
            self.htmls.append(html)
            return html

        monkeypatch.setattr(ped, 'display_dark_table', spy)
        monkeypatch.setattr(ped, 'display', lambda *_a, **_k: None)

    def _assert_dark(self):
        assert self.htmls
        for html in self.htmls:
            assert '<table' in html
            assert '#1a1f2e' in html or '#141929' in html

    def test_portfolio_overview_dark(self, workflow):
        ped.display_portfolio_overview(workflow['portfolio_overview'])
        self._assert_dark()
        assert pd.api.types.is_numeric_dtype(
            workflow['portfolio_overview']['cost_basis_eur'])

    def test_valuation_monitor_dark(self, workflow):
        ped.display_valuation_monitor(workflow['valuation_monitor'])
        self._assert_dark()

    def test_summary_tables_dark(self, workflow):
        ped.display_performance_summary(workflow['performance'])
        ped.display_commitment_liquidity(workflow['commitment_liquidity'])
        ped.display_liquidity_buckets(workflow['commitment_liquidity'])
        ped.display_pme_summary(workflow['pme'])
        ped.display_stress_summary(workflow['stress_results'])
        ped.display_bridge_gaps(workflow['value_bridge'])
        self._assert_dark()
        assert len(self.htmls) == 6

    def test_plots_return_dark_figures(self, workflow):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.colors as mcolors
        from matplotlib.figure import Figure

        from fund_risk_workflow.ui.plot_style import C
        figs = [
            ped.plot_j_curve(workflow['j_curve'], FUND_ID),
            ped.plot_exit_waterfalls(workflow['exit_waterfalls'], FUND_ID),
            ped.plot_cash_management(workflow['cash_summary'], FUND_ID),
            ped.plot_value_bridge_by_company(workflow['value_bridge'],
                                             FUND_ID),
            ped.plot_value_bridge_fund(workflow['value_bridge'], FUND_ID),
            ped.plot_pme(workflow['pme'], FUND_ID),
            ped.plot_stress_summary(workflow['stress_results'], FUND_ID),
        ]
        for fig in figs:
            assert isinstance(fig, Figure)
            assert mcolors.to_hex(fig.get_facecolor()) == C['bg']
