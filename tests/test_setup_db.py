"""
tests/test_setup_db.py
======================
Integration tests for setup_db.py.
These tests rebuild the main database and are skipped in normal test runs.

To run manually, temporarily comment out @pytest.mark.skip on TestSetupDb:
    python3 -m pytest tests/test_setup_db.py -v
"""


import os
import pytest
import sqlalchemy as sa
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent

import sys
sys.path.insert(0, str(ROOT_DIR))

from fund_risk_workflow.data.setup_db import run, table_exists, positions_loaded, enriched_exists
from fund_risk_workflow.data.database import get_engine


@pytest.mark.skip(reason="integration test - run manually with: pytest tests/test_setup_db.py -v")
class TestSetupDb:

    def test_tables_created(self):
        run(force=True)
        engine = get_engine()
        assert table_exists(engine, 'positions')
        assert table_exists(engine, 'positions_enriched')
        assert table_exists(engine, 'funds')

    def test_positions_loaded(self):
        run(force=True)
        engine = get_engine()
        assert positions_loaded(engine)

    def test_enriched_exists(self):
        run(force=True)
        engine = get_engine()
        assert enriched_exists(engine)

    def test_idempotent(self):
        run(force=True)
        engine = get_engine()
        with engine.connect() as conn:
            n1 = conn.execute(
                sa.text('SELECT COUNT(*) FROM positions')).scalar()
        run()
        with engine.connect() as conn:
            n2 = conn.execute(
                sa.text('SELECT COUNT(*) FROM positions')).scalar()
        assert n1 == n2

    def test_row_count(self):
        run(force=True)
        engine = get_engine()
        with engine.connect() as conn:
            n = conn.execute(
                sa.text('SELECT COUNT(*) FROM positions')).scalar()
        assert n == 88000

    def test_four_funds_present(self):
        run(force=True)
        engine = get_engine()
        with engine.connect() as conn:
            funds = conn.execute(
                sa.text('SELECT DISTINCT fund_id FROM positions')
            ).fetchall()
        fund_ids = [f[0] for f in funds]
        for fund in ['AIFM_HedgeFund', 'AIFM_PrivateDebt',
                     'AIFM_RealEstate', 'UCITS_Balanced']:
            assert fund in fund_ids


    def test_pe_fund_data_exists(self):
        run(force=True)
        engine = get_engine()
        with engine.connect() as conn:
            n_funds     = conn.execute(sa.text('SELECT COUNT(*) FROM pe_funds')).scalar()
            n_companies = conn.execute(sa.text('SELECT COUNT(*) FROM pe_portfolio_companies')).scalar()
            n_cashflows = conn.execute(sa.text('SELECT COUNT(*) FROM pe_cash_flows')).scalar()
            n_nav       = conn.execute(sa.text('SELECT COUNT(*) FROM pe_nav_history')).scalar()
        assert n_funds == 1
        assert n_companies == 8
        assert n_cashflows == 24
        assert n_nav > 0

    def test_pe_fund_data_exists(self):
        run(force=True)
        engine = get_engine()
        with engine.connect() as conn:
            n_funds     = conn.execute(sa.text('SELECT COUNT(*) FROM pe_funds')).scalar()
            n_companies = conn.execute(sa.text('SELECT COUNT(*) FROM pe_portfolio_companies')).scalar()
            n_cashflows = conn.execute(sa.text('SELECT COUNT(*) FROM pe_cash_flows')).scalar()
            n_nav       = conn.execute(sa.text('SELECT COUNT(*) FROM pe_nav_history')).scalar()
        assert n_funds == 1
        assert n_companies == 8
        assert n_cashflows == 24
        assert n_nav > 0

    def test_re_run_does_not_duplicate_pe_data(self):
        run(force=True)
        engine = get_engine()
        with engine.connect() as conn:
            n_before = conn.execute(sa.text('SELECT COUNT(*) FROM pe_cash_flows')).scalar()
        run()
        with engine.connect() as conn:
            n_after = conn.execute(sa.text('SELECT COUNT(*) FROM pe_cash_flows')).scalar()
        assert n_before == n_after

    def test_force_rebuilds_cleanly(self):
        run(force=True)
        engine = get_engine()
        with engine.connect() as conn:
            n = conn.execute(sa.text('SELECT COUNT(*) FROM positions')).scalar()
        assert n == 88000