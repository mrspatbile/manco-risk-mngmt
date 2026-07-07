"""
attribution.py
==============
Pure P&L attribution computation module.

Sensitivity-based P&L attribution by risk factor (equity, rates, FX).

All functions are stateless, depend only on numpy/pandas, and require
no database access, file I/O, or external services.

Functions
---------
    compute_pnl_attribution()   Daily P&L attribution by risk factor
    resolve_economic_risk_bucket()  Map position to economic risk factor bucket
"""

import pandas as pd


def resolve_economic_risk_bucket(
    row: dict,
    deriv_contracts: dict | None = None,
) -> str:
    """
    Map any position (equity, bond, derivative, fx, cash) to economic risk factor bucket.

    After Phase B reclassification, derivatives are `asset_class="Derivative"`.
    This function resolves their economic underlying to the correct attribution bucket.

    Parameters
    ----------
    row : dict
        Position record with keys: asset_class, isin, currency (str)
    deriv_contracts : dict, optional
        Loaded from reference_data.load_derivative_contracts()
        Maps {isin: contract_dict}. If None, derivatives map to Residual.

    Returns
    -------
    str
        Economic risk factor bucket: 'Equity', 'Rates', 'FX', or 'Residual'

    Logic
    -----
    Non-derivatives:
      - 'Equity' → 'Equity'
      - 'Bond', 'Loan', 'CLO' → 'Rates'
      - 'FX' → 'FX'
      - 'Cash', other → 'Residual'

    Derivatives:
      - Look up isin in deriv_contracts
      - Map underlying_asset_class:
        - 'Equity' → 'Equity'
        - 'FX' → 'FX'
        - 'Rates', 'Fixed Income' → 'Rates'
        - other → 'Residual'
      - If isin not found: 'Residual'
    """
    asset_class = str(row.get('asset_class', '')).strip()

    # Non-derivatives: direct mapping
    if asset_class != 'Derivative':
        if asset_class == 'Equity':
            return 'Equity'
        elif asset_class in ('Bond', 'Loan', 'CLO'):
            return 'Rates'
        elif asset_class == 'FX':
            return 'FX'
        else:
            return 'Residual'

    # Derivatives: look up underlying asset class
    if asset_class == 'Derivative':
        if not deriv_contracts:
            # No derivative contracts metadata available
            return 'Residual'

        isin = str(row.get('isin', '')).strip()
        if isin not in deriv_contracts:
            # Derivative not found in reference data
            return 'Residual'

        contract = deriv_contracts[isin]
        underlying_class = contract.get('underlying_asset_class', '').strip()

        if underlying_class == 'Equity':
            return 'Equity'
        elif underlying_class == 'FX':
            return 'FX'
        elif underlying_class in ('Rates', 'Fixed Income'):
            return 'Rates'
        else:
            return 'Residual'

    # Fallback
    return 'Residual'


def compute_pnl_attribution(
    positions_history_df: pd.DataFrame,
    market_moves_df: pd.DataFrame,
    pnl_actual_series: pd.Series,
    deriv_contracts: dict | None = None,
) -> pd.DataFrame:
    """
    Sensitivity-based daily P&L attribution.

    Decomposes actual P&L into contributions from equity returns, rate changes,
    and FX moves using position-level sensitivities (beta, duration).

    Methodology:
    - Equity: P&L_eq = beta * market_return * market_value_eur
    - Rates:  P&L_rates = -duration * yield_change * market_value_eur
    - FX:     P&L_fx = market_value_eur * fx_return (for non-EUR positions)
    - Residual: unexplained = P&L_actual - (P&L_eq + P&L_rates + P&L_fx)

    Large or persistent residuals signal model limitations, missing factors
    (credit spread, volatility, carry), wrong sensitivity estimates, or data
    issues. The residual is shown, not suppressed.

    Parameters
    ----------
    positions_history_df : pd.DataFrame
        Daily positions with columns: date, isin, asset_class, currency,
        market_value_eur, beta, dur_adj_mid.
        One row per position per date.
    market_moves_df : pd.DataFrame
        Daily market moves with DatetimeIndex and columns:
        r_market (equity return), dy (yield change), r_fx_<CCY> (FX returns).
        Example columns: 'r_market', 'dy', 'r_fx_USD', 'r_fx_GBP'
    pnl_actual_series : pd.Series
        Daily actual P&L in EUR, indexed by date.
    deriv_contracts : dict, optional
        Loaded from reference_data.load_derivative_contracts().
        Maps {isin: contract_dict}. Used to resolve derivative economic asset class.
        If None, derivatives map to Residual.

    Returns
    -------
    pd.DataFrame
        One row per date with columns:
        - date: trading date (index)
        - pnl_actual: actual P&L (EUR)
        - pnl_equity: equity factor contribution (EUR)
        - pnl_rates: rates factor contribution (EUR)
        - pnl_fx: FX factor contribution (EUR)
        - pnl_explained: sum of factor contributions (EUR)
        - pnl_residual: unexplained P&L (EUR)
        - pct_explained: % of actual P&L explained (0-100, nan if |actual| < 1,000)

    Examples
    --------
    >>> result = compute_pnl_attribution(
    ...     positions_history_df, market_moves_df, pnl_series, deriv_contracts
    ... )
    >>> print(result)
    """
    BASE_CCY = 'EUR'
    fx_cols  = {c: c.replace('r_fx_', '').upper()
                for c in market_moves_df.columns
                if c.startswith('r_fx_')}

    rows = []
    for date, moves in market_moves_df.iterrows():
        r_market = float(moves.get('r_market', 0.0))
        dy       = float(moves.get('dy', 0.0))

        # Use positions for this specific date
        pos_today = positions_history_df[
            positions_history_df['date'] == date
        ]

        if pos_today.empty:
            continue

        pnl_equity = 0.0
        pnl_rates  = 0.0
        pnl_fx     = 0.0

        for _, pos in pos_today.iterrows():
            mv         = float(pos['market_value_eur'])
            ccy        = str(pos.get('currency', BASE_CCY)).upper()

            # Resolve economic risk bucket (handles both regular and derivative assets)
            bucket = resolve_economic_risk_bucket(pos, deriv_contracts)

            if bucket == 'Equity':
                beta = pos.get('beta')
                if pd.notna(beta) and beta != 0:
                    pnl_equity += float(beta) * mv * r_market

            if bucket == 'Rates':
                dur = pos.get('dur_adj_mid')
                if pd.notna(dur) and dur != 0:
                    pnl_rates += -float(dur) * dy * mv

            if ccy != BASE_CCY and bucket in ('FX', 'Rates'):
                fx_col = f'r_fx_{ccy}'
                r_fx   = float(moves.get(fx_col, 0.0))
                pnl_fx += mv * r_fx

        pnl_explained = pnl_equity + pnl_rates + pnl_fx
        pnl_actual    = float(pnl_actual_series.get(date, float('nan')))
        pnl_residual  = pnl_actual - pnl_explained

        pct_explained = (
            abs(pnl_explained) / abs(pnl_actual)
            if pd.notna(pnl_actual) and abs(pnl_actual) > 1_000
            else float('nan')
        )

        rows.append({
            'date':          date,
            'pnl_actual':    pnl_actual,
            'pnl_equity':    pnl_equity,
            'pnl_rates':     pnl_rates,
            'pnl_fx':        pnl_fx,
            'pnl_explained': pnl_explained,
            'pnl_residual':  pnl_residual,
            'pct_explained': pct_explained,
        })

    return pd.DataFrame(rows).set_index('date')
