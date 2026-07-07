"""
var_backtest.py
===============
Rolling fixed-position VaR backtest using 2-step approach:
  Step 1: compute_fixed_position_pnl_series() - reconstruct 250-day P&L
  Step 2: compute_var_from_pnl() - extract VaR at 95%, 97.5%, 99%

For each historical date d, compute VaR as if that date's portfolio existed for 250 days.
"""

import numpy as np
import pandas as pd
from datetime import timedelta
from sqlalchemy import text
from sqlalchemy.engine import Engine

from fund_risk_workflow.data.database import query_positions
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg
from fund_risk_workflow.computation.var import kupiec_test, christoffersen_test
from fund_risk_workflow.pipeline.fixed_position_var import compute_fixed_position_pnl_series, compute_var_from_pnl


def get_yield_tenor_for_bond(maturity_str: str, currency: str) -> str:
    """
    Map bond maturity to constant-tenor yield series.

    Parameters
    ----------
    maturity_str : str
        Bond maturity date (e.g., '2029-08-15')
    currency : str
        Currency code (e.g., 'EUR', 'USD')

    Returns
    -------
    str
        Tenor series name (e.g., 'EUR_2Y', 'USD_5Y')
    """
    try:
        from fund_risk_workflow.config import REFERENCE_DATE
        maturity = pd.Timestamp(maturity_str)
        years_to_maturity = (maturity - pd.Timestamp(REFERENCE_DATE)).days / 365.25
    except:
        years_to_maturity = 5

    if currency == 'EUR':
        if years_to_maturity <= 3:
            return 'EUR_2Y'
        elif years_to_maturity <= 7:
            return 'EUR_5Y'
        else:
            return 'EUR_10Y'
    elif currency == 'USD':
        if years_to_maturity <= 3:
            return 'USD_2Y'
        elif years_to_maturity <= 7:
            return 'USD_5Y'
        else:
            return 'USD_10Y'
    else:
        return 'EUR_5Y'


def compute_var_backtest_rolling(
    engine: Engine,
    fund_id: str,
    start_date: str,
    end_date: str,
    lookback: int = 250,
    confidence: float = 0.99,
) -> pd.DataFrame:
    """
    Rolling 1-day fixed-position VaR backtest (optimized with batch queries).

    For each date d:
    1. Load fixed positions at d from pre-fetched batch
    2. Slice 251-day price window (250 lookback + d) from pre-fetched matrix
    3. Compute fixed-position P&L vectorized
    4. Extract VaR at 95%, 97.5%, 99% from same P&L distribution

    Optimization: Single batch query for all positions and prices,
    vectorized P&L computation instead of nested database loops.

    Parameters
    ----------
    engine : sqlalchemy.Engine
    fund_id : str
    start_date : str
        YYYY-MM-DD
    end_date : str
        YYYY-MM-DD
    lookback : int, default 250
        Number of business days for P&L reconstruction per date
    confidence : float
        (not used; all 3 confidence levels computed)

    Returns
    -------
    pd.DataFrame
        Columns: date, nav_eur, var_95_pct, var_975_pct, var_99_pct,
                 var_95_eur, var_975_eur, var_99_eur, realised_return
    """
    from fund_risk_workflow.computation.var import var_historical

    # Date range for backtest
    backtest_dates = pd.date_range(start=start_date, end=end_date, freq='B')

    # Price dates needed: lookback buffer + backtest window
    price_start = backtest_dates[0] - pd.tseries.offsets.BDay(lookback)
    price_end = backtest_dates[-1]

    # ================================================================
    # BATCH QUERY 1: All positions for backtest window
    # ================================================================
    with engine.connect() as conn:
        pos_sql = text("""
            SELECT position_date, isin, bloomberg_ticker, quantity, market_value_eur, asset_class
            FROM positions
            WHERE fund_id = :fund_id AND position_date BETWEEN :start AND :end
            ORDER BY position_date, isin
        """)
        positions_df = pd.read_sql(
            pos_sql,
            conn,
            params={
                'fund_id': fund_id,
                'start': price_start.strftime('%Y-%m-%d'),
                'end': price_end.strftime('%Y-%m-%d')
            }
        )

    # ================================================================
    # BATCH QUERY 2: All prices for lookback + backtest window
    # ================================================================
    with engine.connect() as conn:
        price_sql = text("""
            SELECT position_date, isin, bloomberg_ticker, price
            FROM positions
            WHERE fund_id = :fund_id AND position_date BETWEEN :start AND :end
            ORDER BY position_date, isin
        """)
        prices_df = pd.read_sql(
            price_sql,
            conn,
            params={
                'fund_id': fund_id,
                'start': price_start.strftime('%Y-%m-%d'),
                'end': price_end.strftime('%Y-%m-%d')
            }
        )

    if positions_df.empty or prices_df.empty:
        return pd.DataFrame()

    # ================================================================
    # IN-MEMORY: Pivot prices into date × instrument matrix
    # ================================================================
    prices_df['position_date'] = pd.to_datetime(prices_df['position_date'])
    prices_matrix = prices_df.pivot_table(
        index='position_date',
        columns='isin',
        values='price',
        aggfunc='first'
    )

    # ================================================================
    # BUILD NAV TIMELINE
    # ================================================================
    positions_df['position_date'] = pd.to_datetime(positions_df['position_date'])
    nav_by_date = positions_df.groupby('position_date')['market_value_eur'].sum()

    # ================================================================
    # MAIN LOOP: Vectorized P&L computation per backtest date
    # ================================================================
    rows = []

    for d in backtest_dates:
        d_str = d.strftime('%Y-%m-%d')

        try:
            # Get positions at date d
            pos_at_d = positions_df[positions_df['position_date'] == d]
            if pos_at_d.empty:
                continue

            nav_d = nav_by_date.get(d, np.nan)
            if pd.isna(nav_d) or nav_d <= 0:
                continue

            # Fixed portfolio: qty by ISIN and asset class for bond scaling
            qty_by_isin = dict(zip(pos_at_d['isin'], pos_at_d['quantity']))
            asset_class_by_isin = dict(zip(pos_at_d['isin'], pos_at_d['asset_class']))

            # Slice 251-day price window (250 lookback + today)
            window_start = d - pd.tseries.offsets.BDay(lookback)
            price_window = prices_matrix.loc[window_start:d].copy()

            if len(price_window) < lookback + 1:
                # Insufficient price history
                continue

            # Compute daily price changes (vectorized)
            price_changes = price_window.diff().iloc[1:, :]  # Drop first row (NaN)

            # Compute fixed-position P&L (vectorized)
            # shape: (250, n_instruments)
            position_pnl = price_changes.copy()
            for isin in position_pnl.columns:
                qty = qty_by_isin.get(isin, 0)
                if qty != 0:
                    pnl = price_changes[isin] * qty

                    # Bond prices are quoted per 100 of par (e.g., 98.5 means 98.5% of par)
                    # Divide price_change by 100 to get correct P&L for bonds
                    asset_class = asset_class_by_isin.get(isin, '')
                    if asset_class == 'Bond':
                        pnl = pnl / 100

                    position_pnl[isin] = pnl
                else:
                    position_pnl[isin] = 0

            # Sum across instruments per day: (250,)
            portfolio_pnl = position_pnl.sum(axis=1)

            # Normalize by NAV
            pnl_returns = (portfolio_pnl / nav_d).values

            if len(pnl_returns) < 10:
                continue

            # Compute VaR at 3 confidence levels from same distribution
            var_95_pct = var_historical(pnl_returns, confidence=0.95)
            var_975_pct = var_historical(pnl_returns, confidence=0.975)
            var_99_pct = var_historical(pnl_returns, confidence=0.99)

            # Realized 1-day return from d-1 to d
            realised_return = np.nan
            if d != backtest_dates[0]:
                prev_d = d - pd.tseries.offsets.BDay(1)
                if prev_d in nav_by_date.index:
                    prev_nav = nav_by_date[prev_d]
                    if prev_nav > 0:
                        realised_return = (nav_d - prev_nav) / prev_nav

            rows.append({
                'date': d,
                'nav_eur': nav_d,
                'var_95_pct': var_95_pct,
                'var_975_pct': var_975_pct,
                'var_99_pct': var_99_pct,
                'var_95_eur': nav_d * var_95_pct,
                'var_975_eur': nav_d * var_975_pct,
                'var_99_eur': nav_d * var_99_pct,
                'realised_return': realised_return,
            })

        except Exception:
            continue

    return pd.DataFrame(rows).reset_index(drop=True)


def create_backtest_report(
    backtest_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Backtest report with Kupiec and Christoffersen tests (95%, 97.5%, 99%).

    Timing alignment: VaR[d] is tested against return that occurs FROM d TO d+1.
    In backtest_df: realised_return[i] = return FROM d[i-1] TO d[i]
                    var_*_pct[i] = VaR estimated AT d[i]
    So we compare: realised_return[1:] against var_*_pct[:-1] (shift by 1 day)

    VaR at all confidence levels already computed during backtest.

    Parameters
    ----------
    backtest_df : pd.DataFrame
        Output from compute_var_backtest_rolling
        (must have var_95_pct, var_975_pct, var_99_pct, realised_return)

    Returns
    -------
    pd.DataFrame
        Report with columns: model, confidence, n_obs, n_breaches, breach_rate, expected,
        kupiec_p, christoffersen_p, result
    """
    if 'realised_return' not in backtest_df.columns:
        raise ValueError("backtest_df must have 'realised_return' column")

    # Timing alignment: compare return[1:] against var[:-1]
    # This compares VaR[d] against the return that happens FROM d TO d+1
    returns = backtest_df['realised_return'].iloc[1:].values

    results = []
    for conf, col in [(0.95, 'var_95_pct'), (0.975, 'var_975_pct'), (0.99, 'var_99_pct')]:
        if col not in backtest_df.columns:
            continue

        vars = backtest_df[col].iloc[:-1].values

        kupiec = kupiec_test(returns, vars, confidence=conf)
        christoffersen = christoffersen_test(returns, vars, confidence=conf)

        results.append({
            'model': f'Fixed-Position {int(conf*100)}% VaR',
            'confidence': int(conf * 100),
            'n_obs': kupiec['n_obs'],
            'n_breaches': kupiec['n_breaches'],
            'breach_rate': kupiec['breach_rate'],
            'expected': kupiec['expected'],
            'kupiec_p': kupiec['p_value'],
            'christoffersen_p': christoffersen['p_value'],
            'result': 'PASS' if (kupiec['p_value'] > 0.05 and christoffersen['p_value'] > 0.05) else 'FAIL',
        })

    return pd.DataFrame(results)
