"""
fixed_position_var.py
=====================
Fixed-position VaR: separated into P&L computation (step 1) and VaR calculation (step 2).

Step 1: compute_fixed_position_pnl_series() — reconstruct 250 days of P&L
Step 2: compute_var_from_pnl() — extract VaR at any confidence level or horizon
"""

import pandas as pd
import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Engine

from fund_risk_workflow.computation.var import var_historical, var_scale, es_historical, es_scale, var_parametric, es_parametric
from scipy import stats


def compute_fixed_position_pnl_series(
    engine: Engine,
    fund_id: str,
    valuation_date: str,
    lookback: int = 250,
) -> tuple[np.ndarray, float]:
    """
    Step 1: Compute 250-day P&L series for fixed current portfolio.

    Takes TODAY's positions and reconstructs historical P&L
    assuming that exact portfolio existed for the last 250 trading days.

    Parameters
    ----------
    engine : sqlalchemy.Engine
    fund_id : str
    valuation_date : str
        YYYY-MM-DD (today's date)
    lookback : int, default 250
        Number of business days for P&L reconstruction

    Returns
    -------
    tuple
        (pnl_returns: np.ndarray of 250 daily returns (decimal),
         nav_eur: float, current NAV in EUR)
    """

    # Load today's positions
    with engine.connect() as conn:
        positions_sql = text("""
            SELECT fund_id, position_date, isin, bloomberg_ticker,
                   quantity, price, market_value_eur, asset_class
            FROM positions
            WHERE fund_id = :fund_id AND position_date = :position_date
        """)
        positions = pd.read_sql(
            positions_sql,
            conn,
            params={'fund_id': fund_id, 'position_date': valuation_date}
        )

    if positions.empty:
        raise ValueError(f"No positions found for {fund_id} on {valuation_date}")

    nav_today = positions['market_value_eur'].sum()

    # Group by ticker and store asset class for bond scaling
    qty_by_ticker = {}
    asset_class_by_ticker = {}
    for _, row in positions.iterrows():
        ticker_key = row['bloomberg_ticker'] if pd.notna(row['bloomberg_ticker']) else f"ISIN:{row['isin']}"
        qty_by_ticker[ticker_key] = row['quantity']
        asset_class_by_ticker[ticker_key] = row['asset_class']

    # Reconstruct 250-day P&L series
    pnl_returns = []
    lookback_range = pd.date_range(end=valuation_date, periods=lookback + 1, freq='B')
    lookback_dates = sorted([dt.strftime('%Y-%m-%d') for dt in lookback_range])

    for i in range(len(lookback_dates) - 1):
        prev_date = lookback_dates[i]
        curr_date = lookback_dates[i + 1]

        try:
            with engine.connect() as conn:
                prices_sql = text("""
                    SELECT bloomberg_ticker, isin, price
                    FROM positions
                    WHERE fund_id = :fund_id AND position_date = :position_date
                """)
                prev_pos = pd.read_sql(prices_sql, conn,
                                      params={'fund_id': fund_id, 'position_date': prev_date})
                curr_pos = pd.read_sql(prices_sql, conn,
                                      params={'fund_id': fund_id, 'position_date': curr_date})

            daily_pnl = 0.0
            for ticker_key, qty in qty_by_ticker.items():
                if pd.isna(qty) or qty == 0:
                    continue

                if ticker_key.startswith('ISIN:'):
                    isin = ticker_key.split(':')[1]
                    prev_row = prev_pos[prev_pos['isin'] == isin]
                    curr_row = curr_pos[curr_pos['isin'] == isin]
                else:
                    prev_row = prev_pos[prev_pos['bloomberg_ticker'] == ticker_key]
                    curr_row = curr_pos[curr_pos['bloomberg_ticker'] == ticker_key]

                if prev_row.empty or curr_row.empty:
                    continue

                prev_price = float(prev_row.iloc[0]['price'])
                curr_price = float(curr_row.iloc[0]['price'])

                if pd.isna(prev_price) or pd.isna(curr_price):
                    continue

                price_change = curr_price - prev_price

                # Bond prices are quoted per 100 of par (e.g., 98.5 means 98.5% of par)
                # Divide price_change by 100 to get correct P&L for bonds
                asset_class = asset_class_by_ticker.get(ticker_key, '')
                if asset_class == 'Bond':
                    price_change = price_change / 100

                daily_pnl += qty * price_change

            daily_return = daily_pnl / nav_today if nav_today > 0 else 0
            pnl_returns.append(daily_return)

        except Exception:
            continue

    if len(pnl_returns) < 10:
        raise ValueError(f"Insufficient P&L observations ({len(pnl_returns)})")

    return np.array(pnl_returns), nav_today


def compute_var_from_pnl(
    pnl_returns: np.ndarray,
    nav_eur: float,
    confidence: float = 0.99,
    horizon: int = 1,
    df: int | None = None,
    valuation_date: str | None = None,
) -> dict:
    """
    Step 2: Compute historical and parametric VaR and ES from P&L series.

    Parametric VaR can use either:
    - Fitted Student-t df from the distribution (if df=None)
    - A predetermined df value (if df is specified, e.g., df=5)

    Parameters
    ----------
    pnl_returns : np.ndarray
        Daily return series (decimal), e.g., from compute_fixed_position_pnl_series()
    nav_eur : float
        Current portfolio NAV in EUR
    confidence : float, default 0.99
        Confidence level (0-1)
    horizon : int, default 1
        Holding period in days (scales using sqrt(horizon))
    df : int or None, default None
        Degrees of freedom for Student-t distribution.
        If None, df is fitted from the distribution using maximum likelihood.
        If specified (e.g., 5), that value is used directly for parametric VaR.

    Returns
    -------
    dict
        Historical VaR/ES: var_hist_pct, var_hist_eur, es_hist_pct, es_hist_eur,
                           var_hist_scaled_pct, var_hist_scaled_eur, es_hist_scaled_pct, es_hist_scaled_eur
        Parametric VaR/ES: var_param_pct, var_param_eur, es_param_pct, es_param_eur,
                           var_param_scaled_pct, var_param_scaled_eur, es_param_scaled_pct, es_param_scaled_eur
        Metadata: nav_eur, n_observations, distribution, mu, sigma, df_used, confidence, horizon, valuation_date
    """
    # Historical VaR
    var_1d_pct = var_historical(pnl_returns, confidence=confidence)
    es_1d_pct = es_historical(pnl_returns, confidence=confidence)

    if horizon > 1:
        var_scaled_pct = var_scale(var_1d_pct, horizon=horizon)
        es_scaled_pct = es_scale(es_1d_pct, horizon=horizon)
    else:
        var_scaled_pct = var_1d_pct
        es_scaled_pct = es_1d_pct

    # Parametric VaR: fit mu and sigma; df is either fitted or predetermined
    mu = np.mean(pnl_returns)
    sigma = np.std(pnl_returns, ddof=1)  # Sample std dev

    # Determine df: fit from distribution or use predetermined value
    if df is None:
        df_used = int(stats.t.fit(pnl_returns)[0])  # Fit df from distribution
        df_used = max(2, df_used)  # Ensure df >= 2 for practical stability
    else:
        df_used = df  # Use the provided value

    var_param_1d_pct = var_parametric(mu, sigma, confidence, dist='t', df=df_used)
    es_param_1d_pct = es_parametric(sigma, mu=mu, confidence=confidence, dist='t', df=df_used)

    if horizon > 1:
        var_param_scaled_pct = var_scale(var_param_1d_pct, horizon=horizon)
        es_param_scaled_pct = es_scale(es_param_1d_pct, horizon=horizon)
    else:
        var_param_scaled_pct = var_param_1d_pct
        es_param_scaled_pct = es_param_1d_pct

    return {
        'nav_eur': nav_eur,
        # Historical
        'var_hist_pct': var_1d_pct,
        'var_hist_eur': nav_eur * var_1d_pct,
        'es_hist_pct': es_1d_pct,
        'es_hist_eur': nav_eur * es_1d_pct,
        'var_hist_scaled_pct': var_scaled_pct,
        'var_hist_scaled_eur': nav_eur * var_scaled_pct,
        'es_hist_scaled_pct': es_scaled_pct,
        'es_hist_scaled_eur': nav_eur * es_scaled_pct,
        # Parametric
        'var_param_pct': var_param_1d_pct,
        'var_param_eur': nav_eur * var_param_1d_pct,
        'es_param_pct': es_param_1d_pct,
        'es_param_eur': nav_eur * es_param_1d_pct,
        'var_param_scaled_pct': var_param_scaled_pct,
        'var_param_scaled_eur': nav_eur * var_param_scaled_pct,
        'es_param_scaled_pct': es_param_scaled_pct,
        'es_param_scaled_eur': nav_eur * es_param_scaled_pct,
        # Metadata
        'n_observations': len(pnl_returns),
        'distribution': pnl_returns,
        'mu': mu,
        'sigma': sigma,
        'df_used': df_used,
        'confidence': confidence,
        'horizon': horizon,
        'valuation_date': valuation_date,
    }


def compute_fixed_position_var_1day(
    engine: Engine,
    fund_id: str,
    valuation_date: str,
    lookback: int = 250,
    confidence: float | list = 0.99,
    horizon: int = 1,
    df: int | None = None,
) -> dict | list:
    """
    Compute 1-day fixed-position VaR at one or multiple confidence levels.

    For efficiency: P&L series computed once, then VaR extracted at all requested
    confidence levels from the same distribution.

    Parameters
    ----------
    engine : sqlalchemy.Engine
    fund_id : str
    valuation_date : str
        YYYY-MM-DD
    lookback : int, default 250
    confidence : float or list, default 0.99
        Single confidence level (0.99) or list ([0.95, 0.975, 0.99])
    horizon : int, default 1
        Holding period in days
    df : int or None, default None
        Degrees of freedom for Student-t parametric VaR.
        If None, df is fitted from the distribution.
        If specified (e.g., 5), that value is used directly.

    Returns
    -------
    dict (if confidence is float)
        VaR result for single confidence level
    list of dicts (if confidence is list)
        VaR results for all requested confidence levels
    """
    pnl_returns, nav = compute_fixed_position_pnl_series(
        engine, fund_id, valuation_date, lookback
    )

    if isinstance(confidence, list):
        return [compute_var_from_pnl(pnl_returns, nav, c, horizon, df=df, valuation_date=valuation_date) for c in confidence]
    else:
        return compute_var_from_pnl(pnl_returns, nav, confidence, horizon, df=df, valuation_date=valuation_date)
