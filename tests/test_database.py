"""
tests/test_database.py
======================
Unit tests for database.py
Run with: python3 -m pytest tests/test_database.py -v
"""

import pytest
import pandas as pd
import numpy as np
import os
from pathlib import Path
import sqlalchemy as sa
from fund_risk_workflow.data.database import (
    create_db,
    load_fund_metadata,
    load_positions,
    load_instruments,
    # create_indexes,
    query_positions,
    query_nav_history,
    query_asset_class_breakdown,
    query_largest_positions,
)
from fund_risk_workflow.data.generate_positions import (
    generate_hedge_fund,
    generate_private_debt,
    generate_real_estate,
    generate_ucits_balanced,
)
from fund_risk_workflow.data.paths import position_file
from fund_risk_workflow.config import VALUATION_DATE

# ----------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------


ROOT_DIR = Path(__file__).parent.parent  # tests/ -> project root
TEST_DB  = str(ROOT_DIR / 'data' / 'test_risk_management.db')

@pytest.fixture(scope='module')
def engine():
    """Create a test database loaded with all fund data."""

    # always start fresh
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    # Generate position files if they don't exist
    DATA_DIR = str(ROOT_DIR / 'data')
    position_files = [
        position_file(DATA_DIR, fund, VALUATION_DATE)
        for fund in ['AIFM_HedgeFund', 'AIFM_PrivateDebt', 'AIFM_RealEstate', 'UCITS_Balanced']
    ]
    if not all(Path(pf).exists() for pf in position_files):
        # Ensure directory exists
        Path(position_files[0]).parent.mkdir(parents=True, exist_ok=True)
        # Generate all position files
        generate_hedge_fund().to_excel(position_files[0], index=False)
        generate_private_debt().to_excel(position_files[1], index=False)
        generate_real_estate().to_excel(position_files[2], index=False)
        generate_ucits_balanced().to_excel(position_files[3], index=False)

    engine = create_db(TEST_DB)
    load_fund_metadata(engine)
    load_positions(engine)
    # create_indexes(engine)
    load_instruments(engine)
    yield engine
    # cleanup
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)





# ----------------------------------------------------------------
# Database creation tests
# ----------------------------------------------------------------

class TestDatabaseCreation:

    def test_db_file_created(self, engine):
        assert os.path.exists(TEST_DB)

    def test_tables_exist(self, engine):
        inspector = sa.inspect(engine)
        tables    = inspector.get_table_names()
        assert 'positions'   in tables
        assert 'funds'       in tables
        assert 'instruments' in tables

    def test_funds_table_has_six_funds(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(
                sa.text('SELECT COUNT(*) as n FROM funds'), conn)
        assert result['n'].values[0] == 6

    def test_instruments_table_not_empty(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(
                sa.text('SELECT COUNT(*) as n FROM instruments'), conn)
        assert result['n'].values[0] > 0


# ----------------------------------------------------------------
# Fund metadata tests
# ----------------------------------------------------------------

class TestFundMetadata:

    def test_all_four_funds_loaded(self, engine):
        with engine.connect() as conn:
            funds = pd.read_sql(
                sa.text('SELECT fund_id FROM funds'), conn)
        fund_ids = set(funds['fund_id'].values)
        assert 'AIFM_HedgeFund'   in fund_ids
        assert 'AIFM_PrivateDebt' in fund_ids
        assert 'AIFM_RealEstate'  in fund_ids
        assert 'UCITS_Balanced'   in fund_ids

    def test_fund_types_correct(self, engine):
        with engine.connect() as conn:
            funds = pd.read_sql(
                sa.text('SELECT fund_id, fund_type FROM funds'), conn)
        funds = funds.set_index('fund_id')
        assert funds.loc['AIFM_HedgeFund',   'fund_type'] == 'AIFM'
        assert funds.loc['AIFM_PrivateDebt',  'fund_type'] == 'AIFM'
        assert funds.loc['AIFM_RealEstate',   'fund_type'] == 'AIFM'
        assert funds.loc['UCITS_Balanced',    'fund_type'] == 'UCITS'

    def test_all_funds_luxembourg_domicile(self, engine):
        with engine.connect() as conn:
            funds = pd.read_sql(
                sa.text('SELECT domicile FROM funds'), conn)
        assert (funds['domicile'] == 'Luxembourg').all()

    def test_all_funds_cssf_regulator(self, engine):
        with engine.connect() as conn:
            funds = pd.read_sql(
                sa.text('SELECT regulator FROM funds'), conn)
        assert (funds['regulator'] == 'CSSF').all()


# ----------------------------------------------------------------
# Positions table tests
# ----------------------------------------------------------------

class TestPositionsTable:

    def test_total_row_count(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(
                sa.text('SELECT COUNT(*) as n FROM positions'), conn)
        assert result['n'].values[0] == 88000

    def test_each_fund_has_250_dates(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(sa.text(
                'SELECT fund_id, COUNT(DISTINCT position_date) as dates '
                'FROM positions GROUP BY fund_id'
            ), conn)
        assert (result['dates'] >= 250).all()

    def test_no_null_fund_ids(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(sa.text(
                'SELECT COUNT(*) as n FROM positions '
                'WHERE fund_id IS NULL'
            ), conn)
        assert result['n'].values[0] == 0

    def test_no_null_dates(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(sa.text(
                'SELECT COUNT(*) as n FROM positions '
                'WHERE position_date IS NULL'
            ), conn)
        assert result['n'].values[0] == 0

    def test_no_null_isins(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(sa.text(
                'SELECT COUNT(*) as n FROM positions '
                'WHERE isin IS NULL'
            ), conn)
        assert result['n'].values[0] == 0

    def test_hedge_fund_has_short_positions(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(sa.text(
                'SELECT COUNT(*) as n FROM positions '
                'WHERE fund_id = "AIFM_HedgeFund" '
                'AND market_value_eur < 0'
            ), conn)
        assert result['n'].values[0] > 0

    def test_ucits_all_long_only(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(sa.text(
                'SELECT COUNT(*) as n FROM positions '
                'WHERE fund_id = "UCITS_Balanced" '
                'AND market_value_eur < 0'
            ), conn)
        assert result['n'].values[0] == 0

    def test_real_estate_has_direct_properties(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(sa.text(
                'SELECT COUNT(*) as n FROM positions '
                'WHERE fund_id = "AIFM_RealEstate" '
                'AND is_direct_property = 1'
            ), conn)
        assert result['n'].values[0] > 0

    def test_direct_properties_no_bloomberg_ticker(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(sa.text(
                'SELECT COUNT(*) as n FROM positions '
                'WHERE is_direct_property = 1 '
                'AND bloomberg_ticker IS NOT NULL'
            ), conn)
        assert result['n'].values[0] == 0

    def test_direct_properties_zero_adv(self, engine):
        with engine.connect() as conn:
            result = pd.read_sql(sa.text(
                'SELECT COUNT(*) as n FROM positions '
                'WHERE is_direct_property = 1 '
                'AND adv_eur > 0'
            ), conn)
        assert result['n'].values[0] == 0


# ----------------------------------------------------------------
# Query function tests
# ----------------------------------------------------------------

class TestQueryPositions:

    def test_returns_dataframe(self, engine):
        result = query_positions(
            engine, 'AIFM_HedgeFund', '2026-03-31')
        assert isinstance(result, pd.DataFrame)

    def test_correct_fund_returned(self, engine):
        result = query_positions(
            engine, 'AIFM_HedgeFund', '2026-03-31')
        assert (result['fund_id'] == 'AIFM_HedgeFund').all()

    def test_correct_date_returned(self, engine):
        result = query_positions(
            engine, 'AIFM_HedgeFund', '2026-03-31')
        assert (result['date'] == '2026-03-31').all()

    def test_no_date_returns_all_dates(self, engine):
        result = query_positions(engine, 'AIFM_HedgeFund')
        assert result['date'].nunique() >= 250

    def test_unknown_fund_returns_empty(self, engine):
        result = query_positions(
            engine, 'UNKNOWN_FUND', '2026-03-31')
        assert len(result) == 0


class TestQueryNavHistory:

    def test_returns_dataframe(self, engine):
        result = query_nav_history(engine, 'AIFM_HedgeFund')
        assert isinstance(result, pd.DataFrame)

    def test_has_correct_columns(self, engine):
        result = query_nav_history(engine, 'AIFM_HedgeFund')
        assert 'nav_eur'  in result.columns
        assert 'pnl_eur'  in result.columns
        assert 'pnl_pct'  in result.columns

    def test_nav_always_positive(self, engine):
        result = query_nav_history(engine, 'AIFM_HedgeFund')
        assert (result['nav_eur'] > 0).all()

    def test_250_days_of_history(self, engine):
        result = query_nav_history(engine, 'AIFM_HedgeFund')
        assert len(result) >= 250

    def test_pnl_is_diff_of_nav(self, engine):
        result       = query_nav_history(engine, 'UCITS_Balanced')
        computed_pnl = result['nav_eur'].diff().dropna()
        actual_pnl   = result['pnl_eur'].dropna()
        pd.testing.assert_series_equal(
            computed_pnl.reset_index(drop=True),
            actual_pnl.reset_index(drop=True),
            check_names=False
        )


class TestQueryAssetClassBreakdown:

    def test_returns_dataframe(self, engine):
        result = query_asset_class_breakdown(
            engine, 'UCITS_Balanced', '2026-03-31')
        assert isinstance(result, pd.DataFrame)

    def test_has_correct_columns(self, engine):
        result = query_asset_class_breakdown(
            engine, 'UCITS_Balanced', '2026-03-31')
        assert 'asset_class'       in result.columns
        assert 'market_value_eur'  in result.columns
        assert 'weight_pct'        in result.columns

    def test_weights_sum_to_100(self, engine):
        result = query_asset_class_breakdown(
            engine, 'UCITS_Balanced', '2026-03-31')
        assert abs(result['weight_pct'].sum() - 100.0) < 1.0

    def test_hedge_fund_breakdown_includes_derivatives(self, engine):
        result = query_asset_class_breakdown(
            engine, 'AIFM_HedgeFund', '2026-03-31')
        # After Phase B, derivatives are classified as asset_class='Derivative'
        # and should appear in the breakdown with non-zero weight
        assert 'Derivative' in result['asset_class'].values
        deriv_row = result[result['asset_class'] == 'Derivative']
        assert len(deriv_row) == 1
        assert abs(deriv_row.iloc[0]['weight_pct']) > 0


class TestQueryLargestPositions:

    def test_returns_correct_number(self, engine):
        result = query_largest_positions(
            engine, 'AIFM_HedgeFund', '2026-03-31', n=5)
        assert len(result) == 5

    def test_ordered_by_absolute_value(self, engine):
        result = query_largest_positions(
            engine, 'AIFM_HedgeFund', '2026-03-31', n=10)
        abs_vals = result['market_value_eur'].abs().values
        assert all(abs_vals[i] >= abs_vals[i+1]
                   for i in range(len(abs_vals)-1))

    def test_returns_dataframe(self, engine):
        result = query_largest_positions(
            engine, 'UCITS_Balanced', '2026-03-31')
        assert isinstance(result, pd.DataFrame)


class TestIndexes:

    def test_fund_date_isin_index_exists(self, engine):
        inspector   = sa.inspect(engine)
        indexes     = inspector.get_indexes('positions')
        index_names = [idx['name'] for idx in indexes]
        assert 'ix_positions_fund_date_isin' in index_names

    def test_fund_date_index_exists(self, engine):
        inspector   = sa.inspect(engine)
        indexes     = inspector.get_indexes('positions')
        index_names = [idx['name'] for idx in indexes]
        assert 'ix_positions_fund_date' in index_names

    def test_index_covers_correct_columns(self, engine):
        inspector = sa.inspect(engine)
        indexes   = inspector.get_indexes('positions')
        ix = next(idx for idx in indexes
                  if idx['name'] == 'ix_positions_fund_date_isin')
        assert 'fund_id' in ix['column_names']
        assert 'position_date' in ix['column_names']
        assert 'isin'    in ix['column_names']


class TestPETables:

    def test_pe_funds_table_exists(self, engine):
        assert sa.inspect(engine).has_table('pe_funds')

    def test_pe_portfolio_companies_table_exists(self, engine):
        assert sa.inspect(engine).has_table('pe_portfolio_companies')

    def test_pe_fund_investments_table_exists(self, engine):
        assert sa.inspect(engine).has_table('pe_fund_investments')

    def test_pe_cash_flows_table_exists(self, engine):
        assert sa.inspect(engine).has_table('pe_cash_flows')

    def test_pe_nav_history_table_exists(self, engine):
        assert sa.inspect(engine).has_table('pe_nav_history')

    def test_pe_fund_investments_unique_constraint(self, engine):
        indexes = sa.inspect(engine).get_unique_constraints('pe_fund_investments')
        names   = [idx['name'] for idx in indexes]
        assert 'uq_fund_company' in names
    @pytest.mark.skip(reason="PE data requires generate_pe_fund - integration test only")
    def test_pe_fund_investment_unique_per_fund_company(self, engine):
        with engine.connect() as conn:
            result = conn.execute(sa.text(
                'SELECT COUNT(*) FROM pe_fund_investments'
            )).scalar()
        assert result == 8

    def test_pe_fund_investment_has_exit_ev_ebitda(self, engine):
        cols = [c['name'] for c in sa.inspect(engine).get_columns('pe_fund_investments')]
        assert 'exit_ev_ebitda' in cols

    def test_pe_valuation_report_table_exists(self, engine):
        assert sa.inspect(engine).has_table('pe_valuation_report')

    def test_pe_valuation_report_has_covenant_fields(self, engine):
        cols = [c['name'] for c in sa.inspect(engine).get_columns('pe_valuation_report')]
        for col in ['covenant_type', 'leverage_covenant', 'leverage_ratio',
                    'coverage_covenant', 'coverage_ratio', 'arr_eur']:
            assert col in cols

    def test_pe_valuation_report_has_data(self, engine):
        # valuation report table exists and has correct structure
        # data population tested via integration tests (test_setup_db.py)
        cols = [c['name'] for c in sa.inspect(engine).get_columns('pe_valuation_report')]
        assert 'key_risks' in cols
        assert 'arr_eur' in cols
        assert 'covenant_type' in cols