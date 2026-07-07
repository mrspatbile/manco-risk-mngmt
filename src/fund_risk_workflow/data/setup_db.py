"""
setup_db.py
===========
Idempotent database setup script. Safe to run at any time.

Logic
-----
1. db does not exist          → create schema, load positions, enrich
2. positions empty            → load positions, enrich
3. positions_enriched missing → enrich only
4. everything exists          → print status, exit

Usage
-----
    python3 -m fund_risk_workflow.data.setup_db           # idempotent
    python3 -m fund_risk_workflow.data.setup_db --force   # full rebuild from scratch
"""

import sys
import os
import argparse
import json
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / 'src'))

import sqlalchemy as sa
from fund_risk_workflow.data.database import create_db, load_fund_metadata, load_positions, get_engine
from fund_risk_workflow.data.enrichment import enrich_positions
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg as Bloomberg
from fund_risk_workflow.config import VALUATION_DATE
from sqlalchemy import text

# Load fund IDs dynamically from fund_registry.json
_REF_DIR = ROOT_DIR / 'reference_data'
with open(_REF_DIR / 'platform' / 'fund_registry.json') as _f:
    _REGISTRY = json.load(_f)
FUNDS    = _REGISTRY['funds']

DATE     = VALUATION_DATE
DATA_DIR = str(ROOT_DIR / 'data')
DB_PATH  = str(ROOT_DIR / 'data' / 'risk_management.db')


def table_exists(engine: sa.Engine, table: str) -> bool:
    return sa.inspect(engine).has_table(table)


def positions_loaded(engine: sa.Engine) -> bool:
    if not table_exists(engine, 'positions'):
        return False
    with engine.connect() as conn:
        n = conn.execute(sa.text('SELECT COUNT(*) FROM positions')).scalar()
    return n > 0


def enriched_exists(engine: sa.Engine) -> bool:
    return table_exists(engine, 'positions_enriched')


def run(force: bool = False) -> None:

    if force and os.path.exists(DB_PATH):
        print('--force: removing existing database...')
        os.remove(DB_PATH)

    # step 0: regenerate position Excel files with real prices
    if force:
        print('Regenerating position Excel files with real prices...')
        from fund_risk_workflow.data.generate_positions import (
            generate_hedge_fund, generate_private_debt,
            generate_real_estate, generate_ucits_balanced,
        )
        from fund_risk_workflow.data.paths import position_file
        from fund_risk_workflow.config import VALUATION_DATE
        import pandas as pd
        fund_generators = {
            'AIFM_HedgeFund'  : generate_hedge_fund,
            'AIFM_PrivateDebt': generate_private_debt,
            'AIFM_RealEstate' : generate_real_estate,
            'UCITS_Balanced'  : generate_ucits_balanced,
        }
        for fund_name, generator in fund_generators.items():
            print(f'  {fund_name}...')
            df = generator()
            filepath = position_file(DATA_DIR, fund_name, VALUATION_DATE)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            df.to_excel(filepath, index=False)
        print('Excel files regenerated.')

    # step 1: create schema if db missing
    if not os.path.exists(DB_PATH):
        print('Creating database schema...')
        create_db()
    else:
        print('Database exists.')

    engine = get_engine()

    # step 1b: load fund metadata (idempotent)
    load_fund_metadata(engine)

    # step 2: load positions if empty
    if not positions_loaded(engine):
        print('Loading positions from Excel files...')
        load_positions(engine, DATA_DIR)
    else:
        with engine.connect() as conn:
            n = conn.execute(
                sa.text('SELECT COUNT(*) FROM positions')).scalar()
        print(f'Positions already loaded ({n:,} rows). Skipping.')

    # step 3: enrich if positions_enriched missing
    if not enriched_exists(engine):
        print('Enriching positions...')
        bbg = Bloomberg()
        for fund_id in FUNDS:
            print(f'  {fund_id}...')
            enrich_positions(engine, fund_id, DATE, bbg)
        print('Enrichment complete.')
    else:
        print('positions_enriched exists. Skipping enrichment.')


    # step 4: conditionally generate PE fund if present in funds table
    with engine.connect() as conn:
        pe_fund_exists = conn.execute(
            text('SELECT COUNT(*) FROM funds WHERE fund_id = :fid'),
            {'fid': 'AIFM_PE_Buyout'}
        ).scalar()

    if pe_fund_exists > 0:
        with engine.connect() as conn:
            n_pe = conn.execute(text('SELECT COUNT(*) FROM pe_funds')).scalar()
        if n_pe == 0:
            print('Generating PE fund data...')
            from fund_risk_workflow.data.generate_pe_fund import generate_pe_fund
            generate_pe_fund(engine)
        else:
            print('PE fund data exists. Skipping.')
    else:
        print('AIFM_PE_Buyout not found in funds table. Skipping PE generation.')

    # step 5: conditionally generate infrastructure fund if present in funds table
    with engine.connect() as conn:
        infra_fund_exists = conn.execute(
            text('SELECT COUNT(*) FROM funds WHERE fund_id = :fid'),
            {'fid': 'AIFM_Infra_Core'}
        ).scalar()

    if infra_fund_exists > 0:
        with engine.connect() as conn:
            n_infra = conn.execute(text('SELECT COUNT(*) FROM infra_funds')).scalar()
        if n_infra == 0:
            print('Generating infrastructure fund data...')
            from fund_risk_workflow.data.generate_infra_fund import generate_infra_fund
            generate_infra_fund(engine)
        else:
            print('Infrastructure fund data exists. Skipping.')
    else:
        print('AIFM_Infra_Core not found in funds table. Skipping Infra generation.')

    print('\nDatabase ready.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Setup risk database.')
    parser.add_argument('--force', action='store_true',
                        help='Rebuild database from scratch.')
    args = parser.parse_args()
    run(force=args.force)