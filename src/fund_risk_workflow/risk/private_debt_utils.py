"""
Private debt risk aggregation utilities.

Pure calculations and DataFrame construction for the closed-ended
AIFM_PrivateDebt monitoring workflow: credit-quality profiles,
concentration views, maturity ladder, credit/rate stress aggregation,
borrower default stress, and closed-ended investor concentration.

No database access, file export, or display logic belongs here.
All monetary outputs are EUR; percentage outputs are in percent
(0-100), not decimals, unless stated otherwise.
"""

import pandas as pd

from fund_risk_workflow.computation.liquidity import investor_concentration
from fund_risk_workflow.computation.stress import (
    HISTORICAL_SCENARIOS,
    stress_combined,
    stress_credit,
    stress_historical,
    stress_rates,
)

# S&P-style rating order used to sort credit-quality tables.
RATING_ORDER = [
    'AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-',
    'BBB+', 'BBB', 'BBB-', 'BB+', 'BB', 'BB-',
    'B+', 'B', 'B-', 'CCC+', 'CCC', 'CCC-', 'CC', 'C', 'D', 'NR',
]

MATURITY_BUCKETS = ['< 1y', '1-3y', '3-5y', '5-7y', '> 7y', 'No stated maturity']


def _validate(risk_df: pd.DataFrame, nav: float) -> None:
    if risk_df is None or risk_df.empty:
        raise ValueError('risk_df is empty — no positions to aggregate')
    if nav is None or nav <= 0:
        raise ValueError(f'NAV must be positive, got {nav}')


def _profile_by(risk_df: pd.DataFrame, nav: float, column: str,
                fill_label: str) -> pd.DataFrame:
    """Aggregate market value by one categorical column into EUR and % NAV."""
    _validate(risk_df, nav)
    df = risk_df.copy()
    df[column] = df[column].fillna(fill_label)
    out = (
        df.groupby(column, dropna=False)
        .agg(market_value_eur=('market_value_eur', 'sum'),
             n_positions=('isin', 'count'))
        .reset_index()
        .sort_values('market_value_eur', ascending=False)
        .reset_index(drop=True)
    )
    out['pct_nav'] = out['market_value_eur'] / nav * 100
    return out


def rating_profile(risk_df: pd.DataFrame, nav: float) -> pd.DataFrame:
    """Credit-quality profile by rating, sorted from strongest to weakest.

    Unrated rows (cash without rating) are labelled 'NR'.
    """
    out = _profile_by(risk_df, nav, 'rating', 'NR')
    out['_order'] = out['rating'].map(
        {r: i for i, r in enumerate(RATING_ORDER)}).fillna(len(RATING_ORDER))
    out = out.sort_values('_order').drop(columns='_order').reset_index(drop=True)
    return out


def seniority_profile(risk_df: pd.DataFrame, nav: float) -> pd.DataFrame:
    """Exposure by seniority / sub-asset class (Senior Secured, CLO tranche, HY, cash)."""
    return _profile_by(risk_df, nav, 'sub_asset_class', 'Other')


def sector_profile(risk_df: pd.DataFrame, nav: float) -> pd.DataFrame:
    """Exposure by borrower sector. Cash/MMF rows have no sector."""
    return _profile_by(risk_df, nav, 'sector', 'Cash & Equivalents')


def country_profile(risk_df: pd.DataFrame, nav: float) -> pd.DataFrame:
    """Exposure by country of risk."""
    return _profile_by(risk_df, nav, 'country', 'Unknown')


def borrower_concentration(risk_df: pd.DataFrame, nav: float) -> pd.DataFrame:
    """Borrower exposure concentration from invested credit positions.

    Uses the full instrument name as the borrower exposure label —
    the position data has no separate borrower master, and the plan
    forbids inventing one. Cash and money-market rows are excluded.
    """
    _validate(risk_df, nav)
    credit = risk_df[
        (risk_df['asset_class'] != 'Cash') & (risk_df['market_value_eur'] > 0)
    ].copy()
    if credit.empty:
        raise ValueError('No invested credit positions found')
    out = (
        credit.groupby('instrument_name')
        .agg(exposure_eur=('market_value_eur', 'sum'))
        .reset_index()
        .sort_values('exposure_eur', ascending=False)
        .reset_index(drop=True)
    )
    out['pct_nav'] = out['exposure_eur'] / nav * 100
    return out


def maturity_ladder(risk_df: pd.DataFrame, nav: float,
                    valuation_date: str) -> pd.DataFrame:
    """Maturity ladder from position-level stated maturities.

    Buckets: < 1y, 1-3y, 3-5y, 5-7y, > 7y, No stated maturity (cash/MMF).
    """
    _validate(risk_df, nav)
    val = pd.Timestamp(valuation_date)
    df = risk_df.copy()
    df['maturity_dt'] = pd.to_datetime(df['maturity'], errors='coerce')
    df['years'] = (df['maturity_dt'] - val).dt.days / 365.25

    def _bucket(y: float) -> str:
        if pd.isna(y):
            return 'No stated maturity'
        if y < 1:
            return '< 1y'
        if y < 3:
            return '1-3y'
        if y < 5:
            return '3-5y'
        if y < 7:
            return '5-7y'
        return '> 7y'

    df['bucket'] = df['years'].map(_bucket)
    out = (
        df.groupby('bucket')
        .agg(market_value_eur=('market_value_eur', 'sum'),
             n_positions=('isin', 'count'))
        .reindex(MATURITY_BUCKETS)
        .dropna(how='all')
        .fillna(0)
        .reset_index()
        .rename(columns={'index': 'bucket'})
    )
    out['pct_nav'] = out['market_value_eur'] / nav * 100
    return out


def credit_stress_assumptions(rmp: dict) -> pd.DataFrame:
    """Tabulate the documented stress assumptions from the risk policy.

    Values are decimals in the policy (0.02 = +200bps) and are kept
    numeric here; display formatting happens in the UI layer.
    """
    scen = rmp.get('stress_scenarios') or {}
    required = ('rate_shock_delta_y', 'credit_spread_delta',
                'recovery_rate_senior_secured')
    missing = [k for k in required if scen.get(k) is None]
    if missing:
        raise ValueError(
            f'risk_policy stress_scenarios missing parameters: {missing}')
    rows = [
        {'parameter': 'Rate shock (parallel shift)',
         'value': scen['rate_shock_delta_y'],
         'unit': 'decimal yield change',
         'source': 'Risk policy (migrated notebook assumption)'},
        {'parameter': 'Credit spread widening',
         'value': scen['credit_spread_delta'],
         'unit': 'decimal spread change',
         'source': 'Risk policy (migrated notebook assumption)'},
        {'parameter': 'Senior secured recovery rate',
         'value': scen['recovery_rate_senior_secured'],
         'unit': 'decimal recovery',
         'source': 'Risk policy (migrated notebook assumption)'},
    ]
    return pd.DataFrame(rows)


def credit_stress_results(risk_df: pd.DataFrame, nav: float,
                          delta_y: float, delta_spread: float) -> pd.DataFrame:
    """Run rate, credit, combined, and historical stresses on the portfolio.

    Returns a numeric DataFrame with scenario, stressed_pnl_eur, pct_nav.
    """
    _validate(risk_df, nav)
    rate = stress_rates(risk_df, delta_y=delta_y)
    credit = stress_credit(risk_df, delta_spread=delta_spread)
    combined = stress_combined(risk_df)
    rows = [
        {'scenario': f'Rate shock {delta_y * 10000:+.0f}bps',
         'stressed_pnl_eur': rate['stressed_pnl_eur']},
        {'scenario': f'Credit widening +{delta_spread * 10000:.0f}bps',
         'stressed_pnl_eur': credit['stressed_pnl_eur']},
        {'scenario': 'Combined (equity, rates, credit, FX)',
         'stressed_pnl_eur': combined['stressed_pnl_eur']},
    ]
    for key in HISTORICAL_SCENARIOS:
        hist = stress_historical(risk_df, key)
        rows.append({'scenario': hist['scenario'],
                     'stressed_pnl_eur': hist['stressed_pnl_eur']})
    out = pd.DataFrame(rows)
    out['pct_nav'] = out['stressed_pnl_eur'] / nav * 100
    return out


def borrower_default_stress(risk_df: pd.DataFrame, nav: float,
                            recovery_rate: float,
                            single_borrower_limit_pct: float = 20.0) -> dict:
    """Single-borrower default stress using the documented recovery assumption.

    Loss = exposure x (1 - recovery_rate). The worst case is the default
    of the largest borrower exposure.

    Returns dict with keys: by_borrower (DataFrame), worst (dict),
    recovery_rate, single_borrower_limit_pct.
    """
    if not 0 <= recovery_rate <= 1:
        raise ValueError(f'recovery_rate must be in [0, 1], got {recovery_rate}')
    by_borrower = borrower_concentration(risk_df, nav)
    by_borrower = by_borrower.rename(columns={'instrument_name': 'borrower'})
    by_borrower['loss_eur'] = by_borrower['exposure_eur'] * (1 - recovery_rate)
    by_borrower['loss_pct_nav'] = by_borrower['loss_eur'] / nav * 100

    worst_row = by_borrower.iloc[0]
    worst = {
        'borrower': worst_row['borrower'],
        'exposure_eur': float(worst_row['exposure_eur']),
        'exposure_pct_nav': float(worst_row['pct_nav']),
        'loss_eur': float(worst_row['loss_eur']),
        'loss_pct_nav': float(worst_row['loss_pct_nav']),
        'limit_breach': bool(worst_row['pct_nav'] > single_borrower_limit_pct),
    }
    return {
        'by_borrower': by_borrower,
        'worst': worst,
        'recovery_rate': recovery_rate,
        'single_borrower_limit_pct': single_borrower_limit_pct,
    }


def closed_ended_investor_concentration(investor_base: pd.DataFrame,
                                        nav: float) -> dict:
    """Ownership/governance concentration indicators for a closed-ended fund.

    Wraps the canonical investor_concentration() ESMA thresholds and adds
    an investor-type breakdown. No redemption stress is derived — the fund
    has no periodic redemption.

    Returns dict with keys: summary (dict), by_investor (DataFrame),
    by_type (DataFrame).
    """
    if investor_base is None or investor_base.empty:
        raise ValueError('investor_base is empty')
    if nav is None or nav <= 0:
        raise ValueError(f'NAV must be positive, got {nav}')
    total_pct = investor_base['nav_pct'].sum()
    if abs(total_pct - 1.0) > 1e-6:
        raise ValueError(
            f'Investor weights must sum to 100%, got {total_pct * 100:.4f}%')

    conc = investor_concentration(investor_base, nav)
    by_type = (
        investor_base.groupby('investor_type')
        .agg(aum_eur=('aum_eur', 'sum'), n_investors=('investor_id', 'count'))
        .reset_index()
        .sort_values('aum_eur', ascending=False)
        .reset_index(drop=True)
    )
    by_type['pct_nav'] = by_type['aum_eur'] / nav * 100

    summary = {
        'largest_investor_pct': conc['largest_investor_pct'],
        'top3_pct': conc['top3_pct'],
        'concentration_flag': conc['concentration_flag'],
        'high_concentration': conc['high_concentration'],
    }
    return {
        'summary': summary,
        'by_investor': conc['by_investor'],
        'by_type': by_type,
    }
