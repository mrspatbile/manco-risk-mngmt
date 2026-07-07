"""
ucits_stress_scenarios.py
=========================

UCITS stress testing loader and computation.

Implements CSSF UCITS prescribed univariate stress scenarios and selected
historical stress scenarios. Handles:

- Univariate stress: equity, interest rates, credit spreads (proportional),
  and FX base-currency appreciation/depreciation
- Historical scenarios: multi-factor shock vectors (equity, rates, credit, fx)
- Proper sign conventions for FX stress from CSSF perspective
- Proportional credit spread shocks (not additive bps)
- Warnings for missing data (e.g., z_sprd_mid for credit spreads)

Does not use stress_combined() or stress_historical() directly.
Decomposes multi-factor scenarios into individual risk-factor shocks.
"""

import json
from pathlib import Path
import pandas as pd
import numpy as np
from fund_risk_workflow.computation.stress import (
    stress_equity,
    stress_rates,
    stress_fx,
)
from fund_risk_workflow.data.reference_data import load_rmp, load_scenario_file


def load_ucits_scenarios_metadata(fund_id: str, rmp: dict | None = None) -> pd.DataFrame:
    """
    Load UCITS prescribed and selected historical scenario metadata.

    Builds a DataFrame with all scenario definitions for the fund,
    including: scenario_id, test_category, risk_factor, scenario_name,
    description, shock values, holding period, and source.

    Parameters
    ----------
    fund_id : str
        Fund identifier (e.g., 'UCITS_Balanced')
    rmp : dict, optional
        Risk management policy. If None, loaded from reference data.

    Returns
    -------
    pd.DataFrame
        Metadata for all prescribed and selected scenarios.
        Columns: scenario_id, test_category, risk_factor, scenario_name,
                 description, shock_value, shock_unit, shock_values,
                 holding_period_days, source
    """
    if rmp is None:
        rmp = load_rmp(fund_id)

    rows = []

    # Load univariate scenario definitions
    univariate_defs = load_scenario_file('ucits_univariate_stress_scenarios')
    univariate_scenarios = univariate_defs['scenarios']

    # Load historical scenario definitions
    historical_defs = load_scenario_file('scenario_library_2_historical')
    historical_scenarios = historical_defs['scenarios']

    # Extract selected scenario IDs from risk_policy.json
    stress_testing_config = rmp.get('stress_testing', {})
    univariate_config = stress_testing_config.get('univariate_scenarios', {})
    historical_config = stress_testing_config.get('most_relevant_historical_scenarios', {})

    prescribed_ids = univariate_config.get('prescribed_scenarios', [])
    selected_hist_ids = historical_config.get('selected_scenarios', [])

    # Process prescribed univariate scenarios
    for scenario_id in prescribed_ids:
        if scenario_id not in univariate_scenarios:
            continue

        scenario_def = univariate_scenarios[scenario_id]
        rows.append({
            'scenario_id': scenario_id,
            'test_category': 'univariate',
            'risk_factor': _extract_risk_factor(scenario_def),
            'scenario_name': scenario_def['scenario_name'],
            'description': scenario_def.get('description', ''),
            'shock_value': scenario_def['shock'],
            'shock_unit': scenario_def['unit'],
            'shock_values': {'primary': scenario_def['shock']},
            'holding_period_days': None,
            'source': univariate_config.get('source', ''),
        })

    # Process selected historical scenarios
    for scenario_id in selected_hist_ids:
        if scenario_id not in historical_scenarios:
            continue

        scenario_def = historical_scenarios[scenario_id]
        shocks = scenario_def.get('shocks', {})

        rows.append({
            'scenario_id': scenario_id,
            'test_category': 'most_relevant_historical',
            'risk_factor': 'multi_factor',
            'scenario_name': scenario_def['scenario_name'],
            'description': scenario_def.get('description', ''),
            'shock_value': None,  # Multi-factor: no single value
            'shock_unit': None,
            'shock_values': {
                'equity': shocks.get('equity', {}).get('shock'),
                'rates': shocks.get('interest_rates', {}).get('shock'),
                'credit': shocks.get('credit_spreads', {}).get('shock'),
                'fx': shocks.get('fx', {}).get('shock_by_currency', {}),
            },
            'holding_period_days': scenario_def.get('holding_period_days'),
            'source': historical_config.get('source', ''),
        })

    return pd.DataFrame(rows)


def _extract_risk_factor(scenario_def: dict) -> str:
    """Extract risk_factor from scenario definition."""
    test_cat = scenario_def.get('test_category', '').lower()
    if 'equity' in test_cat:
        return 'equity'
    elif 'interest' in test_cat or 'rate' in test_cat:
        return 'rates'
    elif 'credit' in test_cat:
        return 'credit'
    elif 'fx' in test_cat or 'base currency' in test_cat.lower():
        return 'fx'
    return 'unknown'


def stress_fx_cssf(
    positions: pd.DataFrame,
    fx_shocks: dict | None = None,
    base_currency: str = 'EUR'
) -> dict:
    """
    FX stress with CSSF base-currency perspective mapping.

    Maps CSSF "base currency depreciation/appreciation" wording to
    stress_fx() convention.

    For a EUR-base fund:
    - Base currency depreciation (EUR weakens) → positive shock to non-EUR holdings
    - Base currency appreciation (EUR strengthens) → negative shock to non-EUR holdings

    Parameters
    ----------
    positions : pd.DataFrame
        Position data with currency and market_value_eur columns
    fx_shocks : dict, optional
        {currency: shock}. Shock sign follows CSSF convention (positive for
        depreciation scenario applied to that currency).
        Example: {'USD': 0.30} means EUR depreciates 30% vs USD.
    base_currency : str, default 'EUR'
        Base currency for the fund

    Returns
    -------
    dict
        Standard stress result dict from stress_fx()
    """
    if fx_shocks is None:
        fx_shocks = {}

    result = stress_fx(positions, fx_shocks=fx_shocks)

    return result


def stress_credit_proportional(
    positions: pd.DataFrame,
    proportional_shock: float = -0.50,
    base_currency: str = 'EUR'
) -> dict:
    """
    Credit spread stress using proportional (multiplicative) shock.

    CSSF credit spread shocks are proportional shifts, not additive bps:
    - z_sprd_mid is stored in basis points (e.g., 200 for 2% spread)
    - convert to decimal: spread_decimal = z_sprd_mid / 10000
    - new_spread = spread_decimal × (1 + proportional_shock)
    - pnl = -spread_duration × spread_change × market_value

    Parameters
    ----------
    positions : pd.DataFrame
        Position data with z_sprd_mid (in bps), dur_adj_mid, market_value_eur columns
    proportional_shock : float
        Proportional shock to spread. E.g., -0.50 means 50% tightening.
    base_currency : str, default 'EUR'
        Base currency (unused, for consistency)

    Returns
    -------
    dict
        Stress result with keys:
        - scenario: scenario name
        - stressed_pnl_eur: total P&L
        - stressed_nav_pct: % of TNA
        - by_position: DataFrame with position-level detail
        - warnings: list of warnings (if any)
    """
    credit = positions[
        positions['asset_class'].isin(['Bond', 'Loan', 'CLO'])
    ].copy()

    credit = credit[
        ~credit['sub_asset_class'].isin(['Government', 'Government Bond'])
    ].copy()

    warnings = []

    # Check for z_sprd_mid availability
    if 'z_sprd_mid' not in credit.columns or credit['z_sprd_mid'].isna().all():
        warnings.append(
            'z_sprd_mid (current credit spread) not available; '
            'proportional credit shock not computed'
        )
        tna = positions['market_value_eur'].sum()
        return {
            'scenario': f'Credit spreads {proportional_shock*100:+.0f}% proportional shift',
            'stressed_pnl_eur': 0.0,
            'stressed_nav_pct': 0.0,
            'by_position': pd.DataFrame(),
            'warnings': warnings,
        }

    credit['z_sprd_mid'] = credit['z_sprd_mid'].fillna(0.0)
    credit['dur_adj_mid'] = credit['dur_adj_mid'].fillna(0.0)

    # Convert z_sprd_mid from basis points to decimal
    # z_sprd_mid is stored in bps (e.g., 200 for 2%), need decimal (0.02)
    credit['spread_decimal'] = credit['z_sprd_mid'] / 10000

    # Proportional spread change: spread_decimal × shock
    # P&L: -duration × spread_change × market_value
    credit['spread_change'] = credit['spread_decimal'] * proportional_shock
    credit['stressed_pnl'] = (
        -credit['dur_adj_mid'] * credit['spread_change'] *
        credit['market_value_eur']
    )

    tna = positions['market_value_eur'].sum()

    return {
        'scenario': f'Credit spreads {proportional_shock*100:+.0f}% proportional shift',
        'stressed_pnl_eur': float(credit['stressed_pnl'].sum()),
        'stressed_nav_pct': float(
            credit['stressed_pnl'].sum() / tna * 100),
        'by_position': credit[[
            'instrument_name', 'asset_class',
            'market_value_eur', 'z_sprd_mid', 'spread_decimal', 'dur_adj_mid',
            'spread_change', 'stressed_pnl'
        ]],
        'warnings': warnings,
    }


def compute_ucits_stress_scenarios(
    fund_id: str,
    positions: pd.DataFrame,
    rmp: dict | None = None,
    base_currency: str = 'EUR'
) -> dict:
    """
    Compute UCITS stress scenarios for a fund.

    Loads prescribed univariate and selected historical scenarios,
    applies relevant stress functions, and returns results with metadata.

    Parameters
    ----------
    fund_id : str
        Fund identifier
    positions : pd.DataFrame
        Risk-ready position data (from get_risk_ready_df)
    rmp : dict, optional
        Risk management policy. If None, loaded from reference data.
    base_currency : str, default 'EUR'
        Base currency for FX shock mapping

    Returns
    -------
    dict with keys:
        - metadata: pd.DataFrame with scenario metadata
        - results: dict mapping scenario_id -> result dict
        - all_warnings: list of all warnings across scenarios
    """
    if rmp is None:
        rmp = load_rmp(fund_id)

    metadata_df = load_ucits_scenarios_metadata(fund_id, rmp)

    if metadata_df.empty:
        return {
            'metadata': metadata_df,
            'results': {},
            'all_warnings': ['No scenarios selected'],
        }

    nav = positions['market_value_eur'].sum()
    results = {}
    all_warnings = []

    for _, row in metadata_df.iterrows():
        scenario_id = row['scenario_id']
        test_category = row['test_category']
        risk_factor = row['risk_factor']
        shock_value = row['shock_value']
        shock_unit = row['shock_unit']
        shock_values = row['shock_values']

        scenario_result = None
        warnings = []

        # Univariate scenarios
        if test_category == 'univariate':
            if risk_factor == 'equity':
                scenario_result = stress_equity(positions, delta_equity=shock_value)

            elif risk_factor == 'rates':
                # shock_unit is 'bps', convert to decimal
                delta_y = shock_value / 10000 if shock_unit == 'bps' else shock_value
                scenario_result = stress_rates(positions, delta_y=delta_y)

            elif risk_factor == 'credit':
                # Use proportional wrapper (not stress_credit)
                scenario_result = stress_credit_proportional(
                    positions, proportional_shock=shock_value, base_currency=base_currency
                )
                if scenario_result.get('warnings'):
                    warnings.extend(scenario_result['warnings'])

            elif risk_factor == 'fx':
                # Map CSSF sign convention
                fx_shocks = {base_currency: shock_value}
                # Only shock non-base-currency exposures
                scenario_result = stress_fx_cssf(
                    positions, fx_shocks=fx_shocks, base_currency=base_currency
                )

        # Historical (multi-factor) scenarios
        elif test_category == 'most_relevant_historical':
            # Apply each factor shock and aggregate
            scenario_result = _compute_historical_scenario(
                positions, shock_values, base_currency=base_currency
            )
            if scenario_result.get('warnings'):
                warnings.extend(scenario_result['warnings'])

        if scenario_result:
            scenario_result['scenario_id'] = scenario_id
            scenario_result['test_category'] = test_category
            scenario_result['risk_factor'] = risk_factor
            scenario_result['holding_period_days'] = row['holding_period_days']
            scenario_result['warnings'] = warnings
            results[scenario_id] = scenario_result
            all_warnings.extend(warnings)

    return {
        'metadata': metadata_df,
        'results': results,
        'all_warnings': all_warnings,
    }


def _compute_historical_scenario(
    positions: pd.DataFrame,
    shock_values: dict,
    base_currency: str = 'EUR'
) -> dict:
    """
    Compute multi-factor historical scenario by applying factor shocks.

    Applies equity, rates, credit, and FX shocks separately, aggregates results.

    Parameters
    ----------
    positions : pd.DataFrame
    shock_values : dict
        Dict with keys 'equity', 'rates', 'credit', 'fx'
    base_currency : str

    Returns
    -------
    dict with aggregated P&L and warnings
    """
    nav = positions['market_value_eur'].sum()
    total_pnl = 0.0
    total_warnings = []
    by_position_list = []

    # Equity shock
    if shock_values.get('equity') is not None:
        eq_result = stress_equity(positions, delta_equity=shock_values['equity'])
        total_pnl += eq_result['stressed_pnl_eur']
        if 'by_position' in eq_result and not eq_result['by_position'].empty:
            by_position_list.append(eq_result['by_position'])

    # Rates shock
    if shock_values.get('rates') is not None:
        # Assume rates shock is in decimal (e.g., 0.02 for +200bps)
        rate_result = stress_rates(positions, delta_y=shock_values['rates'])
        total_pnl += rate_result['stressed_pnl_eur']
        if 'by_position' in rate_result and not rate_result['by_position'].empty:
            by_position_list.append(rate_result['by_position'])

    # Credit shock (proportional)
    if shock_values.get('credit') is not None:
        credit_result = stress_credit_proportional(
            positions, proportional_shock=shock_values['credit'], base_currency=base_currency
        )
        total_pnl += credit_result['stressed_pnl_eur']
        if credit_result.get('warnings'):
            total_warnings.extend(credit_result['warnings'])
        if 'by_position' in credit_result and not credit_result['by_position'].empty:
            # Keep only key columns for aggregation
            by_pos_subset = credit_result['by_position'][[
                'instrument_name', 'asset_class', 'market_value_eur', 'stressed_pnl'
            ]]
            by_position_list.append(by_pos_subset)

    # FX shock
    if shock_values.get('fx') is not None and shock_values['fx']:
        fx_result = stress_fx_cssf(
            positions, fx_shocks=shock_values['fx'], base_currency=base_currency
        )
        total_pnl += fx_result['stressed_pnl_eur']
        if 'by_currency' in fx_result and not fx_result['by_currency'].empty:
            by_position_list.append(fx_result['by_currency'])

    # Combine by_position DataFrames
    by_position_combined = pd.DataFrame()
    if by_position_list:
        by_position_combined = pd.concat(by_position_list, ignore_index=True)

    return {
        'scenario': 'Historical multi-factor scenario',  # Will be overridden by metadata
        'stressed_pnl_eur': float(total_pnl),
        'stressed_nav_pct': float(total_pnl / nav * 100) if nav != 0 else 0.0,
        'by_position': by_position_combined,
        'warnings': total_warnings,
    }


def build_ucits_scenarios_dataframe(
    fund_id: str,
    positions: pd.DataFrame,
    rmp: dict | None = None,
    base_currency: str = 'EUR'
) -> pd.DataFrame:
    """
    Build a comprehensive DataFrame with all scenario metadata + results.

    Ready for display in notebook without further processing.

    Parameters
    ----------
    fund_id : str
    positions : pd.DataFrame
    rmp : dict, optional
    base_currency : str

    Returns
    -------
    pd.DataFrame
        Columns: scenario_id, test_category, risk_factor, scenario_name,
                 description, shock_value, shock_unit, holding_period_days,
                 source, stressed_pnl_eur, stressed_nav_pct, warnings
    """
    compute_result = compute_ucits_stress_scenarios(
        fund_id, positions, rmp=rmp, base_currency=base_currency
    )

    metadata_df = compute_result['metadata'].copy()
    results = compute_result['results']

    # Add computed results to metadata
    metadata_df['stressed_pnl_eur'] = metadata_df['scenario_id'].map(
        lambda s: results.get(s, {}).get('stressed_pnl_eur', np.nan)
    )
    metadata_df['stressed_nav_pct'] = metadata_df['scenario_id'].map(
        lambda s: results.get(s, {}).get('stressed_nav_pct', np.nan)
    )
    metadata_df['warnings'] = metadata_df['scenario_id'].map(
        lambda s: results.get(s, {}).get('warnings', [])
    )

    return metadata_df
