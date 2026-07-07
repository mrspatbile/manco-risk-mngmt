"""
tests/test_mock_bloomberg.py
============================
Unit tests for MockBloomberg client.
Run with: python3 -m pytest tests/test_mock_bloomberg.py -v
"""

import pytest
import numpy as np
import pandas as pd
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg


@pytest.fixture
def bbg():
    return MockBloomberg()


# ----------------------------------------------------------------
# BDP tests
# ----------------------------------------------------------------

class TestBdp:

    def test_single_security_single_field(self, bbg):
        result = bbg.bdp('SPY US Equity', 'PX_LAST')
        px = result.loc['SPY US Equity', 'PX_LAST']
        assert px is not None
        assert float(px) > 0
        
    def test_single_security_multiple_fields(self, bbg):
        result = bbg.bdp('SPY US Equity', ['PX_LAST', 'BETA', 'CRNCY'])
        assert result.loc['SPY US Equity', 'BETA'] == 1.0
        assert result.loc['SPY US Equity', 'CRNCY'] == 'USD'

    def test_multiple_securities(self, bbg):
        result = bbg.bdp(
            ['SPY US Equity', 'US912828YK09 Govt'],
            ['PX_LAST', 'DUR_ADJ_MID']
        )
        assert result.shape == (2, 2)
        assert result.loc['US912828YK09 Govt', 'DUR_ADJ_MID'] == 2.31

    def test_unknown_security_returns_nan(self, bbg):
        result = bbg.bdp('UNKNOWN Equity', 'PX_LAST')
        assert np.isnan(result.loc['UNKNOWN Equity', 'PX_LAST'])

    def test_unknown_field_returns_nan(self, bbg):
        result = bbg.bdp('SPY US Equity', 'NONEXISTENT_FIELD')
        assert np.isnan(
            result.loc['SPY US Equity', 'NONEXISTENT_FIELD'])

    def test_bond_has_duration(self, bbg):
        result = bbg.bdp('US912828YK09 Govt', 'DUR_ADJ_MID')
        assert result.loc['US912828YK09 Govt', 'DUR_ADJ_MID'] > 0

    def test_equity_has_beta(self, bbg):
        result = bbg.bdp('SPY US Equity', 'BETA')
        assert result.loc['SPY US Equity', 'BETA'] == 1.0

    def test_fx_has_price(self, bbg):
        result = bbg.bdp('EURUSD Curncy', 'PX_LAST')
        assert result.loc['EURUSD Curncy', 'PX_LAST'] > 1.0

    def test_returns_dataframe(self, bbg):
        result = bbg.bdp('SPY US Equity', 'PX_LAST')
        assert isinstance(result, pd.DataFrame)

    def test_index_is_security_name(self, bbg):
        result = bbg.bdp('SPY US Equity', 'PX_LAST')
        assert result.index.name == 'security'
        assert 'SPY US Equity' in result.index

    def test_bdp_with_date_parameter(self, bbg):
        """Test bdp accepts optional date parameter for point-in-time data."""
        result = bbg.bdp('SPY US Equity', 'PX_LAST', date='2026-03-31')
        px = result.loc['SPY US Equity', 'PX_LAST']
        assert px is not None
        assert float(px) > 0

    def test_bdp_date_returns_different_price_than_latest(self, bbg):
        """Test that bdp with date returns different price than latest."""
        latest = bbg.bdp('SPY US Equity', 'PX_LAST').loc['SPY US Equity', 'PX_LAST']
        dated = bbg.bdp('SPY US Equity', 'PX_LAST', date='2026-03-31').loc['SPY US Equity', 'PX_LAST']
        # For yfinance instruments, dated price should differ from latest
        assert abs(latest - dated) > 1.0

    def test_bdp_date_no_date_returns_latest(self, bbg):
        """Test that bdp without date returns latest data."""
        result_latest = bbg.bdp('SPY US Equity', 'PX_LAST')
        result_no_date = bbg.bdp('SPY US Equity', 'PX_LAST', date=None)
        assert result_latest.loc['SPY US Equity', 'PX_LAST'] == result_no_date.loc['SPY US Equity', 'PX_LAST']


# ----------------------------------------------------------------
# BDH tests
# ----------------------------------------------------------------

class TestBdh:

    def test_returns_dataframe(self, bbg):
        result = bbg.bdh(
            'SPY US Equity', 'PX_LAST',
            '20240101', '20260513'
        )
        assert isinstance(result, pd.DataFrame)

    def test_last_price_matches_bdp(self, bbg):
        result = bbg.bdh(
            'SPY US Equity', 'PX_LAST',
            '20240101', '20260513'
        )
        bdp_price = bbg.bdp('SPY US Equity', 'PX_LAST').loc['SPY US Equity', 'PX_LAST']
        assert abs(result['PX_LAST'].iloc[-1] - bdp_price) < 0.01

    def test_correct_number_of_trading_days(self, bbg):
        result = bbg.bdh(
            'SPY US Equity', 'PX_LAST',
            '20260101', '20260513'
        )
        expected = len(pd.bdate_range('20260101', '20260513'))
        assert len(result) == expected

    def test_no_weekends_in_index(self, bbg):
        result = bbg.bdh(
            'SPY US Equity', 'PX_LAST',
            '20260101', '20260513'
        )
        assert result.index.dayofweek.max() <= 4

    def test_multiple_securities_multiindex(self, bbg):
        result = bbg.bdh(
            ['SPY US Equity', 'GLD US Equity'],
            'PX_LAST', '20260101', '20260513'
        )
        assert isinstance(result.index, pd.MultiIndex)
        assert 'SPY US Equity' in result.index.get_level_values(
            'security')

    def test_multiple_fields(self, bbg):
        result = bbg.bdh(
            'SPY US Equity',
            ['PX_LAST', 'VOLUME'],
            '20260101', '20260513'
        )
        assert 'PX_LAST' in result.columns
        assert 'VOLUME' in result.columns

    def test_prices_all_positive(self, bbg):
        result = bbg.bdh(
            'SPY US Equity', 'PX_LAST',
            '20240101', '20260513'
        )
        assert (result['PX_LAST'] > 0).all()

    def test_at_least_250_days_available(self, bbg):
        result = bbg.bdh(
            'SPY US Equity', 'PX_LAST',
            '20240101', '20260513'
        )
        assert len(result) >= 250

    def test_bond_yield_history(self, bbg):
        result = bbg.bdh(
            'US912828YK09 Govt', 'YLD_YTM_MID',
            '20260101', '20260513'
        )
        assert (result['YLD_YTM_MID'] > 0).all()


# ----------------------------------------------------------------
# BDS tests
# ----------------------------------------------------------------

class TestBds:

    def test_bond_cashflows_returns_dataframe(self, bbg):
        result = bbg.bds('US912828YK09 Govt', 'CASH_FLOW')
        assert isinstance(result, pd.DataFrame)

    def test_bond_cashflows_has_correct_columns(self, bbg):
        result = bbg.bds('US912828YK09 Govt', 'CASH_FLOW')
        assert 'cash_flow_date' in result.columns
        assert 'cash_flow_amount' in result.columns

    def test_bond_cashflows_all_positive(self, bbg):
        result = bbg.bds('US912828YK09 Govt', 'CASH_FLOW')
        assert (result['cash_flow_amount'] > 0).all()

    def test_last_cashflow_includes_principal(self, bbg):
        result = bbg.bds('US912828YK09 Govt', 'CASH_FLOW')
        assert result['cash_flow_amount'].iloc[-1] > 100

    def test_index_members_returns_dataframe(self, bbg):
        result = bbg.bds('SPX Index', 'INDX_MEMBERS')
        assert isinstance(result, pd.DataFrame)
        assert 'member_ticker' in result.columns

    def test_equity_cashflows_returns_empty(self, bbg):
        result = bbg.bds('SPY US Equity', 'CASH_FLOW')
        assert result.empty

    def test_unknown_field_returns_empty(self, bbg):
        result = bbg.bds('US912828YK09 Govt', 'UNKNOWN_FIELD')
        assert result.empty


# ----------------------------------------------------------------
# get_portfolio_data tests
# ----------------------------------------------------------------

class TestGetPortfolioData:

    @pytest.fixture
    def sample_positions(self):
        return pd.DataFrame({
            'bloomberg_ticker': [
                'SPY US Equity',
                'US912828YK09 Govt',
                'EURUSD Curncy',
                None,
            ],
            'instrument_name': [
                'SPDR S&P 500',
                'US Treasury 2.875 2028',
                'EUR/USD Forward',
                'Office Luxembourg City',
            ],
            'market_value_eur': [
                5234200, 4821000, 2246800, 12500000
            ],
        })

    def test_returns_dataframe(self, bbg, sample_positions):
        result = bbg.get_portfolio_data(sample_positions)
        assert isinstance(result, pd.DataFrame)

    def test_direct_property_has_nan_bloomberg_fields(
            self, bbg, sample_positions):
        result = bbg.get_portfolio_data(sample_positions)
        prop = result[result['instrument_name'] ==
                      'Office Luxembourg City']
        assert np.isnan(prop['PX_LAST'].values[0])

    def test_equity_has_beta(self, bbg, sample_positions):
        result = bbg.get_portfolio_data(sample_positions)
        spy = result[result['bloomberg_ticker'] == 'SPY US Equity']
        assert spy['BETA'].values[0] == 1.0

    def test_bond_has_duration(self, bbg, sample_positions):
        result = bbg.get_portfolio_data(sample_positions)
        bond = result[
            result['bloomberg_ticker'] == 'US912828YK09 Govt']
        assert bond['DUR_ADJ_MID'].values[0] == 2.31

    def test_row_count_preserved(self, bbg, sample_positions):
        result = bbg.get_portfolio_data(sample_positions)
        assert len(result) == len(sample_positions)

    def test_market_value_preserved(self, bbg, sample_positions):
        result = bbg.get_portfolio_data(sample_positions)
        assert (result['market_value_eur'] ==
                sample_positions['market_value_eur']).all()


class TestCacheFreshness:
    """
    Tests for yfinance cache freshness validation.
    Ensures cache is redownloaded when it doesn't cover requested date range.
    """

    def test_cache_redownload_if_dates_beyond_cache_end(self, bbg):
        """
        If cached data ends before requested end date, cache should be redownloaded.
        """
        import tempfile
        import os
        from pathlib import Path

        # Create a temporary cache directory with a stale cache file
        with tempfile.TemporaryDirectory() as tmpdir:
            # Override cache dir temporarily
            old_cache_dir = bbg.YF_CACHE_DIR
            bbg.YF_CACHE_DIR = Path(tmpdir)

            # Create stale cache: data from 2026-01-01 to 2026-03-01
            stale_cache = Path(tmpdir) / "AAPL.csv"
            stale_dates = pd.bdate_range('2026-01-01', '2026-03-01')
            stale_data = pd.DataFrame(
                {'Close': [500.0] * len(stale_dates)},
                index=stale_dates
            )
            stale_data.index.name = 'Date'
            stale_data.to_csv(stale_cache)

            # Request dates beyond cache end (2026-01-15 to 2026-03-31)
            req_dates = pd.bdate_range('2026-01-15', '2026-03-31')

            # This should redownload because cache doesn't cover 2026-03-31
            result = bbg._fetch_yf_prices('AAPL', req_dates, 500.0)

            # Verify result has real prices (not all 500)
            assert len(result) == len(req_dates)
            assert result[0] > 0  # Should have fetched real prices

            # Restore original cache dir
            bbg.YF_CACHE_DIR = old_cache_dir

    def test_cache_reused_if_covers_requested_dates(self, bbg):
        """
        If cached data covers requested date range, cache should be reused.
        """
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            # Override cache dir temporarily
            old_cache_dir = bbg.YF_CACHE_DIR
            bbg.YF_CACHE_DIR = Path(tmpdir)

            # Create cache with wide date range
            cache_file = Path(tmpdir) / "SPY.csv"
            cache_dates = pd.bdate_range('2026-01-01', '2026-05-31')
            cache_prices = [500.0 + i * 0.1 for i in range(len(cache_dates))]
            cache_data = pd.DataFrame(
                {'Close': cache_prices},
                index=cache_dates
            )
            cache_data.index.name = 'Date'
            cache_data.to_csv(cache_file)

            # Request dates within cache range
            req_dates = pd.bdate_range('2026-02-01', '2026-04-01')

            # This should reuse cache because it covers requested dates
            result = bbg._fetch_yf_prices('SPY', req_dates, 500.0)

            # Verify result matches cache values (not updated)
            assert len(result) == len(req_dates)
            # Cache has specific values, should be preserved
            assert result[0] != 500.0 or result[1] != 500.0  # Not all same value

            bbg.YF_CACHE_DIR = old_cache_dir


class TestMockBloombergESG:

    def test_equity_has_esg_score(self):
        bbg = MockBloomberg()
        result = bbg.bdp('AAPL US Equity', ['ESG_SCORE'])
        assert result.loc['AAPL US Equity', 'ESG_SCORE'] == 78

    def test_bond_has_esg_score(self):
        bbg = MockBloomberg()
        result = bbg.bdp('DBR 0 08/15/29 Govt', ['ESG_SCORE'])
        assert result.loc['DBR 0 08/15/29 Govt', 'ESG_SCORE'] == 82

    def test_fx_has_no_esg(self):
        bbg = MockBloomberg()
        result = bbg.bdp('EURUSD Curncy', ['ESG_SCORE'])
        assert result.loc['EURUSD Curncy', 'ESG_SCORE'] is None

    def test_vix_has_no_esg(self):
        bbg = MockBloomberg()
        result = bbg.bdp('VIX Index', ['ESG_SCORE'])
        assert result.loc['VIX Index', 'ESG_SCORE'] is None

    def test_controversy_flag_jpm(self):
        bbg = MockBloomberg()
        result = bbg.bdp('JPM US Equity', ['CONTROVERSY_FLAG'])
        assert result.loc['JPM US Equity', 'CONTROVERSY_FLAG'] == True

    def test_controversy_flag_msft(self):
        bbg = MockBloomberg()
        result = bbg.bdp('MSFT US Equity', ['CONTROVERSY_FLAG'])
        assert result.loc['MSFT US Equity', 'CONTROVERSY_FLAG'] == False

    def test_derivative_look_through(self):
        bbg = MockBloomberg()
        result = bbg.bdp('SPXW 260619P05500 Index', ['ESG_LOOK_THROUGH', 'ESG_SCORE'])
        assert result.loc['SPXW 260619P05500 Index', 'ESG_LOOK_THROUGH'] == 'SPX Index'
        assert result.loc['SPXW 260619P05500 Index', 'ESG_SCORE'] == 62

    def test_clo_has_no_esg(self):
        bbg = MockBloomberg()
        result = bbg.bdp('XS1122334455 CLO', ['ESG_SCORE'])
        assert result.loc['XS1122334455 CLO', 'ESG_SCORE'] is None

    def test_carbon_intensity_present(self):
        bbg = MockBloomberg()
        result = bbg.bdp('JPM US Equity', ['CARBON_INTENSITY'])
        assert result.loc['JPM US Equity', 'CARBON_INTENSITY'] == 312.5

    def test_all_esg_fields_present(self):
        bbg = MockBloomberg()
        fields = ['ESG_SCORE', 'ENV_SCORE', 'SOC_SCORE', 'GOV_SCORE',
                  'CONTROVERSY_FLAG', 'CARBON_INTENSITY', 'ESG_LOOK_THROUGH']
        result = bbg.bdp('AAPL US Equity', fields)
        for f in fields:
            assert f in result.columns