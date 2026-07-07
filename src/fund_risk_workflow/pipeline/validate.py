"""
validate_pipeline.py
====================
End-to-end validation of the risk management infrastructure.
Verifies that all components work correctly together before
domain risk notebooks begin.

Usage
-----
    python3 -m fund_risk_workflow.pipeline.validate

Output
------
    Validation report showing pass/fail for each check
    across all four funds.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / 'src'))

from fund_risk_workflow.data.mock_bloomberg import MockBloomberg
from fund_risk_workflow.data.database import (
    create_db, load_fund_metadata, load_positions,
    load_instruments, get_engine, query_positions,
    query_nav_history, query_asset_class_breakdown,
)
from fund_risk_workflow.data.enrichment import enrich_positions, get_risk_ready_df
from fund_risk_workflow.risk.risk_utils import (
    var_historical, var_parametric, var_scale,
    es_historical, es_parametric,
    kupiec_test, christoffersen_test,
    stress_equity, stress_rates, stress_combined,
    stress_historical, stress_property,
    days_to_liquidate, liquidity_buckets,
    redemption_stress,
)
from fund_risk_workflow.config import VALUATION_DATE

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
FUNDS     = [
    'AIFM_HedgeFund',
    'AIFM_PrivateDebt',
    'AIFM_RealEstate',
    'UCITS_Balanced',
]
TEST_DATE = VALUATION_DATE
PASS      = '✓ PASS'
FAIL      = '✗ FAIL'

results   = {}


def check(name: str, condition: bool, detail: str = '') -> bool:
    """Record a check result and print it."""
    status = PASS if condition else FAIL
    detail_str = f' ({detail})' if detail else ''
    print(f'  {status} {name}{detail_str}')
    return condition


# ================================================================
# Section 1: Mock Bloomberg
# ================================================================
print('\n' + '='*60)
print('1. MOCK BLOOMBERG')
print('='*60)

bbg     = MockBloomberg()
checks  = []

# BDP
ref = bbg.bdp('SPY US Equity', ['PX_LAST', 'BETA', 'CRNCY'])
checks.append(check(
    'bdp returns correct price for SPY',
    abs(ref.loc['SPY US Equity', 'PX_LAST'] - 742.31) < 0.01
))
checks.append(check(
    'bdp returns correct beta for SPY',
    ref.loc['SPY US Equity', 'BETA'] == 1.0
))

# BDH
hist = bbg.bdh('SPY US Equity', 'PX_LAST', '20240101', '20260513')
checks.append(check(
    'bdh returns at least 250 days of history',
    len(hist) >= 250
))
checks.append(check(
    'bdh last price matches bdp',
    abs(hist['PX_LAST'].iloc[-1] - 742.31) < 0.01
))

# BDS
cfs = bbg.bds('US912828YK09 Govt', 'CASH_FLOW')
checks.append(check(
    'bds returns bond cash flows',
    len(cfs) > 0 and 'cash_flow_amount' in cfs.columns
))

# Portfolio enrichment
positions_test = pd.DataFrame({
    'bloomberg_ticker': ['SPY US Equity', 'US912828YK09 Govt', None],
    'instrument_name' : ['SPY', 'T Bond', 'Direct Property'],
    'market_value_eur': [1e6, 500e3, 5e6],
})
enriched_test = bbg.get_portfolio_data(positions_test)
checks.append(check(
    'get_portfolio_data skips None tickers',
    pd.isna(enriched_test.iloc[2]['PX_LAST'])
))

results['Mock Bloomberg'] = all(checks)


# ================================================================
# Section 2: Database
# ================================================================
print('\n' + '='*60)
print('2. DATABASE')
print('='*60)

engine = get_engine()
checks = []

# tables exist
import sqlalchemy as sa
inspector  = sa.inspect(engine)
tables     = inspector.get_table_names()
checks.append(check(
    'positions table exists',
    'positions' in tables
))
checks.append(check(
    'funds table exists',
    'funds' in tables
))
checks.append(check(
    'instruments table exists',
    'instruments' in tables
))

# row counts
with engine.connect() as conn:
    n_rows = pd.read_sql(
        sa.text('SELECT COUNT(*) as n FROM positions'), conn
    )['n'].values[0]
checks.append(check(
    'positions table has expected rows',
    n_rows >= 10000,
    f'{n_rows:,} rows'
))

# all four funds present
with engine.connect() as conn:
    fund_ids = pd.read_sql(
        sa.text('SELECT DISTINCT fund_id FROM positions'), conn
    )['fund_id'].tolist()
for fund in FUNDS:
    checks.append(check(
        f'{fund} present in database',
        fund in fund_ids
    ))

# 250 days per fund
with engine.connect() as conn:
    dates_per_fund = pd.read_sql(sa.text(
        'SELECT fund_id, COUNT(DISTINCT date) as n_dates '
        'FROM positions GROUP BY fund_id'
    ), conn)
for _, row in dates_per_fund.iterrows():
    checks.append(check(
        f'{row["fund_id"]}: at least 250 days',
        row['n_dates'] >= 250,
        f'{row["n_dates"]} days'
    ))

# indexes
indexes     = inspector.get_indexes('positions')
index_names = [idx['name'] for idx in indexes]
checks.append(check(
    'composite index on (fund_id, date, isin)',
    'ix_positions_fund_date_isin' in index_names
))
checks.append(check(
    'composite index on (fund_id, date)',
    'ix_positions_fund_date' in index_names
))

results['Database'] = all(checks)


# ================================================================
# Section 3: Enrichment
# ================================================================
print('\n' + '='*60)
print('3. ENRICHMENT')
print('='*60)

checks = []

for fund_id in FUNDS:
    enriched = enrich_positions(engine, fund_id, TEST_DATE, bbg)
    risk_df  = get_risk_ready_df(engine, fund_id, TEST_DATE)

    checks.append(check(
        f'{fund_id}: enrichment returns DataFrame',
        isinstance(enriched, pd.DataFrame)
    ))
    checks.append(check(
        f'{fund_id}: enrichment_source column present',
        'enrichment_source' in enriched.columns
    ))
    checks.append(check(
        f'{fund_id}: risk-ready DataFrame has sensitivity columns',
        all(c in risk_df.columns for c in
            ['beta', 'dur_adj_mid', 'convexity', 'adv_eur'])
    ))

# real estate specific
re_df = get_risk_ready_df(engine, 'AIFM_RealEstate', TEST_DATE)
direct = re_df[re_df['is_direct_property'] == True]
checks.append(check(
    'Real estate: direct properties have fund_admin source',
    (direct['enrichment_source'] == 'fund_admin').all()
))
checks.append(check(
    'Real estate: direct properties have ltv_pct',
    direct['ltv_pct'].notna().all()
))
checks.append(check(
    'Real estate: direct properties have no Bloomberg ticker',
    direct['bloomberg_ticker'].isna().all() if 'bloomberg_ticker'
    in direct.columns else True
))

# positions_enriched table created
tables = sa.inspect(engine).get_table_names()
checks.append(check(
    'positions_enriched table created',
    'positions_enriched' in tables
))

# raw positions unchanged
with engine.connect() as conn:
    n_after = pd.read_sql(
        sa.text('SELECT COUNT(*) as n FROM positions'), conn
    )['n'].values[0]
checks.append(check(
    'raw positions table unchanged after enrichment',
    n_after == n_rows
))

results['Enrichment'] = all(checks)


# ================================================================
# Section 4: VaR and ES
# ================================================================
print('\n' + '='*60)
print('4. VAR AND ES')
print('='*60)

checks = []
np.random.seed(42)
test_returns = np.random.normal(0.0005, 0.012, 250)

# VaR
var99 = var_historical(test_returns, confidence=0.99)
var95 = var_historical(test_returns, confidence=0.95)
checks.append(check('var_historical returns positive', var99 > 0))
checks.append(check('var99 > var95', var99 > var95))

var_p = var_parametric(mu=0, sigma=0.012, confidence=0.99, dist='t')
checks.append(check('var_parametric returns positive', var_p > 0))

var_10d = var_scale(var99, horizon=10)
checks.append(check(
    'var_scale correct',
    abs(var_10d - var99 * np.sqrt(10)) < 1e-10
))

# ES
es99 = es_historical(test_returns, confidence=0.99)
checks.append(check('es_historical >= var_historical', es99 >= var99))

es_p = es_parametric(sigma=0.012, confidence=0.99, dist='t')
var_p_comp = var_parametric(mu=0, sigma=0.012, confidence=0.99, dist='t')
checks.append(check('es_parametric >= var_parametric', es_p >= var_p_comp))

# NAV history and P&L for backtesting
nav_hf = query_nav_history(engine, 'AIFM_HedgeFund')
pnl    = nav_hf['pnl_pct'].dropna().values
checks.append(check(
    'NAV history available for hedge fund',
    len(nav_hf) >= 250
))
checks.append(check(
    'P&L derived correctly from NAV',
    not np.isnan(pnl).all()
))

results['VaR and ES'] = all(checks)


# ================================================================
# Section 5: Stress Scenarios
# ================================================================
print('\n' + '='*60)
print('5. STRESS SCENARIOS')
print('='*60)

checks  = []
hf_df   = get_risk_ready_df(engine, 'AIFM_HedgeFund', TEST_DATE)
re_df   = get_risk_ready_df(engine, 'AIFM_RealEstate', TEST_DATE)

# equity stress
eq_res = stress_equity(hf_df, delta_equity=-0.30)
checks.append(check(
    'equity stress returns negative P&L for crash',
    eq_res['stressed_pnl_eur'] < 0
))

# rate stress
rate_res = stress_rates(hf_df, delta_y=0.02)
checks.append(check(
    'rate stress returns negative P&L for rate rise',
    rate_res['stressed_pnl_eur'] < 0
))

# combined stress
comb_res = stress_combined(hf_df)
checks.append(check(
    'combined stress total equals sum of components',
    abs(comb_res['stressed_pnl_eur'] - (
        comb_res['equity_pnl'] + comb_res['rates_pnl'] +
        comb_res['credit_pnl'] + comb_res['fx_pnl']
    )) < 1.0
))

# historical scenarios
for scenario in ['2008', '2020', '2022']:
    res = stress_historical(hf_df, scenario)
    checks.append(check(
        f'historical scenario {scenario} runs correctly',
        isinstance(res['stressed_pnl_eur'], float)
    ))

checks.append(check(
    '2008 scenario worse than 2020',
    stress_historical(hf_df, '2008')['stressed_pnl_eur'], 
    stress_historical(hf_df, '2020')['stressed_pnl_eur'],
))

# real estate stress
prop_res = stress_property(re_df)
checks.append(check(
    'property stress returns negative P&L',
    prop_res['stressed_pnl_eur'] < 0
))

# run all scenarios on all four funds
for fund_id in FUNDS:
    df = get_risk_ready_df(engine, fund_id, TEST_DATE)
    try:
        stress_combined(df)
        stress_historical(df, '2020')
        checks.append(check(
            f'{fund_id}: stress scenarios run without errors',
            True
        ))
    except Exception as e:
        checks.append(check(
            f'{fund_id}: stress scenarios run without errors',
            False, str(e)
        ))

results['Stress Scenarios'] = all(checks)


# ================================================================
# Section 6: Liquidity
# ================================================================
print('\n' + '='*60)
print('6. LIQUIDITY')
print('='*60)

checks = []

for fund_id in FUNDS:
    df  = get_risk_ready_df(engine, fund_id, TEST_DATE)
    nav = df['market_value_eur'].sum()

    # days to liquidate
    df  = days_to_liquidate(df)
    checks.append(check(
        f'{fund_id}: days_to_liquidate column added',
        'days_to_liquidate' in df.columns
    ))

    # liquidity buckets
    df  = liquidity_buckets(df)
    checks.append(check(
        f'{fund_id}: liquidity_bucket column added',
        'liquidity_bucket' in df.columns
    ))

    # real estate: direct properties in > 1 year bucket
    if fund_id == 'AIFM_RealEstate':
        direct = df[df['is_direct_property'] == True]
        checks.append(check(
            'Real estate: direct properties in > 1 year bucket',
            (direct['liquidity_bucket'] == '> 1 year').all()
        ))

    # redemption stress
    red = redemption_stress(df, nav, redemption_pct=0.10)
    checks.append(check(
        f'{fund_id}: redemption stress runs correctly',
        'coverage_ratio' in red and red['coverage_ratio'] >= 0
    ))

results['Liquidity'] = all(checks)


# ================================================================
# Section 7: Infrastructure Fund Tables
# ================================================================
print('\n' + '='*60)
print('7. INFRASTRUCTURE FUND')
print('='*60)

checks = []
infra_tables = [
    'infra_funds', 'infra_assets', 'infra_fund_investments',
    'infra_cash_flows', 'infra_nav_history', 'infra_valuation_report',
    'infra_debt', 'infra_covenants',
]
tables = sa.inspect(engine).get_table_names()

for tbl in infra_tables:
    checks.append(check(f'{tbl} table exists', tbl in tables))

with engine.connect() as conn:
    n_funds = conn.execute(
        sa.text('SELECT COUNT(*) FROM infra_funds')).scalar()
    n_assets = conn.execute(
        sa.text('SELECT COUNT(*) FROM infra_assets')).scalar()
    n_vr = conn.execute(
        sa.text('SELECT COUNT(*) FROM infra_valuation_report')).scalar()
    n_cov = conn.execute(
        sa.text('SELECT COUNT(*) FROM infra_covenants')).scalar()
    n_breaches = conn.execute(
        sa.text("SELECT COUNT(*) FROM infra_covenants "
                "WHERE dscr_breach = 1 OR ltv_breach = 1")).scalar()
    n_waivers = conn.execute(
        sa.text("SELECT COUNT(*) FROM infra_covenants "
                "WHERE waiver_granted = 1")).scalar()

checks.append(check('infra fund loaded', n_funds >= 1, f'{n_funds} fund'))
checks.append(check('8 assets loaded', n_assets == 8, f'{n_assets} assets'))
checks.append(check(
    'valuation reports present',
    n_vr >= 100,
    f'{n_vr} reports'
))
checks.append(check(
    'covenant readings present',
    n_cov >= 100,
    f'{n_cov} readings'
))
checks.append(check(
    'at least 2 covenant breaches recorded',
    n_breaches >= 2,
    f'{n_breaches} breaches'
))
checks.append(check(
    'at least 2 waivers granted',
    n_waivers >= 2,
    f'{n_waivers} waivers'
))

results['Infrastructure Fund'] = all(checks)


# ================================================================
# Final report
# ================================================================
print('\n' + '='*60)
print('VALIDATION REPORT')
print('='*60)

all_passed = True
for section, passed in results.items():
    status    = PASS if passed else FAIL
    all_passed = all_passed and passed
    print(f'  {status} {section}')

print()
if all_passed:
    print('All checks passed. Infrastructure is ready.')
    print('AIFM and UCITS domain notebooks can begin.')
else:
    print('Some checks failed. Review output above before proceeding.')

sys.exit(0 if all_passed else 1)