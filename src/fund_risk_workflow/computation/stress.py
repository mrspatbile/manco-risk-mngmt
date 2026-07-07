"""
stress.py
=========
Pure stress scenario computation module.

All stress functions are stateless, depend only on numpy/pandas, and require
no database access, file I/O, or external services.

Scope
-----
This module contains scenario analysis for market stress events:
- Equity crashes (parallel shock to all equity positions)
- Rate shifts (duration-convexity approximation)
- Credit spread widening
- FX depreciation
- Combined multi-factor stress
- Historical scenarios (2008 GFC, 2011 sovereign, 2020 Covid, 2022 rates)
- Property value declines
- Rental income compression
- LTV covenant breach

Functions
---------
    stress_equity()         Equity market crash scenario
    stress_rates()          Parallel rate shift scenario
    stress_credit()         Credit spread widening scenario
    stress_fx()             FX depreciation scenario
    stress_combined()       Multi-factor combined scenario
    stress_historical()     Named historical scenario (2008, 2011, 2020, 2022)
    stress_property()       Direct property value decline
    stress_rental()         Rental income compression
    stress_ltv()            LTV covenant breach test
"""

import numpy as np
import pandas as pd

from fund_risk_workflow.data.reference_data import load_historical_scenarios

HISTORICAL_SCENARIOS = load_historical_scenarios()


def stress_equity(
    positions: pd.DataFrame,
    delta_equity: float = -0.30
) -> dict:
    """
    Equity stress scenario.
    Applies a parallel shift to all equity positions.

    ΔP = beta * delta_equity * market_value_eur

    Parameters
    ----------
    positions : pd.DataFrame
        Enriched positions with columns:
        asset_class, beta, market_value_eur
    delta_equity : float
        Equity market shock. Default -0.30 (-30%).

    Returns
    -------
    dict with keys:
        stressed_pnl_eur : total P&L in EUR
        stressed_nav_pct : stressed return as % of NAV
        by_position      : pd.DataFrame with position-level P&L

    Examples
    --------
    >>> result = stress_equity(positions, delta_equity=-0.30)
    >>> print(f'Equity crash P&L: {result["stressed_pnl_eur"]:,.0f}')
    """
    eq = positions[
        positions['asset_class'].isin(['Equity', 'Real Estate'])
    ].copy()

    eq['beta']           = eq['beta'].fillna(1.0)
    eq['stressed_pnl']   = (
        eq['beta'] * delta_equity * eq['market_value_eur'])

    nav = positions['market_value_eur'].sum()

    return {
        'scenario'        : f'Equity {delta_equity*100:.0f}%',
        'stressed_pnl_eur': float(eq['stressed_pnl'].sum()),
        'stressed_nav_pct': float(
            eq['stressed_pnl'].sum() / nav * 100),
        'by_position'     : eq[[
            'instrument_name', 'asset_class',
            'market_value_eur', 'beta', 'stressed_pnl'
        ]],
    }


def stress_rates(
    positions: pd.DataFrame,
    delta_y: float = 0.02
) -> dict:
    """
    Parallel rate shift stress scenario.
    Uses duration-convexity approximation.

    ΔP = -D * Δy * MV + ½ * C * Δy² * MV

    Parameters
    ----------
    positions : pd.DataFrame
        Enriched positions with columns:
        asset_class, dur_adj_mid, convexity, market_value_eur
    delta_y : float
        Rate shock in decimal. Default 0.02 (+200bps).

    Returns
    -------
    dict with keys:
        stressed_pnl_eur, stressed_nav_pct, by_position

    Examples
    --------
    >>> result = stress_rates(positions, delta_y=0.02)
    >>> print(f'Rate shock P&L: {result["stressed_pnl_eur"]:,.0f}')
    """
    bonds = positions[
        positions['asset_class'].isin(
            ['Bond', 'Loan', 'CLO'])
    ].copy()

    bonds['dur_adj_mid'] = bonds['dur_adj_mid'].fillna(0.0)
    bonds['convexity']   = bonds['convexity'].fillna(0.0)

    bonds['stressed_pnl'] = (
        -bonds['dur_adj_mid'] * delta_y *
        bonds['market_value_eur'] +
        0.5 * bonds['convexity'] * delta_y**2 *
        bonds['market_value_eur']
    )

    nav = positions['market_value_eur'].sum()

    return {
        'scenario'        : f'Rates {delta_y*100:+.0f}bps',
        'stressed_pnl_eur': float(bonds['stressed_pnl'].sum()),
        'stressed_nav_pct': float(
            bonds['stressed_pnl'].sum() / nav * 100),
        'by_position'     : bonds[[
            'instrument_name', 'asset_class',
            'market_value_eur', 'dur_adj_mid',
            'convexity', 'stressed_pnl'
        ]],
    }


def stress_credit(
    positions: pd.DataFrame,
    delta_spread: float = 0.03
) -> dict:
    """
    Credit spread stress scenario.

    ΔP = -D_spread * delta_spread * MV

    Uses dur_adj_mid as proxy for spread duration
    when specific spread duration is not available.

    Parameters
    ----------
    positions : pd.DataFrame
        Enriched positions with columns:
        asset_class, dur_adj_mid, market_value_eur
    delta_spread : float
        Credit spread shock in decimal. Default 0.03 (+300bps).

    Returns
    -------
    dict with keys:
        stressed_pnl_eur, stressed_nav_pct, by_position

    Examples
    --------
    >>> result = stress_credit(positions, delta_spread=0.03)
    """
    credit = positions[
        positions['asset_class'].isin(
            ['Bond', 'Loan', 'CLO'])
    ].copy()

    credit = credit[
        ~credit['sub_asset_class'].isin(
            ['Government', 'Government Bond'])
    ].copy()

    credit['dur_adj_mid']  = credit['dur_adj_mid'].fillna(0.0)
    credit['stressed_pnl'] = (
        -credit['dur_adj_mid'] * delta_spread *
        credit['market_value_eur']
    )

    nav = positions['market_value_eur'].sum()

    return {
        'scenario'        : f'Credit +{delta_spread*100:.0f}bps',
        'stressed_pnl_eur': float(credit['stressed_pnl'].sum()),
        'stressed_nav_pct': float(
            credit['stressed_pnl'].sum() / nav * 100),
        'by_position'     : credit[[
            'instrument_name', 'asset_class',
            'market_value_eur', 'dur_adj_mid', 'stressed_pnl'
        ]],
    }


def stress_fx(
    positions: pd.DataFrame,
    fx_shocks: dict | None = None
) -> dict:
    """
    FX stress scenario.

    ΔP = notional_foreign * delta_fx

    For non-EUR positions: uses market_value_eur as proxy
    for notional exposure.

    Parameters
    ----------
    positions : pd.DataFrame
        Positions with columns: currency, market_value_eur
    fx_shocks : dict, optional
        {currency: shock} e.g. {'USD': -0.10, 'GBP': -0.15}
        Default: USD -10%, GBP -15%, JPY -10%

    Returns
    -------
    dict with keys:
        stressed_pnl_eur, stressed_nav_pct, by_currency

    Examples
    --------
    >>> result = stress_fx(positions,
    ...     fx_shocks={'USD': -0.10, 'GBP': -0.15})
    """
    if fx_shocks is None:
        fx_shocks = {'USD': -0.10, 'GBP': -0.15, 'JPY': -0.10}

    fx_pos = positions[
        positions['currency'] != 'EUR'].copy()

    fx_pos['fx_shock']     = fx_pos['currency'].map(fx_shocks).fillna(0)
    fx_pos['stressed_pnl'] = (
        fx_pos['market_value_eur'] * fx_pos['fx_shock'])

    nav = positions['market_value_eur'].sum()

    by_ccy = fx_pos.groupby('currency').agg(
        market_value_eur=('market_value_eur', 'sum'),
        fx_shock=('fx_shock', 'first'),
        stressed_pnl=('stressed_pnl', 'sum')
    ).reset_index()

    return {
        'scenario'        : 'FX stress',
        'stressed_pnl_eur': float(fx_pos['stressed_pnl'].sum()),
        'stressed_nav_pct': float(
            fx_pos['stressed_pnl'].sum() / nav * 100),
        'by_currency'     : by_ccy,
    }


def stress_combined(
    positions: pd.DataFrame,
    scenario: dict | None = None
) -> dict:
    """
    Combined stress scenario applying multiple shocks
    simultaneously (AIFMD Annex VI requirement).

    Parameters
    ----------
    positions : pd.DataFrame
        Enriched positions DataFrame.
    scenario : dict, optional
        Shock parameters. Default: Annex VI combined scenario.
        Keys: delta_equity, delta_y, delta_spread, fx_shocks

    Returns
    -------
    dict with keys:
        stressed_pnl_eur, stressed_nav_pct,
        equity_pnl, rates_pnl, credit_pnl, fx_pnl

    Examples
    --------
    >>> result = stress_combined(positions, scenario={
    ...     'delta_equity' : -0.20,
    ...     'delta_y'      : 0.01,
    ...     'delta_spread' : 0.015,
    ...     'fx_shocks'    : {'USD': -0.10}
    ... })
    """
    if scenario is None:
        scenario = {
            'delta_equity' : -0.20,
            'delta_y'      : 0.01,
            'delta_spread' : 0.015,
            'fx_shocks'    : {'USD': -0.10, 'GBP': -0.15},
        }

    eq_res  = stress_equity(
        positions, scenario.get('delta_equity', -0.20))
    rate_res = stress_rates(
        positions, scenario.get('delta_y', 0.01))
    cr_res  = stress_credit(
        positions, scenario.get('delta_spread', 0.015))
    fx_res  = stress_fx(
        positions, scenario.get('fx_shocks'))

    total_pnl = (
        eq_res['stressed_pnl_eur'] +
        rate_res['stressed_pnl_eur'] +
        cr_res['stressed_pnl_eur'] +
        fx_res['stressed_pnl_eur']
    )
    nav = positions['market_value_eur'].sum()

    return {
        'scenario'        : 'Combined stress',
        'stressed_pnl_eur': float(total_pnl),
        'stressed_nav_pct': float(total_pnl / nav * 100),
        'equity_pnl'      : eq_res['stressed_pnl_eur'],
        'rates_pnl'       : rate_res['stressed_pnl_eur'],
        'credit_pnl'      : cr_res['stressed_pnl_eur'],
        'fx_pnl'          : fx_res['stressed_pnl_eur'],
    }


def stress_historical(
    positions: pd.DataFrame,
    scenario: str = '2020'
) -> dict:
    """
    Historical stress scenario using predefined factor shocks
    from actual stress periods.

    Available scenarios:
    - '2008' : GFC Sep-Dec 2008
    - '2011' : EU Sovereign Debt Crisis 2011
    - '2020' : Covid Feb-Mar 2020
    - '2022' : Rate shock Jan-Dec 2022

    Parameters
    ----------
    positions : pd.DataFrame
        Enriched positions DataFrame.
    scenario : str
        Scenario name. Default '2020'.

    Returns
    -------
    dict with keys:
        stressed_pnl_eur, stressed_nav_pct,
        equity_pnl, rates_pnl, credit_pnl

    Examples
    --------
    >>> result = stress_historical(positions, scenario='2008')
    """
    if scenario not in HISTORICAL_SCENARIOS:
        raise ValueError(
            f'Unknown scenario: {scenario}. '
            f'Choose from {list(HISTORICAL_SCENARIOS.keys())}')

    params = HISTORICAL_SCENARIOS[scenario]
    result = stress_combined(positions, params)
    result['scenario'] = params['name']

    return result


def stress_property(
    positions: pd.DataFrame,
    delta_value_by_type: dict | None = None
) -> dict:
    """
    Real estate property value stress scenario.
    Applied to direct property holdings only.

    ΔP = delta_property_value * market_value_eur

    Parameters
    ----------
    positions : pd.DataFrame
        Enriched positions with columns:
        is_direct_property, property_type, market_value_eur
    delta_value_by_type : dict, optional
        {property_type: shock}
        Default: Office -20%, Retail -25%,
                 Residential -10%, Logistics -5%

    Returns
    -------
    dict with keys:
        stressed_pnl_eur, stressed_nav_pct, by_property_type

    Examples
    --------
    >>> result = stress_property(positions,
    ...     delta_value_by_type={'Office': -0.25})
    """
    if delta_value_by_type is None:
        delta_value_by_type = {
            'Office'     : -0.20,
            'Retail'     : -0.25,
            'Residential': -0.10,
            'Logistics'  : -0.05,
        }

    direct = positions[
        positions['is_direct_property'] == True].copy()

    if direct.empty:
        return {
            'scenario'        : 'Property value stress',
            'stressed_pnl_eur': 0.0,
            'stressed_nav_pct': 0.0,
            'by_property_type': pd.DataFrame(),
        }

    direct['shock'] = direct['property_type'].map(
        delta_value_by_type).fillna(-0.15)

    direct['stressed_pnl'] = (
        direct['shock'] * direct['market_value_eur']
    )

    nav = positions['market_value_eur'].sum()

    by_type = direct.groupby('property_type').agg(
        market_value_eur=('market_value_eur', 'sum'),
        shock=('shock', 'first'),
        stressed_pnl=('stressed_pnl', 'sum')
    ).reset_index()

    return {
        'scenario'        : 'Property value stress',
        'stressed_pnl_eur': float(direct['stressed_pnl'].sum()),
        'stressed_nav_pct': float(
            direct['stressed_pnl'].sum() / nav * 100),
        'by_property_type': by_type,
    }


def stress_rental(
    positions: pd.DataFrame,
    delta_vacancy: float = 0.10,
    delta_yield: float = -0.005
) -> dict:
    """
    Real estate rental income stress scenario.
    Applied to direct property holdings only.

    ΔIncome = (delta_vacancy + delta_yield) * market_value_eur

    Parameters
    ----------
    positions : pd.DataFrame
        Enriched positions with is_direct_property flag.
    delta_vacancy : float
        Vacancy rate increase in percentage points.
        Default 0.10 (+10pp).
    delta_yield : float
        Rental yield compression in decimal.
        Default -0.005 (-50bps).

    Returns
    -------
    dict with keys:
        stressed_pnl_eur, stressed_nav_pct, by_position

    Examples
    --------
    >>> result = stress_rental(positions,
    ...     delta_vacancy=0.10, delta_yield=-0.005)
    """
    direct = positions[
        positions['is_direct_property'] == True].copy()

    if direct.empty:
        return {
            'scenario'        : 'Rental income stress',
            'stressed_pnl_eur': 0.0,
            'stressed_nav_pct': 0.0,
            'by_position'     : pd.DataFrame(),
        }

    direct['stressed_pnl'] = (
        (-delta_vacancy + delta_yield) *
        direct['market_value_eur']
    )

    nav = positions['market_value_eur'].sum()

    return {
        'scenario'        : (f'Rental stress: vacancy '
                             f'+{delta_vacancy*100:.0f}pp, '
                             f'yield {delta_yield*100:+.0f}bps'),
        'stressed_pnl_eur': float(direct['stressed_pnl'].sum()),
        'stressed_nav_pct': float(
            direct['stressed_pnl'].sum() / nav * 100),
        'by_position'     : direct[[
            'instrument_name', 'property_type',
            'market_value_eur', 'stressed_pnl'
        ]],
    }


def stress_ltv(
    positions: pd.DataFrame,
    delta_property_value: float = -0.20,
    ltv_threshold: float = 0.75
) -> dict:
    """
    LTV covenant breach stress scenario.
    Tests whether a property value decline causes LTV
    to breach the covenant threshold.

    Parameters
    ----------
    positions : pd.DataFrame
        Enriched positions with ltv_pct column.
    delta_property_value : float
        Property value decline. Default -0.20 (-20%).
    ltv_threshold : float
        LTV covenant threshold. Default 0.75 (75%).

    Returns
    -------
    dict with keys:
        n_breaches, breaching_properties, by_position

    Examples
    --------
    >>> result = stress_ltv(positions,
    ...     delta_property_value=-0.20, ltv_threshold=0.75)
    """
    direct = positions[
        positions['is_direct_property'] == True].copy()

    if direct.empty or 'ltv_pct' not in direct.columns:
        return {
            'scenario'            : 'LTV covenant stress',
            'n_breaches'          : 0,
            'breaching_properties': [],
            'by_position'         : pd.DataFrame(),
        }

    direct['ltv_pct_decimal'] = direct['ltv_pct'] / 100
    direct['stressed_ltv']    = (
        direct['ltv_pct_decimal'] / (1 + delta_property_value))
    direct['ltv_breach']      = (
        direct['stressed_ltv'] > ltv_threshold)

    breaching = direct[direct['ltv_breach']]

    return {
        'scenario'            : (f'LTV stress: property '
                                 f'{delta_property_value*100:.0f}%'),
        'n_breaches'          : int(direct['ltv_breach'].sum()),
        'breaching_properties': breaching[
            'instrument_name'].tolist(),
        'by_position'         : direct[[
            'instrument_name', 'property_type',
            'ltv_pct', 'stressed_ltv', 'ltv_breach'
        ]],
    }
