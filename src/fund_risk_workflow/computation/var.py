"""
var.py
======
Pure Value-at-Risk computation module.

All functions are stateless, depend only on numpy/pandas/scipy,
and require no database access, file I/O, or external services.

Scope
-----
This module contains the core VaR and Expected Shortfall (ES) calculation
logic and backtesting framework. It does NOT contain:
- Position or portfolio loading (data module)
- Visualization or reporting (ui or reporting modules)
- Stress testing, liquidity, leverage, ESG, or fund-specific analytics

Functions
---------
VaR Estimation:
    var_historical()        Historical simulation VaR
    var_parametric()        Parametric VaR (normal or Student-t)
    var_scale()             Scale 1-day VaR to multi-day horizon

Expected Shortfall:
    es_historical()         Historical ES (CVaR)
    es_parametric()         Parametric ES
    es_scale()              Scale 1-day ES to multi-day horizon
    es_from_var()           Approximate ES from VaR (heuristic)

Backtesting:
    kupiec_test()           Kupiec POF test (breach rate)
    christoffersen_test()   Christoffersen independence test
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm, t as student_t


# ================================================================
# VaR Estimation
# ================================================================

def var_historical(
    returns: np.ndarray | pd.Series,
    confidence: float = 0.99,
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
    df: int = 5,
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
    horizon: int = 10,
) -> float:
    """
    Scale 1-day VaR to longer horizon using square root of time.

    VaR_Td = VaR_1d * sqrt(T)

    Assumes returns are i.i.d. (independent and identically distributed).

    Common horizons:
    - 10 days : Basel III regulatory VaR
    - 20 days : UCITS and AIFMD standard

    Parameters
    ----------
    var_1d : float
        1-day VaR as positive number.
    horizon : int
        Number of trading days. Default 10 (Basel III).

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
# Expected Shortfall (CVaR)
# ================================================================

def es_historical(
    returns: np.ndarray | pd.Series,
    confidence: float = 0.99
) -> float:
    """
    Historical Expected Shortfall (CVaR).
    Mean of all returns that breach the VaR threshold.

    ES_alpha = -E[R | R < -VaR]

    Apply to liquid portion only.

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

    Closed-form solutions:

    1. Normal distribution:
        ES_alpha = sigma * phi(z_alpha) / alpha

    2. Student-t distribution:
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


def es_from_var(var_estimate: float, confidence: float = 0.99) -> float:
    """
    Rough approximation of Expected Shortfall from VaR.

    For normal distribution: ES ≈ VaR × (1 + φ(q) / (1 - confidence))
    where φ is the standard normal PDF and q is the quantile.

    This is a heuristic; for accurate ES, use historical quantile directly.

    Parameters
    ----------
    var_estimate : float
        VaR estimate (decimal)
    confidence : float, default 0.99
        Confidence level (0-1)

    Returns
    -------
    float
        Approximate ES
    """
    alpha = 1 - confidence
    if alpha <= 0 or alpha >= 1:
        raise ValueError("confidence must be in (0, 1)")

    q = norm.ppf(alpha)
    phi_q = norm.pdf(q)
    es_adjustment = phi_q / alpha
    return var_estimate * (1 + es_adjustment)


# ================================================================
# Backtesting
# ================================================================

def kupiec_test(
    returns_series: np.ndarray | pd.Series,
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
    returns_series : array-like
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
    >>> result = kupiec_test(returns_series, var_series, confidence=0.99)
    >>> print(result['result'])
    """
    ret = np.asarray(returns_series)
    var = np.asarray(var_series)

    mask       = ~(np.isnan(ret) | np.isnan(var))
    ret, var   = ret[mask], var[mask]

    n          = len(ret)
    breaches   = (ret < -var).sum()
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
    returns_series: np.ndarray | pd.Series,
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
    returns_series : array-like
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
    >>> result = christoffersen_test(returns, var, confidence=0.99)
    """
    ret = np.asarray(returns_series)
    var = np.asarray(var_series)

    mask     = ~(np.isnan(ret) | np.isnan(var))
    ret, var = ret[mask], var[mask]

    breaches = (ret < -var).astype(int)

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
