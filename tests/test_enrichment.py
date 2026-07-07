"""
tests/test_enrichment.py
========================
Unit tests for enrichment.py
Run with: python3 -m pytest tests/test_enrichment.py -v
"""

import pytest
import pandas as pd
import numpy as np
import os
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import text

from fund_risk_workflow.data.database import create_db, load_fund_metadata, load_positions
from fund_risk_workflow.data.enrichment import (
    enrich_positions,
    enrich_all_funds,
    query_enriched,
    get_risk_ready_df,
    _save_enriched,
)
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg


# ----------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------

ROOT_DIR = Path(__file__).parent.parent
TEST_DB  = str(ROOT_DIR / 'data' / 'test_enrichment.db')

TEST_DATE = '2026-03-31'


@pytest.fixture(scope='module')
def engine():
    """Create test database with real Excel data."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    engine = create_db(TEST_DB)
    load_fund_metadata(engine)

    # use real Excel files if available, else skip
    data_dir = 'data'
    excel_files = [
        f'{data_dir}/fund_positions_AIFM_HedgeFund.xlsx',
        f'{data_dir}/fund_positions_AIFM_RealEstate.xlsx',
        f'{data_dir}/fund_positions_UCITS_Balanced.xlsx',
        f'{data_dir}/fund_positions_AIFM_PrivateDebt.xlsx',
    ]
    missing = [f for f in excel_files if not os.path.exists(f)]
    if missing:
        pytest.skip(f'Excel files not found: {missing}')

    load_positions(engine)
    yield engine

    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture(scope='module')
def bbg():
    return MockBloomberg()


@pytest.fixture(scope='module')
def hedge_fund_enriched(engine, bbg):
    return enrich_positions(
        engine, 'AIFM_HedgeFund', TEST_DATE, bbg)


@pytest.fixture(scope='module')
def real_estate_enriched(engine, bbg):
    return enrich_positions(
        engine, 'AIFM_RealEstate', TEST_DATE, bbg)


@pytest.fixture(scope='module')
def private_debt_enriched(engine, bbg):
    return enrich_positions(
        engine, 'AIFM_PrivateDebt', TEST_DATE, bbg)


@pytest.fixture(scope='module')
def ucits_enriched(engine, bbg):
    return enrich_positions(
        engine, 'UCITS_Balanced', TEST_DATE, bbg)


# ----------------------------------------------------------------
# enrich_positions tests
# ----------------------------------------------------------------

class TestEnrichPositions:

    def test_returns_dataframe(self, hedge_fund_enriched):
        assert isinstance(hedge_fund_enriched, pd.DataFrame)

    def test_correct_number_of_positions(self, hedge_fund_enriched):
        assert len(hedge_fund_enriched) == 16

    def test_enrichment_source_column_exists(self, hedge_fund_enriched):
        assert 'enrichment_source' in hedge_fund_enriched.columns

    def test_bloomberg_positions_have_source_bloomberg(
            self, hedge_fund_enriched):
        bbg_pos = hedge_fund_enriched[
            (hedge_fund_enriched['bloomberg_ticker'].notna()) &
            (~hedge_fund_enriched['bloomberg_ticker'].str.endswith('Curncy', na=False))]
        assert (bbg_pos['enrichment_source'] == 'bloomberg').all()

    def test_cash_has_source_none(self, hedge_fund_enriched):
        cash = hedge_fund_enriched[
            hedge_fund_enriched['asset_class'] == 'Cash']
        assert (cash['enrichment_source'] == 'none').all()

    def test_equity_has_beta(self, hedge_fund_enriched):
        equities = hedge_fund_enriched[
            (hedge_fund_enriched['asset_class'] == 'Equity') &
            (hedge_fund_enriched['quantity'] > 0)
        ]
        assert equities['beta'].notna().any()

    def test_bond_has_duration(self, hedge_fund_enriched):
        bonds = hedge_fund_enriched[
            hedge_fund_enriched['asset_class'] == 'Bond']
        assert bonds['dur_adj_mid'].notna().any()

    def test_bond_has_convexity(self, hedge_fund_enriched):
        bonds = hedge_fund_enriched[
            hedge_fund_enriched['asset_class'] == 'Bond']
        assert bonds['convexity'].notna().any()

    def test_spy_beta_is_one(self, hedge_fund_enriched):
        spy = hedge_fund_enriched[
            hedge_fund_enriched['bloomberg_ticker'] == 'SPY US Equity']
        assert abs(spy['beta'].values[0] - 1.0) < 0.01

    def test_treasury_duration_correct(self, hedge_fund_enriched):
        bond = hedge_fund_enriched[
            hedge_fund_enriched['isin'] == 'US912828YK09']
        assert abs(bond['dur_adj_mid'].values[0] - 2.31) < 0.01

    def test_raw_positions_preserved(self, hedge_fund_enriched):
        assert 'market_value_eur' in hedge_fund_enriched.columns
        assert 'weight_pct'       in hedge_fund_enriched.columns
        assert 'fund_id'          in hedge_fund_enriched.columns


# ----------------------------------------------------------------
# Real estate enrichment tests
# ----------------------------------------------------------------

class TestRealEstateEnrichment:

    def test_direct_properties_have_fund_admin_source(
            self, real_estate_enriched):
        direct = real_estate_enriched[
            real_estate_enriched['is_direct_property'] == True]
        assert (direct['enrichment_source'] == 'fund_admin').all()

    def test_direct_properties_have_ltv(self, real_estate_enriched):
        direct = real_estate_enriched[
            real_estate_enriched['is_direct_property'] == True]
        assert direct['ltv_pct'].notna().all()

    def test_direct_properties_have_rental_yield(
            self, real_estate_enriched):
        direct = real_estate_enriched[
            real_estate_enriched['is_direct_property'] == True]
        assert direct['rental_yield_pct'].notna().all()

    def test_direct_properties_no_beta(self, real_estate_enriched):
        direct = real_estate_enriched[
            real_estate_enriched['is_direct_property'] == True]
        assert direct['beta'].isna().all()

    def test_listed_reits_have_bloomberg_source(
            self, real_estate_enriched):
        reits = real_estate_enriched[
            (real_estate_enriched['asset_class'] == 'Real Estate') &
            (real_estate_enriched['is_direct_property'] == False)
        ]
        assert (reits['enrichment_source'] == 'bloomberg').all()

    def test_listed_reits_have_beta(self, real_estate_enriched):
        reits = real_estate_enriched[
            (real_estate_enriched['asset_class'] == 'Real Estate') &
            (real_estate_enriched['is_direct_property'] == False)
        ]
        assert reits['beta'].notna().any()


# ----------------------------------------------------------------
# positions_enriched table tests
# ----------------------------------------------------------------

class TestEnrichedTable:

    def test_enriched_table_exists(self, engine,
                                    hedge_fund_enriched):
        inspector = sa.inspect(engine)
        assert 'positions_enriched' in inspector.get_table_names()

    def test_enriched_table_has_rows(self, engine,
                                      hedge_fund_enriched):
        with engine.connect() as conn:
            result = pd.read_sql(
                text('SELECT COUNT(*) as n '
                     'FROM positions_enriched'), conn)
        assert result['n'].values[0] > 0

    def test_enriched_index_exists(self, engine,
                                    hedge_fund_enriched):
        inspector   = sa.inspect(engine)
        indexes     = inspector.get_indexes('positions_enriched')
        index_names = [idx['name'] for idx in indexes]
        assert 'ix_enriched_fund_date_isin' in index_names

    def test_raw_positions_unchanged(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(
                text('SELECT COUNT(*) as n FROM positions'),
                conn)
        assert result['n'].values[0] == 88000

    def test_no_duplicate_enriched_rows(self, engine,
                                         hedge_fund_enriched):
        with engine.connect() as conn:
            result = pd.read_sql(text(
                'SELECT fund_id, position_date, isin, '
                'COUNT(*) as n '
                'FROM positions_enriched '
                'GROUP BY fund_id, position_date, isin '
                'HAVING n > 1'
            ), conn)
        assert len(result) == 0


# ----------------------------------------------------------------
# query_enriched tests
# ----------------------------------------------------------------

class TestQueryEnriched:

    def test_returns_dataframe(self, engine, hedge_fund_enriched):
        result = query_enriched(
            engine, 'AIFM_HedgeFund', TEST_DATE)
        assert isinstance(result, pd.DataFrame)

    def test_has_enrichment_columns(self, engine,
                                     hedge_fund_enriched):
        result = query_enriched(
            engine, 'AIFM_HedgeFund', TEST_DATE)
        assert 'dur_adj_mid'  in result.columns
        assert 'beta'         in result.columns
        assert 'enrichment_source' in result.columns

    def test_join_preserves_all_positions(self, engine,
                                           hedge_fund_enriched):
        result = query_enriched(
            engine, 'AIFM_HedgeFund', TEST_DATE)
        assert len(result) == 16


# ----------------------------------------------------------------
# get_risk_ready_df tests
# ----------------------------------------------------------------

class TestGetRiskReadyDf:

    def test_returns_dataframe(self, engine, hedge_fund_enriched):
        result = get_risk_ready_df(
            engine, 'AIFM_HedgeFund', TEST_DATE)
        assert isinstance(result, pd.DataFrame)

    def test_has_stress_testing_columns(self, engine,
                                         hedge_fund_enriched):
        result = get_risk_ready_df(
            engine, 'AIFM_HedgeFund', TEST_DATE)
        assert 'beta'        in result.columns
        assert 'dur_adj_mid' in result.columns
        assert 'convexity'   in result.columns
        assert 'z_sprd_mid'  in result.columns

    def test_has_liquidity_columns(self, engine,
                                    hedge_fund_enriched):
        result = get_risk_ready_df(
            engine, 'AIFM_HedgeFund', TEST_DATE)
        assert 'adv_eur'            in result.columns
        assert 'is_direct_property' in result.columns

    def test_has_real_estate_columns(self, engine,
                                      real_estate_enriched):
        result = get_risk_ready_df(
            engine, 'AIFM_RealEstate', TEST_DATE)
        assert 'ltv_pct'          in result.columns
        assert 'rental_yield_pct' in result.columns
        assert 'vacancy_rate_pct' in result.columns

    def test_has_audit_trail(self, engine, hedge_fund_enriched):
        result = get_risk_ready_df(
            engine, 'AIFM_HedgeFund', TEST_DATE)
        assert 'enrichment_source' in result.columns

    def test_ordered_by_absolute_market_value(
            self, engine, hedge_fund_enriched):
        result = get_risk_ready_df(
            engine, 'AIFM_HedgeFund', TEST_DATE)
        abs_vals = result['market_value_eur'].abs().values
        assert all(abs_vals[i] >= abs_vals[i+1]
                   for i in range(len(abs_vals)-1))