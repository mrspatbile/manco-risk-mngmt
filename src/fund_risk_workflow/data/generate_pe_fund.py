"""
generate_pe_fund.py
===================
Generates synthetic PE fund data for AIFM_PE_Buyout.
Simulates a 10-year EUR 200m buyout fund with 8 portfolio companies
across different sectors and geographies, vintage 2018.

Populates:
    pe_funds
    pe_portfolio_companies
    pe_fund_investments
    pe_cash_flows
    pe_nav_history
    pe_valuation_report

Usage
-----
    python3 -m fund_risk_workflow.data.generate_pe_fund
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
    get_engine, PEFund, PEPortfolioCompany, PEFundInvestment,
    PECashFlow, PENavHistory, PEValuationReport,
    PEFundCashManagement,
)

from sqlalchemy.orm import Session

np.random.seed(42)

# ----------------------------------------------------------------
# Fund configuration
# ----------------------------------------------------------------
# Note: FUND_ID, FUND_NAME, VINTAGE, TARGET_SIZE are set by generate_pe_fund()
# at function call time from fund_profile.json. They are not defined at module
# import time to ensure they come from a single source of truth.
# These are module-level variables that get populated by generate_pe_fund().
FUND_ID = None
FUND_NAME = None
TARGET_SIZE = None
VINTAGE = None

# PE-specific fund configuration (not in fund_profile.json)
FUND_LIFE = 10
INV_PERIOD_END = '2023-12-31'
COMMITTED   = 350_000_000

HOLD_AT_COST_QUARTERS = 6  # 1.5 years

# ----------------------------------------------------------------
# Fund economics
# ----------------------------------------------------------------
MGMT_FEE_RATE    = 0.0175        # 1.75% of committed p.a.
HURDLE_RATE      = 0.08          # 8% preferred return to LPs
CARRY_RATE       = 0.20          # 20% carried interest to GP
CATCHUP_RATE     = 1.00          # 100% GP catch-up

# ----------------------------------------------------------------
# cash management
# ----------------------------------------------------------------

CASH_RESERVE_PCT  = 0.08         # 8% of committed held as cash reserve
CASH_RATE         = 0.035        # 3.5% p.a. EUR money market rate
SUB_LINE_PCT      = 0.15         # 15% of committed = max sub line
SUB_LINE_RATE     = 0.050        # EURIBOR + 150bps = 5.0% p.a.
SUB_LINE_DAYS     = 90           # capital calls bridged for 90 days

# ----------------------------------------------------------------
# Portfolio companies
# ----------------------------------------------------------------
with open(_REF_DIR / 'portfolios' / 'pe_companies.json') as _f:
    _data = json.load(_f)
    # Handle schema_version wrapper
    COMPANIES = _data.get('companies') if isinstance(_data, dict) and 'schema_version' in _data else _data


def compute_entry_equity_check(company_id: str) -> float:
    """
    Derive the equity check written at entry from first principles.

    Equity Check = (Entry EV - Net Debt at entry) * Ownership %

    For EBITDA-positive companies:  Entry EV = EBITDA * EV/EBITDA multiple
    For pre-profit companies:       Entry EV = Revenue * EV/Sales multiple
    """
    c = next(x for x in COMPANIES if x['company_id'] == company_id)
    p = COMPANY_PROFILES[company_id]

    ebitda = p['revenue_start'] * p['ebitda_margin_start']
    if c['entry_ev_ebitda'] is not None:
        ev = ebitda * c['entry_ev_ebitda']
    else:
        ev = p['revenue_start'] * c['entry_ev_sales']

    equity_check = ev - p['net_debt_start']
    return round(equity_check * c['ownership_pct'] / 100, 0)

# ----------------------------------------------------------------
# Cash flow generation
# ----------------------------------------------------------------
def generate_cash_flows(valuation_reports: list = None, 
                        use_sub_line: bool = True) -> list:
    """
    Generate PE fund cash flows from first principles.

    Capital calls: derived from compute_entry_equity_check()
    Management fees: 1.75% of committed p.a., charged semi-annually
    Distributions: exit proceeds derived from appraisal NAV at exit date,
                   run through European waterfall

    European waterfall order:
        1. Return of contributed capital to LPs
        2. Preferred return: 8% p.a. on contributed capital
        3. GP catch-up: 100% to GP until GP has 20% of total profits
        4. Carried interest: 80% LP / 20% GP on remaining profits
    """
    if valuation_reports is None:
        valuation_reports = generate_valuation_reports()

    flows = []

    # ── 1. Capital calls ─────────────────────────────────────────────────────
    capital_events = [
        ('2018-06-15', 'PE_001', 'Initial investment TechCo'),
        ('2018-11-01', 'PE_003', 'Initial investment Logistics Plus'),
        ('2019-03-20', 'PE_002', 'Initial investment MedDevice'),
        ('2019-06-01', 'PE_007', 'Initial investment FoodCo'),
        ('2019-09-15', 'PE_004', 'Initial investment RetailGroup'),
        ('2020-04-01', 'PE_005', 'Initial investment EnergyTrans'),
        ('2021-01-15', 'PE_006', 'Initial investment FinTech Nordic'),
        ('2022-03-01', 'PE_008', 'Initial investment SoftwareHub'),
        ('2023-06-15', 'PE_001', 'Follow-on TechCo'),
    ]

    follow_ons = {'2023-06-15_PE_001': 5_000_000}

    for date, company_id, desc in capital_events:
        key    = f"{date}_{company_id}"
        amount = follow_ons.get(key, compute_entry_equity_check(company_id))

        # sub line: LP capital call is delayed 90 days from investment date
        call_date = (pd.Timestamp(date) + pd.Timedelta(days=SUB_LINE_DAYS)).strftime('%Y-%m-%d') \
                    if use_sub_line else date

        flows.append(dict(
            fund_id    = FUND_ID,
            company_id = company_id,
            cash_flow_date = call_date,
            flow_type  = 'capital_call',
            amount_eur = -amount,
            description= desc + (' (sub line bridge)' if use_sub_line else ''),
        ))

    # ── 2. Management fees: 1.75% of committed p.a., semi-annual ────────────
    mgmt_fee_semi = round(COMMITTED * MGMT_FEE_RATE / 2, 0)
    fee_dates = pd.date_range(start='2018-06-30', end='2026-03-31', freq='6ME')
    for fee_date in fee_dates:
        flows.append(dict(
            fund_id    = FUND_ID,
            company_id = None,
            cash_flow_date = fee_date.strftime('%Y-%m-%d'),
            flow_type  = 'management_fee',
            amount_eur = -mgmt_fee_semi,
            description= f'Management fee {fee_date.strftime("%b %Y")}',
        ))

    # ── 3. Exit proceeds derived from appraisal, run through waterfall ───────
    call_flows = [f for f in flows if f['flow_type'] == 'capital_call']

    # build exit NAV lookup from valuation reports
    exit_nav_lookup = {}
    for c in COMPANIES:
        if not c.get('exit_date'):
            continue
        cid       = c['company_id']
        exit_date = c['exit_date']
        company_reports = [
            r for r in valuation_reports
            if r['company_id'] == cid and r['valuation_date'] <= exit_date
        ]

        if company_reports:
            latest = max(company_reports, key=lambda r: r['valuation_date'])
            exit_nav_lookup[cid] = latest['appraised_nav_eur']

    exits = [c for c in COMPANIES if c.get('exit_date')]

    for ex in exits:
        cid       = ex['company_id']
        exit_date = ex['exit_date']
        gross_exit = exit_nav_lookup.get(cid, 0)

        if gross_exit <= 0:
            continue

        # contributed capital for this company only
        contributed = sum(
            abs(f['amount_eur']) for f in call_flows
            if f['company_id'] == cid
        )

        # pro-rata management fees
        n_active = len([c for c in COMPANIES
                        if pd.Timestamp(c['investment_date']) <= pd.Timestamp(exit_date)])
        fees_paid = sum(
            abs(f['amount_eur']) / n_active
            for f in flows
            if f['flow_type'] == 'management_fee' and f['cash_flow_date'] <= exit_date
        )

        total_contributed = contributed + fees_paid

        # preferred return: years from this company's first call to exit
        company_first_call = min(
            f['cash_flow_date'] for f in call_flows if f['company_id'] == cid
        )
        years = (pd.Timestamp(exit_date) - pd.Timestamp(company_first_call)).days / 365
        preferred_return = round(total_contributed * ((1 + HURDLE_RATE) ** years - 1), 0)

        # waterfall
        remaining       = gross_exit
        lp_distribution = 0
        gp_distribution = 0

        # step 1: return of capital
        roc = min(remaining, total_contributed)
        lp_distribution += roc
        remaining -= roc

        # step 2: preferred return
        if remaining > 0:
            pref = min(remaining, preferred_return)
            lp_distribution += pref
            remaining -= pref

        # step 3: GP catch-up
        if remaining > 0:
            total_profit = gross_exit - total_contributed
            gp_target    = total_profit * CARRY_RATE
            catchup      = min(remaining, gp_target)
            gp_distribution += catchup
            remaining -= catchup

        # step 4: 80/20 split
        if remaining > 0:
            gp_distribution += remaining * CARRY_RATE
            lp_distribution += remaining * (1 - CARRY_RATE)

        if lp_distribution > 0:
            flows.append(dict(
                fund_id    = FUND_ID,
                company_id = cid,
                cash_flow_date = exit_date,
                flow_type  = 'exit_proceeds',
                amount_eur = round(lp_distribution, 0),
                description= f"Exit proceeds {ex['company_name']} (LP share)",
            ))

        if gp_distribution > 0:
            flows.append(dict(
                fund_id    = FUND_ID,
                company_id = cid,
                cash_flow_date = exit_date,
                flow_type  = 'carried_interest',
                amount_eur = round(gp_distribution, 0),
                description= f"Carried interest {ex['company_name']} (GP share)",
            ))

    # ── 4. Interim distributions from active companies ───────────────────────
    interim_distributions = [
        ('2021-06-30', 'PE_003',  8_000_000, 'Interim distribution Logistics Plus'),
        ('2022-06-30', 'PE_003',  6_000_000, 'Interim distribution Logistics Plus'),
        ('2024-06-30', 'PE_002',  4_000_000, 'Interim distribution MedDevice'),
        ('2024-12-15', None,      2_000_000, 'Dividend recapitalisation'),
        ('2025-06-30', 'PE_001',  6_000_000, 'Interim distribution TechCo'),
        ('2025-12-15', 'PE_005',  5_000_000, 'Interim distribution EnergyTrans'),
    ]

    for date, company_id, amount, desc in interim_distributions:
        flows.append(dict(
            fund_id    = FUND_ID,
            company_id = company_id,
            cash_flow_date = date,
            flow_type  = 'distribution',
            amount_eur = amount,
            description= desc,
        ))

        if use_sub_line:
            flows.append(dict(
                fund_id    = FUND_ID,
                company_id = company_id,
                cash_flow_date = date,
                flow_type  = 'sub_line_draw',
                amount_eur = -amount,
                description= f'Sub line draw -- {desc}',
            ))
            flows.append(dict(
                fund_id    = FUND_ID,
                company_id = company_id,
                cash_flow_date = call_date,
                flow_type  = 'sub_line_repay',
                amount_eur = amount,
                description= f'Sub line repay -- {desc}',
            ))

    return sorted(flows, key=lambda x: x['cash_flow_date'])

def generate_fund_cash_management(valuation_reports: list = None) -> list:
    """
    Generate quarterly fund-level treasury snapshots.

    Cash reserve: 8% of committed held at fund level, earns 3.5% p.a.
    Sub line: drawn to bridge capital calls for 90 days, costs 5.0% p.a.

    Cash reserve mechanics:
        - Starts at CASH_RESERVE_PCT * COMMITTED at fund close (2018-Q2)
        - Drawn down as capital calls are made
        - Replenished from distributions and exit proceeds
        - Interest earned quarterly on average balance

    Sub line mechanics:
        - Drawn at investment date to fund the equity check
        - Repaid 90 days later when LP capital call is made
        - Interest accrues daily, charged quarterly
        - Max draw: SUB_LINE_PCT * COMMITTED
    """
    if valuation_reports is None:
        valuation_reports = generate_valuation_reports()

    flows       = generate_cash_flows(valuation_reports)
    call_flows  = [f for f in flows if f['flow_type'] == 'capital_call']
    dist_flows  = [f for f in flows if f['flow_type'] in
                   ('distribution', 'exit_proceeds', 'carried_interest')]

    # quarterly dates for the fund life
    quarters = pd.date_range(
        start='2018-06-30', end='2026-03-31', freq='QE'
    )

    # initial cash reserve
    cash_balance         = COMMITTED * CASH_RESERVE_PCT
    sub_line_limit       = COMMITTED * SUB_LINE_PCT
    sub_line_drawn       = 0.0
    cum_interest_earned  = 0.0
    cum_interest_paid    = 0.0

    # build lookup of cash flow events by quarter
    def flows_in_quarter(q_start, q_end, flow_types):
        return [
            f for f in flows
            if f['flow_type'] in flow_types
            and q_start <= pd.Timestamp(f['cash_flow_date']) <= q_end
        ]

    records = []

    mgmt_fee_semi = round(COMMITTED * MGMT_FEE_RATE / 2, 0)

    for i, quarter in enumerate(quarters):
        q_start = quarters[i - 1] + pd.Timedelta(days=1) if i > 0 else pd.Timestamp('2018-04-01')
        q_end   = quarter

        # sub line draws and repayments from explicit flow types
        draws_q   = flows_in_quarter(q_start, q_end, ['sub_line_draw'])
        repays_q  = flows_in_quarter(q_start, q_end, ['sub_line_repay'])
        total_draws   = sum(abs(f['amount_eur']) for f in draws_q)
        total_repays  = sum(f['amount_eur'] for f in repays_q)

        sub_line_drawn = max(0, sub_line_drawn + total_draws - total_repays)

        # capital calls this quarter (delayed LP funding, not investment date)
        calls_q     = flows_in_quarter(q_start, q_end, ['capital_call'])
        total_calls = sum(abs(f['amount_eur']) for f in calls_q)
        
        # management fees paid this quarter
        fees_q      = flows_in_quarter(q_start, q_end, ['management_fee'])
        total_fees  = sum(abs(f['amount_eur']) for f in fees_q)

        # upcoming fees: next 4 quarters = 2 semi-annual payments
        next_4q_fees = mgmt_fee_semi * 2

        # gross exit proceeds this quarter from appraisal (before waterfall)
        exited_this_q   = [
            c for c in COMPANIES
            if c.get('exit_date')
            and q_start <= pd.Timestamp(c['exit_date']) <= q_end
        ]
  
        exit_proceeds_q = 0.0
        for c in exited_this_q:
            company_reports = [
                r for r in valuation_reports
                if r['company_id'] == c['company_id']
                and r['valuation_date'] <= c['exit_date']
            ]

            if company_reports:
                latest = max(company_reports, key=lambda r: r['valuation_date'])
                exit_proceeds_q += latest['appraised_nav_eur']
        

        # retain enough to cover next 4 quarters fees, distribute the rest
        if exit_proceeds_q > 0:
            retained    = min(next_4q_fees, exit_proceeds_q)
            distributed = exit_proceeds_q - retained

        else:
            retained    = 0.0
            distributed = 0.0


        # interim distributions paid out this quarter
        dist_flows_q = flows_in_quarter(q_start, q_end, ['distribution'])
        total_dists  = sum(f['amount_eur'] for f in dist_flows_q) + distributed

        cash_balance = (
            cash_balance
            # + total_calls          # LP capital arriving # hsiis it not included bcs we are using to repay subline
            # + retained             # retained from exit proceeds
            - total_draws          # investments via sub line
            - total_fees           # management fees paid
            - total_dists          # distributions paid to LPs
        )
        cash_balance = max(0, cash_balance) + retained 


        # interest earned on average cash balance (quarterly)
        interest_earned = cash_balance * CASH_RATE / 4
        cum_interest_earned += interest_earned

        # interest paid on sub line (quarterly)
        interest_paid = sub_line_drawn * SUB_LINE_RATE / 4
        cum_interest_paid += interest_paid

        net_cash = cash_balance - sub_line_drawn

        records.append(dict(
            fund_id                  = FUND_ID,
            cash_management_date     = quarter.strftime('%Y-%m-%d'),
            cash_balance_eur         = round(cash_balance, 2),
            cash_interest_earned     = round(interest_earned, 2),
            cash_rate                = CASH_RATE,
            sub_line_drawn           = round(sub_line_drawn, 2),
            sub_line_limit           = round(sub_line_limit, 2),
            sub_line_interest        = round(interest_paid, 2),
            sub_line_rate            = SUB_LINE_RATE,
            net_cash_position        = round(net_cash, 2),
            cumulative_interest_earned = round(cum_interest_earned, 2),
            cumulative_interest_paid   = round(cum_interest_paid, 2),
        ))

    return records

# ----------------------------------------------------------------
# NAV history generation (quarterly)
# ----------------------------------------------------------------
# MOIC (Multiple on Invested Capital) = current NAV / cost basis
# moic_path traces the J-curve: starts below 1.0x in early years
# (management fees, slow value creation) and rises above 2.0x
# as portfolio companies grow and are exited.
# MOIC < 1.0x: investment below cost (typical years 1-2)
# MOIC = 1.0x: at cost (breakeven)
# MOIC > 1.0x: value creation above cost


def generate_nav_history(valuation_reports: list) -> list:
    """
    Derive quarterly NAV history from independent appraisal reports.
    NAV = appraised_nav_eur from pe_valuation_report (source of truth).
    Fund-level NAV = sum of active company NAVs per quarter.
    """
    nav_rows = []

    # company-level: one row per valuation report
    for vr in valuation_reports:
        nav_rows.append(dict(
            fund_id        = vr['fund_id'],
            company_id     = vr['company_id'],
            nav_date       = vr['valuation_date'],
            nav_eur        = vr['appraised_nav_eur'],
            gross_multiple = round(vr['appraised_nav_eur'] /
                        compute_entry_equity_check(vr['company_id']), 3),
            unrealised_gain= round(vr['appraised_nav_eur'] -
                        compute_entry_equity_check(vr['company_id']), 2),
            cost_basis_eur = compute_entry_equity_check(vr['company_id']),
        ))

    # fund-level: sum of company NAVs per quarter
    df = pd.DataFrame(nav_rows)
    fund_nav = df.groupby('nav_date')['nav_eur'].sum().reset_index()
    for _, row in fund_nav.iterrows():
        nav_rows.append(dict(
            fund_id        = FUND_ID,
            company_id     = None,
            nav_date       = row['nav_date'],
            nav_eur        = round(row['nav_eur'], 2),
            gross_multiple = None,
            unrealised_gain= None,
            cost_basis_eur = None,
        ))

    return nav_rows


# ----------------------------------------------------------------
# Main: populate PE tables
# ----------------------------------------------------------------


# ----------------------------------------------------------------
# Valuation report generation (quarterly independent appraisal)
# ----------------------------------------------------------------
# Data simulates quarterly reports received from independent valuation
# firm (e.g. KPMG, Duff & Phelps). In production this arrives as a
# structured report. The ManCo stores and consumes it, does not compute it.

COMPANY_PROFILES = {
    'PE_001': {
        # TechCo: solid performer, 8% revenue CAGR, slight multiple expansion then compression
        'appraiser': 'KPMG Luxembourg', 'valuation_basis': 'Market approach',
        'covenant_type': 'leverage',
        'leverage_covenant': 6.5, 'coverage_covenant': 2.0,
        'discount_rate': 0.12,
        'revenue_start': 45_000_000, 'revenue_cagr': 0.08,
        'ebitda_margin_start': 0.22, 'ebitda_margin_end': 0.26,
        'net_debt_start': 35_000_000, 'debt_repayment_pa': 3_000_000,
        'interest_rate': 0.055,
        # EV/EBITDA: entry 11.5x, peak 13x in 2021, compressed to 10x by 2023, recovery to 11x
        'ev_multiple_path': {2018: 10.0, 2019: 10.5, 2020: 10.0, 2021: 11.0,
                     2022: 10.0, 2023: 9.0, 2024: 9.5, 2025: 10.0, 2026: 10.0},
        'key_risks': 'Technology disruption, key person dependency, customer concentration',
    },
    'PE_002': {
        # MedDevice: defensive sector, steady growth, resilient multiples
        'appraiser': 'Duff & Phelps', 'valuation_basis': 'Income approach',
        'covenant_type': 'leverage',
        'leverage_covenant': 5.5, 'coverage_covenant': 2.5,
        'discount_rate': 0.11,
        'revenue_start': 38_000_000, 'revenue_cagr': 0.07,
        'ebitda_margin_start': 0.25, 'ebitda_margin_end': 0.28,
        'net_debt_start': 28_000_000, 'debt_repayment_pa': 2_500_000,
        'interest_rate': 0.050,
        'ev_multiple_path': {2019: 13.2, 2020: 13.0, 2021: 14.5,
                             2022: 13.0, 2023: 12.0, 2024: 12.5, 2025: 13.0, 2026: 13.0},
        'key_risks': 'Regulatory approval risk, reimbursement pressure, clinical trial outcomes',
    },
    'PE_003': {
        # Logistics Plus: exited 2023, good performer
        'appraiser': 'Lincoln International', 'valuation_basis': 'Market approach',
        'covenant_type': 'leverage',
        'leverage_covenant': 6.0, 'coverage_covenant': 2.0,
        'discount_rate': 0.13,
        'revenue_start': 55_000_000, 'revenue_cagr': 0.08,
        'ebitda_margin_start': 0.18, 'ebitda_margin_end': 0.21,
        'net_debt_start': 22_000_000, 'debt_repayment_pa': 2_000_000,
        'interest_rate': 0.058,
        'ev_multiple_path': {2018: 7.5, 2019: 8.0, 2020: 7.5, 2021: 9.0,
                            2022: 8.0, 2023: 8.5},
        'key_risks': 'E-commerce disruption, fuel cost exposure, driver shortage',
        'exit_date': '2023-06-30',
    },
    'PE_004': {
        # RetailGroup France: DISTRESSED - structural decline, covenant breach
        'appraiser': 'KPMG Luxembourg', 'valuation_basis': 'Market approach',
        'covenant_type': 'leverage',
        'leverage_covenant': 5.5, 'coverage_covenant': 2.0,
        'discount_rate': 0.14,
        'revenue_start': 42_000_000, 'revenue_cagr': 0.01,
        'ebitda_margin_start': 0.14, 'ebitda_margin_end': -0.04,
        'net_debt_start': 18_000_000, 'debt_repayment_pa': 300_000,
        'interest_rate': 0.068,
        'ev_multiple_path': {2019: 6.0, 2020: 5.0, 2021: 5.5,
                            2022: 4.0, 2023: 3.0, 2024: 2.0, 2025: 1.5, 2026: 1.0},
        'key_risks': 'Structural decline of physical retail, rising vacancy rates, '
                     'e-commerce competition, covenant breach risk from 2024',
    },
    'PE_005': {
        # EnergyTrans: growth story, capex heavy early, improving margins
        'appraiser': 'Duff & Phelps', 'valuation_basis': 'Income approach',
        'covenant_type': 'revenue',
        'leverage_covenant': 7.0, 'coverage_covenant': 1.8,
        'discount_rate': 0.13,
        'revenue_start': 28_000_000, 'revenue_cagr': 0.08,
        'ebitda_margin_start': 0.16, 'ebitda_margin_end': 0.18,
        'net_debt_start': 24_000_000, 'debt_repayment_pa': 1_500_000,
        'interest_rate': 0.060,
        'ev_multiple_path': {2020: 9.0, 2021: 11.0, 2022: 8.0,
                     2023: 7.5, 2024: 8.0, 2025: 8.5, 2026: 9.0},
        'revenue_covenant_eur': 25_000_000,
        'key_risks': 'Energy transition policy risk, technology obsolescence, capex intensity',
    },
    'PE_006': {
        # FinTech Nordic: pre-profit growth, high multiple on revenue, path to profitability
        'appraiser': 'Lincoln International', 'valuation_basis': 'Market approach',
        'covenant_type': 'liquidity',
        'leverage_covenant': None, 'coverage_covenant': None,
        'discount_rate': 0.18,
        'revenue_start': 12_000_000, 'revenue_cagr': 0.12,
        'ebitda_margin_start': -0.20, 'ebitda_margin_end': 0.15,
        'net_debt_start': 8_000_000, 'debt_repayment_pa': 0,
        'interest_rate': 0.075,
        'ev_multiple_path': {2021: 15.5, 2022: 10.0, 2023: 8.0,
                             2024: 9.0, 2025: 10.0, 2026: 11.0},
        'revenue_covenant_eur': 10_000_000,
        'cash_covenant_eur': 3_000_000,
        'key_risks': 'Regulatory fintech risk, customer acquisition cost, '
                     'path to profitability, competition from incumbents',
    },
    'PE_007': {
        # FoodCo Benelux: exited 2024, good performer
        'appraiser': 'KPMG Luxembourg', 'valuation_basis': 'Market approach',
        'covenant_type': 'leverage',
        'leverage_covenant': 5.5, 'coverage_covenant': 2.2,
        'discount_rate': 0.12,
        'revenue_start': 48_000_000, 'revenue_cagr': 0.07,
        'ebitda_margin_start': 0.16, 'ebitda_margin_end': 0.19,
        'net_debt_start': 20_000_000, 'debt_repayment_pa': 2_000_000,
        'interest_rate': 0.055,
        'ev_multiple_path': {2019: 7.5, 2020: 7.0, 2021: 8.5,
                            2022: 7.5, 2023: 7.0, 2024: 7.5},
        'key_risks': 'Consumer spending slowdown, private label competition, raw material costs',
        'exit_date': '2024-03-31',
    },
    'PE_008': {
        # SoftwareHub: recent investment, strong growth trajectory
        'appraiser': 'Duff & Phelps', 'valuation_basis': 'Market approach',
        'covenant_type': 'leverage',
        'leverage_covenant': 6.0, 'coverage_covenant': 2.0,
        'discount_rate': 0.13,
        'revenue_start': 32_000_000, 'revenue_cagr': 0.12,
        'ebitda_margin_start': 0.20, 'ebitda_margin_end': 0.26,
        'net_debt_start': 30_000_000, 'debt_repayment_pa': 2_000_000,
        'interest_rate': 0.062,
        'ev_multiple_path': {2022: 14.8, 2023: 11.0, 2024: 11.5,
                             2025: 12.0, 2026: 12.5},
        'key_risks': 'Talent retention, cyber security, integration risk post-acquisition',
    },
}

LIQUIDATION_VALUE = {
    'PE_001': 8_000_000,   # TechCo: IP, equipment
    'PE_002': 12_000_000,  # MedDevice: patents, machinery
    'PE_003': 5_000_000,   # Logistics Plus: fleet, warehouse
    'PE_004': 6_000_000,   # RetailGroup: property, fixtures
    'PE_005': 10_000_000,  # EnergyTrans: physical assets, permits
    'PE_006': 1_000_000,   # FinTech: mostly intangibles, very low
    'PE_007': 4_000_000,   # FoodCo: brand, equipment
    'PE_008': 5_000_000,   # SoftwareHub: IP, customer contracts
}


def generate_valuation_reports() -> list:
    """Generate quarterly independent appraisal reports for all companies."""
    reports = []

    for company_id, inv in [(c['company_id'], c) for c in COMPANIES]:
        profile      = COMPANY_PROFILES[company_id]
        start_date   = pd.Timestamp(inv['investment_date'])
        exit_date    = pd.Timestamp(profile['exit_date']) if 'exit_date' in profile else None
        cost_basis   = compute_entry_equity_check(company_id)
        nav_data     = {
            n['company_id']: n
            for n in [dict(
                company_id     = nr.company_id,
                date           = nr.date,
                nav_eur        = nr.nav_eur,
                gross_multiple = nr.gross_multiple,
            ) for nr in []]
        }

        # generate quarterly dates from first full quarter after investment
        first_quarter = start_date + pd.offsets.QuarterEnd(1)
        quarters      = pd.date_range(
            start=first_quarter,
            end=pd.Timestamp('2026-03-31'),
            freq='QE'
        )

        n_quarters         = len(quarters)
        revenue_start      = profile['revenue_start']
        revenue_cagr       = profile['revenue_cagr']
        ebitda_margin_start= profile['ebitda_margin_start']
        ebitda_margin_end  = profile['ebitda_margin_end']
        net_debt           = profile['net_debt_start']
        debt_repayment_pa  = profile['debt_repayment_pa']
        interest_rate      = profile['interest_rate']

        for i, quarter in enumerate(quarters):
            if exit_date and quarter > exit_date:
                break

            # interpolate metrics over fund life
            t = i / max(n_quarters - 1, 1)

            revenue_ltm  = revenue_start * (1 + revenue_cagr) ** (i / 4)
            ebitda_margin= ebitda_margin_start + t * (ebitda_margin_end - ebitda_margin_start)
            ebitda_ltm   = revenue_ltm * ebitda_margin
            net_debt_q   = max(0, net_debt - debt_repayment_pa * (i / 4))
            interest_exp = net_debt_q * interest_rate

            # EV and NAV
            # EV and NAV
            year = quarter.year
            ev_multiple_path = profile['ev_multiple_path']

            # interpolate between the two nearest path years
            path_years = sorted(ev_multiple_path.keys())
            if year <= path_years[0]:
                ev_ebitda = ev_multiple_path[path_years[0]]
            elif year >= path_years[-1]:
                ev_ebitda = ev_multiple_path[path_years[-1]]
            else:
                # linear interpolation between surrounding years
                y_lo = max(y for y in path_years if y <= year)
                y_hi = min(y for y in path_years if y >= year)
                if y_lo == y_hi:
                    ev_ebitda = ev_multiple_path[y_lo]
                else:
                    frac = (quarter.month / 12 + quarter.year - y_lo) / (y_hi - y_lo)
                    ev_ebitda = ev_multiple_path[y_lo] + frac * (ev_multiple_path[y_hi] - ev_multiple_path[y_lo])


            if ebitda_ltm > 0:
                ev_eur = ebitda_ltm * ev_ebitda
            else:
                # pre-profit or loss-making: use entry_ev_sales if available,
                # otherwise fall back to 1.5x revenue
                ev_ebitda = None
                if inv.get('entry_ev_sales') is not None:
                    ev_eur = revenue_ltm * inv['entry_ev_sales']
                else:
                    ev_eur = revenue_ltm * 1.5

            equity_value      = ev_eur - net_debt_q
            liquidation_floor = LIQUIDATION_VALUE[company_id]
            market_nav        = max(liquidation_floor, equity_value)
            if i < HOLD_AT_COST_QUARTERS:
                appraised_nav = cost_basis
            else:
                appraised_nav = market_nav


            # covenant ratios
            leverage_ratio  = net_debt_q / ebitda_ltm if ebitda_ltm > 0 else None
            coverage_ratio  = ebitda_ltm / interest_exp if interest_exp > 0 else None
            arr_eur         = revenue_ltm * 0.6 if company_id == 'PE_006' else None

            # key risks evolve for distressed company
            key_risks = profile['key_risks']
            if company_id == 'PE_004' and quarter >= pd.Timestamp('2022-01-01'):
                if leverage_ratio and leverage_ratio > profile['leverage_covenant'] * 0.8:
                    key_risks = key_risks + ' — COVENANT HEADROOM < 20%: monitoring intensified'
            if company_id == 'PE_004' and quarter >= pd.Timestamp('2024-01-01'):
                key_risks = key_risks + ' — COVENANT BREACH: waiver requested'

            reports.append(dict(
                fund_id             = FUND_ID,
                company_id          = company_id,
                valuation_date      = quarter.strftime('%Y-%m-%d'),
                appraised_nav_eur   = round(appraised_nav, 2),
                ebitda_ltm_eur      = round(ebitda_ltm, 2),
                revenue_ltm_eur     = round(revenue_ltm, 2),
                ebitda_margin       = round(ebitda_margin, 4),
                net_debt_eur        = round(net_debt_q, 2),
                ev_eur              = round(ev_eur, 2),
                ev_ebitda           = round(ev_ebitda, 2) if ev_ebitda else None,
                interest_expense_eur= round(interest_exp, 2),
                discount_rate       = profile['discount_rate'],
                valuation_basis     = profile['valuation_basis'],
                appraiser           = profile['appraiser'],
                key_risks           = key_risks,
                covenant_type       = profile['covenant_type'],
                leverage_covenant   = profile.get('leverage_covenant'),
                leverage_ratio      = round(leverage_ratio, 3) if leverage_ratio else None,
                coverage_covenant   = profile.get('coverage_covenant'),
                coverage_ratio      = round(coverage_ratio, 3) if coverage_ratio else None,
                revenue_covenant_eur= profile.get('revenue_covenant_eur'),
                cash_covenant_eur   = profile.get('cash_covenant_eur'),
                arr_eur             = round(arr_eur, 2) if arr_eur else None,
            ))

    return reports


def _load_pe_fund_metadata() -> dict:
    """Load PE fund common metadata from fund_profile.json at function call time.

    Returns the metadata dict for AIFM_PE_Buyout, which is the single source
    of truth for fund_id, fund_name, inception_date, and target size.
    """
    fund_id = 'AIFM_PE_Buyout'
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


def generate_pe_fund(engine=None) -> None:
    """Generate PE fund data. Reads common fund metadata from fund_profile.json."""
    global FUND_ID, FUND_NAME, TARGET_SIZE, VINTAGE

    if engine is None:
        engine = get_engine()

    # Load common fund metadata from fund_profile.json at call time
    _fund_meta = _load_pe_fund_metadata()
    FUND_ID = _fund_meta['fund_id']
    FUND_NAME = _fund_meta['fund_name']
    TARGET_SIZE = int(_fund_meta['target_nav_eur'])
    VINTAGE = int(_fund_meta['inception_date'][:4])

    with Session(engine) as session:

        # clear existing PE data
        session.query(PEValuationReport).filter_by(fund_id=FUND_ID).delete()
        session.query(PENavHistory).filter_by(fund_id=FUND_ID).delete()
        session.query(PECashFlow).filter_by(fund_id=FUND_ID).delete()
        session.query(PEFundInvestment).filter_by(fund_id=FUND_ID).delete()
        session.query(PEFund).filter_by(fund_id=FUND_ID).delete()
        session.query(PEFundCashManagement).filter_by(fund_id=FUND_ID).delete()

        for c in COMPANIES:
            session.query(PEPortfolioCompany).filter_by(
                company_id=c['company_id']).delete()
        session.commit()

        # PE fund metadata
        session.add(PEFund(
            fund_id               = FUND_ID,
            fund_name             = FUND_NAME,
            vintage_year          = VINTAGE,
            target_size_eur       = TARGET_SIZE,
            investment_period_end = INV_PERIOD_END,
            fund_life_years       = FUND_LIFE,
            currency              = 'EUR',
            domicile              = 'Luxembourg',
            strategy              = 'Buyout',
        ))

        # portfolio companies and fund investments
        for c in COMPANIES:
            session.add(PEPortfolioCompany(
                company_id       = c['company_id'],
                company_name     = c['company_name'],
                sector           = c['sector'],
                country          = c['country'],
                investment_stage = c['investment_stage'],
                status           = c['status'],
            ))
            session.add(PEFundInvestment(
                fund_id         = FUND_ID,
                company_id      = c['company_id'],
                investment_date = c['investment_date'],
                entry_ev_ebitda = c['entry_ev_ebitda'],
                entry_ev_sales  = c['entry_ev_sales'],
                cost_basis_eur  = compute_entry_equity_check(c['company_id']),
                ownership_pct   = c['ownership_pct'],
                exit_date       = c.get('exit_date'),
                exit_price_eur  = c.get('exit_price_eur'),
                exit_multiple   = c.get('exit_multiple'),
            ))


        # valuation reports first - source of truth for NAV
        val_reports = generate_valuation_reports()
        for vr in val_reports:
            session.add(PEValuationReport(**vr))

        for cf in generate_cash_flows(val_reports, use_sub_line=True):
            session.add(PECashFlow(**cf))

        # NAV history derived from appraisal reports
        for nav in generate_nav_history(val_reports):
            session.add(PENavHistory(**nav))

        # fund-level cash management and sub line
        for cm in generate_fund_cash_management(val_reports):
            session.add(PEFundCashManagement(**cm))

        session.commit()


    val_reports = generate_valuation_reports()
    print(f'PE fund {FUND_ID} generated successfully.')
    print(f'  Companies         : {len(COMPANIES)}')
    print(f'  Cash flows        : {len(generate_cash_flows())}')
    print(f'  Valuation reports : {len(val_reports)}')
    print(f'  NAV quarters      : {len([n for n in generate_nav_history(val_reports) if n["company_id"] is not None])}')


if __name__ == '__main__':
    generate_pe_fund()