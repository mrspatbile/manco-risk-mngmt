"""
PE buyout monitoring workflow.

Orchestrates data loading and computation for the closed-ended
AIFM_PE_Buyout fund from the populated PE database tables. Produces
presentation-ready results consumed by ui/pe_buyout_display.py.
Performs no display, no file export, and never calls data generators.
"""

import pandas as pd

import fund_risk_workflow.risk.pe_utils as peu
# Waterfall economics: the same constants that produced the stored PE
# cash flows. Imported as configuration; no generator function is called.
from fund_risk_workflow.data.generate_pe_fund import CARRY_RATE, HURDLE_RATE
from fund_risk_workflow.data.reference_data import load_fund_profile, load_rmp
from fund_risk_workflow.risk.esg_utils import build_private_esg_df

EXPECTED_FUND_ID = 'AIFM_PE_Buyout'
PME_BENCHMARK = 'SX5E Index'

PE_SECTIONS = (
    "identification", "sector_exposure", "country_exposure",
    "stage_exposure", "top5_positions", "leverage_detail",
    "performance", "aifmd_ii_disclosure",
)


def build_pe_buyout_workflow(
    engine,
    bbg,
    fund_id: str,
    valuation_date: str,
    quarter: str,
) -> dict:
    """Build the PE buyout risk-monitoring result set.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        Database engine for the populated PE tables.
    bbg : MockBloomberg
        Market-data provider used only for the cached PME benchmark
        series (cache-only path from the first actual cash-flow date).
    fund_id : str
        Must be 'AIFM_PE_Buyout'.
    valuation_date : str
        Point-in-time valuation date, e.g. '2026-03-31'.
    quarter : str
        Reporting quarter end used for appraisals and ESG.

    Returns
    -------
    dict with keys:
        rmp, profile, fund, portfolio_companies, valuations,
        cash_flows, nav_history, cash_management,
        portfolio_overview, valuation_monitor,
        performance, j_curve, exit_waterfalls,
        cash_summary, value_bridge, commitment_liquidity,
        pme, stress_results, esg_df

    Raises
    ------
    ValueError
        For a wrong fund ID or missing required PE data.
    """
    if fund_id != EXPECTED_FUND_ID:
        raise ValueError(
            f'build_pe_buyout_workflow expects {EXPECTED_FUND_ID}, '
            f'got {fund_id!r}')

    profile = load_fund_profile(fund_id)
    rmp = load_rmp(fund_id)

    # Raw inputs from the populated PE tables
    from sqlalchemy.orm import Session

    from fund_risk_workflow.data.database import (
        PECashFlow,
        PEFund,
        PENavHistory,
        PEPortfolioCompany,
        PEValuationReport,
    )
    with Session(engine) as session:
        fund = session.query(PEFund).filter_by(fund_id=fund_id).first()
        if fund is None:
            raise ValueError(f'PE fund not found in database: {fund_id}')
        portfolio_companies = pd.DataFrame([{
            'company_id': c.company_id, 'company_name': c.company_name,
            'sector': c.sector, 'country': c.country,
            'investment_stage': c.investment_stage, 'status': c.status,
        } for c in session.query(PEPortfolioCompany).all()])
        valuations = pd.DataFrame([{
            'company_id': v.company_id, 'valuation_date': v.valuation_date,
            'appraised_nav_eur': v.appraised_nav_eur,
            'ev_ebitda': v.ev_ebitda, 'appraiser': v.appraiser,
        } for v in session.query(PEValuationReport).filter_by(
            fund_id=fund_id).all()])
        cash_flows = pd.DataFrame([{
            'cash_flow_date': c.cash_flow_date, 'company_id': c.company_id,
            'flow_type': c.flow_type, 'amount_eur': c.amount_eur,
        } for c in session.query(PECashFlow).filter_by(
            fund_id=fund_id).all()])
        nav_history = pd.DataFrame([{
            'nav_date': n.nav_date, 'company_id': n.company_id,
            'nav_eur': n.nav_eur,
        } for n in session.query(PENavHistory).filter_by(
            fund_id=fund_id).all()])

    if valuations.empty or cash_flows.empty or nav_history.empty:
        raise ValueError(f'PE tables are not populated for {fund_id}')

    # Portfolio, valuation, performance
    portfolio_overview = peu.pe_portfolio_overview(engine, fund_id)
    valuation_monitor = peu.pe_covenant_summary(engine, fund_id, quarter)
    performance = {
        'irr': peu.fund_irr(engine, fund_id, as_of_date=valuation_date),
        'multiples': peu.pe_multiples(engine, fund_id,
                                      as_of_date=valuation_date),
        'multiples_by_company': peu.pe_multiples_by_company(
            engine, fund_id, as_of_date=valuation_date),
        'multiples_timeseries': peu.pe_multiples_timeseries(engine, fund_id),
    }
    j_curve = peu.pe_quarterly_cashflow_frame(engine, fund_id)
    exit_waterfalls = peu.pe_exit_waterfalls(
        engine, fund_id, hurdle_rate=HURDLE_RATE, carry_rate=CARRY_RATE)
    cash_summary = peu.pe_cash_management_frame(engine, fund_id)
    value_bridge = peu.pe_value_bridge(engine, fund_id)
    commitment_liquidity = peu.pe_commitment_liquidity(
        engine, fund_id, valuation_date,
        stress_call_pct=(
            rmp['liquidity_stress']['capital_call_stress_pct_of_unfunded']),
    )

    # PME from the local cached benchmark, requested from the first
    # actual cash-flow date so no simulated prefix or network attempt
    lp = peu.pe_lp_cash_flows(engine, fund_id, valuation_date)
    bench = bbg.bdh(PME_BENCHMARK, 'PX_LAST',
                    lp['first_flow_date'], valuation_date)
    prices = bench['PX_LAST'].dropna()
    if prices.empty:
        raise ValueError(
            f'No cached benchmark prices for {PME_BENCHMARK} between '
            f'{lp["first_flow_date"]} and {valuation_date}')
    prices.index = pd.to_datetime(prices.index)
    pme = peu.pme_long_nickels(
        lp['cash_flows'], lp['dates'], prices,
        terminal_nav=lp['terminal_nav'], valuation_date=valuation_date)
    pme['benchmark'] = PME_BENCHMARK
    pme['terminal_nav'] = lp['terminal_nav']

    stress_results = peu.pe_stress_scenarios(
        engine, fund_id, quarter, params=rmp['stress_scenarios'])

    esg_df = build_private_esg_df(fund_id, quarter, 'pe', engine)

    return {
        'rmp': rmp,
        'profile': profile,
        'fund': fund,
        'portfolio_companies': portfolio_companies,
        'valuations': valuations,
        'cash_flows': cash_flows,
        'nav_history': nav_history,
        'cash_management': cash_summary,
        'portfolio_overview': portfolio_overview,
        'valuation_monitor': valuation_monitor,
        'performance': performance,
        'j_curve': j_curve,
        'exit_waterfalls': exit_waterfalls,
        'cash_summary': cash_summary,
        'value_bridge': value_bridge,
        'commitment_liquidity': commitment_liquidity,
        'pme': pme,
        'stress_results': stress_results,
        'esg_df': esg_df,
    }
