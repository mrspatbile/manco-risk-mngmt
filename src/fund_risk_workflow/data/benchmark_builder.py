"""
Canonical benchmark return builder.

Centralizes all benchmark construction logic to ensure consistent,
reproducible benchmark returns across relative VaR and attribution workflows.

Functions
---------
    build_benchmark_returns()   Build composite benchmark returns from reference portfolio config
"""

import pandas as pd
from fund_risk_workflow.data.reference_data import load_reference_portfolio


def build_benchmark_returns(
    reference_portfolio_id: str,
    bbg,
    start_date: str,
    valuation_date: str,
) -> pd.Series:
    """
    Build composite benchmark returns from reference portfolio config.

    Loads the reference portfolio definition by ID, fetches price histories
    for all components, aligns dates, and computes weighted composite returns.

    This is the canonical path for all benchmark construction. Both relative VaR
    and P&L attribution should use this function to ensure consistency.

    Parameters
    ----------
    reference_portfolio_id : str
        Reference portfolio identifier (e.g., 'global_equity_60_eur_gov_40', 'sp500_reference')
    bbg : MockBloomberg or BloombergAPI
        Bloomberg data provider
    start_date : str
        Start date for price history (YYYY-MM-DD)
    valuation_date : str
        End date for price history (YYYY-MM-DD)

    Returns
    -------
    pd.Series
        Daily returns as a decimal series, indexed by date.
        Length = number of business days in [start_date, valuation_date).

    Raises
    ------
    FileNotFoundError
        If reference portfolio config file does not exist
    ValueError
        If config is invalid (missing fields, weights don't sum to 1.0, etc.)
    Exception
        If Bloomberg data fetch fails for any component

    Examples
    --------
    >>> benchmark_returns = build_benchmark_returns(
    ...     'global_equity_60_eur_gov_40',
    ...     bbg,
    ...     '2026-01-01',
    ...     '2026-03-31'
    ... )
    >>> print(benchmark_returns.index.min(), benchmark_returns.index.max())
    >>> print(f"Rows: {len(benchmark_returns)}")
    """
    # Load and validate reference portfolio config
    ref_portfolio = load_reference_portfolio(reference_portfolio_id)
    components = ref_portfolio.get('components', [])

    if not components:
        raise ValueError(
            f"Reference portfolio '{reference_portfolio_id}' has no components"
        )

    # Validate weights sum to 1.0
    total_weight = sum(c.get('weight', 0) for c in components)
    if not (0.99 < total_weight < 1.01):
        raise ValueError(
            f"Reference portfolio '{reference_portfolio_id}' weights sum to {total_weight:.4f}, not 1.0"
        )

    # Fetch price history for each component
    component_returns = {}
    for comp in components:
        ticker = comp['proxy_ticker']
        identifier = comp['identifier']

        try:
            hist = bbg.bdh(ticker, 'PX_LAST', start_date, valuation_date)
            if hist.empty:
                raise ValueError(f"No price data for {ticker} in [{start_date}, {valuation_date}]")

            # Calculate daily percent changes
            ret = hist['PX_LAST'].pct_change().dropna()
            component_returns[identifier] = ret

        except Exception as e:
            raise ValueError(
                f"Failed to fetch data for component '{identifier}' (ticker: {ticker}): {e}"
            )

    # Align all component return series to the same date range
    # Use the shortest series as the reference (conservative approach)
    min_len = min(len(ret) for ret in component_returns.values())
    aligned_returns = {k: v.iloc[-min_len:] for k, v in component_returns.items()}

    # Build composite benchmark returns: weighted sum
    composite = pd.Series(0.0, index=aligned_returns[list(aligned_returns.keys())[0]].index)

    for comp in components:
        weight = comp['weight']
        comp_id = comp['identifier']
        composite = composite.add(aligned_returns[comp_id] * weight, fill_value=0.0)

    return composite.dropna()
