"""
tests/test_esg_utils.py
=======================
Unit tests for esg_utils.py
Run with: python3 -m pytest tests/test_esg_utils.py -v
"""
import pytest
import pandas as pd
import numpy as np
from src.esg_utils import (
    build_esg_df, esg_portfolio_summary,
    ESG_FIELDS, ESG_THRESHOLD
)
from src.mock_bloomberg import MockBloomberg
from src.database import get_engine
from src.enrichment import get_risk_ready_df


ENGINE  = get_engine()
BBG     = MockBloomberg()
DATE    = '2026-05-13'


@pytest.fixture
def hf_esg_df():
    risk_df = get_risk_ready_df(ENGINE, 'AIFM_HedgeFund', DATE)
    return build_esg_df(risk_df, BBG, ENGINE, 'AIFM_HedgeFund', DATE)


@pytest.fixture
def hf_summary(hf_esg_df):
    risk_df = get_risk_ready_df(ENGINE, 'AIFM_HedgeFund', DATE)
    nav     = risk_df['market_value_eur'].sum()
    return esg_portfolio_summary(hf_esg_df, nav)


class TestBuildEsgDf:

    def test_returns_dataframe(self, hf_esg_df):
        assert isinstance(hf_esg_df, pd.DataFrame)

    def test_required_columns(self, hf_esg_df):
        for col in ['instrument_name', 'asset_class', 'market_value_eur',
                    'esg_score', 'controversy_flag', 'esg_exposure_eur']:
            assert col in hf_esg_df.columns

    def test_liquid_equity_has_esg(self, hf_esg_df):
        msft = hf_esg_df[hf_esg_df['instrument_name'] == 'Microsoft Corp'].iloc[0]
        assert msft['esg_score'] == 81

    def test_fx_has_zero_exposure(self, hf_esg_df):
        fx = hf_esg_df[hf_esg_df['asset_class'] == 'FX']
        assert (fx['esg_exposure_eur'] == 0).all()

    def test_cash_has_zero_exposure(self, hf_esg_df):
        cash = hf_esg_df[hf_esg_df['asset_class'] == 'Cash']
        assert (cash['esg_exposure_eur'] == 0).all()

    def test_derivative_uses_delta_adjusted_notional(self, hf_esg_df):
        deriv = hf_esg_df[hf_esg_df['asset_class'] == 'Derivative'].iloc[0]
        # delta 0.28 x 100 contracts x 100 size x 5842.31 x 0.89 ≈ 14.5m
        assert deriv['esg_exposure_eur'] > 10e6

    def test_controversy_flag_jpm(self, hf_esg_df):
        jpm = hf_esg_df[hf_esg_df['instrument_name'] == 'JPMorgan Chase'].iloc[0]
        assert jpm['controversy_flag'] == True

    def test_controversy_flag_msft_false(self, hf_esg_df):
        msft = hf_esg_df[hf_esg_df['instrument_name'] == 'Microsoft Corp'].iloc[0]
        assert msft['controversy_flag'] == False


class TestEsgPortfolioSummary:

    def test_returns_dict(self, hf_summary):
        assert isinstance(hf_summary, dict)

    def test_required_keys(self, hf_summary):
        for key in ['wav_esg', 'wav_env', 'wav_soc', 'wav_gov',
                    'wav_carbon', 'pct_low_esg', 'pct_controversy']:
            assert key in hf_summary

    def test_wav_esg_in_range(self, hf_summary):
        assert 0 <= hf_summary['wav_esg'] <= 100

    def test_pct_low_esg_nonnegative(self, hf_summary):
        assert hf_summary['pct_low_esg'] >= 0

    def test_pct_controversy_nonnegative(self, hf_summary):
        assert hf_summary['pct_controversy'] >= 0

    def test_esg_threshold_constant(self):
        assert ESG_THRESHOLD == 30