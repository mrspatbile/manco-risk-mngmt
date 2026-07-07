"""
tests/test_derivative_exposure_helper.py
========================================
Unit tests for derivative exposure helper (Phase 3a).
Run with: python3 -m pytest tests/test_derivative_exposure_helper.py -v
"""

import pytest
import pandas as pd
import numpy as np
from fund_risk_workflow.computation.derivatives import (
    fetch_derivative_market_inputs,
    compute_derivative_exposure,
    compute_derivative_exposures_portfolio,
)
from fund_risk_workflow.data.reference_data import load_derivative_contracts
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg
from fund_risk_workflow.data.database import get_engine, query_positions
from fund_risk_workflow.config import VALUATION_DATE


class TestFetchDerivativeMarketInputs:
    """Test Bloomberg market inputs fetcher."""

    def test_fetch_valid_ticker(self):
        """Fetch market inputs for valid option ticker."""
        bbg = MockBloomberg()
        inputs = fetch_derivative_market_inputs('SPXW 260619P05500 Index', bbg)

        assert inputs is not None
        assert 'delta' in inputs
        assert 'underlying_price' in inputs
        assert 'contract_size' in inputs
        assert 'ccy' in inputs
        assert inputs['contract_size'] == 100

    def test_fetch_with_cache(self):
        """Verify cache stores and reuses market inputs."""
        bbg = MockBloomberg()
        cache = {}

        # First call populates cache
        inputs1 = fetch_derivative_market_inputs('SPY US Equity', bbg, cache=cache)
        assert 'SPY US Equity' in cache

        # Mock bbg to raise if called again (proves cache was used)
        class MockBBGRaises:
            def bdp(self, *args, **kwargs):
                raise RuntimeError("Bloomberg called twice (cache not used)")

        bbg_fails = MockBBGRaises()

        # Second call should use cache, not raise
        inputs2 = fetch_derivative_market_inputs('SPY US Equity', bbg_fails, cache=cache)
        assert inputs1 == inputs2

    def test_fetch_empty_ticker_raises(self):
        """Empty ticker should raise ValueError."""
        bbg = MockBloomberg()
        with pytest.raises(ValueError, match="bloomberg_ticker"):
            fetch_derivative_market_inputs('', bbg)

    def test_fetch_none_ticker_raises(self):
        """None ticker should raise ValueError."""
        bbg = MockBloomberg()
        with pytest.raises(ValueError, match="bloomberg_ticker"):
            fetch_derivative_market_inputs(None, bbg)


class TestComputeDerivativeExposure:
    """Test single-position exposure computation."""

    def test_future_gross_notional(self):
        """Test futures gross notional: qty=30000, csize=100, price=523.42, fx=0.89"""
        result = compute_derivative_exposure(
            quantity=30000,
            delta=1.0,
            underlying_price=523.42,
            contract_multiplier=100,
            fx_rate=0.89,
            contract_type='future'
        )

        expected_gross = 30000 * 100 * 523.42 * 0.89
        assert result['gross_notional_eur'] == pytest.approx(expected_gross)

    def test_future_delta_adjusted_exposure(self):
        """Test futures delta-adjusted (delta=1): qty=-30000, csize=100, price=523.42, fx=0.89"""
        result = compute_derivative_exposure(
            quantity=-30000,
            delta=1.0,
            underlying_price=523.42,
            contract_multiplier=100,
            fx_rate=0.89,
            contract_type='future'
        )

        # Delta-adjusted preserves sign: 1.0 * (-30000) * 100 * 523.42 * 0.89
        expected_delta_adj = -30000 * 100 * 523.42 * 0.89
        assert result['delta_adjusted_notional_eur'] == pytest.approx(expected_delta_adj)

    def test_future_delta_none_treated_as_one(self):
        """Test that delta=None for futures is treated as delta=1."""
        result = compute_derivative_exposure(
            quantity=1000,
            delta=None,  # ← None
            underlying_price=100.0,
            contract_multiplier=100,
            fx_rate=1.0,
            contract_type='future'
        )

        # Delta implicitly 1.0
        expected = 1.0 * 1000 * 100 * 100.0 * 1.0
        assert result['delta_adjusted_notional_eur'] == pytest.approx(expected)

    def test_option_gross_notional(self):
        """Test option gross notional: qty=100, csize=100, price=5842.31, fx=0.89"""
        result = compute_derivative_exposure(
            quantity=100,
            delta=-0.28,
            underlying_price=5842.31,
            contract_multiplier=100,
            fx_rate=0.89,
            contract_type='option'
        )

        expected_gross = 100 * 100 * 5842.31 * 0.89
        assert result['gross_notional_eur'] == pytest.approx(expected_gross)

    def test_option_delta_adjusted_notional(self):
        """Test option delta-adjusted: qty=-100, delta=-0.28, csize=100, price=5842.31, fx=0.89"""
        result = compute_derivative_exposure(
            quantity=-100,
            delta=-0.28,
            underlying_price=5842.31,
            contract_multiplier=100,
            fx_rate=0.89,
            contract_type='option'
        )

        # Delta-adjusted: -0.28 * (-100) * 100 * 5842.31 * 0.89
        expected_delta_adj = -0.28 * (-100) * 100 * 5842.31 * 0.89
        assert result['delta_adjusted_notional_eur'] == pytest.approx(expected_delta_adj)

    def test_forward_notional(self):
        """Test forward exposure: qty=10M, csize=1, rate=1.1234, fx=0.89"""
        result = compute_derivative_exposure(
            quantity=10000000,
            delta=None,  # Forwards default to delta=1
            underlying_price=1.1234,
            contract_multiplier=1,
            fx_rate=0.89,
            contract_type='forward'
        )

        expected_gross = 10000000 * 1 * 1.1234 * 0.89
        expected_delta_adj = 1.0 * 10000000 * 1 * 1.1234 * 0.89
        assert result['gross_notional_eur'] == pytest.approx(expected_gross)
        assert result['delta_adjusted_notional_eur'] == pytest.approx(expected_delta_adj)

    def test_exposure_basis_hint_option(self):
        """Test exposure basis hint for option is delta_adjusted_underlying_notional."""
        result = compute_derivative_exposure(
            quantity=100,
            delta=0.5,
            underlying_price=100.0,
            contract_multiplier=100,
            fx_rate=1.0,
            contract_type='option'
        )

        assert result['exposure_basis'] == 'delta_adjusted_underlying_notional'

    def test_exposure_basis_hint_future(self):
        """Test exposure basis hint for future is underlying_notional."""
        result = compute_derivative_exposure(
            quantity=100,
            delta=1.0,
            underlying_price=100.0,
            contract_multiplier=100,
            fx_rate=1.0,
            contract_type='future'
        )

        assert result['exposure_basis'] == 'underlying_notional'

    def test_missing_underlying_price_raises(self):
        """Missing underlying_price should raise ValueError."""
        with pytest.raises(ValueError, match="underlying_price"):
            compute_derivative_exposure(
                quantity=100,
                delta=0.5,
                underlying_price=None,  # ← Missing
                contract_multiplier=100,
                fx_rate=1.0,
                contract_type='option'
            )

    def test_missing_contract_multiplier_raises(self):
        """Missing or invalid contract_multiplier should raise ValueError."""
        with pytest.raises(ValueError, match="contract_multiplier"):
            compute_derivative_exposure(
                quantity=100,
                delta=0.5,
                underlying_price=100.0,
                contract_multiplier=None,  # ← Missing
                fx_rate=1.0,
                contract_type='option'
            )

    def test_zero_contract_multiplier_raises(self):
        """Zero contract_multiplier should raise ValueError."""
        with pytest.raises(ValueError, match="contract_multiplier"):
            compute_derivative_exposure(
                quantity=100,
                delta=0.5,
                underlying_price=100.0,
                contract_multiplier=0,  # ← Invalid
                fx_rate=1.0,
                contract_type='option'
            )

    def test_option_missing_delta_raises(self):
        """Option with delta=None (no default for options) should raise ValueError."""
        with pytest.raises(ValueError, match="delta"):
            compute_derivative_exposure(
                quantity=100,
                delta=None,  # ← Missing for option
                underlying_price=100.0,
                contract_multiplier=100,
                fx_rate=1.0,
                contract_type='option'
            )

    def test_no_fallback_to_market_value(self):
        """Verify no fallback to market_value_eur when underlying_price missing."""
        # If there were a fallback, it would return a value instead of raising
        with pytest.raises(ValueError):
            compute_derivative_exposure(
                quantity=100,
                delta=0.5,
                underlying_price=None,  # Missing
                contract_multiplier=100,
                fx_rate=1.0,
                contract_type='option'
            )

    def test_hedge_flag_does_not_affect_output(self):
        """Hedge flag should not change helper output (caller applies netting)."""
        result_hedge = compute_derivative_exposure(
            quantity=100,
            delta=0.5,
            underlying_price=100.0,
            contract_multiplier=100,
            fx_rate=1.0,
            contract_type='option',
            is_hedge=True  # Hedge flag
        )

        result_no_hedge = compute_derivative_exposure(
            quantity=100,
            delta=0.5,
            underlying_price=100.0,
            contract_multiplier=100,
            fx_rate=1.0,
            contract_type='option',
            is_hedge=False  # Not a hedge
        )

        # Delta-adjusted output should be identical
        assert result_hedge['delta_adjusted_notional_eur'] == \
               result_no_hedge['delta_adjusted_notional_eur']
        # Gross also identical
        assert result_hedge['gross_notional_eur'] == \
               result_no_hedge['gross_notional_eur']


class TestComputeDerivativeExposuresPortfolio:
    """Test portfolio-level exposure computation."""

    def test_portfolio_basic(self):
        """Test portfolio computation with one option."""
        deriv_contracts = load_derivative_contracts()
        bbg = MockBloomberg()

        risk_df = pd.DataFrame({
            'isin': ['OPT_SPX_PUT_001'],
            'quantity': [-100],
            'price': [45.2],
            'market_value_eur': [-4031.8],
            'bloomberg_ticker': ['SPXW 260619P05500 Index'],
            'asset_class': ['Derivative'],
            'sub_asset_class': ['Listed Option'],
            'is_hedge': [False],
            'fx_rate': [0.89],
        })

        result = compute_derivative_exposures_portfolio(
            risk_df, bbg, deriv_contracts
        )

        assert 'by_position' in result
        assert 'gross_total_eur' in result
        assert 'delta_adjusted_total_eur' in result
        assert len(result['by_position']) == 1

    def test_portfolio_multiple_derivatives(self):
        """Test portfolio with multiple derivatives (future, option, forward)."""
        deriv_contracts = load_derivative_contracts()
        bbg = MockBloomberg()

        risk_df = pd.DataFrame({
            'isin': ['FUT_SPY_SHORT_001', 'OPT_SPX_PUT_001', 'FWD_EURUSD_001'],
            'quantity': [-30000, -100, 10000000],
            'price': [523.42, 45.2, 1.1234],
            'market_value_eur': [-1398226560, -4031.8, 10000000],
            'bloomberg_ticker': ['SPY US Equity', 'SPXW 260619P05500 Index', 'EURUSD Curncy'],
            'asset_class': ['Derivative', 'Derivative', 'Derivative'],
            'sub_asset_class': ['Future', 'Listed Option', 'Forward'],
            'is_hedge': [True, False, True],
            'fx_rate': [0.89, 0.89, 0.89],
        })

        result = compute_derivative_exposures_portfolio(
            risk_df, bbg, deriv_contracts
        )

        assert len(result['by_position']) == 3
        assert result['gross_total_eur'] > 0
        assert result['delta_adjusted_total_eur'] is not None
        assert 'future' in result['by_contract_type']
        assert 'option' in result['by_contract_type']
        assert 'forward' in result['by_contract_type']

    def test_portfolio_missing_contract_raises(self):
        """Portfolio with unknown ISIN should raise ValueError."""
        deriv_contracts = load_derivative_contracts()
        bbg = MockBloomberg()

        risk_df = pd.DataFrame({
            'isin': ['UNKNOWN_DERIV_001'],  # Not in deriv_contracts
            'quantity': [100],
            'price': [100.0],
            'market_value_eur': [10000.0],
            'bloomberg_ticker': ['SPY US Equity'],
            'asset_class': ['Derivative'],
            'is_hedge': [False],
            'fx_rate': [1.0],
        })

        with pytest.raises(ValueError, match="not found in derivative_contracts"):
            compute_derivative_exposures_portfolio(
                risk_df, bbg, deriv_contracts
            )

    def test_portfolio_empty_derivatives(self):
        """Portfolio with no derivatives should return empty results."""
        deriv_contracts = load_derivative_contracts()
        bbg = MockBloomberg()

        risk_df = pd.DataFrame({
            'isin': ['SPY US Equity'],
            'quantity': [1000],
            'price': [523.42],
            'market_value_eur': [523420.0],
            'bloomberg_ticker': ['SPY US Equity'],
            'asset_class': ['Equity'],  # ← Not Derivative
            'is_hedge': [False],
            'fx_rate': [0.89],
        })

        result = compute_derivative_exposures_portfolio(
            risk_df, bbg, deriv_contracts
        )

        assert len(result['by_position']) == 0
        assert result['gross_total_eur'] == 0.0
        assert result['delta_adjusted_total_eur'] == 0.0

    def test_portfolio_cache_used(self):
        """Verify cache is used within portfolio computation."""
        deriv_contracts = load_derivative_contracts()
        bbg = MockBloomberg()

        # Portfolio with same derivative twice
        risk_df = pd.DataFrame({
            'isin': ['OPT_SPX_PUT_001', 'OPT_SPX_PUT_001'],
            'quantity': [-100, -50],
            'price': [45.2, 45.2],
            'market_value_eur': [-4031.8, -2015.9],
            'bloomberg_ticker': ['SPXW 260619P05500 Index', 'SPXW 260619P05500 Index'],
            'asset_class': ['Derivative', 'Derivative'],
            'is_hedge': [False, False],
            'fx_rate': [0.89, 0.89],
        })

        result = compute_derivative_exposures_portfolio(
            risk_df, bbg, deriv_contracts
        )

        # Cache should have only one entry for the ticker
        assert 'SPXW 260619P05500 Index' in result['bbg_cache']
        assert len(result['by_position']) == 2

    def test_portfolio_one_row_per_position(self):
        """Portfolio result should have one row per derivative position."""
        deriv_contracts = load_derivative_contracts()
        bbg = MockBloomberg()

        risk_df = pd.DataFrame({
            'isin': ['FUT_SPY_SHORT_001', 'FUT_SPY_SHORT_001', 'OPT_SPX_PUT_001'],
            'quantity': [-10000, -20000, -100],
            'price': [523.42, 523.42, 45.2],
            'market_value_eur': [-465840000, -931680000, -4031.8],
            'bloomberg_ticker': ['SPY US Equity', 'SPY US Equity', 'SPXW 260619P05500 Index'],
            'asset_class': ['Derivative', 'Derivative', 'Derivative'],
            'is_hedge': [True, False, False],
            'fx_rate': [0.89, 0.89, 0.89],
        })

        result = compute_derivative_exposures_portfolio(
            risk_df, bbg, deriv_contracts
        )

        assert len(result['by_position']) == 3
        assert list(result['by_position']['quantity']) == [-10000, -20000, -100]


class TestDerivativeExposureIntegration:
    """Integration tests comparing helper to current inline formulas."""

    def test_hedge_future_matches_current_formula(self):
        """
        Reproduce current AIFM Hedge Fund short hedge future scenario:
        FUT_SPY_SHORT_001: qty=-30000, price=523.42, csize=100, fx=0.89, delta=1.0
        """
        result = compute_derivative_exposure(
            quantity=-30000,
            delta=1.0,
            underlying_price=523.42,
            contract_multiplier=100,
            fx_rate=0.89,
            contract_type='future'
        )

        # Current inline formula (leverage.py line 77):
        # deriv_gross_map[idx] = abs(qty) * csize * undl_px * fx_rate
        current_gross = abs(-30000) * 100 * 523.42 * 0.89
        assert result['gross_notional_eur'] == pytest.approx(current_gross)

        # Current inline formula (leverage.py line 78-79):
        # deriv_commitment_map[idx] = delta * qty * csize * undl_px * fx_rate
        current_delta_adj = 1.0 * (-30000) * 100 * 523.42 * 0.89
        assert result['delta_adjusted_notional_eur'] == pytest.approx(current_delta_adj)

    def test_put_option_matches_current_formula(self):
        """
        Reproduce current OPT_SPX_PUT_001 scenario:
        qty=-100, delta=-0.28, price=5842.31, csize=100, fx=0.89
        """
        result = compute_derivative_exposure(
            quantity=-100,
            delta=-0.28,
            underlying_price=5842.31,
            contract_multiplier=100,
            fx_rate=0.89,
            contract_type='option'
        )

        # Current gross exposure (all notional)
        current_gross = abs(-100) * 100 * 5842.31 * 0.89
        assert result['gross_notional_eur'] == pytest.approx(current_gross)

        # Current delta-adjusted exposure
        current_delta_adj = -0.28 * (-100) * 100 * 5842.31 * 0.89
        assert result['delta_adjusted_notional_eur'] == pytest.approx(current_delta_adj)

    def test_forward_matches_current_formula(self):
        """
        Reproduce current FWD_EURUSD_001 scenario:
        qty=10M, delta=1.0, rate=1.1234, csize=1, fx=0.89
        """
        result = compute_derivative_exposure(
            quantity=10000000,
            delta=1.0,
            underlying_price=1.1234,
            contract_multiplier=1,
            fx_rate=0.89,
            contract_type='forward'
        )

        current_gross = abs(10000000) * 1 * 1.1234 * 0.89
        current_delta_adj = 1.0 * 10000000 * 1 * 1.1234 * 0.89

        assert result['gross_notional_eur'] == pytest.approx(current_gross)
        assert result['delta_adjusted_notional_eur'] == pytest.approx(current_delta_adj)

    def test_active_derivatives_from_aifm_hedge_fund(self):
        """Test all active derivatives in AIFM_HedgeFund using live data."""
        deriv_contracts = load_derivative_contracts()
        bbg = MockBloomberg()

        # Query actual derivatives from database
        engine = get_engine()
        positions = query_positions(
            engine, 'AIFM_HedgeFund', position_date=VALUATION_DATE
        )
        derivatives = positions[positions['asset_class'] == 'Derivative']

        if len(derivatives) == 0:
            pytest.skip("No derivatives in AIFM_HedgeFund for this date")

        # Compute exposures for all
        result = compute_derivative_exposures_portfolio(
            derivatives, bbg, deriv_contracts
        )

        # Verify we got results
        assert len(result['by_position']) == len(derivatives)
        assert result['gross_total_eur'] >= 0
        assert isinstance(result['delta_adjusted_total_eur'], float)

        # Spot-check one position
        first_pos = result['by_position'].iloc[0]
        assert 'gross_notional_eur' in first_pos
        assert 'delta_adjusted_notional_eur' in first_pos
        assert first_pos['contract_type'] in ['future', 'option', 'forward']
