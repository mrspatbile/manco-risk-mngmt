"""
Real estate monitoring workflow.

Orchestrates data loading, enrichment, and computation for the
closed-ended mixed AIFM_RealEstate fund (direct properties, listed
REITs, FX hedge, cash). Produces presentation-ready results consumed by
ui/real_estate_display.py. Performs no display and no file export.
"""

import fund_risk_workflow.risk.real_estate_utils as reu
from fund_risk_workflow.data.database import query_positions
from fund_risk_workflow.data.enrichment import get_risk_ready_df
from fund_risk_workflow.data.reference_data import (
    load_fund_profile,
    load_investor_base,
    load_rmp,
    load_tenant_register,
)
from fund_risk_workflow.risk.esg_utils import build_esg_df
from fund_risk_workflow.risk.leverage_computation import (
    compute_granular_leverage_breakdown,
    compute_leverage,
)
from fund_risk_workflow.risk.private_debt_utils import (
    closed_ended_investor_concentration,
)

EXPECTED_FUND_ID = 'AIFM_RealEstate'


def build_real_estate_workflow(
    engine,
    bbg,
    fund_id: str,
    valuation_date: str,
) -> dict:
    """Build the real estate risk-monitoring result set.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        Database engine for position and reference queries.
    bbg : MockBloomberg
        Market-data provider used for enrichment-dependent metrics.
    fund_id : str
        Must be 'AIFM_RealEstate'.
    valuation_date : str
        Point-in-time valuation date, e.g. '2026-03-31'.

    Returns
    -------
    dict with keys:
        rmp, profile, positions, risk_df, nav,
        sleeve_summary, direct_property_profile,
        leverage, granular_leverage,
        stress_assumptions, stress_results, ltv_stress,
        investor_base, investor_concentration,
        tenant_register, tenant_concentration, tenant_default_stress,
        lease_reconciliation, esg_df

    Raises
    ------
    ValueError
        For a wrong fund ID, a date with no positions, nonpositive NAV,
        or a lease register that fails rent reconciliation.
    """
    if fund_id != EXPECTED_FUND_ID:
        raise ValueError(
            f'build_real_estate_workflow expects {EXPECTED_FUND_ID}, '
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

    # Sleeve separation and direct property monitoring
    sleeves = reu.sleeve_summary(risk_df, nav)
    property_profile = reu.direct_property_profile(risk_df, nav)

    # Leverage — same canonical computation as the hedge-fund reference
    leverage = compute_leverage(risk_df, nav, bbg, fund_id)
    granular_leverage = compute_granular_leverage_breakdown(
        leverage['risk_df'], nav)

    # Property, rental, rate, and LTV stress from documented policy assumptions
    stress_assumptions = reu.property_stress_assumptions(rmp)
    stress_results = reu.property_stress_results(risk_df, nav, rmp)
    ltv_stress = reu.ltv_stress_summary(risk_df, rmp)

    # Closed-ended ownership/governance concentration from the simulated register
    investor_base = load_investor_base(fund_id, nav_eur=nav)
    investor_conc = closed_ended_investor_concentration(investor_base, nav)

    # Simulated lease register linked to the actual property ISINs;
    # reconciliation raises if the linkage breaks
    tenant_register = load_tenant_register(fund_id)
    lease_reconciliation = reu.reconcile_lease_rents(tenant_register, risk_df)
    tenant_conc = reu.tenant_concentration(tenant_register, nav)
    tenant_default = reu.tenant_default_stress(
        tenant_register, nav,
        capitalisation_yield=(
            rmp['stress_scenarios']['tenant_default_capitalisation_yield']),
    )

    # ESG with reference scores for no-ticker instruments (direct properties)
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
        'sleeve_summary': sleeves,
        'direct_property_profile': property_profile,
        'leverage': leverage,
        'granular_leverage': granular_leverage,
        'stress_assumptions': stress_assumptions,
        'stress_results': stress_results,
        'ltv_stress': ltv_stress,
        'investor_base': investor_base,
        'investor_concentration': investor_conc,
        'tenant_register': tenant_register,
        'tenant_concentration': tenant_conc,
        'tenant_default_stress': tenant_default,
        'lease_reconciliation': lease_reconciliation,
        'esg_df': esg_df,
    }
