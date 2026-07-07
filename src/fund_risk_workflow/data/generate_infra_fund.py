"""
generate_infra_fund.py
======================
Generates synthetic infrastructure fund data for AIFM_Infra_Core.

Simulates a 15-year EUR 1.2bn core/core-plus infrastructure fund,
vintage 2019, with 8 assets across regulated utilities, transport
concessions, renewable energy, social infrastructure, and one
core-plus development asset.

Valuation methodology: yield capitalisation (EV = EBITDA / discount_rate)
for all assets. This is the standard approach for regulated and contracted
infrastructure where long-duration, predictable cash flows are discounted
at a risk-adjusted WACC. Appraiser inputs are simulated; in production these
are consumed from an external administrator or independent appraiser. Risk
management layer is independent per AIFMD governance requirements.

Populates:
    infra_funds
    infra_assets
    infra_fund_investments
    infra_cash_flows
    infra_nav_history
    infra_valuation_report
    infra_debt
    infra_covenants

Usage
-----
    python3 -m fund_risk_workflow.data.generate_infra_fund
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parent.parent.parent.parent  # src/fund_risk_workflow/data/ -> project root
_REF_DIR = ROOT_DIR / 'reference_data'
sys.path.insert(0, str(ROOT_DIR / "src"))

from fund_risk_workflow.data.database import (
    get_engine,
    InfraFund, InfraAsset, InfraFundInvestment,
    InfraCashFlow, InfraNavHistory, InfraValuationReport,
    InfraDebt, InfraCovenant,
)
from fund_risk_workflow.config import VALUATION_DATE
from sqlalchemy.orm import Session

np.random.seed(42)

# ----------------------------------------------------------------
# Fund configuration
# ----------------------------------------------------------------
# Note: FUND_ID, FUND_NAME, VINTAGE, TARGET_SIZE are set by generate_infra_fund()
# at function call time from fund_profile.json. They are not defined at module
# import time to ensure they come from a single source of truth.
# These are module-level variables that get populated by generate_infra_fund().
FUND_ID = None
FUND_NAME = None
TARGET_SIZE = None
VINTAGE = None

# Infrastructure-specific fund configuration (not in fund_profile.json)
FUND_LIFE = 15
COMMITTED   = 1_200_000_000
DRAWN       = 1_020_000_000       # 85% of committed

MGMT_FEE_RATE = 0.0100            # 1.0% of committed p.a.

# ----------------------------------------------------------------
# Asset master: load from reference_data
# ----------------------------------------------------------------
with open(_REF_DIR / 'portfolios' / 'infra_assets.json') as _f:
    _data = json.load(_f)
    # Handle schema_version wrapper
    INFRA_ASSETS = _data.get('assets') if isinstance(_data, dict) and 'schema_version' in _data else _data

# Re-open to avoid duplicate load (legacy pattern)
with open(_REF_DIR / 'portfolios' / 'infra_assets.json') as _f:
    _data2 = json.load(_f)
    # Handle schema_version wrapper
    ASSETS = _data2.get('assets') if isinstance(_data2, dict) and 'schema_version' in _data2 else _data2

ASSET_IDS = [a['asset_id'] for a in ASSETS]

# ----------------------------------------------------------------
# Asset profiles — model calibration (DCF/yield cap inputs).
# This is NOT master data; it is the appraiser's financial model.
# Stays in Python, not in reference_data.
# ----------------------------------------------------------------
ASSET_PROFILES = {
    'INFRA_001': {
        # AquaNet Rhein — regulated water, Germany
        'appraiser'          : 'KPMG Luxembourg',
        'valuation_basis'    : 'Yield capitalisation (RAB)',
        'discount_rate'      : 0.060,
        'inflation_assumption': 0.020,
        'cost_basis_eur'     : 120_000_000,
        'revenue_start'      : 58_000_000,
        'revenue_cagr'       : 0.025,       # CPI-linked
        'ebitda_margin_start': 0.42,
        'ebitda_margin_end'  : 0.44,
        'net_debt_start'     : 215_000_000,
        'debt_repayment_pa'  : 7_500_000,
        'interest_rate'      : 0.028,
        'dscr_covenant'      : 1.15,
        'ltv_covenant'       : 0.72,
        'key_risks'          : 'Regulatory reset risk, capex overrun, climate-related asset damage',
    },
    'INFRA_002': {
        # Réseau Électrique Nord — regulated electricity distribution, France
        'appraiser'          : 'Duff & Phelps',
        'valuation_basis'    : 'Yield capitalisation (RAB)',
        'discount_rate'      : 0.063,
        'inflation_assumption': 0.020,
        'cost_basis_eur'     : 145_000_000,
        'revenue_start'      : 72_000_000,
        'revenue_cagr'       : 0.022,
        'ebitda_margin_start': 0.40,
        'ebitda_margin_end'  : 0.43,
        'net_debt_start'     : 265_000_000,
        'debt_repayment_pa'  : 9_000_000,
        'interest_rate'      : 0.030,
        'dscr_covenant'      : 1.15,
        'ltv_covenant'       : 0.73,
        'key_risks'          : 'CRE tariff reset, grid investment obligations, renewables integration costs',
    },
    'INFRA_003': {
        # Autopista Norte — toll road concession, Spain
        # DSCR breach Q2 2020 (COVID traffic collapse), waiver Q3 2020
        'appraiser'          : 'Lincoln International',
        'valuation_basis'    : 'DCF / yield capitalisation',
        'discount_rate'      : 0.075,
        'inflation_assumption': 0.020,
        'cost_basis_eur'     : 130_000_000,
        'revenue_start'      : 62_000_000,
        'revenue_cagr'       : 0.030,
        'ebitda_margin_start': 0.55,
        'ebitda_margin_end'  : 0.58,
        'net_debt_start'     : 240_000_000,
        'debt_repayment_pa'  : 8_000_000,
        'interest_rate'      : 0.032,
        'dscr_covenant'      : 1.18,
        'ltv_covenant'       : 0.72,
        'key_risks'          : 'Traffic volume risk, ramp-up underperformance, political interference with tariffs',
        # COVID traffic shock: Q2 2020 revenue drops 42%
        'covid_shock_quarter': '2020-06-30',
        'covid_revenue_drop' : 0.60,
    },
    'INFRA_004': {
        # Aeroporto Adriatico — airport concession, Italy
        'appraiser'          : 'KPMG Luxembourg',
        'valuation_basis'    : 'DCF / yield capitalisation',
        'discount_rate'      : 0.078,
        'inflation_assumption': 0.020,
        'cost_basis_eur'     : 160_000_000,
        'revenue_start'      : 85_000_000,
        'revenue_cagr'       : 0.028,
        'ebitda_margin_start': 0.38,
        'ebitda_margin_end'  : 0.42,
        'net_debt_start'     : 295_000_000,
        'debt_repayment_pa'  : 10_000_000,
        'interest_rate'      : 0.033,
        'dscr_covenant'      : 1.20,
        'ltv_covenant'       : 0.78,
        'key_risks'          : 'Passenger volume risk, aeronautical tariff regulation, COVID-19 recovery tail risk',
    },
    'INFRA_005': {
        # Zephyr Wind — offshore wind with CPI-linked offtake, Netherlands
        'appraiser'          : 'Duff & Phelps',
        'valuation_basis'    : 'Yield capitalisation (contracted offtake)',
        'discount_rate'      : 0.062,
        'inflation_assumption': 0.020,
        'cost_basis_eur'     : 95_000_000,
        'revenue_start'      : 42_000_000,
        'revenue_cagr'       : 0.025,
        'ebitda_margin_start': 0.68,
        'ebitda_margin_end'  : 0.70,
        'net_debt_start'     : 165_000_000,
        'debt_repayment_pa'  : 6_000_000,
        'interest_rate'      : 0.026,
        'dscr_covenant'      : 1.12,
        'ltv_covenant'       : 0.70,
        'key_risks'          : 'Wind resource variability, offshore maintenance costs, merchant tail risk post-offtake',
    },
    'INFRA_006': {
        # Midlands Health PPP — availability-based hospital, United Kingdom
        'appraiser'          : 'Lincoln International',
        'valuation_basis'    : 'Yield capitalisation (availability payments)',
        'discount_rate'      : 0.058,
        'inflation_assumption': 0.030,   # RPI-linked
        'cost_basis_eur'     : 85_000_000,
        'revenue_start'      : 28_000_000,
        'revenue_cagr'       : 0.030,    # RPI
        'ebitda_margin_start': 0.52,
        'ebitda_margin_end'  : 0.54,
        'net_debt_start'     : 140_000_000,
        'debt_repayment_pa'  : 5_500_000,
        'interest_rate'      : 0.024,
        'dscr_covenant'      : 1.10,
        'ltv_covenant'       : 0.70,
        'key_risks'          : 'NHS counterparty credit, availability deductions, life-cycle capex underestimation',
    },
    'INFRA_007': {
        # Baltic Port Logistics — core-plus port expansion, Poland
        # LTV breach Q3 2023 (construction overrun), waiver Q4 2023
        'appraiser'          : 'Duff & Phelps',
        'valuation_basis'    : 'DCF (merchant cash flows)',
        'discount_rate'      : 0.092,
        'inflation_assumption': 0.025,
        'cost_basis_eur'     : 115_000_000,
        'revenue_start'      : 38_000_000,
        'revenue_cagr'       : 0.035,
        'ebitda_margin_start': 0.38,
        'ebitda_margin_end'  : 0.44,
        'net_debt_start'     : 120_000_000,
        'debt_repayment_pa'  : 5_000_000,
        'interest_rate'      : 0.048,
        'dscr_covenant'      : 1.05,
        'ltv_covenant'       : 0.87,
        'key_risks'          : 'Construction completion risk, merchant volume uncertainty, Baltic trade geopolitics',
        # Construction overrun: Q3 2023, additional debt draw of EUR 35m
        'overrun_quarter'    : '2023-09-30',
        'overrun_debt_eur'   : 35_000_000,
    },
    'INFRA_008': {
        # Nordvärme — regulated district heating, Sweden
        'appraiser'          : 'KPMG Luxembourg',
        'valuation_basis'    : 'Yield capitalisation (RAB)',
        'discount_rate'      : 0.063,
        'inflation_assumption': 0.020,
        'cost_basis_eur'     : 90_000_000,
        'revenue_start'      : 44_000_000,
        'revenue_cagr'       : 0.025,
        'ebitda_margin_start': 0.41,
        'ebitda_margin_end'  : 0.43,
        'net_debt_start'     : 168_000_000,
        'debt_repayment_pa'  : 6_000_000,
        'interest_rate'      : 0.027,
        'dscr_covenant'      : 1.15,
        'ltv_covenant'       : 0.72,
        'key_risks'          : 'Regulatory review risk, fuel cost exposure, heat demand sensitivity to temperature',
    },
}

# Investment schedule: entry_date per asset
INVESTMENT_SCHEDULE = {
    'INFRA_001': '2019-06-30',
    'INFRA_002': '2019-12-31',
    'INFRA_003': '2020-03-31',
    'INFRA_004': '2020-09-30',
    'INFRA_005': '2021-03-31',
    'INFRA_006': '2021-06-30',
    'INFRA_007': '2022-03-31',
    'INFRA_008': '2021-09-30',
}

PROJECT_VALUATION_DATE = pd.Timestamp(VALUATION_DATE)


# ----------------------------------------------------------------
# Noise profiles — asset-type-specific quarterly variation
#
# vol      : sigma of the lognormal multiplicative revenue shock.
#            Regulated utilities (RAB) are the most stable; merchant
#            and construction-risk assets the most volatile.
# seasonal : quarter-end month → multiplicative factor.
#            Captures traffic seasonality (toll road, airport),
#            wind-resource seasonality (offshore wind), and heating
#            demand seasonality (district heating).
# ----------------------------------------------------------------
NOISE_PROFILES: dict = {
    'INFRA_001': {   # AquaNet Rhein — RAB utility, very stable
        'vol'     : 0.015,
        'seasonal': {3: 1.00, 6: 1.00, 9: 1.00, 12: 1.00},
    },
    'INFRA_002': {   # Réseau Électrique — RAB utility, very stable
        'vol'     : 0.015,
        'seasonal': {3: 1.00, 6: 1.00, 9: 1.00, 12: 1.00},
    },
    'INFRA_003': {   # Autopista Norte — toll road, Q1 traffic dip (winter)
        'vol'     : 0.025,
        'seasonal': {3: 0.92, 6: 1.04, 9: 1.06, 12: 0.98},
    },
    'INFRA_004': {   # Aeroporto Adriatico — airport, summer peak
        'vol'     : 0.030,
        'seasonal': {3: 0.93, 6: 1.08, 9: 1.06, 12: 0.93},
    },
    'INFRA_005': {   # Zephyr Wind — offshore wind, higher output Q4/Q1
        'vol'     : 0.035,
        'seasonal': {3: 1.06, 6: 0.92, 9: 0.94, 12: 1.08},
    },
    'INFRA_006': {   # Midlands Health PPP — availability payments, minimal vol
        'vol'     : 0.005,
        'seasonal': {3: 1.00, 6: 1.00, 9: 1.00, 12: 1.00},
    },
    'INFRA_007': {   # Baltic Port — merchant cash flows, highest vol
        'vol'     : 0.040,
        'seasonal': {3: 1.00, 6: 1.00, 9: 1.00, 12: 1.00},
    },
    'INFRA_008': {   # Nordvärme — district heating, strong Q4/Q1 demand
        'vol'     : 0.015,
        'seasonal': {3: 1.08, 6: 0.88, 9: 0.90, 12: 1.14},
    },
}


# ----------------------------------------------------------------
# Valuation reports — quarterly independent appraisal
# ----------------------------------------------------------------

def generate_valuation_reports() -> list:
    """
    Generate quarterly appraiser reports for all 8 assets.

    EV methodology: yield capitalisation
        EV = EBITDA / discount_rate
    Equity value = EV - net_debt (floored at zero)

    COVID shock (INFRA_003): Q2 2020 revenue drops 42% then recovers
    linearly by Q4 2020.

    Construction overrun (INFRA_007): from Q3 2023 net_debt rises by
    EUR 35m, which is immediately visible in the LTV calculation.
    """
    reports = []

    for asset in ASSETS:
        aid     = asset['asset_id']
        p       = ASSET_PROFILES[aid]
        entry   = pd.Timestamp(INVESTMENT_SCHEDULE[aid])
        first_q = entry + pd.offsets.QuarterEnd(1)
        quarters = pd.date_range(start=first_q, end=PROJECT_VALUATION_DATE, freq='QE')

        n_q             = len(quarters)
        revenue         = p['revenue_start']
        net_debt        = p['net_debt_start']
        discount_rate   = p['discount_rate']
        inflation       = p['inflation_assumption']
        np_prof         = NOISE_PROFILES[aid]

        # pre-compute the overrun quarter index for INFRA_007 ramp
        overrun_i = None
        if 'overrun_quarter' in p:
            overrun_ts = pd.Timestamp(p['overrun_quarter'])
            overrun_i  = next(
                (idx for idx, qq in enumerate(quarters) if qq == overrun_ts), None
            )

        for i, q in enumerate(quarters):
            # ── revenue trend ────────────────────────────────────────
            rev_q = revenue * (1 + p['revenue_cagr']) ** (i / 4)

            # seasonal adjustment + per-quarter noise
            # seasonal: deterministic pattern (Q1 dip, summer peak, etc.)
            # noise:    lognormal shock with asset-type vol tier
            seasonal_factor = np_prof['seasonal'][q.month]
            noise_factor    = np.random.lognormal(0.0, np_prof['vol'])
            rev_q          *= seasonal_factor * noise_factor

            # COVID shock for toll road: applied after noise so the
            # 60% traffic collapse always dominates random variation
            if aid == 'INFRA_003':
                if q == pd.Timestamp('2020-06-30'):
                    rev_q *= (1 - p['covid_revenue_drop'])
                elif q == pd.Timestamp('2020-09-30'):
                    rev_q *= (1 - p['covid_revenue_drop'] * 0.5)
                elif q == pd.Timestamp('2020-12-31'):
                    rev_q *= (1 - p['covid_revenue_drop'] * 0.15)

            # INFRA_007: convex ramp-up from the overrun quarter.
            # Construction disruption suppresses port throughput;
            # revenue recovers exponentially as new berths open.
            # ramp(j=0)=0.85, ramp→1.0 as j→∞ (≈0.98 at j=6).
            if overrun_i is not None and i >= overrun_i:
                j      = i - overrun_i
                ramp   = 1.0 - 0.15 * np.exp(-2.5 * j / 6)
                rev_q *= ramp

            # EBITDA margin interpolates linearly over fund life
            t       = i / max(n_q - 1, 1)
            margin  = (p['ebitda_margin_start']
                       + t * (p['ebitda_margin_end'] - p['ebitda_margin_start']))
            ebitda  = rev_q * margin

            # net debt amortises each quarter
            net_debt_q = max(0.0, net_debt - p['debt_repayment_pa'] * (i / 4))

            # construction overrun for port: additional debt from Q3 2023
            if aid == 'INFRA_007' and q >= pd.Timestamp(p['overrun_quarter']):
                net_debt_q += p['overrun_debt_eur']

            # EV via yield capitalisation
            ev = ebitda / discount_rate if ebitda > 0 else 0.0

            # terminal value: simple perpetuity on final EBITDA
            terminal_value = ebitda / discount_rate * 0.25

            equity = max(0.0, ev - net_debt_q)

            reports.append(dict(
                fund_id              = FUND_ID,
                asset_id             = aid,
                valuation_date       = q.strftime('%Y-%m-%d'),
                appraised_ev_eur     = round(ev, 2),
                net_debt_eur         = round(net_debt_q, 2),
                implied_equity_eur   = round(equity, 2),
                ebitda_eur           = round(ebitda, 2),
                revenue_eur          = round(rev_q, 2),
                discount_rate        = discount_rate,
                inflation_assumption = inflation,
                terminal_value_eur   = round(terminal_value, 2),
                appraiser            = p['appraiser'],
                valuation_basis      = p['valuation_basis'],
                key_risks            = p['key_risks'],
            ))

    return reports


# ----------------------------------------------------------------
# NAV history — derived from valuation reports
# ----------------------------------------------------------------

def generate_nav_history(valuation_reports: list) -> list:
    """
    Derive quarterly NAV from valuation reports.
    Asset-level: one row per report.
    Fund-level: sum of active asset NAVs per quarter.
    """
    nav_rows = []
    cost_map = {a['asset_id']: ASSET_PROFILES[a['asset_id']]['cost_basis_eur']
                for a in ASSETS}

    for vr in valuation_reports:
        cost = cost_map[vr['asset_id']]
        nav_rows.append(dict(
            fund_id  = vr['fund_id'],
            asset_id = vr['asset_id'],
            nav_date = vr['valuation_date'],
            nav_eur  = vr['implied_equity_eur'],
            moic     = round(vr['implied_equity_eur'] / cost, 3) if cost > 0 else None,
        ))

    # fund-level aggregate per quarter
    df      = pd.DataFrame(nav_rows)
    by_date = df.groupby('nav_date')['nav_eur'].sum().reset_index()
    for _, row in by_date.iterrows():
        nav_rows.append(dict(
            fund_id  = FUND_ID,
            asset_id = None,
            nav_date = row['nav_date'],
            nav_eur  = round(row['nav_eur'], 2),
            moic     = None,
        ))

    return nav_rows


# ----------------------------------------------------------------
# Cash flows
# ----------------------------------------------------------------

def generate_cash_flows(valuation_reports: list) -> list:
    """
    Generate fund cash flows.

    Capital calls: one call per asset at investment date (equity check = cost_basis).
    Management fees: 1.0% of committed p.a., charged semi-annually.
    Distributions: 70% of EBITDA less debt service, distributed quarterly,
                   starting 6 quarters after investment date.
    """
    flows = []

    # 1. Capital calls
    for asset in ASSETS:
        aid  = asset['asset_id']
        cost = ASSET_PROFILES[aid]['cost_basis_eur']
        date = INVESTMENT_SCHEDULE[aid]
        flows.append(dict(
            fund_id     = FUND_ID,
            asset_id    = aid,
            cash_flow_date = date,
            flow_type   = 'capital_call',
            amount_eur  = -cost,
            currency    = 'EUR',
            description = f'Initial equity investment {asset["asset_name"]}',
        ))

    # 2. Management fees: 1.0% of committed p.a., semi-annual
    mgmt_fee_semi = round(COMMITTED * MGMT_FEE_RATE / 2, 0)
    fee_dates     = pd.date_range(start='2019-06-30', end='2026-03-31', freq='6ME')
    for fd in fee_dates:
        flows.append(dict(
            fund_id     = FUND_ID,
            asset_id    = None,
            cash_flow_date = fd.strftime('%Y-%m-%d'),
            flow_type   = 'management_fee',
            amount_eur  = -mgmt_fee_semi,
            currency    = 'EUR',
            description = f'Management fee {fd.strftime("%b %Y")}',
        ))

    # 3. Distributions: derived from EBITDA and debt service per quarter
    #    Payout = (EBITDA - debt_service) * 0.70, starting 6Q after entry
    vr_map = {}
    for vr in valuation_reports:
        vr_map.setdefault(vr['asset_id'], {})[vr['valuation_date']] = vr

    for asset in ASSETS:
        aid     = asset['asset_id']
        p       = ASSET_PROFILES[aid]
        entry   = pd.Timestamp(INVESTMENT_SCHEDULE[aid])
        first_q = entry + pd.offsets.QuarterEnd(7)   # 6Q ramp-up before distributions
        quarters = pd.date_range(start=first_q, end=PROJECT_VALUATION_DATE, freq='QE')

        annual_debt_service = (p['net_debt_start'] * p['interest_rate']
                               + p['debt_repayment_pa'])
        quarterly_ds        = annual_debt_service / 4

        for q in quarters:
            q_str = q.strftime('%Y-%m-%d')
            vr    = vr_map.get(aid, {}).get(q_str)
            if vr is None:
                continue
            ebitda_q      = vr['ebitda_eur'] / 4
            distributable = max(0.0, ebitda_q - quarterly_ds) * 0.70
            if distributable < 50_000:
                continue
            flows.append(dict(
                fund_id     = FUND_ID,
                asset_id    = aid,
                cash_flow_date = q_str,
                flow_type   = 'distribution',
                amount_eur  = round(distributable, 0),
                currency    = 'EUR',
                description = f'Quarterly distribution {asset["asset_name"]} {q.strftime("%b %Y")}',
            ))

    return sorted(flows, key=lambda x: x['cash_flow_date'])


# ----------------------------------------------------------------
# Debt tranches
# ----------------------------------------------------------------

def generate_debt() -> list:
    """
    One senior secured debt tranche per asset.
    Bullet maturity aligned with mid-point of concession life.
    INFRA_007 has a mezzanine tranche drawn for the construction overrun.
    """
    records = []

    debt_config = {
        'INFRA_001': dict(lender='KfW / Syndicate', maturity='2038-12-31',
                          rate_type='fixed',    margin_bps=85),
        'INFRA_002': dict(lender='BNP Paribas / Crédit Agricole', maturity='2035-12-31',
                          rate_type='fixed',    margin_bps=90),
        'INFRA_003': dict(lender='BBVA / Santander', maturity='2035-12-31',
                          rate_type='floating', margin_bps=175),
        'INFRA_004': dict(lender='UniCredit / Intesa', maturity='2037-12-31',
                          rate_type='fixed',    margin_bps=120),
        'INFRA_005': dict(lender='ABN AMRO / Rabobank', maturity='2036-12-31',
                          rate_type='fixed',    margin_bps=80),
        'INFRA_006': dict(lender='HSBC / Lloyds', maturity='2042-12-31',
                          rate_type='fixed',    margin_bps=70),
        'INFRA_007': dict(lender='PKO Bank / mBank', maturity='2040-12-31',
                          rate_type='floating', margin_bps=250),
        'INFRA_008': dict(lender='SEB / Handelsbanken', maturity='2042-12-31',
                          rate_type='fixed',    margin_bps=82),
    }

    for asset in ASSETS:
        aid = asset['asset_id']
        p   = ASSET_PROFILES[aid]
        cfg = debt_config[aid]

        # current outstanding = net_debt_start less amortisation to 2026-Q1
        years_held  = (PROJECT_VALUATION_DATE - pd.Timestamp(INVESTMENT_SCHEDULE[aid])).days / 365
        outstanding = max(0.0, p['net_debt_start'] - p['debt_repayment_pa'] * years_held)

        # INFRA_007: add construction overrun tranche
        if aid == 'INFRA_007':
            outstanding += p['overrun_debt_eur']

        records.append(dict(
            asset_id           = aid,
            tranche_name       = 'Senior Secured',
            lender             = cfg['lender'],
            outstanding_eur    = round(outstanding, 0),
            maturity           = cfg['maturity'],
            interest_rate_type = cfg['rate_type'],
            margin_bps         = cfg['margin_bps'],
            amortisation_type  = 'sculpted',
            dscr_covenant      = p['dscr_covenant'],
            ltv_covenant       = p['ltv_covenant'],
        ))

        # INFRA_007 mezzanine tranche (construction overrun)
        if aid == 'INFRA_007':
            records.append(dict(
                asset_id           = aid,
                tranche_name       = 'Mezzanine (Overrun)',
                lender             = 'PKO Bank',
                outstanding_eur    = p['overrun_debt_eur'],
                maturity           = '2030-12-31',
                interest_rate_type = 'floating',
                margin_bps         = 450,
                amortisation_type  = 'bullet',
                dscr_covenant      = None,
                ltv_covenant       = 0.80,
            ))

    return records


# ----------------------------------------------------------------
# Covenant readings — quarterly DSCR and LTV
# ----------------------------------------------------------------

def generate_covenants(valuation_reports: list) -> list:
    """
    Derive quarterly DSCR and LTV from valuation reports.

    DSCR = EBITDA / annual debt service
    LTV  = net_debt / appraised_ev

    INFRA_003: DSCR breach in 2020-Q2 (COVID). Waiver granted 2020-Q3.
    INFRA_007: LTV breach in 2023-Q3 (construction overrun). Waiver 2023-Q4.
    """
    records = []

    vr_by_asset = {}
    for vr in valuation_reports:
        vr_by_asset.setdefault(vr['asset_id'], []).append(vr)

    for asset in ASSETS:
        aid = asset['asset_id']
        p   = ASSET_PROFILES[aid]
        annual_ds = p['net_debt_start'] * p['interest_rate'] + p['debt_repayment_pa']

        for vr in vr_by_asset.get(aid, []):
            ebitda   = vr['ebitda_eur']
            net_debt = vr['net_debt_eur']
            ev       = vr['appraised_ev_eur']

            dscr = round(ebitda / annual_ds, 3) if annual_ds > 0 else None
            ltv  = round(net_debt / ev, 3) if ev > 0 else None

            dscr_breach = bool(dscr is not None and dscr < p['dscr_covenant'])
            ltv_breach  = bool(ltv  is not None and ltv  > p['ltv_covenant'])

            # COVID breach and waiver for toll road
            waiver_granted = False
            waiver_notes   = None
            if aid == 'INFRA_003':
                if vr['valuation_date'] == '2020-06-30' and dscr_breach:
                    waiver_granted = False   # breach, waiver not yet granted
                    waiver_notes   = 'DSCR breach — COVID-19 traffic suspension. Waiver process initiated.'
                elif vr['valuation_date'] == '2020-09-30':
                    # waiver granted retroactively
                    waiver_granted = True
                    waiver_notes   = 'Formal waiver granted by BBVA/Santander syndicate. 6-month holiday period.'
                    dscr_breach    = False   # waiver cures the breach for reporting

            # Construction overrun breach and waiver for port
            if aid == 'INFRA_007':
                if vr['valuation_date'] == '2023-09-30' and ltv_breach:
                    waiver_granted = False
                    waiver_notes   = 'LTV breach — construction overrun EUR 35m. Waiver request submitted to PKO Bank.'
                elif vr['valuation_date'] == '2023-12-31':
                    waiver_granted = True
                    waiver_notes   = 'Waiver granted. Equity cure of EUR 10m injected. LTV expected within covenant by Q2 2024.'
                    ltv_breach     = False

            dscr_headroom = (round(dscr - p['dscr_covenant'], 3)
                             if dscr is not None else None)
            ltv_headroom  = (round(p['ltv_covenant'] - ltv, 3)
                             if ltv is not None else None)

            records.append(dict(
                asset_id       = aid,
                fund_id        = FUND_ID,
                observation_date = vr['valuation_date'],
                dscr_actual    = dscr,
                dscr_covenant  = p['dscr_covenant'],
                dscr_headroom  = dscr_headroom,
                ltv_actual     = ltv,
                ltv_covenant   = p['ltv_covenant'],
                ltv_headroom   = ltv_headroom,
                dscr_breach    = dscr_breach,
                ltv_breach     = ltv_breach,
                waiver_granted = waiver_granted,
                waiver_notes   = waiver_notes,
            ))

    return records


# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------

def _load_infra_fund_metadata() -> dict:
    """Load infrastructure fund common metadata from fund_profile.json at function call time.

    Returns the metadata dict for AIFM_Infra_Core, which is the single source
    of truth for fund_id, fund_name, inception_date, and target size.
    """
    fund_id = 'AIFM_Infra_Core'
    profile_path = _REF_DIR / 'funds' / fund_id / 'fund_profile.json'
    with open(profile_path) as f:
        profile = json.load(f)

    meta = {
        'fund_id': profile['fund_id'],
        'fund_name': profile['fund_name'],
        'inception_date': profile['inception_date'],
        'target_nav_eur': profile['target_nav_eur'],
    }
    return meta


def generate_infra_fund(engine=None) -> None:
    """Generate infrastructure fund data. Reads common fund metadata from fund_profile.json."""
    global FUND_ID, FUND_NAME, TARGET_SIZE, VINTAGE

    if engine is None:
        engine = get_engine()

    # Load common fund metadata from fund_profile.json at call time
    _fund_meta = _load_infra_fund_metadata()
    FUND_ID = _fund_meta['fund_id']
    FUND_NAME = _fund_meta['fund_name']
    TARGET_SIZE = int(_fund_meta['target_nav_eur'])
    VINTAGE = int(_fund_meta['inception_date'][:4])

    with Session(engine) as session:

        # clear existing infra data
        session.query(InfraCovenant).filter_by(fund_id=FUND_ID).delete()
        session.query(InfraDebt).filter(
            InfraDebt.asset_id.in_(ASSET_IDS)
        ).delete(synchronize_session=False)
        session.query(InfraNavHistory).filter_by(fund_id=FUND_ID).delete()
        session.query(InfraCashFlow).filter_by(fund_id=FUND_ID).delete()
        session.query(InfraValuationReport).filter_by(fund_id=FUND_ID).delete()
        session.query(InfraFundInvestment).filter_by(fund_id=FUND_ID).delete()
        session.query(InfraFund).filter_by(fund_id=FUND_ID).delete()
        for a in ASSETS:
            session.query(InfraAsset).filter_by(asset_id=a['asset_id']).delete()
        session.commit()

        # fund metadata
        session.add(InfraFund(
            fund_id              = FUND_ID,
            fund_name            = FUND_NAME,
            vintage_year         = VINTAGE,
            target_size_eur      = TARGET_SIZE,
            committed_eur        = COMMITTED,
            drawn_eur            = DRAWN,
            fund_life_years      = FUND_LIFE,
            currency             = 'EUR',
            domicile             = 'Luxembourg',
            benchmark            = 'CPI + 4%',
            aifmd_classification = 'AIFMD Art. 4(1)(a) — closed-ended PERE/Infra',
        ))

        # assets and fund investments
        for asset in ASSETS:
            aid = asset['asset_id']
            p   = ASSET_PROFILES[aid]

            session.add(InfraAsset(
                asset_id             = aid,
                asset_name           = asset['asset_name'],
                sector               = asset['sector'],
                sub_type             = asset['sub_type'],
                country              = asset['country'],
                regulatory_framework = asset['regulatory_framework'],
                concession_start     = asset['concession_start'],
                concession_end       = asset['concession_end'],
                inflation_linkage    = asset['inflation_linkage'],
            ))

            session.add(InfraFundInvestment(
                fund_id          = FUND_ID,
                asset_id         = aid,
                entry_date       = INVESTMENT_SCHEDULE[aid],
                exit_date        = None,
                ownership_pct    = 100.0,
                cost_basis_eur   = p['cost_basis_eur'],
                committed_equity = p['cost_basis_eur'],
                drawn_equity     = p['cost_basis_eur'],
            ))

        # valuation reports — source of truth for NAV
        val_reports = generate_valuation_reports()
        for vr in val_reports:
            session.add(InfraValuationReport(**vr))

        # NAV history derived from valuation reports
        for nav in generate_nav_history(val_reports):
            session.add(InfraNavHistory(**nav))

        # cash flows
        for cf in generate_cash_flows(val_reports):
            session.add(InfraCashFlow(**cf))

        # debt tranches
        for debt in generate_debt():
            session.add(InfraDebt(**debt))

        # covenant readings
        for cov in generate_covenants(val_reports):
            session.add(InfraCovenant(**cov))

        session.commit()

    val_reports = generate_valuation_reports()
    n_breach    = sum(
        1 for c in generate_covenants(val_reports)
        if c['dscr_breach'] or c['ltv_breach']
    )
    n_waiver    = sum(
        1 for c in generate_covenants(val_reports)
        if c['waiver_granted']
    )

    print(f'Infrastructure fund {FUND_ID} generated successfully.')
    print(f'  Assets             : {len(ASSETS)}')
    print(f'  Valuation reports  : {len(val_reports)}')
    print(f'  Cash flows         : {len(generate_cash_flows(val_reports))}')
    print(f'  Covenant readings  : {len(generate_covenants(val_reports))}')
    print(f'  Covenant breaches  : {n_breach}')
    print(f'  Waivers granted    : {n_waiver}')


if __name__ == '__main__':
    generate_infra_fund()
