"""
Infrastructure monitoring workflow.

Orchestrates data loading and computation for the closed-ended
AIFM_Infra_Core fund from the populated infrastructure database tables.
Produces presentation-ready results consumed by
ui/infrastructure_display.py. Performs no display, no file export, and
never calls data generators.
"""

import pandas as pd

import fund_risk_workflow.risk.infra_utils as inu
from fund_risk_workflow.data.reference_data import load_fund_profile, load_rmp
from fund_risk_workflow.risk.esg_utils import build_private_esg_df

EXPECTED_FUND_ID = 'AIFM_Infra_Core'

INFRA_SECTIONS = (
    "identification", "asset_breakdown", "sector_breakdown",
    "country_breakdown", "top5_positions", "leverage_detail",
    "performance",
)


def build_infrastructure_workflow(
    engine,
    fund_id: str,
    valuation_date: str,
    quarter: str,
) -> dict:
    """Build the infrastructure risk-monitoring result set.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        Database engine for the populated infrastructure tables.
    fund_id : str
        Must be 'AIFM_Infra_Core'.
    valuation_date : str
        Point-in-time valuation date, e.g. '2026-03-31'.
    quarter : str
        Reporting quarter end used for appraisals, concentration, and ESG.

    Returns
    -------
    dict with keys:
        rmp, profile, fund, assets, investments, valuations,
        nav_history, portfolio_overview, valuation_summary,
        performance, covenant_monitor, concentration,
        inflation_sensitivity, duration_profile,
        cashflow_profile, cashflow_coverage,
        stress_results, esg_df

    Raises
    ------
    ValueError
        For a wrong fund ID or missing required infrastructure data.
    """
    if fund_id != EXPECTED_FUND_ID:
        raise ValueError(
            f'build_infrastructure_workflow expects {EXPECTED_FUND_ID}, '
            f'got {fund_id!r}')

    profile = load_fund_profile(fund_id)
    rmp = load_rmp(fund_id)

    from sqlalchemy.orm import Session

    from fund_risk_workflow.data.database import (
        InfraAsset,
        InfraFund,
        InfraFundInvestment,
        InfraNavHistory,
        InfraValuationReport,
    )
    with Session(engine) as session:
        fund = session.query(InfraFund).filter_by(fund_id=fund_id).first()
        if fund is None:
            raise ValueError(
                f'Infrastructure fund not found in database: {fund_id}')
        assets = pd.DataFrame([{
            'asset_id': a.asset_id, 'asset_name': a.asset_name,
            'sector': a.sector, 'sub_type': a.sub_type,
            'country': a.country, 'concession_end': a.concession_end,
            'inflation_linkage': a.inflation_linkage,
        } for a in session.query(InfraAsset).all()])
        investments = pd.DataFrame([{
            'asset_id': i.asset_id, 'ownership_pct': i.ownership_pct,
            'committed_equity': i.committed_equity,
            'drawn_equity': i.drawn_equity,
        } for i in session.query(InfraFundInvestment).filter_by(
            fund_id=fund_id).all()])
        valuations = pd.DataFrame([{
            'asset_id': v.asset_id, 'valuation_date': v.valuation_date,
            'implied_equity_eur': v.implied_equity_eur,
            'discount_rate': v.discount_rate,
            'inflation_assumption': v.inflation_assumption,
            'appraiser': v.appraiser,
        } for v in session.query(InfraValuationReport).filter_by(
            fund_id=fund_id).all()])
        nav_rows = pd.DataFrame([{
            'nav_date': n.nav_date, 'asset_id': n.asset_id,
            'nav_eur': n.nav_eur,
        } for n in session.query(InfraNavHistory).filter_by(
            fund_id=fund_id).all()])

    if assets.empty or valuations.empty or nav_rows.empty:
        raise ValueError(
            f'Infrastructure tables are not populated for {fund_id}')

    monitoring = rmp['valuation_monitoring']

    portfolio_overview = inu.infra_portfolio_overview(engine, fund_id,
                                                      quarter)
    valuation_summary = {
        'nav_timeseries': inu.fund_nav_timeseries(engine, fund_id),
        'asset_breakdown': inu.asset_nav_breakdown(engine, fund_id, quarter),
        'discount_rate_movement': inu.discount_rate_movement(
            engine, fund_id, quarter,
            flag_threshold_bps=monitoring['discount_rate_flag_threshold_bps']),
    }

    bench = rmp['performance_benchmark']
    target_irr = (bench['cpi_assumption']
                  + bench['benchmark_spread_bps'] / 10_000)
    irr = inu.infra_irr(engine, fund_id)
    performance = {
        'multiples': inu.infra_multiples(engine, fund_id),
        'irr': irr,
        'target_irr': target_irr,
        'cpi_assumption': bench['cpi_assumption'],
        'benchmark_spread_bps': bench['benchmark_spread_bps'],
        'irr_vs_target': irr - target_irr,
    }

    covenant = {
        'dscr': inu.covenant_monitor(
            engine, fund_id, 'dscr',
            watch_headroom_pct=monitoring['covenant_watch_headroom_pct']),
        'ltv': inu.covenant_monitor(
            engine, fund_id, 'ltv',
            watch_headroom_pct=monitoring['covenant_watch_headroom_pct']),
    }

    concentration = inu.concentration_detail(engine, fund_id, quarter)
    inflation = inu.inflation_sensitivity(engine, fund_id)
    duration = inu.duration_profile(engine, fund_id)
    cashflow_profile = inu.infra_quarterly_cashflow_frame(engine, fund_id)
    coverage = inu.cashflow_coverage(engine, fund_id)
    stress_results = inu.infra_stress_summary(
        engine, fund_id, scenarios=rmp['stress_scenarios']['scenarios'])

    esg_df = build_private_esg_df(fund_id, quarter, 'infra', engine)

    return {
        'rmp': rmp,
        'profile': profile,
        'fund': fund,
        'assets': assets,
        'investments': investments,
        'valuations': valuations,
        'nav_history': nav_rows,
        'portfolio_overview': portfolio_overview,
        'valuation_summary': valuation_summary,
        'performance': performance,
        'covenant_monitor': covenant,
        'concentration': concentration,
        'inflation_sensitivity': inflation,
        'duration_profile': duration,
        'cashflow_profile': cashflow_profile,
        'cashflow_coverage': coverage,
        'stress_results': stress_results,
        'esg_df': esg_df,
    }
