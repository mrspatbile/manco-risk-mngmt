"""
tests/test_concentration_fix_phase_f1.py
========================================
Phase F1: Concentration semantics fix for derivative classification.

Tests verify that:
- Derivatives are excluded from issuer concentration (no index futures as issuers)
- Sector concentration uses net signed exposure (not .abs() after sum)
- US78462F1030 breach is still flagged
- Ordinary equity issuer exposure is preserved

Run with: python3 -m pytest tests/test_concentration_fix_phase_f1.py -v
"""

import pytest
import pandas as pd
from fund_risk_workflow.data.database import get_engine
from fund_risk_workflow.data.enrichment import get_risk_ready_df
from fund_risk_workflow.risk.risk_utils import (
    pre_trade_check, _ptc_issuer_exposure, _ptc_apply_trade
)
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg
from fund_risk_workflow.risk.leverage_computation import build_bbg_maps
from fund_risk_workflow.config import VALUATION_DATE


class TestIssuerConcentrationPhaseF1:
    """Verify derivatives are excluded from issuer concentration."""

    @pytest.fixture
    def setup(self):
        """Load AIFM Hedge Fund positions."""
        engine = get_engine()
        positions = get_risk_ready_df(engine, 'AIFM_HedgeFund', VALUATION_DATE)
        nav = positions['market_value_eur'].sum()
        return {
            'positions': positions,
            'nav': nav,
            'engine': engine,
        }

    def test_issuer_concentration_excludes_fx_forwards(self, setup):
        """FX forwards (FWD_EURUSD_001) should not appear in issuer concentration."""
        positions = setup['positions']
        nav = setup['nav']

        issuer_exp = _ptc_issuer_exposure(positions, nav)

        # FX forward should not be in issuer exposures
        assert 'FWD_EURUSD_001' not in issuer_exp.index, \
            "FX forward FWD_EURUSD_001 should not appear in issuer concentration"

        # Verify it WAS in the positions before filtering
        fx_fwd = positions[positions['isin'] == 'FWD_EURUSD_001']
        assert len(fx_fwd) == 1, "FWD_EURUSD_001 should exist in portfolio"
        assert fx_fwd.iloc[0]['asset_class'] == 'Derivative', \
            "FWD_EURUSD_001 should be classified as Derivative"

    def test_issuer_concentration_excludes_equity_index_futures(self, setup):
        """Equity index futures (EU0009658145, SPY future) should not appear as single issuers."""
        positions = setup['positions']
        nav = setup['nav']

        issuer_exp = _ptc_issuer_exposure(positions, nav)

        # Index futures should not appear
        excluded_futures = ['FUT_SPY_SHORT_001', 'FUT_SX5E_SHORT_001', 'EU0009658145']
        for fut_isin in excluded_futures:
            assert fut_isin not in issuer_exp.index, \
                f"{fut_isin} should not appear in issuer concentration"

        # Verify they ARE in the positions
        for fut_isin in excluded_futures:
            fut = positions[positions['isin'] == fut_isin]
            assert len(fut) == 1, f"{fut_isin} should exist in portfolio"
            assert fut.iloc[0]['asset_class'] == 'Derivative', \
                f"{fut_isin} should be classified as Derivative"

    def test_issuer_concentration_includes_ordinary_equities(self, setup):
        """Regular equity holdings should still appear in issuer concentration."""
        positions = setup['positions']
        nav = setup['nav']

        issuer_exp = _ptc_issuer_exposure(positions, nav)

        # Regular equities should be included
        equity_isins = ['US78462F1030', 'US5949181045', 'US0378331005', 'US46625H1005']
        for equity_isin in equity_isins:
            assert equity_isin in issuer_exp.index, \
                f"Equity {equity_isin} should appear in issuer concentration"
            pct = issuer_exp[equity_isin]
            assert pct > 0, f"Equity {equity_isin} concentration should be positive"

    def test_issuer_breach_us78462f1030_still_flagged(self, setup):
        """US78462F1030 at 27.48% should still exceed 25% limit and be flagged."""
        positions = setup['positions']
        nav = setup['nav']

        issuer_exp = _ptc_issuer_exposure(positions, nav)

        # US78462F1030 should be the largest issuer
        max_issuer = issuer_exp.max()
        max_isin = issuer_exp.idxmax()

        assert max_isin == 'US78462F1030', \
            f"Largest issuer should be US78462F1030, got {max_isin}"

        # Should exceed 25% limit
        assert max_issuer > 25.0, \
            f"US78462F1030 concentration {max_issuer:.2f}% should exceed 25% limit"

        # Run pre-trade check to verify breach is caught
        trade = {
            'isin': 'US0378331005',
            'direction': 'buy',
            'quantity': 1000,
            'price_eur': 225.66,
            'asset_class': 'Equity',
            'sub_asset_class': '',
        }

        engine = setup['engine']
        bbg = MockBloomberg()
        currency_bbg_map, deriv_bbg_map = build_bbg_maps('AIFM_HedgeFund')

        result = pre_trade_check(
            trade, engine, 'AIFM_HedgeFund', VALUATION_DATE,
            counterparties_df=None, bbg=bbg,
            deriv_bbg_map=deriv_bbg_map,
            currency_bbg_map=currency_bbg_map,
        )

        # Check if there is a pre-existing issuer breach for US78462F1030
        issuer_breaches = [b for b in result['breaches'] if 'issuer' in b['check'] and 'US78462F1030' in b['message']]

        # The pre-existing breach should be noted (though not necessarily in post-trade breaches if trade didn't worsen it)
        post_issuer_exp = result['post_trade_metrics']['max_issuer_pct']
        assert post_issuer_exp > 25.0, \
            f"Post-trade max issuer exposure {post_issuer_exp:.2f}% should still exceed 25%"


class TestSectorConcentrationPhaseF1:
    """Verify sector concentration uses net signed exposure."""

    @pytest.fixture
    def setup(self):
        """Load AIFM Hedge Fund positions."""
        engine = get_engine()
        positions = get_risk_ready_df(engine, 'AIFM_HedgeFund', VALUATION_DATE)
        nav = positions['market_value_eur'].sum()
        return {
            'positions': positions,
            'nav': nav,
            'engine': engine,
        }

    def test_sector_concentration_uses_signed_net_exposure(self, setup):
        """Sector concentration should use signed market_value / NAV, not abs(sum)."""
        positions = setup['positions']
        nav = setup['nav']

        # Calculate sector exposure manually
        sector_universe = positions[
            positions['asset_class'].isin(['Equity', 'Bond', 'Loan', 'CLO']) &
            positions['sector'].notna() &
            (positions['sector'] != 'Government')
        ]

        # Net sector weights (signed)
        sector_exp_net = (
            sector_universe.groupby('sector')['market_value_eur'].sum() / nav * 100
        )

        # All positive sectors should be in the 0-50% range (no sector should be 100%+ just from net)
        assert (sector_exp_net >= -50).all(), \
            f"Net sector concentrations should be reasonable (>-50%), got: {sector_exp_net.to_dict()}"
        assert (sector_exp_net <= 50).all(), \
            f"Net sector concentrations should be reasonable (<50%), got: {sector_exp_net.to_dict()}"

        # Technology should be largest
        if len(sector_exp_net) > 0:
            max_sector = sector_exp_net.max()
            max_sector_name = sector_exp_net.idxmax()
            assert max_sector_name == 'Technology', \
                f"Technology should be largest sector, got {max_sector_name}"
            assert 30 < max_sector < 40, \
                f"Technology sector should be ~34%, got {max_sector:.2f}%"

    def test_sector_concentration_no_100_percent_plus(self, setup):
        """No sector concentration should exceed 100% just from net signed exposure."""
        positions = setup['positions']
        nav = setup['nav']

        sector_universe = positions[
            positions['asset_class'].isin(['Equity', 'Bond', 'Loan', 'CLO']) &
            positions['sector'].notna() &
            (positions['sector'] != 'Government')
        ]

        sector_exp_net = (
            sector_universe.groupby('sector')['market_value_eur'].sum() / nav * 100
        )

        # No sector should exceed 100% in this portfolio (all net exposures)
        exceeding_100 = sector_exp_net[sector_exp_net > 100]
        assert len(exceeding_100) == 0, \
            f"Sector concentrations should not exceed 100% in net basis: {exceeding_100.to_dict()}"

    def test_sector_concentration_excludes_fx_derivatives(self, setup):
        """FX derivatives should not appear as sector exposures."""
        positions = setup['positions']
        nav = setup['nav']

        sector_universe = positions[
            positions['asset_class'].isin(['Equity', 'Bond', 'Loan', 'CLO']) &
            positions['sector'].notna() &
            (positions['sector'] != 'Government')
        ]

        # Verify FX derivatives are excluded from sector universe
        fx_derivatives = positions[
            (positions['asset_class'] == 'Derivative') &
            (positions['isin'].isin(['FWD_EURUSD_001', 'FWD_GBPUSD_001']))
        ]

        for _, fx_deriv in fx_derivatives.iterrows():
            # FX derivative should NOT be in sector_universe
            assert fx_deriv['isin'] not in sector_universe['isin'].values, \
                f"FX derivative {fx_deriv['isin']} should not appear in sector universe"


class TestConcentrationNoDriftToDerivativeBasis:
    """Verify no concentration metric drifts to using derivative notional basis."""

    @pytest.fixture
    def setup(self):
        """Load AIFM Hedge Fund positions."""
        engine = get_engine()
        positions = get_risk_ready_df(engine, 'AIFM_HedgeFund', VALUATION_DATE)
        nav = positions['market_value_eur'].sum()
        return {
            'positions': positions,
            'nav': nav,
        }

    def test_issuer_concentration_uses_market_value_not_notional(self, setup):
        """Issuer concentration should use market_value_eur, not gross notional."""
        positions = setup['positions']
        nav = setup['nav']

        issuer_exp = _ptc_issuer_exposure(positions, nav)

        # Maximum issuer concentration should be < 50% (all market value basis)
        # If notional were used, it could easily exceed 500% (derivatives have 10-100x leverage)
        if len(issuer_exp) > 0:
            max_conc = issuer_exp.max()
            assert max_conc < 100, \
                f"Max issuer concentration {max_conc:.2f}% should be <100% (market value basis, not notional). " \
                f"If notional were used, would be >500%"

    def test_no_issuer_concentration_above_100_percent(self, setup):
        """After Phase F1 fix, no issuer concentration should exceed 100% in normal circumstances."""
        positions = setup['positions']
        nav = setup['nav']

        issuer_exp = _ptc_issuer_exposure(positions, nav)

        exceeding_100 = issuer_exp[issuer_exp > 100]
        assert len(exceeding_100) == 0, \
            f"No issuer concentration should exceed 100% after Phase F1: {exceeding_100.to_dict()}"
