"""
leverage.py
===========
Pure leverage computation module.

Computes gross and commitment leverage per EU Regulation 231/2013 Articles 7-8.

All functions are stateless, depend only on numpy/pandas, and require
no database access, file I/O, or external services (Bloomberg is optional).

Functions
---------
    compute_leverage()   Gross and commitment leverage (EU231/2013 Arts. 7-8)
"""

import pandas as pd
from fund_risk_workflow.computation.derivatives import compute_derivative_exposures_portfolio
from fund_risk_workflow.data.reference_data import load_derivative_contracts


def compute_leverage(
    positions_df: pd.DataFrame,
    nav: float,
    bbg=None,
    deriv_bbg_map: dict | None = None,
    currency_bbg_map: dict | None = None,
    external_borrowings_eur: float = 0.0,
) -> dict:
    """
    Compute gross and commitment leverage per EU231/2013 Articles 7-8.

    Mirrors the Section 4 notebook computation exactly when bbg and maps
    are provided. Falls back to abs(market_value_eur) for derivatives
    when bbg is not available (conservative; correct for linear instruments).

    Parameters
    ----------
    positions_df     : enriched positions DataFrame
    nav              : fund NAV in EUR
    bbg              : MockBloomberg instance (optional)
    deriv_bbg_map    : dict  instrument_name → BBG ticker
    currency_bbg_map : dict  CCY → BBG FX ticker  e.g. {'USD': 'EURUSD Curncy'}
    external_borrowings_eur : float, default 0.0
        External borrowings in EUR (e.g., from parent company)

    Returns
    -------
    dict with keys:
        gross_leverage, commitment_leverage,
        gross_exposure, commitment_exposure,
        long_eq, short_hedge, short_spec, net_eq,
        bonds, fx_exposure, deriv_notional_commitment, borrowings
    """
    df = positions_df.copy()
    df['abs_exposure'] = df['market_value_eur'].abs()

    # ── derivative notionals ───────────────────────────────────────────────
    deriv_gross_map:      dict = {}
    deriv_commitment_map: dict = {}

    deriv_df = df[df['asset_class'] == 'Derivative'].copy()

    if len(deriv_df) > 0:
        # Require Bloomberg and reference data for derivative notional computation
        # Do NOT fall back to market value, as this materially understates exposure
        # when contract multiplier or underlying notional is required
        if bbg is None:
            missing_derivs = deriv_df['isin'].tolist()
            raise ValueError(
                f"Derivative notional exposure computation requires Bloomberg data provider, "
                f"but bbg is None. Cannot compute exposure for derivatives: {missing_derivs}. "
                f"AIFMD leverage calculation cannot proceed without required market inputs."
            )

        if deriv_bbg_map is None:
            missing_derivs = deriv_df[['isin', 'instrument_name']].to_dict('records')
            raise ValueError(
                f"Derivative notional exposure computation requires Bloomberg ticker mapping, "
                f"but deriv_bbg_map is None. Cannot compute exposure for derivatives: {missing_derivs}. "
                f"AIFMD leverage calculation cannot proceed without required market data sources."
            )

        try:
            deriv_contracts = load_derivative_contracts()

            # Add bloomberg_ticker column from deriv_bbg_map for helper
            deriv_df['bloomberg_ticker'] = deriv_df['instrument_name'].map(deriv_bbg_map)

            # Check for unmapped derivatives
            unmapped = deriv_df[deriv_df['bloomberg_ticker'].isna()]
            if len(unmapped) > 0:
                unmapped_list = unmapped[['isin', 'instrument_name']].to_dict('records')
                raise ValueError(
                    f"Derivative Bloomberg ticker mapping incomplete. "
                    f"Cannot find Bloomberg tickers for derivatives: {unmapped_list}. "
                    f"Check deriv_bbg_map and position data."
                )

            # Compute using helper
            helper_result = compute_derivative_exposures_portfolio(
                deriv_df, bbg, deriv_contracts, currency_bbg_map=currency_bbg_map
            )

            # Map helper outputs to leverage format
            for _, pos_result in helper_result['by_position'].iterrows():
                idx = deriv_df[deriv_df['isin'] == pos_result['isin']].index[0]
                deriv_gross_map[idx] = pos_result['gross_notional_eur']

                # Commitment: use delta-adjusted, then apply hedge netting
                delta_adj = pos_result['delta_adjusted_notional_eur']
                deriv_commitment_map[idx] = (
                    delta_adj
                    if deriv_df.loc[idx, 'is_hedge'] != 1 else 0.0
                )

        except ValueError:
            # Re-raise validation errors from helper or mapping
            raise
        except Exception as e:
            # Any other error from helper computation
            deriv_list = deriv_df[['isin', 'instrument_name', 'bloomberg_ticker']].to_dict('records')
            raise ValueError(
                f"Derivative notional exposure computation failed for derivatives: {deriv_list}. "
                f"Helper error: {str(e)}. "
                f"AIFMD leverage calculation cannot use market_value_eur as fallback for notional exposure."
            ) from e

    # ── gross (Art. 7) ─────────────────────────────────────────────────
    # Cash (uninvested) excluded; Borrowing handled separately below.
    gross_exposure = df.apply(
        lambda r: deriv_gross_map.get(r.name, 0.0) if r['asset_class'] == 'Derivative'
        else (0.0 if r['asset_class'] in ('Cash', 'Borrowing') else r['abs_exposure']),
        axis=1,
    ).sum()

    # Borrowings — EU231/2013 Recital 13: all borrowings included at absolute value.
    # Exception (Recital 14): capital call credit facilities that are temporary and fully
    # covered by investor commitments are excluded (PE/infra only, not applicable to HF).
    borrowings = df.loc[df['asset_class'] == 'Borrowing', 'market_value_eur'].abs().sum()
    borrowings += abs(external_borrowings_eur)

    gross_exposure += borrowings
    gross_leverage  = gross_exposure / nav if nav else 0.0

    # ── commitment (Art. 8) ────────────────────────────────────────────
    mask_eq    = df['asset_class'] == 'Equity'
    mask_long  = df['market_value_eur'] >= 0
    mask_hedge = df['is_hedge'].fillna(0) == 1

    long_eq     = df.loc[mask_eq & mask_long,               'market_value_eur'].sum()
    short_hedge = df.loc[mask_eq & ~mask_long & mask_hedge,  'market_value_eur'].sum()
    short_spec  = df.loc[mask_eq & ~mask_long & ~mask_hedge, 'market_value_eur'].abs().sum()
    net_eq      = abs(long_eq + short_hedge) + short_spec

    bonds = df.loc[
        df['asset_class'].isin(['Bond', 'Loan', 'CLO']), 'market_value_eur'
    ].abs().sum()

    fx_exposure = df.loc[
        (df['asset_class'] == 'FX') & (df['is_hedge'].fillna(0) != 1),
        'market_value_eur',
    ].abs().sum()

    deriv_notional_commitment = sum(deriv_commitment_map.values())
    # Borrowings also added to commitment exposure (Recital 13 applies to both methods).
    commitment_exposure = net_eq + bonds + fx_exposure + deriv_notional_commitment + borrowings
    commitment_leverage = commitment_exposure / nav if nav else 0.0

    return {
        'gross_leverage'            : gross_leverage,
        'commitment_leverage'       : commitment_leverage,
        'gross_exposure'            : gross_exposure,
        'commitment_exposure'       : commitment_exposure,
        'long_eq'                   : long_eq,
        'short_hedge'               : short_hedge,
        'short_spec'                : short_spec,
        'net_eq'                    : net_eq,
        'bonds'                     : bonds,
        'fx_exposure'               : fx_exposure,
        'deriv_notional_commitment' : deriv_notional_commitment,
        'borrowings'                : borrowings,
    }
