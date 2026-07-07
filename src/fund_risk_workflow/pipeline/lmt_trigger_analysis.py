"""LMT trigger analysis workflow — build parameters and run gate/swing/suspension simulation.

Orchestrates the complete LMT trigger analysis for a single fund:
- Loads LMT parameters from fund calibration
- Computes monthly redemption schedule
- Runs gate, swing pricing, and suspension mechanics
- Returns analysis results for display
"""

import pandas as pd


def build_lmt_analysis_inputs(
    fund_id: str,
    calibration_inputs: dict,
    calibration_config: dict,
) -> dict:
    """Build LMT analysis inputs from fund calibration data.

    Loads LMT parameters and builds redemption schedule for a single fund.

    Parameters
    ----------
    fund_id : str
        Fund identifier (e.g., 'UCITS_Balanced')
    calibration_inputs : dict
        Raw calibration data from load_investor_and_calibration_data().
        Requires: lmt_calibration, contractual_terms, stress_assumptions
    calibration_config : dict
        Normalized calibration config with investor and stress assumptions.
        Requires: investors, stress_months, redemption_concentration, seed

    Returns
    -------
    dict
        LMT analysis inputs:
        - 'lmt_config': dict with liquid_pct, gate_threshold, swing_threshold, etc.
        - 'lmt_params': dict with schedule, contractual_terms, stress_assumptions
        - 'schedule': monthly redemption schedule (list of rates)
    """
    from fund_risk_workflow.data.reference_data import get_lmt_parameters, build_lmt_parameters

    lmt_config = get_lmt_parameters(fund_id, calibration_inputs)
    lmt_params = build_lmt_parameters(fund_id, calibration_inputs, calibration_config)

    return {
        'lmt_config': lmt_config,
        'lmt_params': lmt_params,
        'schedule': lmt_params['schedule'],
    }


def run_lmt_trigger_analysis(
    engine,
    fund_id: str,
    lmt_inputs: dict,
    valuation_date: str,
) -> dict:
    """Run LMT trigger analysis for a single fund.

    Simulates gate, swing pricing, and suspension mechanics over the
    redemption schedule. Queries positions and computes NAV internally.

    Parameters
    ----------
    engine
        Database engine for querying positions.
    fund_id : str
        Fund identifier.
    lmt_inputs : dict
        Output from build_lmt_analysis_inputs().
        Requires: lmt_config, schedule
    valuation_date : str
        Valuation date (e.g., '2026-03-31').

    Returns
    -------
    dict
        Analysis results:
        - 'df_analysis': DataFrame from lmt_trigger_analysis()
        - 'lmt_config': dict with thresholds and parameters
        - 'schedule': monthly redemption schedule
    """
    from fund_risk_workflow.data.database import query_positions
    from fund_risk_workflow.risk.risk_utils import lmt_trigger_analysis

    # Query positions and compute NAV
    pos = query_positions(engine, fund_id, position_date=valuation_date)
    nav = pos['market_value_eur'].sum()

    lmt_config = lmt_inputs['lmt_config']
    schedule = lmt_inputs['schedule']

    lmt_result = lmt_trigger_analysis(
        nav=nav,
        liquid_pct=lmt_config['liquid_pct'],
        gate_threshold=lmt_config['gate_threshold'],
        swing_threshold=lmt_config['swing_threshold'],
        redemption_schedule=schedule,
        consecutive_gate_for_suspension=lmt_config['consec_gate'],
        backlog_pct_for_suspension=lmt_config['backlog_pct'],
        contagion_multiplier=lmt_config['contagion'],
    )

    return {
        'df_analysis': lmt_result['df'],
        'lmt_config': lmt_config,
        'schedule': schedule,
    }


def prepare_scenarios_data(scenarios_result: dict) -> dict:
    """Prepare scenarios data for display.

    Parameters
    ----------
    scenarios_result : dict
        Output from compute_redemption_scenarios().

    Returns
    -------
    dict
        Display-ready scenarios data.
    """
    return {
        'redemption_scenarios': scenarios_result['redemption_scenarios'],
        'largest_investor_name': scenarios_result['largest_investor_name'],
        'largest_investor_pct': scenarios_result['largest_investor_pct'],
    }
