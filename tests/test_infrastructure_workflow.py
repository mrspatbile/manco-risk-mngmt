"""Tests for infrastructure workflow additions in infra_utils, builder, displays."""

import pytest

import fund_risk_workflow.risk.infra_utils as inu
import fund_risk_workflow.ui.infrastructure_display as ind
from fund_risk_workflow.config import QUARTER, VALUATION_DATE
from fund_risk_workflow.data.database import get_engine
from fund_risk_workflow.data.reference_data import load_rmp
from fund_risk_workflow.pipeline.infrastructure_workflow import (
    build_infrastructure_workflow,
)

FUND_ID = 'AIFM_Infra_Core'


@pytest.fixture(scope='module')
def engine():
    return get_engine()


@pytest.fixture(scope='module')
def workflow(engine):
    return build_infrastructure_workflow(engine, FUND_ID,
                                         VALUATION_DATE, QUARTER)


# ── infra_utils additions ───────────────────────────────────────────────────

class TestInfraUtilsAdditions:
    def test_portfolio_overview(self, engine):
        out = inu.infra_portfolio_overview(engine, FUND_ID, QUARTER)
        assert len(out['assets']) == 8
        assert out['assets']['nav_pct'].sum() == pytest.approx(100.0)
        assert out['total_nav_eur'] > 0
        assert not out['fund_metadata'].empty

    def test_covenant_monitor_dscr(self, engine):
        out = inu.covenant_monitor(engine, FUND_ID, 'dscr')
        assert len(out) == 8
        row = out.iloc[0]
        assert row['headroom'] == pytest.approx(
            row['actual'] - row['covenant'])
        assert row['status'] in ('Breach', 'Watch', 'OK')
        assert isinstance(row['history'], list)

    def test_covenant_monitor_ltv_headroom_inverted(self, engine):
        out = inu.covenant_monitor(engine, FUND_ID, 'ltv')
        row = out.iloc[0]
        assert row['headroom'] == pytest.approx(
            row['covenant'] - row['actual'])

    def test_covenant_monitor_bad_metric_raises(self, engine):
        with pytest.raises(ValueError, match='metric'):
            inu.covenant_monitor(engine, FUND_ID, 'dsra')

    def test_discount_rate_movement(self, engine):
        out = inu.discount_rate_movement(engine, FUND_ID, QUARTER)
        assert len(out) == 8
        assert out.attrs['quarter'] == QUARTER
        assert out.attrs['prev_quarter'] < QUARTER
        assert 'flagged' in out.columns

    def test_concentration_detail_sums(self, engine):
        out = inu.concentration_detail(engine, FUND_ID, QUARTER)
        for key in ('country', 'sub_type'):
            assert out[key]['nav_pct'].sum() == pytest.approx(100.0)
        assert 'concentrated' in out['sector'].columns

    def test_quarterly_cashflow_identities(self, engine):
        cf = inu.infra_quarterly_cashflow_frame(engine, FUND_ID)
        assert (cf['ncf'] == cf['distributions'] - cf['calls']
                - cf['fees']).all()
        assert cf['cncf'].iloc[-1] == pytest.approx(cf['ncf'].sum())
        assert cf['dpi'].iloc[-1] > 0

    def test_stress_summary_from_policy(self, engine):
        rmp = load_rmp(FUND_ID)
        out = inu.infra_stress_summary(
            engine, FUND_ID, scenarios=rmp['stress_scenarios']['scenarios'])
        assert len(out['summary']) == 3
        # combined scenario must be at least as severe as each single shock
        summary = out['summary'].set_index('scenario')
        combined = summary.loc['(c) Combined', 'nav_change_pct']
        assert combined <= summary['nav_change_pct'].drop('(c) Combined').min()

    def test_stress_missing_fields_raise(self, engine):
        with pytest.raises(ValueError, match='missing'):
            inu.infra_stress_summary(engine, FUND_ID,
                                     scenarios=[{'name': 'x'}])

    def test_stress_empty_scenarios_raise(self, engine):
        with pytest.raises(ValueError, match='No stress scenarios'):
            inu.infra_stress_summary(engine, FUND_ID, scenarios=[])


# ── workflow builder ────────────────────────────────────────────────────────

class TestWorkflowBuilder:
    def test_wrong_fund_id_raises(self, engine):
        with pytest.raises(ValueError, match='expects'):
            build_infrastructure_workflow(engine, 'AIFM_PE_Buyout',
                                          VALUATION_DATE, QUARTER)

    def test_result_keys_complete(self, workflow):
        required = {
            'rmp', 'fund', 'assets', 'investments', 'valuations',
            'nav_history', 'portfolio_overview', 'valuation_summary',
            'performance', 'covenant_monitor', 'concentration',
            'inflation_sensitivity', 'duration_profile',
            'cashflow_profile', 'cashflow_coverage',
            'stress_results', 'esg_df',
        }
        assert required.issubset(workflow.keys())

    def test_performance_benchmark_from_policy(self, workflow):
        assert workflow['performance']['target_irr'] == pytest.approx(0.06)
        assert workflow['performance']['irr_vs_target'] == pytest.approx(
            workflow['performance']['irr'] - 0.06)

    def test_esg_df_populated(self, workflow):
        esg = workflow['esg_df']
        assert len(esg) == 8
        assert 'esg_reporter' in esg.columns


# ── presentation ────────────────────────────────────────────────────────────

class TestDisplay:
    @pytest.fixture(autouse=True)
    def capture(self, monkeypatch):
        self.htmls = []
        real = ind.display_dark_table

        def spy(df, **kwargs):
            html = real(df, **kwargs)
            self.htmls.append(html)
            return html

        monkeypatch.setattr(ind, 'display_dark_table', spy)
        monkeypatch.setattr(ind, 'display', lambda *_a, **_k: None)

    def _assert_dark(self):
        assert self.htmls
        for html in self.htmls:
            assert '<table' in html
            assert '#1a1f2e' in html or '#141929' in html

    def test_tables_dark(self, workflow):
        ind.display_fund_metadata(workflow['portfolio_overview'])
        ind.display_asset_portfolio(workflow['portfolio_overview'])
        ind.display_discount_rate_movement(
            workflow['valuation_summary']['discount_rate_movement'])
        ind.display_performance(workflow['performance'])
        ind.display_sector_concentration(workflow['concentration'])
        ind.display_inflation_summary(workflow['inflation_sensitivity'])
        ind.display_duration_profile(workflow['duration_profile'])
        ind.display_stress_summary(workflow['stress_results'])
        ind.display_asset_stress_detail(workflow['stress_results'],
                                        '(c) Combined')
        self._assert_dark()
        assert len(self.htmls) == 9

    def test_covenant_monitor_has_sparklines(self, workflow):
        import matplotlib
        matplotlib.use('Agg')
        ind.display_covenant_monitor(workflow['covenant_monitor']['dscr'],
                                     'DSCR')
        self._assert_dark()
        assert 'data:image/png;base64' in self.htmls[0]

    def test_plots_return_dark_figures(self, workflow):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.colors as mcolors
        from matplotlib.figure import Figure

        from fund_risk_workflow.ui.plot_style import C
        figs = [
            ind.plot_nav_timeseries(
                workflow['valuation_summary']['nav_timeseries'], FUND_ID),
            ind.plot_nav_by_asset(
                workflow['valuation_summary']['asset_breakdown'], FUND_ID),
            ind.plot_moic_decomposition(workflow['performance'], FUND_ID),
            ind.plot_concentration(workflow['concentration'], FUND_ID),
            ind.plot_inflation_linkage(workflow['inflation_sensitivity'],
                                       FUND_ID),
            ind.plot_duration_profile(workflow['duration_profile'], FUND_ID),
            ind.plot_infra_j_curve(workflow['cashflow_profile'], FUND_ID),
            ind.plot_cashflow_coverage(workflow['cashflow_coverage'],
                                       FUND_ID),
            ind.plot_stress_impact(workflow['stress_results'], FUND_ID),
            ind.plot_asset_stress_detail(workflow['stress_results'],
                                         '(c) Combined', FUND_ID),
        ]
        for fig in figs:
            assert isinstance(fig, Figure)
            assert mcolors.to_hex(fig.get_facecolor()) == C['bg']
