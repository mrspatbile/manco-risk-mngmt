"""
derivatives.py
==============
Canonical derivative exposure computation module.

Computes exposure bases (gross notional, delta-adjusted notional) for derivative
positions. Does not apply regulatory logic (hedge netting, AIFMD vs UCITS rules);
that is caller's responsibility.

All functions are stateless, depend only on numpy/pandas, and return raw exposure
metrics. Caller chooses which basis to use for AIFMD gross exposure method,
AIFMD commitment exposure method, ESG exposure, or other workflows.

Functions
---------
    fetch_derivative_market_inputs()    Fetch DELTA, OPT_UNDL_PX, CONTRACT_SIZE from Bloomberg
    compute_derivative_exposure()       Compute exposure bases for one position
    compute_derivative_exposures_portfolio()  Compute exposures for portfolio snapshot
"""

import pandas as pd


def fetch_derivative_market_inputs(
    bloomberg_ticker: str,
    bbg,
    cache: dict | None = None,
    contract_type: str | None = None,
) -> dict:
    """
    Fetch DELTA, OPT_UNDL_PX/PX_LAST, CONTRACT_SIZE from Bloomberg for a derivative.

    Supports optional per-run cache to avoid repeated fetches of the same
    ticker within a single portfolio calculation.

    Parameters
    ----------
    bloomberg_ticker : str
        Bloomberg ticker (e.g., 'SPXW 260619P05500 Index', 'SPY US Equity', 'EURUSD Curncy')
    bbg : MockBloomberg or BloombergAPI
        Bloomberg data provider
    cache : dict, optional
        Running cache {ticker: market_inputs_dict}. Modified in-place.
    contract_type : str, optional
        'future', 'option', or 'forward'. Used to select appropriate price field.

    Returns
    -------
    dict with keys:
        delta : float or None
            Hedge ratio (None if not available or not applicable to futures/forwards)
        underlying_price : float
            OPT_UNDL_PX (options), PX_LAST (spot/forward)
        contract_size : float
            CONTRACT_SIZE (multiplier). Defaults to 1 if not found.
        ccy : str
            Settlement currency from CRNCY

    Raises
    ------
    ValueError
        If bloomberg_ticker is None or empty
    """
    if not bloomberg_ticker:
        raise ValueError("bloomberg_ticker is required and cannot be empty")

    # Check cache first
    if cache is not None and bloomberg_ticker in cache:
        return cache[bloomberg_ticker]

    # Fetch from Bloomberg
    bd = bbg.bdp(
        bloomberg_ticker,
        ['DELTA', 'OPT_UNDL_PX', 'PX_LAST', 'CONTRACT_SIZE', 'CRNCY']
    )

    delta = bd.loc[bloomberg_ticker, 'DELTA']

    # For options, use OPT_UNDL_PX; for futures/forwards, use PX_LAST (spot/forward price)
    underlying_price = bd.loc[bloomberg_ticker, 'OPT_UNDL_PX']
    if pd.isna(underlying_price):
        underlying_price = bd.loc[bloomberg_ticker, 'PX_LAST']

    contract_size = bd.loc[bloomberg_ticker, 'CONTRACT_SIZE']
    ccy = bd.loc[bloomberg_ticker, 'CRNCY']

    # Handle NaN values
    if pd.isna(contract_size) or contract_size is None:
        contract_size = 1.0  # Default multiplier
    if pd.isna(delta):
        delta = None
    if pd.isna(ccy):
        ccy = 'Unknown'

    market_inputs = {
        'delta': delta,
        'underlying_price': underlying_price,
        'contract_size': contract_size,
        'ccy': ccy,
    }

    # Update cache if provided
    if cache is not None:
        cache[bloomberg_ticker] = market_inputs

    return market_inputs


def compute_derivative_exposure(
    quantity: float,
    delta: float | None,
    underlying_price: float | None,
    contract_multiplier: float,
    fx_rate: float,
    contract_type: str,
    is_hedge: bool = False,
) -> dict:
    """
    Compute derivative exposure bases for a single position.

    Returns both gross and delta-adjusted notional. Caller decides which basis
    to use (AIFMD gross exposure method, AIFMD commitment exposure method, etc).

    Does not apply hedge netting; is_hedge is returned as-is for caller logic.

    Parameters
    ----------
    quantity : float
        Quantity of derivative contracts (may be negative)
    delta : float or None
        Hedge ratio. None for futures (treated as delta=1) or if unavailable.
    underlying_price : float or None
        Spot or forward price of underlying. Required for notional calc.
    contract_multiplier : float
        Notional units per contract (e.g., 100 for equity options)
    fx_rate : float
        Conversion factor from derivative settlement currency to EUR.
        Default 1.0 (already in EUR or rate already applied).
    contract_type : str
        'future', 'option', or 'forward'. Controls delta logic.
    is_hedge : bool, default False
        Flag for caller's hedge netting logic (not applied here).

    Returns
    -------
    dict with keys:
        market_value_eur : float
            Premium or cash position value (for reference)
        gross_notional_eur : float
            abs(qty) × contract_multiplier × underlying_price × fx_rate
            (no delta adjustment; input to AIFMD gross exposure method)
        delta_adjusted_notional_eur : float
            delta × qty × contract_multiplier × underlying_price × fx_rate
            (input to AIFMD commitment exposure method; hedge netting is caller's responsibility)
        underlying_price : float
            For reference
        contract_multiplier : float
            For reference
        delta : float or None
            For reference
        contract_type : str
            For reference
        exposure_basis : str
            'underlying_notional' (futures, forwards)
            'delta_adjusted_underlying_notional' (options)

    Raises
    ------
    ValueError
        If underlying_price is None and exposure is notional
    ValueError
        If contract_multiplier is None or ≤ 0
    """
    # Validate contract_multiplier
    if contract_multiplier is None or contract_multiplier <= 0:
        raise ValueError(
            f"contract_multiplier must be positive, got {contract_multiplier}"
        )

    # Validate underlying_price for notional exposures
    if underlying_price is None:
        raise ValueError(
            f"underlying_price is required for {contract_type} notional exposure calculation"
        )

    # Handle delta
    if delta is None:
        if contract_type in ('future', 'forward'):
            delta = 1.0  # Futures and forwards have implicit delta=1
        else:
            raise ValueError(
                f"delta is required for {contract_type} but was None"
            )

    # Compute gross notional (absolute value of quantity, full notional)
    gross_notional_eur = abs(quantity) * contract_multiplier * underlying_price * fx_rate

    # Compute delta-adjusted notional (preserves sign of quantity)
    delta_adjusted_notional_eur = delta * quantity * contract_multiplier * underlying_price * fx_rate

    # Determine exposure basis hint
    if contract_type == 'option':
        exposure_basis = 'delta_adjusted_underlying_notional'
    else:
        exposure_basis = 'underlying_notional'

    return {
        'market_value_eur': abs(quantity * contract_multiplier * underlying_price * fx_rate),
        'gross_notional_eur': gross_notional_eur,
        'delta_adjusted_notional_eur': delta_adjusted_notional_eur,
        'underlying_price': underlying_price,
        'contract_multiplier': contract_multiplier,
        'delta': delta,
        'contract_type': contract_type,
        'exposure_basis': exposure_basis,
    }


def compute_derivative_exposures_portfolio(
    risk_df: pd.DataFrame,
    bbg,
    deriv_contracts: dict,
    currency_bbg_map: dict | None = None,
) -> dict:
    """
    Compute derivative exposures for all derivative positions in portfolio.

    Aggregates single-position exposures and returns gross, delta-adjusted totals.
    Does not apply hedge netting; caller handles that logic.

    Parameters
    ----------
    risk_df : pd.DataFrame
        Risk-ready positions. Requires columns:
        - isin, quantity, market_value_eur, bloomberg_ticker
        - asset_class, is_hedge, price, fx_rate
    bbg : MockBloomberg or BloombergAPI
        Bloomberg data provider
    deriv_contracts : dict
        Loaded from reference_data.load_derivative_contracts()
        {isin: contract_dict}
    currency_bbg_map : dict, optional
        {ccy: bbg_fx_ticker} for FX conversions (e.g., {'USD': 'EURUSD Curncy'})

    Returns
    -------
    dict with keys:
        by_position : pd.DataFrame
            One row per derivative with columns:
            - isin, quantity, market_value_eur
            - gross_notional_eur, delta_adjusted_notional_eur
            - delta, underlying_price, contract_multiplier
            - exposure_basis, contract_type

        gross_total_eur : float
            Sum of gross_notional_eur for all derivatives
            (input to AIFMD gross exposure method)

        delta_adjusted_total_eur : float
            Sum of delta_adjusted_notional_eur for all derivatives
            (input to AIFMD commitment exposure method; hedge netting is caller's responsibility)

        by_contract_type : dict
            {'future': {...gross, delta_adj...}, 'option': {...}, 'forward': {...}}

        bbg_cache : dict
            Running cache of {ticker: market_inputs}

    Raises
    ------
    ValueError
        If any derivative is missing from deriv_contracts
    ValueError
        If required market inputs are unavailable and cannot be omitted
    """
    # Filter to derivatives only
    deriv_mask = risk_df['asset_class'] == 'Derivative'
    derivatives = risk_df[deriv_mask].copy()

    if len(derivatives) == 0:
        return {
            'by_position': pd.DataFrame(),
            'gross_total_eur': 0.0,
            'delta_adjusted_total_eur': 0.0,
            'by_contract_type': {},
            'bbg_cache': {},
        }

    # Running cache for Bloomberg fetches
    bbg_cache = {}

    rows = []
    for _, pos in derivatives.iterrows():
        isin = pos['isin']

        # Look up contract in reference data
        if isin not in deriv_contracts:
            raise ValueError(
                f"Derivative {isin} not found in derivative_contracts. "
                f"Available: {sorted(deriv_contracts.keys())}"
            )

        contract = deriv_contracts[isin]
        contract_type = contract['contract_type']
        contract_multiplier = contract['contract_multiplier']
        settlement_ccy = contract['settlement_currency']

        # Fetch market inputs from Bloomberg
        bbg_ticker = pos['bloomberg_ticker']
        if pd.isna(bbg_ticker) or not bbg_ticker:
            raise ValueError(
                f"Derivative {isin} has no bloomberg_ticker; cannot fetch market inputs"
            )

        market_inputs = fetch_derivative_market_inputs(bbg_ticker, bbg, cache=bbg_cache, contract_type=contract_type)
        delta = market_inputs.get('delta')
        underlying_price = market_inputs.get('underlying_price')

        # FX conversion if needed
        fx_rate = pos.get('fx_rate', 1.0)
        if settlement_ccy != 'EUR' and currency_bbg_map:
            fx_ticker = currency_bbg_map.get(settlement_ccy)
            if fx_ticker:
                fx_data = bbg.bdp(fx_ticker, 'PX_LAST')
                fx_rate_raw = fx_data.loc[fx_ticker, 'PX_LAST']
                if fx_rate_raw and not pd.isna(fx_rate_raw):
                    fx_rate = 1.0 / float(fx_rate_raw)  # Invert to get EUR conversion

        # Compute exposure
        try:
            exposure = compute_derivative_exposure(
                quantity=pos['quantity'],
                delta=delta,
                underlying_price=underlying_price,
                contract_multiplier=contract_multiplier,
                fx_rate=fx_rate,
                contract_type=contract_type,
                is_hedge=pos.get('is_hedge', False),
            )
        except ValueError as e:
            raise ValueError(f"Derivative {isin}: {str(e)}") from e

        # Build output row
        row = {
            'isin': isin,
            'quantity': pos['quantity'],
            'market_value_eur': pos['market_value_eur'],
            'gross_notional_eur': exposure['gross_notional_eur'],
            'delta_adjusted_notional_eur': exposure['delta_adjusted_notional_eur'],
            'delta': exposure['delta'],
            'underlying_price': exposure['underlying_price'],
            'contract_multiplier': exposure['contract_multiplier'],
            'contract_type': exposure['contract_type'],
            'exposure_basis': exposure['exposure_basis'],
        }
        rows.append(row)

    # Create output DataFrame
    by_position = pd.DataFrame(rows)

    # Compute totals
    gross_total_eur = by_position['gross_notional_eur'].sum()
    delta_adjusted_total_eur = by_position['delta_adjusted_notional_eur'].sum()

    # Aggregate by contract type
    by_contract_type = {}
    for contract_type in by_position['contract_type'].unique():
        mask = by_position['contract_type'] == contract_type
        by_contract_type[contract_type] = {
            'gross_total_eur': by_position.loc[mask, 'gross_notional_eur'].sum(),
            'delta_adjusted_total_eur': by_position.loc[mask, 'delta_adjusted_notional_eur'].sum(),
            'n_positions': mask.sum(),
        }

    return {
        'by_position': by_position,
        'gross_total_eur': float(gross_total_eur),
        'delta_adjusted_total_eur': float(delta_adjusted_total_eur),
        'by_contract_type': by_contract_type,
        'bbg_cache': bbg_cache,
    }
