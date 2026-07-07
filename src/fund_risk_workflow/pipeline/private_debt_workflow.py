"""
Private debt monitoring workflow.

Orchestrates data loading, enrichment, and computation for the
closed-ended AIFM_PrivateDebt fund. Produces presentation-ready
results consumed by ui/private_debt_display.py. Performs no display
and no file export.
"""

import pandas as pd

import fund_risk_workflow.risk.private_debt_utils as pdu
from fund_risk_workflow.data.database import query_positions
from fund_risk_workflow.data.enrichment import get_risk_ready_df
from fund_risk_workflow.data.reference_data import (
    load_fund_profile,
    load_investor_base,
    load_rmp,
)
from fund_risk_workflow.risk.esg_utils import build_esg_df
from fund_risk_workflow.risk.leverage_computation import (
    compute_granular_leverage_breakdown,
    compute_leverage,
)

EXPECTED_FUND_ID = 'AIFM_PrivateDebt'


def build_private_debt_workflow(
    engine,
    bbg,
    fund_id: str,
    valuation_date: str,
) -> dict:
    """Build the private debt risk-monitoring result set.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        Database engine for position and reference queries.
    bbg : MockBloomberg
        Market-data provider used for enrichment-dependent metrics.
    fund_id : str
        Must be 'AIFM_PrivateDebt'.
    valuation_date : str
        Point-in-time valuation date, e.g. '2026-03-31'.

    Returns
    -------
    dict with keys:
        rmp, profile, positions, risk_df, nav,
        credit_profile, concentration, maturity_profile,
        leverage, granular_leverage,
        stress_assumptions, stress_results, borrower_default,
        investor_base, investor_concentration, esg_df

    Raises
    ------
    ValueError
        For a wrong fund ID, a date with no positions, or nonpositive NAV.
    """
    if fund_id != EXPECTED_FUND_ID:
        raise ValueError(
            f'build_private_debt_workflow expects {EXPECTED_FUND_ID}, '
            f'got {fund_id!r}')

    profile = load_fund_profile(fund_id)
    if profile['redemption_terms']['structure'] != 'closed_ended':
        raise ValueError(
            f'{fund_id} fund profile is not closed-ended; '
            'this workflow assumes no periodic redemption')

    rmp = load_rmp(fund_id)

    positions = query_positions(engine, fund_id, valuation_date)
    if positions is None or len(positions) == 0:
        raise ValueError(
            f'No positions found for {fund_id} at {valuation_date}')

    risk_df = get_risk_ready_df(engine, fund_id, valuation_date)
    nav = float(risk_df['market_value_eur'].sum())
    if nav <= 0:
        raise ValueError(f'Nonpositive NAV for {fund_id}: {nav}')

    # Credit-quality, concentration, and maturity views
    credit_profile = {
        'rating': pdu.rating_profile(risk_df, nav),
        'seniority': pdu.seniority_profile(risk_df, nav),
    }
    concentration = {
        'sector': pdu.sector_profile(risk_df, nav),
        'country': pdu.country_profile(risk_df, nav),
        'borrower': pdu.borrower_concentration(risk_df, nav),
    }
    maturity_profile = pdu.maturity_ladder(risk_df, nav, valuation_date)

    # Leverage — same canonical computation as the hedge-fund reference
    leverage = compute_leverage(risk_df, nav, bbg, fund_id)
    granular_leverage = compute_granular_leverage_breakdown(
        leverage['risk_df'], nav)

    # Credit and rate stress from documented policy assumptions
    scen = rmp['stress_scenarios']
    stress_assumptions = pdu.credit_stress_assumptions(rmp)
    stress_results = pdu.credit_stress_results(
        risk_df, nav,
        delta_y=scen['rate_shock_delta_y'],
        delta_spread=scen['credit_spread_delta'],
    )
    borrower_default = pdu.borrower_default_stress(
        risk_df, nav,
        recovery_rate=scen['recovery_rate_senior_secured'],
        single_borrower_limit_pct=(
            rmp['concentration_limits_internal']['single_borrower_max_pct']),
    )

    # Closed-ended ownership/governance concentration from the simulated register
    investor_base = load_investor_base(fund_id, nav_eur=nav)
    investor_conc = pdu.closed_ended_investor_concentration(investor_base, nav)

    # ESG with reference scores for no-ticker credit instruments (incl. the
    # explicitly simulated CLO look-through scores)
    esg_df = build_esg_df(
        risk_df, bbg, engine, fund_id, valuation_date,
        use_reference_scores_for_unlisted=True,
    )

    return {
        'rmp': rmp,
        'profile': profile,
        'positions': positions,
        'risk_df': risk_df,
        'nav': nav,
        'credit_profile': credit_profile,
        'concentration': concentration,
        'maturity_profile': maturity_profile,
        'leverage': leverage,
        'granular_leverage': granular_leverage,
        'stress_assumptions': stress_assumptions,
        'stress_results': stress_results,
        'borrower_default': borrower_default,
        'investor_base': investor_base,
        'investor_concentration': investor_conc,
        'esg_df': esg_df,
    }
