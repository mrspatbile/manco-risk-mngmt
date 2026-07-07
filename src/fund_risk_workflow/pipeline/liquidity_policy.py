"""Liquidity policy workflow — build and export suggested monitoring blocks.

Creates fund-specific liquidity monitoring policy recommendations from
calibration data, redemption scenarios, and stress test results.
"""

import json
from pathlib import Path


def load_redemption_scenarios_from_rmp(fund_id: str) -> list:
    """Load and filter redemption scenarios from fund RMP.

    Extracts numeric redemption scenarios from risk_policy.json liquidity_monitoring.
    Filters out non-numeric values (e.g., "largest_investor" string marker).
    The display function will compute the actual largest investor scenario.

    Parameters
    ----------
    fund_id : str
        Fund identifier (e.g., 'UCITS_Balanced')

    Returns
    -------
    list of tuples
        [(redemption_pct, scenario_name), ...] with numeric pcts only.
        E.g., [(0.10, 'Normal'), (0.25, 'Large'), (0.50, 'Stress')]
    """
    from fund_risk_workflow.data.reference_data import load_rmp

    rmp = load_rmp(fund_id)
    liq_monitoring = rmp.get('liquidity_monitoring', {})
    scenarios_from_rmp = liq_monitoring.get('redemption_scenarios', [])

    # Filter to numeric scenarios only
    redemption_scenarios = [
        (s['redemption_pct'], s['name'])
        for s in scenarios_from_rmp
        if isinstance(s['redemption_pct'], (int, float))
    ]

    return redemption_scenarios


def build_fund_liquidity_policy(
    fund_id: str,
    engine,
    calibration_inputs: dict,
    scenarios_result: dict,
    valuation_date: str,
) -> dict:
    """Build a liquidity monitoring policy block for a fund.

    Creates a structured policy recommendation based on fund calibration,
    investor scenarios, and NAV. Computes NAV internally from positions.

    Parameters
    ----------
    fund_id : str
        Fund identifier (e.g., 'UCITS_Balanced')
    engine
        Database engine for querying positions.
    calibration_inputs : dict
        Raw calibration data from load_investor_and_calibration_data().
        Requires: contractual_terms, stress_assumptions
    scenarios_result : dict
        Output from compute_redemption_scenarios() with:
        - 'redemption_scenarios': list of scenario dicts
        - 'largest_investor_name', 'largest_investor_pct'
    valuation_date : str
        Valuation date for position query (e.g., '2026-03-31')

    Returns
    -------
    dict
        Liquidity monitoring policy block with:
        - pct_adv, stress_window_days, notice_period_days
        - redemption_scenarios, largest_investor_name/pct
        - _note: summary of calibration
    """
    from fund_risk_workflow.data.database import query_positions
    from fund_risk_workflow.ui.liquidity_calibration_display import suggest_liquidity_policy_block

    # Query positions and compute NAV
    pos = query_positions(engine, fund_id, position_date=valuation_date)
    nav_eur = pos['market_value_eur'].sum()

    # Extract contractual terms (required)
    contractual = calibration_inputs['contractual_terms']
    notice_days = contractual['notice_period_days']

    # Extract stress assumptions (required)
    stress_assumptions = calibration_inputs['stress_assumptions']
    stress_window = stress_assumptions['stress_window_days']

    # Build policy block
    policy = suggest_liquidity_policy_block(
        fund_id,
        scenarios_result,
        nav_eur,
        notice_period_days=notice_days,
        stress_window_days=stress_window,
    )

    return policy


def export_liquidity_policy(
    fund_id: str,
    policy: dict,
    output_dir: str | None = None,
) -> str:
    """Export liquidity monitoring policy to JSON file.

    Parameters
    ----------
    fund_id : str
        Fund identifier (e.g., 'UCITS_Balanced')
    policy : dict
        Policy block from build_fund_liquidity_policy()
    output_dir : str, optional
        Directory to save policy file. If None, uses reference_data/funds/{fund_id}/

    Returns
    -------
    str
        Path to exported file
    """
    if output_dir is None:
        module_dir = Path(__file__).parent
        output_dir = module_dir / f'../../reference_data/funds/{fund_id}'
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / 'suggested_liquidity_policy.json'

    with open(output_file, 'w') as f:
        json.dump(policy, f, indent=2)

    return str(output_file)
