"""
risk_utils.py
=============
Shared risk utility functions for AIFM and UCITS risk notebooks.
Implements VaR, ES, backtesting, stress scenarios and liquidity
functions in compliance with AIFMD, UCITS and ESMA guidelines.

Regulatory context
------------------
    AIFMD        : Directive 2011/61/EU
    UCITS        : Directive 2009/65/EC
    ESMA LST     : ESMA34-39-897 (liquidity stress testing)
    ESMA backt.  : ESMA34-43-392 (VaR backtesting)
    Annex VI     : AIFMD Level 2 stress testing framework

Usage
-----
    from risk_utils import (
        var_historical, var_parametric, var_scale,
        es_historical, es_parametric, es_scale,
        kupiec_test, christoffersen_test,
        exception_report, full_backtest_report,
        stress_equity, stress_rates, stress_credit,
        stress_fx, stress_combined, stress_historical,
        stress_property, stress_rental, stress_ltv,
        days_to_liquidate, liquidity_buckets,
        redemption_stress, investor_concentration,
        liquidity_adjusted_var,
    )
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm, t as student_t
from typing import Optional


# ================================================================
# VaR functions
# ================================================================

def var_historical(
    returns: np.ndarray | pd.Series,
    confidence: float = 0.99
) -> float:
    """
    Historical simulation VaR.
    Sorts actual returns and reads off empirical quantile.
    No distribution assumption.

    Parameters
    ----------
    returns : array-like
        Daily portfolio returns in decimal (e.g. -0.02 for -2%)
    confidence : float
        Confidence level. Default 0.99 (AIFMD standard).

    Returns
    -------
    float
        VaR as positive number (loss convention).
        e.g. 0.025 means 2.5% of NAV at risk.

    Examples
    --------
    >>> returns = np.random.normal(0, 0.01, 250)
    >>> var = var_historical(returns, confidence=0.99)
    >>> print(f'99% VaR: {var:.4f}')
    """
    returns = np.asarray(returns)
    returns = returns[~np.isnan(returns)]
    alpha   = 1 - confidence
    return float(-np.percentile(returns, alpha * 100))


def var_parametric(
    mu: float,
    sigma: float,
    confidence: float = 0.99,
    dist: str = 't',
    df: int = 5
) -> float:
    """
    Parametric VaR under normal or Student-t distribution.

    VaR = -(mu + z_alpha * sigma)

    sigma is an explicit input, agnostic to source:
    - historical rolling volatility
    - risk system output (Bloomberg PORT, Axioma)
    - fund administrator assumption (illiquid assets)

    Parameters
    ----------
    mu : float
        Mean daily return in decimal.
    sigma : float
        Daily volatility in decimal.
    confidence : float
        Confidence level. Default 0.99.
    dist : str
        Distribution: 't' (Student-t) or 'normal'.
        Student-t recommended for fat tails. Default 't'.
    df : int
        Degrees of freedom for Student-t. Default 5.

    Returns
    -------
    float
        VaR as positive number (loss convention).

    Examples
    --------
    >>> var = var_parametric(mu=0.0005, sigma=0.012,
    ...                      confidence=0.99, dist='t', df=5)
    """
    alpha = 1 - confidence
    if dist == 't':
        z = student_t.ppf(alpha, df=df)
    else:
        z = norm.ppf(alpha)
    return float(-(mu + z * sigma))


def var_scale(
    var_1d: float,
    horizon: int = 10
) -> float:
    """
    Scale 1-day VaR to longer horizon using square root of time.

    VaR_Td = VaR_1d * sqrt(T)

    Common horizons:
    - 10 days : Basel III regulatory VaR
    - 20 days : UCITS and AIFMD standard

    Parameters
    ----------
    var_1d : float
        1-day VaR as positive number.
    horizon : int
        Number of trading days. Default 10.

    Returns
    -------
    float
        Scaled VaR as positive number.

    Examples
    --------
    >>> var_10d = var_scale(var_1d=0.025, horizon=10)
    >>> var_20d = var_scale(var_1d=0.025, horizon=20)
    """
    return float(var_1d * np.sqrt(horizon))


# ================================================================
# Expected Shortfall functions
# ================================================================

def es_historical(
    returns: np.ndarray | pd.Series,
    confidence: float = 0.99
) -> float:
    """
    Historical Expected Shortfall (CVaR).
    Mean of all returns that breach the VaR threshold.

    ES_alpha = -E[R | R < -VaR_alpha]

    Not suitable for direct real estate or private debt
    where no daily return history exists. Apply to liquid
    portion only.

    Parameters
    ----------
    returns : array-like
        Daily portfolio returns in decimal.
    confidence : float
        Confidence level. Default 0.99.

    Returns
    -------
    float
        ES as positive number (loss convention).
        Always >= var_historical(returns, confidence).

    Examples
    --------
    >>> returns = np.random.normal(0, 0.01, 250)
    >>> es = es_historical(returns, confidence=0.99)
    """
    returns  = np.asarray(returns)
    returns  = returns[~np.isnan(returns)]
    var      = var_historical(returns, confidence)
    breaches = returns[returns < -var]
    if len(breaches) == 0:
        return var
    return float(-breaches.mean())


def es_parametric(
    sigma: float,
    mu: float = 0.0,
    confidence: float = 0.99,
    dist: str = 't',
    df: int = 5
) -> float:
    """
    Parametric Expected Shortfall.

    Normal distribution:
        ES_alpha = sigma * phi(z_alpha) / (1 - alpha)

    Student-t distribution:
        ES_alpha = sigma * f_t(t_alpha) * (nu + t_alpha^2)
                   / [(nu - 1) * (1 - alpha)]

    Parameters
    ----------
    sigma : float
        Daily volatility in decimal.
    mu : float
        Mean daily return. Default 0.
    confidence : float
        Confidence level. Default 0.99.
    dist : str
        'normal' or 't'. Default 't'.
    df : int
        Degrees of freedom for Student-t. Default 5.

    Returns
    -------
    float
        ES as positive number. Always >= var_parametric.

    Examples
    --------
    >>> es = es_parametric(sigma=0.012, confidence=0.99, dist='t')
    """
    alpha = 1 - confidence

    if dist == 'normal':
        z  = norm.ppf(alpha)
        es = sigma * norm.pdf(z) / alpha
        return float(es - mu)

    else:  # Student-t
        t_alpha = student_t.ppf(alpha, df=df)
        f_t     = student_t.pdf(t_alpha, df=df)
        es      = sigma * f_t * (df + t_alpha**2) / ((df - 1) * alpha)
        return float(es - mu)


def es_scale(
    es_1d: float,
    horizon: int = 10
) -> float:
    """
    Scale 1-day ES to longer horizon using square root of time.

    ES_Td = ES_1d * sqrt(T)

    Parameters
    ----------
    es_1d : float
        1-day ES as positive number.
    horizon : int
        Number of trading days. Default 10.

    Returns
    -------
    float
        Scaled ES as positive number.

    Examples
    --------
    >>> es_20d = es_scale(es_1d=0.032, horizon=20)
    """
    return float(es_1d * np.sqrt(horizon))


# ================================================================
# Backtesting functions
# ================================================================

def kupiec_test(
    pnl_series: np.ndarray | pd.Series,
    var_series: np.ndarray | pd.Series,
    confidence: float = 0.99
) -> dict:
    """
    Kupiec Proportion of Failures (POF) test.
    Tests whether the breach rate equals the expected rate.

    H0: breach rate = 1 - confidence
    Reject H0 if model is miscalibrated.

    Parameters
    ----------
    pnl_series : array-like
        Daily P&L in decimal. Negative = loss.
    var_series : array-like
        Daily VaR estimates as positive numbers.
    confidence : float
        Confidence level. Default 0.99.

    Returns
    -------
    dict with keys:
        n_obs      : number of observations
        n_breaches : number of VaR breaches
        breach_rate: actual breach rate
        expected   : expected breach rate (1 - confidence)
        lr_stat    : likelihood ratio statistic
        p_value    : p-value (reject H0 if < 0.05)
        result     : 'PASS' or 'FAIL'

    Examples
    --------
    >>> result = kupiec_test(pnl, var_series, confidence=0.99)
    >>> print(result['result'])
    """
    pnl = np.asarray(pnl_series)
    var = np.asarray(var_series)

    mask       = ~(np.isnan(pnl) | np.isnan(var))
    pnl, var   = pnl[mask], var[mask]

    n          = len(pnl)
    breaches   = (pnl < -var).sum()
    p_actual   = breaches / n
    p_expected = 1 - confidence

    # handle edge cases
    if breaches == 0:
        lr = -2 * n * np.log(1 - p_expected)
    elif breaches == n:
        lr = -2 * n * np.log(p_expected)
    else:
        lr = -2 * (
            np.log((1 - p_expected)**(n - breaches) *
                   p_expected**breaches) -
            np.log((1 - p_actual)**(n - breaches) *
                   p_actual**breaches)
        )

    p_value = 1 - stats.chi2.cdf(lr, df=1)

    return {
        'n_obs'      : int(n),
        'n_breaches' : int(breaches),
        'breach_rate': round(float(p_actual), 4),
        'expected'   : round(float(p_expected), 4),
        'lr_stat'    : round(float(lr), 4),
        'p_value'    : round(float(p_value), 4),
        'result'     : 'PASS' if p_value > 0.05 else 'FAIL',
    }


def christoffersen_test(
    pnl_series: np.ndarray | pd.Series,
    var_series: np.ndarray | pd.Series,
    confidence: float = 0.99
) -> dict:
    """
    Christoffersen independence test.
    Tests whether VaR breaches are independent over time.
    Clustered breaches indicate model failure even if the
    total breach count is acceptable.

    Parameters
    ----------
    pnl_series : array-like
        Daily P&L in decimal.
    var_series : array-like
        Daily VaR estimates as positive numbers.
    confidence : float
        Confidence level. Default 0.99.

    Returns
    -------
    dict with keys:
        n00, n01, n10, n11 : transition counts
        p01, p11           : transition probabilities
        lr_ind             : independence LR statistic
        p_value            : p-value
        result             : 'PASS' or 'FAIL'

    Examples
    --------
    >>> result = christoffersen_test(pnl, var, confidence=0.99)
    """
    pnl = np.asarray(pnl_series)
    var = np.asarray(var_series)

    mask     = ~(np.isnan(pnl) | np.isnan(var))
    pnl, var = pnl[mask], var[mask]

    breaches = (pnl < -var).astype(int)

    # transition counts
    n00 = ((breaches[:-1] == 0) & (breaches[1:] == 0)).sum()
    n01 = ((breaches[:-1] == 0) & (breaches[1:] == 1)).sum()
    n10 = ((breaches[:-1] == 1) & (breaches[1:] == 0)).sum()
    n11 = ((breaches[:-1] == 1) & (breaches[1:] == 1)).sum()

    # transition probabilities
    p01 = n01 / (n00 + n01) if (n00 + n01) > 0 else 0
    p11 = n11 / (n10 + n11) if (n10 + n11) > 0 else 0
    p   = (n01 + n11) / (n00 + n01 + n10 + n11)

    # LR statistic
    def safe_log(x):
        return np.log(x) if x > 0 else 0

    lr_ind = -2 * (
        (n00 + n10) * safe_log(1 - p) +
        (n01 + n11) * safe_log(p) -
        n00 * safe_log(1 - p01) -
        n01 * safe_log(p01 if p01 > 0 else 1e-10) -
        n10 * safe_log(1 - p11) -
        n11 * safe_log(p11 if p11 > 0 else 1e-10)
    )

    p_value = 1 - stats.chi2.cdf(lr_ind, df=1)

    return {
        'n00'    : int(n00),
        'n01'    : int(n01),
        'n10'    : int(n10),
        'n11'    : int(n11),
        'p01'    : round(float(p01), 4),
        'p11'    : round(float(p11), 4),
        'lr_ind' : round(float(lr_ind), 4),
        'p_value': round(float(p_value), 4),
        'result' : 'PASS' if p_value > 0.05 else 'FAIL',
    }


def exception_report(
    pnl_series: pd.Series,
    var_series: pd.Series,
    confidence: float = 0.99,
    dates: Optional[pd.DatetimeIndex] = None
) -> pd.DataFrame:
    """
    ESMA exception report: documents each VaR breach.
    For funds the regulatory standard is exception-based,
    not the Basel traffic light capital multiplier framework.

    Breach rate thresholds (ESMA/CSSF standard):
    - < 1% at 99% : model acceptable
    - 1-2% at 99% : review assumptions, document
    - > 2% at 99% : model review required, notify board

    Parameters
    ----------
    pnl_series : pd.Series
        Daily P&L in decimal.
    var_series : pd.Series
        Daily VaR estimates as positive numbers.
    confidence : float
        Confidence level. Default 0.99.
    dates : pd.DatetimeIndex, optional
        Dates corresponding to pnl and var series.

    Returns
    -------
    pd.DataFrame
        One row per breach with columns:
        date, pnl, var, excess_loss, action_required
    """
    pnl = np.asarray(pnl_series)
    var = np.asarray(var_series)

    mask         = ~(np.isnan(pnl) | np.isnan(var))
    breach_mask  = (pnl < -var) & mask
    breach_idx   = np.where(breach_mask)[0]

    n            = mask.sum()
    n_breaches   = breach_mask.sum()
    breach_rate  = n_breaches / n if n > 0 else 0

    if breach_rate < 0.01:
        action = 'Model acceptable'
    elif breach_rate < 0.02:
        action = 'Review assumptions, document'
    else:
        action = 'Model review required, notify board'

    rows = []
    for idx in breach_idx:
        rows.append({
            'date'       : dates[idx] if dates is not None
                           else idx,
            'pnl'        : round(float(pnl[idx]), 6),
            'var'        : round(float(var[idx]), 6),
            'excess_loss': round(float(-pnl[idx] - var[idx]), 6),
            'action'     : action,
        })

    report = pd.DataFrame(rows)

    print(f'Exception report ({confidence*100:.0f}% VaR):')
    print(f'  observations : {n}')
    print(f'  breaches     : {n_breaches}')
    print(f'  breach rate  : {breach_rate*100:.2f}%'
          f' (expected {(1-confidence)*100:.1f}%)')
    print(f'  action       : {action}')

    return report


def full_backtest_report(
    pnl_series: pd.Series,
    var_dict: dict,
    dates: Optional[pd.DatetimeIndex] = None
) -> pd.DataFrame:
    """
    Full backtesting report running all tests for all
    confidence levels and models.

    Parameters
    ----------
    pnl_series : pd.Series
        Daily P&L in decimal.
    var_dict : dict
        Dictionary of {model_name: var_series}.
        e.g. {'historical': var_hist, 'parametric': var_param}
    dates : pd.DatetimeIndex, optional

    Returns
    -------
    pd.DataFrame
        Rows: models x confidence levels
        Columns: n_obs, n_breaches, breach_rate, expected,
                 kupiec_p, christoffersen_p, result

    Examples
    --------
    >>> report = full_backtest_report(
    ...     pnl,
    ...     {'historical': var_hist, 'parametric': var_param}
    ... )
    """
    rows = []
    for model_name, var_series in var_dict.items():
        for confidence in [0.99, 0.975, 0.95]:
            kup  = kupiec_test(pnl_series, var_series, confidence)
            chri = christoffersen_test(
                pnl_series, var_series, confidence)

            rows.append({
                'model'            : model_name,
                'confidence'       : f'{confidence*100:.1f}%',
                'n_obs'            : kup['n_obs'],
                'n_breaches'       : kup['n_breaches'],
                'breach_rate'      : kup['breach_rate'],
                'expected'         : kup['expected'],
                'kupiec_p'         : kup['p_value'],
                'christoffersen_p' : chri['p_value'],
                'result'           : (
                    'PASS'
                    if kup['result'] == 'PASS' and
                       chri['result'] == 'PASS'
                    else 'FAIL'
                ),
            })

    return pd.DataFrame(rows)


# ================================================================
# Stress scenario functions (AIFMD Annex VI)
# ================================================================

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

    # exclude government bonds (no credit spread)
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
    scenarios = {
        '2008': {
            'name'         : 'GFC 2008 (Sep-Dec 2008)',
            'delta_equity' : -0.40,
            'delta_y'      : -0.01,
            'delta_spread' : 0.03,
            'fx_shocks'    : {'USD': -0.05, 'GBP': -0.15},
        },
        '2020': {
            'name'         : 'Covid 2020 (Feb-Mar 2020)',
            'delta_equity' : -0.30,
            'delta_y'      : -0.005,
            'delta_spread' : 0.02,
            'fx_shocks'    : {'USD': 0.05, 'GBP': -0.05},
        },
        '2022': {
            'name'         : 'Rate shock 2022 (Jan-Dec 2022)',
            'delta_equity' : -0.20,
            'delta_y'      : 0.03,
            'delta_spread' : 0.015,
            'fx_shocks'    : {'USD': 0.10, 'GBP': -0.05},
        },
    }

    if scenario not in scenarios:
        raise ValueError(
            f'Unknown scenario: {scenario}. '
            f'Choose from {list(scenarios.keys())}')

    params = scenarios[scenario]
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

    # property value decline: shock is negative, so pnl is negative
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

    # vacancy increase and yield compression both reduce income
    # delta_vacancy is positive (more vacancy = less income)
    # delta_yield is negative (lower yield = less income)
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

    # stressed LTV: if property value falls, LTV rises
    # stressed_ltv = current_ltv / (1 + delta_property_value)
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


# ================================================================
# Liquidity functions (ESMA34-39-897)
# ================================================================

def days_to_liquidate(
    positions: pd.DataFrame,
    pct_adv: float = 0.25
) -> pd.DataFrame:
    """
    Estimate days to liquidate each position assuming the
    fund can trade pct_adv of average daily volume per day.

    days_i = market_value_i / (ADV_i * pct_adv)

    Direct properties and private loans: days = infinity
    since no liquid secondary market exists.

    Parameters
    ----------
    positions : pd.DataFrame
        Positions with columns: market_value_eur, adv_eur,
        is_direct_property
    pct_adv : float
        Fraction of ADV tradeable per day. Default 0.25.

    Returns
    -------
    pd.DataFrame
        Original positions with added column: days_to_liquidate

    Examples
    --------
    >>> positions = days_to_liquidate(positions, pct_adv=0.25)
    >>> print(positions[['instrument_name', 'days_to_liquidate']])
    """
    df = positions.copy()

    # direct properties and zero ADV: illiquid
    illiquid_mask = (
        (df.get('is_direct_property', False) == True) |
        (df['adv_eur'] == 0) |
        (df['adv_eur'].isna())
    )

    df['days_to_liquidate'] = np.where(
        illiquid_mask,
        np.inf,
        df['market_value_eur'].abs() / (df['adv_eur'] * pct_adv)
    )

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

    bins   = [0, 1, 7, 30, 90, 365, np.inf]
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

    # assets liquidatable within notice period
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
    Adds bid-ask spread cost to standard VaR.

    LVaR = VaR + liquidity_cost
    liquidity_cost = ½ * spread * MV * stress_multiplier

    Default spreads by asset class (in decimal):
    - Large cap equity  : 5bps  * 3x  = 15bps stressed
    - IG bonds          : 10bps * 5x  = 50bps stressed
    - HY bonds          : 50bps * 10x = 500bps stressed
    - Senior loans      : 100bps* 20x = 2000bps stressed
    - Listed REITs      : 15bps * 5x  = 75bps stressed
    - Direct properties : 5-8% transaction cost

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
        liquidity_cost: total liquidity cost
        lvar          : liquidity-adjusted VaR
        lvar_pct      : % increase vs standard VaR

    Examples
    --------
    >>> result = liquidity_adjusted_var(
    ...     var=0.025, positions=positions, stress_multiplier=3.0)
    >>> print(f'LVaR: {result["lvar"]:.4f}')
    """
    # normal spreads by asset class (in decimal)
    normal_spreads = {
        'Equity'     : 0.0005,   # 5bps
        'Real Estate': 0.0015,   # 15bps (REITs)
        'Bond'       : 0.0010,   # 10bps (IG default)
        'Loan'       : 0.0100,   # 100bps
        'CLO'        : 0.0050,   # 50bps
        'FX'         : 0.0002,   # 2bps
        'Derivative' : 0.0010,   # 10bps
        'Cash'       : 0.0000,   # no spread
    }

    df = positions.copy()
    df['spread']         = df['asset_class'].map(
        normal_spreads).fillna(0.001)

    # direct properties: use transaction cost instead of spread
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


# ================================================================
# Public API
# ================================================================

__all__ = [
    # VaR
    'var_historical',
    'var_parametric',
    'var_scale',
    # ES
    'es_historical',
    'es_parametric',
    'es_scale',
    # backtesting
    'kupiec_test',
    'christoffersen_test',
    'exception_report',
    'full_backtest_report',
    # stress scenarios
    'stress_equity',
    'stress_rates',
    'stress_credit',
    'stress_fx',
    'stress_combined',
    'stress_historical',
    'stress_property',
    'stress_rental',
    'stress_ltv',
    # liquidity
    'days_to_liquidate',
    'liquidity_buckets',
    'redemption_stress',
    'investor_concentration',
    'liquidity_adjusted_var',
]