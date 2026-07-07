"""
liquidity.py
============
Pure liquidity computation module.

All functions are stateless, depend only on numpy/pandas, and require
no database access, file I/O, or external services.

Scope
-----
This module contains liquidity profiling, liquidity stress testing, and
liquidity-adjusted risk metrics:
- Days to liquidate (position-level)
- Liquidity buckets (ESMA classification)
- Liquidity profile (aggregated by bucket)
- Redemption stress test
- LMT (Liquidity Management Tools) trigger analysis
- Investor concentration
- Liquidity-adjusted VaR

Functions
---------
    days_to_liquidate()        Position-level liquidation timeline
    liquidity_buckets()        ESMA bucket classification
    compute_liquidity_profile() Aggregated liquidity by bucket
    redemption_stress()        Can fund meet redemptions?
    lmt_trigger_analysis()     12-month LMT simulation (gate/swing/suspension)
    investor_concentration()   Top investor % analysis
    liquidity_adjusted_var()   VaR + liquidity cost (LVaR)
"""

import numpy as np
import pandas as pd

from fund_risk_workflow.config import LIQUIDITY_BUCKET_ORDER


def days_to_liquidate(
    positions: pd.DataFrame,
    pct_adv: float = 0.25
) -> pd.DataFrame:
    """
    Estimate days to liquidate each position assuming the
    fund can trade pct_adv of average daily volume per day.

    days_i = market_value_i / (ADV_i * pct_adv)

    Special cases (independent of ADV):
    - Cash: 0 days (immediate)
    - FX forwards: 2 days (OTC T+2 settlement)
    - Listed options/derivatives: 1 day (exchange traded)
    - Direct properties and private loans: infinity

    Parameters
    ----------
    positions : pd.DataFrame
        Positions with columns: market_value_eur, adv_eur,
        asset_class, sub_asset_class, is_direct_property
    pct_adv : float
        Fraction of ADV tradeable per day. Default 0.25.

    Returns
    -------
    pd.DataFrame
        Original positions with added column: days_to_liquidate
    """
    df = positions.copy()

    illiquid_mask = (
        (df.get('is_direct_property', pd.Series(False, index=df.index)) == True) |
        (df['adv_eur'] == 0) |
        (df['adv_eur'].isna())
    )

    df['days_to_liquidate'] = np.where(
        illiquid_mask,
        np.inf,
        df['market_value_eur'].abs() / (df['adv_eur'] * pct_adv)
    )

    df.loc[df['asset_class'] == 'Cash', 'days_to_liquidate'] = 0
    df.loc[df['asset_class'] == 'FX', 'days_to_liquidate'] = 2

    listed_deriv_mask = (
        (df['asset_class'] == 'Derivative') &
        (df.get('sub_asset_class', '') == 'Listed Option')
    )
    df.loc[listed_deriv_mask, 'days_to_liquidate'] = 1

    return df


def liquidity_buckets(
    positions: pd.DataFrame
) -> pd.DataFrame:
    """
    Assign ESMA liquidity buckets based on days to liquidate.

    ESMA standard buckets (ESMA34-39-897):
    - 1 day
    - 2-7 days
    - 8-30 days
    - 31-90 days
    - 91-365 days
    - > 1 year

    Parameters
    ----------
    positions : pd.DataFrame
        Positions with column: days_to_liquidate
        (run days_to_liquidate() first)

    Returns
    -------
    pd.DataFrame
        Original positions with added column: liquidity_bucket

    Examples
    --------
    >>> positions = days_to_liquidate(positions)
    >>> positions = liquidity_buckets(positions)
    >>> print(positions.groupby('liquidity_bucket')[
    ...     'market_value_eur'].sum())
    """
    df = positions.copy()

    bins   = [-np.inf, 1, 7, 30, 90, 365, np.inf]
    labels = [
        '1 day',
        '2-7 days',
        '8-30 days',
        '31-90 days',
        '91-365 days',
        '> 1 year',
    ]

    df['liquidity_bucket'] = pd.cut(
        df['days_to_liquidate'],
        bins=bins,
        labels=labels,
        right=True
    )

    return df


def compute_liquidity_profile(
    risk_df: pd.DataFrame,
    pct_adv: float = 0.25,
) -> dict:
    """
    Compute liquidity profile — ESMA buckets with summary statistics.

    Combines days_to_liquidate() and liquidity_buckets() with aggregation.
    NAV is computed internally from risk_df.

    Parameters
    ----------
    risk_df : pd.DataFrame
        Risk-ready positions with market_value_eur, adv_eur, asset_class columns
    pct_adv : float, optional
        Max % of ADV tradeable per day without market impact. Default 0.25 (25%).

    Returns
    -------
    dict with keys:
        risk_df_liq : pd.DataFrame
            Positions with added columns: days_to_liquidate, liquidity_bucket
        bucket_full : pd.DataFrame
            Liquidity summary by bucket (ESMA standard order)
        nav : float
            Fund NAV computed from risk_df
    """
    nav = risk_df['market_value_eur'].sum()

    risk_df_liq = days_to_liquidate(risk_df, pct_adv=pct_adv)
    risk_df_liq = liquidity_buckets(risk_df_liq)

    bucket_summary = risk_df_liq.groupby('liquidity_bucket').agg(
        market_value_eur=('market_value_eur', 'sum'),
        abs_exposure=('market_value_eur', lambda x: x.abs().sum()),
        n_positions=('isin', 'count')
    ).reset_index()

    bucket_summary['pct_nav_net'] = bucket_summary['market_value_eur'] / nav * 100
    bucket_summary['pct_nav_abs'] = bucket_summary['abs_exposure'] / nav * 100

    bucket_full = bucket_summary.set_index('liquidity_bucket').reindex(LIQUIDITY_BUCKET_ORDER).fillna(0).reset_index()

    return {
        'risk_df_liq': risk_df_liq,
        'bucket_full': bucket_full,
        'nav': nav,
    }


def redemption_stress(
    positions: pd.DataFrame,
    nav: float,
    redemption_pct: float = 0.25,
    notice_days: int = 5
) -> dict:
    """
    Redemption stress test: can the fund meet redemptions
    by selling liquid assets within the notice period?

    liquidity_gap = liquid_assets - redemption_amount
    - positive: fund can meet redemption
    - negative: shortfall, gate or side pocket needed

    Parameters
    ----------
    positions : pd.DataFrame
        Positions with liquidity_bucket column.
        Run days_to_liquidate() and liquidity_buckets() first.
    nav : float
        Fund NAV in EUR.
    redemption_pct : float
        Redemption as fraction of NAV. Default 0.25 (25%).
    notice_days : int
        Notice period in days. Default 5.

    Returns
    -------
    dict with keys:
        redemption_amount_eur : redemption in EUR
        liquid_assets_eur     : assets liquidatable in notice period
        liquidity_gap_eur     : gap (positive = can meet)
        coverage_ratio        : liquid / redemption
        can_meet_redemption   : bool
        recommendation        : action if shortfall

    Examples
    --------
    >>> result = redemption_stress(positions, nav=250e6,
    ...     redemption_pct=0.25, notice_days=5)
    >>> print(result['recommendation'])
    """
    redemption_amount = nav * redemption_pct

    liquid_buckets = ['1 day', '2-7 days']
    if notice_days >= 8:
        liquid_buckets.append('8-30 days')

    liquid_assets = positions[
        positions['liquidity_bucket'].isin(liquid_buckets)
    ]['market_value_eur'].sum()

    liquidity_gap  = liquid_assets - redemption_amount
    coverage_ratio = (liquid_assets / redemption_amount
                      if redemption_amount > 0 else np.inf)

    if liquidity_gap >= 0:
        recommendation = 'Fund can meet redemption'
    elif coverage_ratio >= 0.5:
        recommendation = 'Partial gate recommended'
    else:
        recommendation = ('Full gate or side pocket required '
                          'for illiquid assets')

    return {
        'redemption_pct'      : redemption_pct,
        'redemption_amount_eur': float(redemption_amount),
        'liquid_assets_eur'   : float(liquid_assets),
        'liquidity_gap_eur'   : float(liquidity_gap),
        'coverage_ratio'      : round(float(coverage_ratio), 4),
        'can_meet_redemption' : bool(liquidity_gap >= 0),
        'recommendation'      : recommendation,
    }


def lmt_trigger_analysis(
    nav: float,
    liquid_pct: float,
    gate_threshold: float | None,
    swing_threshold: float | None,
    redemption_schedule: list,
    consecutive_gate_for_suspension: int | None = 3,
    backlog_pct_for_suspension: float      = 0.25,
    swing_factor: float                    = 0.005,
    contagion_multiplier: float            = 1.0,
    apply_contagion: bool                  = True,
) -> dict:
    """
    MRS-84: AIFMD II LMT time-series simulation.

    Simulates 12 months of redemptions for an open-ended fund, modelling
    gate activation, swing pricing, contagion feedback, and suspension
    mechanics per the AIFMD II LMT framework.

    Parameters
    ----------
    nav : float
        Total fund NAV in EUR at month 0.
    liquid_pct : float
        Fraction of NAV in the liquid sleeve (0–1).
    gate_threshold : float or None
        Gate triggers when gross redemption demand exceeds this fraction of
        *total NAV*. Paid redemptions are capped at min(gate_threshold *
        total_nav, liquid_nav); excess is deferred into the backlog.
        If None, gate is disabled and all redemptions are paid immediately.
    swing_threshold : float or None
        Swing pricing activates when the gross (contagion-adjusted) redemption
        rate exceeds this fraction of total NAV.
        If None, swing pricing is disabled.
    redemption_schedule : list of float
        12 base gross redemption requests, each as a fraction of *that
        month's* total NAV before contagion scaling. len >= 12; only first
        12 elements are used.
    consecutive_gate_for_suspension : int or None, default 3
        Number of consecutive months the gate must be active before the
        suspension condition can be evaluated.
        If None, suspension is disabled and suspension_active is always False.
    backlog_pct_for_suspension : float
        Outstanding backlog as a fraction of liquid NAV that must also be
        breached simultaneously for suspension to trigger. Default 0.25 (25%).
    swing_factor : float
        Dilution levy when swing pricing is active (e.g. 0.005 = 50 bps).
        Default 0.005.
    contagion_multiplier : float
        Scaling factor applied to the base redemption schedule in any month
        immediately following a month in which the gate was active.
        Default 1.0 (no contagion). Set to 1.3–1.5 for realistic stress.
    apply_contagion : bool, default True
        If True, apply contagion feedback when conditions are met (gate active in
        previous month and contagion_multiplier != 1.0).
        If False, use base redemption schedule with no feedback amplification.

    Returns
    -------
    dict with keys:
        'df' : pd.DataFrame with 12 rows and columns:
            month                    : period number (1–12)
            base_gross_pct           : raw schedule value before contagion (%)
            effective_gross_pct      : contagion-adjusted gross rate actually used (%)
            effective_gross_eur      : contagion-adjusted gross request in EUR
            paid_eur                 : amount paid to redeeming investors this month
            deferred_eur             : newly deferred from this month's gross request
            backlog_eur              : cumulative unpaid balance carried forward
            gate_active              : bool — gate in force this month
            swing_active             : bool — swing pricing applied this month
            suspension_active        : bool — suspension in force
            consecutive_gate_months  : running count of consecutive gate months
            liquid_nav_eur           : liquid sleeve at end of month
            illiquid_nav_eur         : illiquid sleeve (static)
            total_nav_eur            : liquid + illiquid at end of month
        'gate_threshold' : float or None (from input)
        'swing_threshold' : float or None (from input)
        'consecutive_gate_for_suspension' : int or None (from input)

    Examples
    --------
    >>> schedule = [0.05, 0.08, 0.12, 0.15, 0.10, 0.06,
    ...             0.04, 0.03, 0.02, 0.02, 0.02, 0.01]
    >>> df = lmt_trigger_analysis(
    ...     nav=250e6, liquid_pct=0.70,
    ...     gate_threshold=0.10, swing_threshold=0.05,
    ...     redemption_schedule=schedule,
    ...     contagion_multiplier=1.5)
    """
    liquid_nav      = nav * liquid_pct
    illiquid_nav    = nav * (1.0 - liquid_pct)
    backlog         = 0.0
    consec_gate     = 0
    prev_gate       = False
    rows            = []

    for month in range(1, 13):
        total_nav     = liquid_nav + illiquid_nav
        base_pct      = float(redemption_schedule[month - 1])

        # Contagion: apply only if enabled, previous gate active, and multiplier != 1.0
        if apply_contagion and prev_gate and contagion_multiplier != 1.0:
            eff_pct = min(base_pct * contagion_multiplier, 1.0)
        else:
            eff_pct = base_pct

        eff_eur = eff_pct * total_nav

        # Swing pricing: disabled if swing_threshold is None
        swing_active = swing_threshold is not None and eff_pct > swing_threshold

        # Gate cap: if gate_threshold is None, no cap (allow all payments)
        if gate_threshold is not None:
            contractual_cap = gate_threshold * total_nav
            gate_cap_eur = min(contractual_cap, liquid_nav)
        else:
            gate_cap_eur = liquid_nav  # No gate; pay from available liquid

        total_demand = eff_eur + backlog

        # Suspension: disabled if consecutive_gate_for_suspension is None
        suspension_active = (
            consecutive_gate_for_suspension is not None
            and consec_gate >= consecutive_gate_for_suspension
            and (backlog / liquid_nav if liquid_nav > 0 else 0.0)
                 >= backlog_pct_for_suspension
        )

        if suspension_active:
            paid_eur     = 0.0
            deferred_eur = eff_eur
            gate_active  = True
            consec_gate += 1
        else:
            # Gate only triggers if gate_threshold is defined and demand exceeds cap
            if gate_threshold is not None and total_demand > gate_cap_eur:
                gate_active  = True
                paid_eur     = min(gate_cap_eur, total_demand)
                deferred_eur = max(0.0, eff_eur - max(0.0, gate_cap_eur - backlog))
                consec_gate += 1
            else:
                gate_active  = False
                paid_eur     = total_demand
                deferred_eur = 0.0
                consec_gate  = 0

        prev_gate  = gate_active
        backlog    = max(0.0, total_demand - paid_eur)

        liquid_nav = max(0.0, liquid_nav - paid_eur)

        rows.append({
            'month'                  : month,
            'base_gross_pct'         : round(base_pct * 100, 4),
            'effective_gross_pct'    : round(eff_pct * 100, 4),
            'effective_gross_eur'    : round(eff_eur, 2),
            'paid_eur'               : round(paid_eur, 2),
            'deferred_eur'           : round(deferred_eur, 2),
            'backlog_eur'            : round(backlog, 2),
            'gate_active'            : gate_active,
            'swing_active'           : swing_active,
            'suspension_active'      : suspension_active,
            'consecutive_gate_months': consec_gate,
            'liquid_nav_eur'         : round(liquid_nav, 2),
            'illiquid_nav_eur'       : round(illiquid_nav, 2),
            'total_nav_eur'          : round(liquid_nav + illiquid_nav, 2),
        })

    return {
        'df': pd.DataFrame(rows),
        'gate_threshold': gate_threshold,
        'swing_threshold': swing_threshold,
        'consecutive_gate_for_suspension': consecutive_gate_for_suspension,
    }


def investor_concentration(
    investor_df: pd.DataFrame,
    nav: float,
    threshold: float = 0.20
) -> dict:
    """
    Investor concentration analysis per ESMA guidelines.

    ESMA thresholds:
    - single investor > 20% of NAV: flag as concentration risk
    - top 3 investors > 50% of NAV: flag as high concentration

    Parameters
    ----------
    investor_df : pd.DataFrame
        Investor register with columns:
        investor_id, investor_name, aum_eur
    nav : float
        Fund NAV in EUR.
    threshold : float
        Single investor threshold. Default 0.20 (20%).

    Returns
    -------
    dict with keys:
        largest_investor_pct  : largest investor % of NAV
        top3_pct              : top 3 investors % of NAV
        concentration_flag    : bool
        high_concentration    : bool
        largest_redemption_eur: largest investor AUM in EUR
        by_investor           : pd.DataFrame

    Examples
    --------
    >>> investors = pd.DataFrame({
    ...     'investor_id'  : ['INV001', 'INV002'],
    ...     'investor_name': ['Pension Fund A', 'Insurance B'],
    ...     'aum_eur'      : [50e6, 30e6]
    ... })
    >>> result = investor_concentration(investors, nav=250e6)
    """
    df = investor_df.copy()
    df['pct_nav'] = df['aum_eur'] / nav

    df = df.sort_values('aum_eur', ascending=False)

    largest_pct = float(df['pct_nav'].iloc[0])
    top3_pct    = float(df['pct_nav'].head(3).sum())

    return {
        'largest_investor_pct' : round(largest_pct, 4),
        'top3_pct'             : round(top3_pct, 4),
        'concentration_flag'   : bool(largest_pct > threshold),
        'high_concentration'   : bool(top3_pct > 0.50),
        'largest_redemption_eur': float(df['aum_eur'].iloc[0]),
        'by_investor'          : df[[
            'investor_id', 'investor_name',
            'aum_eur', 'pct_nav'
        ]],
    }


def liquidity_adjusted_var(
    var: float,
    positions: pd.DataFrame,
    stress_multiplier: float = 3.0
) -> dict:
    """
    Liquidity-adjusted VaR (LVaR).
    Add liquidity cost (positions can't be unwound immediately)

    LVaR = VaR + liquidity_cost
    liquidity_cost = ½ * spread * MV * stress_multiplier

    Default spreads by asset class (in decimal):
    - Large cap equity  : 5bps  * 3x  = 15bps stressed
    - IG bonds          : 10bps * 3x  = 30bps stressed
    - HY bonds          : 50bps * 3x  = 150bps stressed
    - Senior loans      : 100bps * 3x = 300bps stressed
    - Listed REITs      : 15bps * 3x  = 45bps stressed
    - Direct properties : 6.5% transaction cost

    Parameters
    ----------
    var : float
        Standard VaR as positive number.
    positions : pd.DataFrame
        Enriched positions with asset_class, market_value_eur.
    stress_multiplier : float
        Global spread stress multiplier. Default 3.0.

    Returns
    -------
    dict with keys:
        var           : standard VaR
        liquidity_cost: total liquidity cost (% NAV)
        lvar          : liquidity-adjusted VaR
        lvar_pct_increase : % increase vs standard VaR
        by_asset_class: breakdown by asset class

    Examples
    --------
    >>> result = liquidity_adjusted_var(
    ...     var=0.025, positions=positions, stress_multiplier=3.0)
    >>> print(f'LVaR: {result["lvar"]:.4f}')
    """
    normal_spreads = {
        'Equity'     : 0.0005,
        'Real Estate': 0.0015,
        'Bond'       : 0.0010,
        'Loan'       : 0.0100,
        'CLO'        : 0.0050,
        'FX'         : 0.0002,
        'Derivative' : 0.0010,
        'Cash'       : 0.0000,
    }

    df = positions.copy()
    df['spread'] = df['asset_class'].map(
        normal_spreads).fillna(0.001)

    if 'is_direct_property' in df.columns:
        df.loc[df['is_direct_property'] == True, 'spread'] = 0.065

    df['liquidity_cost'] = (
        0.5 * df['spread'] * stress_multiplier *
        df['market_value_eur'].abs()
    )

    total_liq_cost = float(df['liquidity_cost'].sum())
    nav            = float(df['market_value_eur'].sum())
    liq_cost_pct   = total_liq_cost / abs(nav) if nav != 0 else 0

    lvar = var + liq_cost_pct

    return {
        'var'           : round(float(var), 6),
        'liquidity_cost': round(float(liq_cost_pct), 6),
        'lvar'          : round(float(lvar), 6),
        'lvar_pct_increase': round(
            float((lvar - var) / var * 100
                  if var > 0 else 0), 2),
        'by_asset_class': df.groupby('asset_class').agg(
            market_value_eur=('market_value_eur', 'sum'),
            liquidity_cost=('liquidity_cost', 'sum')
        ).reset_index(),
    }
