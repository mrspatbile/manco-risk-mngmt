"""
ucits_relative_var.py
===================
UCITS relative VaR computation.

Relative VaR compares the fund's VaR against a reference portfolio VaR:

    Relative VaR = fund_var / reference_portfolio_var

UCITS Article 83 limits relative VaR to 2x the reference portfolio (where applicable).

Historical VaR uses reconstructed historical P&L: positions are held fixed as of
the risk date and revalued under historical market moves from the lookback window.
It is not based on realised historical fund returns.
"""

import pandas as pd
import numpy as np
from typing import Tuple
from sqlalchemy.engine import Engine

from fund_risk_workflow.computation.var import var_historical, var_parametric, var_scale, es_historical, es_scale
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg


def build_reference_portfolio_pnl(
    bbg: MockBloomberg,
    reference_portfolio_config: dict,
    valuation_date: str,
    lookback_days: int = 250,
) -> Tuple[np.ndarray, float]:
    """
    Reconstruct reference portfolio P&L series using fixed-position approach.

    Reconstructs the reference portfolio at the valuation date and holds it fixed,
    revaluing under historical market moves from the lookback window.

    Parameters
    ----------
    bbg : MockBloomberg
        Bloomberg data provider
    reference_portfolio_config : dict
        Reference portfolio definition with 'components' array.
        Each component has: identifier, asset_class, weight, proxy_ticker, currency
    valuation_date : str
        Valuation date (YYYY-MM-DD)
    lookback_days : int, default 250
        Number of business days for P&L reconstruction

    Returns
    -------
    tuple
        (pnl_returns: np.ndarray of daily returns (decimal),
         nav_eur: float, NAV of reference portfolio in EUR)

    Raises
    ------
    ValueError
        If components do not sum to 100% or if Bloomberg data is missing
    """
    components = reference_portfolio_config.get('components', [])

    # Validate weights sum to 1.0
    total_weight = sum(c.get('weight', 0) for c in components)
    if not (0.99 < total_weight < 1.01):
        raise ValueError(
            f"Reference portfolio weights must sum to 1.0. Got {total_weight:.4f}"
        )

    # Generate lookback dates
    lookback_range = pd.date_range(end=valuation_date, periods=lookback_days + 1, freq='B')
    lookback_dates = sorted([dt.strftime('%Y-%m-%d') for dt in lookback_range])

    # Fetch price history for each component
    component_returns = {}
    for comp in components:
        ticker = comp['proxy_ticker']
        try:
            hist = bbg.bdh(ticker, 'PX_LAST', lookback_dates[0], valuation_date)
            if hist.empty:
                raise ValueError(f"No data for {ticker}")
            ret = hist['PX_LAST'].pct_change().dropna().values
            component_returns[comp['identifier']] = ret
        except Exception as e:
            raise ValueError(f"Failed to fetch data for component {ticker}: {e}")

    # Align all returns to same index
    min_len = min(len(ret) for ret in component_returns.values())
    aligned_returns = {k: v[-min_len:] for k, v in component_returns.items()}

    # Compute portfolio returns as weighted sum
    pnl_returns = np.zeros(min_len)
    for comp in components:
        weight = comp['weight']
        comp_id = comp['identifier']
        pnl_returns += weight * aligned_returns[comp_id]

    # Reference portfolio NAV is typically normalized to 1.0 (or any baseline)
    # since we're only interested in the returns, not absolute values
    nav = 1.0

    return pnl_returns, nav


def compute_reference_portfolio_var(
    bbg: MockBloomberg,
    reference_portfolio_config: dict,
    valuation_date: str,
    confidence: float = 0.99,
    horizon_days: int = 20,
    lookback_days: int = 250,
) -> dict:
    """
    Compute VaR for reference portfolio using historical simulation.

    Parameters
    ----------
    bbg : MockBloomberg
        Bloomberg data provider
    reference_portfolio_config : dict
        Reference portfolio definition
    valuation_date : str
        Valuation date (YYYY-MM-DD)
    confidence : float, default 0.99
        Confidence level (e.g., 0.99 for 99%)
    horizon_days : int, default 20
        Holding period in days
    lookback_days : int, default 250
        Lookback window for estimation

    Returns
    -------
    dict
        {
            'var_1d_pct': float,
            'var_scaled_pct': float,
            'var_1d_decimal': float,
            'var_scaled_decimal': float,
            'es_1d_pct': float,
            'es_scaled_pct': float,
            'confidence': float,
            'horizon_days': int,
            'lookback_days': int,
            'nav': float,
            'valuation_date': str,
        }
    """
    pnl_returns, nav = build_reference_portfolio_pnl(
        bbg, reference_portfolio_config, valuation_date, lookback_days
    )

    # Compute 1-day VaR
    var_1d = var_historical(pnl_returns, confidence=confidence)

    # Scale to holding period
    var_scaled = var_scale(var_1d, horizon=horizon_days)

    # Compute ES
    es_1d = es_historical(pnl_returns, confidence=confidence)
    es_scaled = es_scale(es_1d, horizon=horizon_days)

    return {
        'var_1d_pct': var_1d * 100,
        'var_scaled_pct': var_scaled * 100,
        'var_1d_decimal': var_1d,
        'var_scaled_decimal': var_scaled,
        'es_1d_pct': es_1d * 100,
        'es_scaled_pct': es_scaled * 100,
        'confidence': confidence,
        'horizon_days': horizon_days,
        'lookback_days': lookback_days,
        'nav': nav,
        'valuation_date': valuation_date,
    }


def compute_ucits_relative_var(
    fund_var_result: dict,
    reference_var_result: dict,
    ucits_config: dict,
) -> dict:
    """
    Compute UCITS relative VaR and check limit compliance.

    Relative VaR is the ratio of fund VaR to reference portfolio VaR.
    Per UCITS regulation (where applicable), this ratio should not exceed 2x.

    Parameters
    ----------
    fund_var_result : dict
        Fund VaR result from compute_fixed_position_var_1day or similar.
        Must include: 'var_hist_pct' or 'var_scaled_pct'
    reference_var_result : dict
        Reference portfolio VaR result from compute_reference_portfolio_var.
        Must include: 'var_scaled_pct' or 'var_scaled_decimal'
    ucits_config : dict
        UCITS regulatory configuration with 'var_framework.relative_limit_multiplier'

    Returns
    -------
    dict
        {
            'fund_var_pct': float,
            'reference_var_pct': float,
            'relative_var_ratio': float,
            'limit_multiplier': float,
            'breach': bool,
            'utilisation_pct': float,
            'status': str,  # 'OK', 'WARNING', 'BREACH'
        }

    Raises
    ------
    KeyError
        If required keys are missing from inputs
    """
    # Extract VaR figures (try both percentage and decimal forms)
    fund_var_pct = fund_var_result.get('var_hist_pct')
    if fund_var_pct is None:
        fund_var_pct = fund_var_result.get('var_scaled_pct')
    if fund_var_pct is None:
        raise KeyError(
            "fund_var_result must contain 'var_hist_pct' or 'var_scaled_pct'"
        )

    reference_var_pct = reference_var_result.get('var_scaled_pct')
    if reference_var_pct is None:
        var_decimal = reference_var_result.get('var_scaled_decimal')
        if var_decimal is None:
            raise KeyError(
                "reference_var_result must contain 'var_scaled_pct' or 'var_scaled_decimal'"
            )
        reference_var_pct = var_decimal * 100

    # Get limit from UCITS config
    limit_multiplier = ucits_config.get(
        'var_framework', {}
    ).get('relative_limit_multiplier', 2.0)

    # Compute ratio (handle zero reference VaR edge case)
    if reference_var_pct == 0:
        relative_var_ratio = np.inf if fund_var_pct > 0 else 0.0
    else:
        relative_var_ratio = fund_var_pct / reference_var_pct

    # Determine status
    breach = relative_var_ratio > limit_multiplier
    utilisation = (relative_var_ratio / limit_multiplier) * 100

    if breach:
        status = 'BREACH'
    elif utilisation >= 80:
        status = 'WARNING'
    else:
        status = 'OK'

    return {
        'fund_var_pct': fund_var_pct,
        'reference_var_pct': reference_var_pct,
        'relative_var_ratio': relative_var_ratio,
        'limit_multiplier': limit_multiplier,
        'breach': breach,
        'utilisation_pct': utilisation,
        'status': status,
    }


def evaluate_relative_var_limit(
    fund_var_pct: float,
    reference_var_pct: float,
    limit_multiplier: float = 2.0,
) -> dict:
    """
    Simple standalone evaluation of relative VaR limit compliance.

    Parameters
    ----------
    fund_var_pct : float
        Fund VaR in percent
    reference_var_pct : float
        Reference portfolio VaR in percent
    limit_multiplier : float, default 2.0
        Relative VaR limit multiplier

    Returns
    -------
    dict
        {'ratio': float, 'breach': bool, 'utilisation_pct': float}
    """
    if reference_var_pct == 0:
        ratio = np.inf if fund_var_pct > 0 else 0.0
    else:
        ratio = fund_var_pct / reference_var_pct

    breach = ratio > limit_multiplier
    utilisation = (ratio / limit_multiplier) * 100

    return {
        'ratio': ratio,
        'breach': breach,
        'utilisation_pct': utilisation,
    }


def compute_ucits_relative_var_point_in_time(engine, fund_id: str, var_result: dict,
                                              var_confidence: float, var_lookback: int,
                                              var_holding_period: int, relative_var_limit: float,
                                              bbg, valuation_date: str, rmp: dict) -> dict:
    """Compute relative VaR point-in-time."""
    from fund_risk_workflow.data.benchmark_builder import build_benchmark_returns

    ref_portfolio_id = rmp['global_exposure_policy']['reference_portfolio_id']
    start_date = (pd.Timestamp(valuation_date) - pd.tseries.offsets.BDay(var_lookback)).strftime('%Y-%m-%d')

    # Build reference portfolio returns using canonical builder
    ref_ret = build_benchmark_returns(
        ref_portfolio_id,
        bbg,
        start_date,
        valuation_date,
    ).values

    var_ref_1d = var_historical(ref_ret, confidence=var_confidence)
    relative_var = var_result['var_hist_pct'] / var_ref_1d
    status = ('🔴 BREACH' if relative_var > relative_var_limit else
              '🟡 WARNING' if relative_var > relative_var_limit * 0.80 else
              '🟢 OK')

    return {
        'fund_var_1d_pct': var_result['var_hist_pct'],
        'reference_var_1d_pct': var_ref_1d,
        'relative_var_ratio': relative_var,
        'status': status,
        'var_holding_period': var_holding_period,
        'relative_var_limit': relative_var_limit,
        'utilisation_pct': relative_var / relative_var_limit * 100,
    }
