"""
Leverage computation — Gross and Commitment method.

Implements AIFMD Article 7 / EU 231/2013 leverage calculation.
Supports both open-ended (HF, UCITS) and closed-ended (PE, Infra) funds.

Regulatory basis:
    AIFMD (Directive 2011/61/EU) — Article 7 leverage limits
    Delegated Regulation EU 231/2013 — Articles 7-10 leverage methodology
    Recitals 13-14 — borrowing and capital call facility treatment
"""

import pandas as pd
from typing import Tuple, Dict
from fund_risk_workflow.data.database import get_engine, Position
from sqlalchemy.orm import Session
from fund_risk_workflow.risk.leverage_config import INSTRUMENT_SOURCE



def build_bbg_maps(fund_id: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Build Bloomberg ticker mappings from position database.

    Parameters
    ----------
    fund_id : str
        Fund identifier (e.g., 'AIFM_HedgeFund')

    Returns
    -------
    currency_bbg_map : dict
        {instrument_name → bloomberg_ticker} for FX positions
    deriv_bbg_map : dict
        {instrument_name → bloomberg_ticker} for Derivative positions
    """
    ENGINE = get_engine()

    currency_bbg_map = {}
    deriv_bbg_map = {}

    with Session(ENGINE) as session:
        positions = session.query(Position).filter_by(fund_id=fund_id).all()

        for pos in positions:
            if pos.asset_class == 'FX' and pos.bloomberg_ticker:
                currency_bbg_map[pos.instrument_name] = pos.bloomberg_ticker
            elif pos.asset_class == 'Derivative' and pos.bloomberg_ticker:
                deriv_bbg_map[pos.instrument_name] = pos.bloomberg_ticker

    return currency_bbg_map, deriv_bbg_map


def compute_derivative_notionals(
    risk_df: pd.DataFrame,
    bbg,
    deriv_bbg_map: Dict[str, str],
    currency_bbg_map: Dict[str, str],
) -> Tuple[Dict, Dict]:
    """
    Compute gross and commitment-method notionals for derivatives.

    Parameters
    ----------
    risk_df : pd.DataFrame
        Risk-ready positions with asset_class, quantity, is_hedge columns
    bbg : MockBloomberg or BloombergAPI
        Bloomberg data provider
    deriv_bbg_map : dict
        {instrument_name → bloomberg_ticker} for derivatives
    currency_bbg_map : dict
        {instrument_name → bloomberg_ticker} for FX rates

    Returns
    -------
    deriv_gross_map : dict
        {row_index → notional_eur} for gross method
    deriv_commitment_map : dict
        {row_index → delta_adjusted_notional_eur} for commitment method
    """

    deriv_gross_map = {}
    deriv_commitment_map = {}

    mask_derivative = risk_df['asset_class'] == 'Derivative'
    deriv_rows = risk_df[mask_derivative].copy()

    for idx, row in deriv_rows.iterrows():
        instrument_name = row['instrument_name']

        if instrument_name not in deriv_bbg_map:
            continue

        ticker = deriv_bbg_map[instrument_name]
        bbg_data = bbg.bdp(
            ticker, ['DELTA', 'OPT_UNDL_PX', 'CONTRACT_SIZE', 'CRNCY']
        )

        delta = bbg_data.loc[ticker, 'DELTA']
        undl_px = bbg_data.loc[ticker, 'OPT_UNDL_PX']
        contract_size = bbg_data.loc[ticker, 'CONTRACT_SIZE']
        currency = bbg_data.loc[ticker, 'CRNCY']
        qtd = row['quantity']

        # FX conversion
        ticker_fx = currency_bbg_map.get(currency)
        if ticker_fx:
            fx_data = bbg.bdp(ticker_fx, ['PX_LAST'])
            fx_rate = 1 / fx_data.loc[ticker_fx, 'PX_LAST']
        else:
            fx_rate = 1.0

        # Gross: absolute notional
        deriv_gross_map[idx] = abs(qtd) * contract_size * undl_px * fx_rate

        # Commitment: delta-adjusted, netting allowed for hedges only
        if row['is_hedge'] == 1:
            deriv_commitment_map[idx] = 0.0  # Hedges excluded from commitment
        else:
            deriv_commitment_map[idx] = (
                delta * qtd * contract_size * undl_px * fx_rate
            )

    return deriv_gross_map, deriv_commitment_map


def compute_leverage(
    risk_df: pd.DataFrame,
    nav: float,
    bbg,
    fund_id: str,
    borrowings_eur: float = 0.0,
) -> dict:
    """
    Compute gross and commitment method leverage per AIFMD Article 7.

    Parameters
    ----------
    risk_df : pd.DataFrame
        Risk-ready positions with market_value_eur, asset_class, is_hedge columns
    nav : float
        Fund NAV in EUR
    bbg : MockBloomberg or BloombergAPI
        Bloomberg data provider
    fund_id : str
        Fund identifier for BBG map lookup
    borrowings_eur : float, optional
        Current borrowings in EUR (prime broker debit). Default 0.

    Returns
    -------
    dict with keys:
        gross_exposure : float
        gross_leverage : float
        commitment_exposure : float
        commitment_leverage : float
    """

    # Build Bloomberg mappings
    currency_bbg_map, deriv_bbg_map = build_bbg_maps(fund_id)

    # Compute derivative notionals
    deriv_gross_map, deriv_commitment_map = compute_derivative_notionals(
        risk_df, bbg, deriv_bbg_map, currency_bbg_map
    )

    # ── GROSS METHOD (Article 7) ─────────────────────────────────────────────
    # Cash and Borrowing rows excluded; borrowings added separately at absolute value
    risk_df_copy = risk_df.copy()
    risk_df_copy['abs_exposure'] = risk_df_copy['market_value_eur'].abs()

    risk_df_copy['gross_exposure'] = risk_df_copy.apply(
        lambda r: (
            deriv_gross_map.get(r.name, 0.0)
            if r['asset_class'] == 'Derivative'
            else (
                0.0
                if r['asset_class'] in ('Cash', 'Borrowing')
                else r['abs_exposure']
            )
        ),
        axis=1,
    )

    gross_exposure = risk_df_copy['gross_exposure'].sum() + borrowings_eur
    gross_leverage = gross_exposure / nav if nav > 0 else float('inf')

    # ── COMMITMENT METHOD (Article 8) ─────────────────────────────────────────
    # Netting allowed only for hedges; borrowings included at absolute value
    mask_eq = risk_df['asset_class'] == 'Equity'
    mask_long = risk_df['market_value_eur'] >= 0
    mask_hedge = risk_df['is_hedge'] == 1
    mask_spec = risk_df['is_hedge'] == 0

    long_eq = risk_df[mask_eq & mask_long]['market_value_eur'].sum()
    short_hedge = risk_df[mask_eq & ~mask_long & mask_hedge]['market_value_eur'].sum()
    short_spec = (
        risk_df[mask_eq & ~mask_long & mask_spec]['market_value_eur'].abs().sum()
    )
    net_eq = abs(long_eq + short_hedge) + short_spec

    bonds = (
        risk_df[risk_df['asset_class'].isin(['Bond', 'Loan', 'CLO'])][
            'market_value_eur'
        ]
        .abs()
        .sum()
    )

    fx = (
        risk_df[
            (risk_df['asset_class'] == 'FX') & (risk_df['is_hedge'] == 0)
        ]['market_value_eur']
        .abs()
        .sum()
    )

    deriv_notional_commitment = sum(deriv_commitment_map.values())

    commitment_exposure = (
        net_eq + bonds + fx + deriv_notional_commitment + borrowings_eur
    )
    commitment_leverage = (
        commitment_exposure / nav if nav > 0 else float('inf')
    )

    return {
        'gross_exposure': gross_exposure,
        'gross_leverage': gross_leverage,
        'commitment_exposure': commitment_exposure,
        'commitment_leverage': commitment_leverage,
        'deriv_notional_commitment': deriv_notional_commitment,
        'deriv_gross_map': deriv_gross_map,
        'risk_df': risk_df_copy,  # with gross_exposure column added
    }


def compute_granular_leverage_breakdown(
    risk_df: pd.DataFrame,
    nav: float,
    borrowings_eur: float = 0.0,
) -> pd.DataFrame:
    """
    Compute AIFMD II granular leverage breakdown by asset class and source.

    Groups positions by asset_class and sub_asset_class, computes gross exposure
    and position count, maps to instrument source (borrowing, listed, OTC), and
    optionally appends borrowing row.

    Parameters
    ----------
    risk_df : pd.DataFrame
        Risk-ready positions with asset_class, sub_asset_class, gross_exposure columns
    nav : float
        Fund NAV in EUR

    borrowings_eur : float, optional
        Total borrowings in EUR. Default 0.

    Returns
    -------
    pd.DataFrame
        Granular breakdown with columns: asset_class, sub_asset_class, gross_eur,
        n_positions, gross_x_nav, source, listed_otc
    """

    instrument_source = INSTRUMENT_SOURCE
    
    # Group by asset class and sub-asset class
    granular = risk_df.groupby(['asset_class', 'sub_asset_class']).agg(
        gross_eur=('gross_exposure', 'sum'),
        n_positions=('isin', 'count'),
    ).reset_index()

    # Compute weight as multiple of NAV
    granular['gross_x_nav'] = granular['gross_eur'] / nav

    # Map source and listed/OTC classification
    granular['source'] = granular.apply(
        lambda r: instrument_source.get(
            (r['asset_class'], r['sub_asset_class']),
            ('Other', 'Other'),
        )[0],
        axis=1,
    )
    granular['listed_otc'] = granular.apply(
        lambda r: instrument_source.get(
            (r['asset_class'], r['sub_asset_class']),
            ('Other', 'Other'),
        )[1],
        axis=1,
    )

    # Exclude zero-exposure rows (e.g., cash)
    granular = granular[granular['gross_eur'] > 0].sort_values(
        'gross_eur', ascending=False
    )

    # Append borrowing row if borrowings present
    if borrowings_eur > 0:
        borrow_row = pd.DataFrame(
            [
                {
                    'asset_class': 'Borrowing',
                    'sub_asset_class': 'PB Financing',
                    'gross_eur': borrowings_eur,
                    'n_positions': 1,
                    'gross_x_nav': borrowings_eur / nav,
                    'source': 'Financial Borrowing',
                    'listed_otc': 'N/A',
                }
            ]
        )
        granular = pd.concat([granular, borrow_row], ignore_index=True)

    return granular
