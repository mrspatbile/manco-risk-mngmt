"""
tests/test_esg_utils.py
=======================
Unit tests for esg_utils.py
Run with: python3 -m pytest tests/test_esg_utils.py -v
"""
import pytest
import pandas as pd
from fund_risk_workflow.risk.esg_utils import (
    build_esg_df, esg_portfolio_summary, build_private_esg_df,
    ESG_THRESHOLD_LOW, ESG_THRESHOLD_HIGH
)
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg
from fund_risk_workflow.data.database import get_engine
from fund_risk_workflow.data.enrichment import get_risk_ready_df


ENGINE  = get_engine()
BBG     = MockBloomberg()
DATE    = '2026-03-31'
QUARTER = '2026-03-31'   # last quarter-end before VALUATION_DATE



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
        # After Phase D: equity derivatives use delta-adjusted notional, FX derivatives have zero
        derivs = hf_esg_df[hf_esg_df['asset_class'] == 'Derivative']
        # Find an equity derivative (non-zero exposure)
        equity_derivs = derivs[derivs['esg_exposure_eur'] > 0]
        assert len(equity_derivs) > 0, "Should have equity derivatives with positive ESG exposure"

        deriv = equity_derivs.iloc[0]
        # delta_adjusted_notional for equity derivatives should be > 0
        assert deriv['esg_exposure_eur'] > 0

        # Verify FX derivatives have zero exposure
        fx_derivs = derivs[derivs['isin'].isin(['FWD_EURUSD_001', 'FWD_GBPUSD_001'])]
        assert (fx_derivs['esg_exposure_eur'] == 0).all(), "FX derivatives should have zero ESG exposure"

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
        assert ESG_THRESHOLD_LOW == 40
        assert ESG_THRESHOLD_HIGH == 70


class TestBuildPrivateEsgDf:

    _LISTED_COLS = {
        'instrument_name', 'asset_class', 'market_value_eur',
        'esg_score', 'env_score', 'soc_score', 'gov_score',
        'controversy_flag', 'carbon_intensity', 'esg_exposure_eur',
    }

    def test_pe_returns_dataframe(self):
        df = build_private_esg_df('AIFM_PE_Buyout', QUARTER, 'pe', ENGINE)
        assert isinstance(df, pd.DataFrame)

    def test_pe_columns_include_listed_cols(self):
        df = build_private_esg_df('AIFM_PE_Buyout', QUARTER, 'pe', ENGINE)
        for col in self._LISTED_COLS:
            assert col in df.columns, f"Missing column: {col}"

    def test_pe_extra_columns_present(self):
        df = build_private_esg_df('AIFM_PE_Buyout', QUARTER, 'pe', ENGINE)
        assert 'esg_reporter' in df.columns
        assert 'esg_report_date' in df.columns

    def test_pe_esg_reporter_not_null(self):
        df = build_private_esg_df('AIFM_PE_Buyout', QUARTER, 'pe', ENGINE)
        assert df['esg_reporter'].notna().all()

    def test_pe_asset_class(self):
        df = build_private_esg_df('AIFM_PE_Buyout', QUARTER, 'pe', ENGINE)
        assert (df['asset_class'] == 'Private Equity').all()

    def test_pe_exposure_nonnegative(self):
        df = build_private_esg_df('AIFM_PE_Buyout', QUARTER, 'pe', ENGINE)
        assert (df['esg_exposure_eur'] >= 0).all()

    def test_pe_portfolio_summary_works(self):
        df  = build_private_esg_df('AIFM_PE_Buyout', QUARTER, 'pe', ENGINE)
        nav = df['esg_exposure_eur'].sum()
        summary = esg_portfolio_summary(df, nav)
        assert isinstance(summary, dict)
        assert 'wav_esg' in summary
        assert 0 <= summary['wav_esg'] <= 100

    def test_infra_columns_include_listed_cols(self):
        df = build_private_esg_df('AIFM_Infra_Core', QUARTER, 'infra', ENGINE)
        for col in self._LISTED_COLS:
            assert col in df.columns, f"Missing column: {col}"

    def test_infra_extra_columns_present(self):
        df = build_private_esg_df('AIFM_Infra_Core', QUARTER, 'infra', ENGINE)
        assert 'esg_reporter' in df.columns
        assert 'esg_report_date' in df.columns

    def test_infra_esg_reporter_not_null(self):
        df = build_private_esg_df('AIFM_Infra_Core', QUARTER, 'infra', ENGINE)
        assert df['esg_reporter'].notna().all()

    def test_infra_asset_class(self):
        df = build_private_esg_df('AIFM_Infra_Core', QUARTER, 'infra', ENGINE)
        assert (df['asset_class'] == 'Infrastructure').all()

    def test_invalid_asset_type_raises(self):
        with pytest.raises(ValueError, match="asset_type"):
            build_private_esg_df('AIFM_PE_Buyout', QUARTER, 'listed', ENGINE)
