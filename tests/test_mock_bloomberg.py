"""
tests/test_mock_bloomberg.py
============================
Unit tests for MockBloomberg client.
Run with: python3 -m pytest tests/test_mock_bloomberg.py -v
"""

import pytest
import numpy as np
import pandas as pd
from mock_bloomberg import MockBloomberg


@pytest.fixture
def bbg():
    return MockBloomberg()


# ----------------------------------------------------------------
# BDP tests
# ----------------------------------------------------------------

class TestBdp:

    def test_single_security_single_field(self, bbg):
        result = bbg.bdp('SPY US Equity', 'PX_LAST')
        assert result.loc['SPY US Equity', 'PX_LAST'] == 523.42

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
        assert abs(result['PX_LAST'].iloc[-1] - 523.42) < 0.01

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