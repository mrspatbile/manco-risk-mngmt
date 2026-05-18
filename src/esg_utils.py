"""
esg_utils.py
============
ESG risk indicator utilities for all fund notebooks.

Functions
---------
build_esg_df(risk_df, bbg, engine, fund_id, date)
    Builds position-level ESG DataFrame with look-through for derivatives.

esg_portfolio_summary(esg_df, nav)
    Computes portfolio-level weighted ESG metrics and flags.

ESG_THRESHOLD : int
    Internal RMP threshold below which ESG score is flagged. Default 30.
    Not prescribed by regulation; defined in the Risk Management Policy.
"""

import pandas as pd
import numpy as np
from src.database import query_positions

ESG_THRESHOLD = 30

ESG_FIELDS = ['ESG_SCORE', 'ENV_SCORE', 'SOC_SCORE', 'GOV_SCORE',
              'CONTROVERSY_FLAG', 'CARBON_INTENSITY']


def build_esg_df(
    risk_df: pd.DataFrame,
    bbg,
    engine,
    fund_id: str,
    date: str,
) -> pd.DataFrame:
    """
    Build position-level ESG DataFrame with look-through for derivatives.

    For liquid instruments: ESG data fetched from Bloomberg via bdp.
    For illiquid instruments: ESG data from fund admin embedded in positions.
    For derivatives: delta-adjusted notional used as ESG exposure weight.
    For futures: full notional used (delta = 1).
    For FX: no ESG exposure assigned.

    Parameters
    ----------
    risk_df : pd.DataFrame
        Enriched positions from get_risk_ready_df.
    bbg : MockBloomberg
        Bloomberg connection.
    engine : sa.Engine
        SQLAlchemy engine.
    fund_id : str
        Fund identifier.
    date : str
        Valuation date.

    Returns
    -------
    pd.DataFrame with columns:
        instrument_name, asset_class, market_value_eur, weight_pct,
        esg_score, env_score, soc_score, gov_score, controversy_flag,
        carbon_intensity, esg_exposure_eur
    """
    raw_positions = query_positions(engine, fund_id, date)
    ticker_map    = dict(zip(raw_positions['isin'],
                             raw_positions['bloomberg_ticker']))
    esg_rows = []

    for _, pos in risk_df.iterrows():
        row = {
            'instrument_name' : pos['instrument_name'],
            'asset_class'     : pos['asset_class'],
            'sub_asset_class' : pos.get('sub_asset_class', ''),
            'market_value_eur': pos['market_value_eur'],
            'weight_pct'      : pos['weight_pct'],
        }
        ticker = ticker_map.get(pos['isin'])

        # fetch ESG from Bloomberg or use fund admin data
        if ticker and pd.notna(ticker):
            bbg_esg = bbg.bdp(ticker, ESG_FIELDS)
            for f in ESG_FIELDS:
                row[f.lower()] = bbg_esg.loc[ticker, f]
        else:
            for f in ESG_FIELDS:
                row[f.lower()] = pos.get(f.lower())

        # ESG exposure: delta-adjusted for derivatives, full notional otherwise
        if (pos['asset_class'] == 'Derivative' and
                ticker and pd.notna(ticker)):
            bbg_d         = bbg.bdp(ticker,
                                    ['DELTA', 'OPT_UNDL_PX', 'CONTRACT_SIZE'])
            delta         = abs(bbg_d.loc[ticker, 'DELTA'])
            undl_px       = bbg_d.loc[ticker, 'OPT_UNDL_PX']
            contract_size = bbg_d.loc[ticker, 'CONTRACT_SIZE']
            quantity      = abs(pos['quantity'])
            fx_rate       = pos.get('fx_rate', 1.0)
            row['esg_exposure_eur'] = (delta * quantity *
                                       contract_size * undl_px * fx_rate)
        elif pos['asset_class'] == 'FX':
            row['esg_exposure_eur'] = 0.0
        elif pos['asset_class'] == 'Cash':
            row['esg_exposure_eur'] = 0.0
        else:
            row['esg_exposure_eur'] = abs(pos['market_value_eur'])

        esg_rows.append(row)

    return pd.DataFrame(esg_rows)


def esg_portfolio_summary(
    esg_df: pd.DataFrame,
    nav: float,
) -> dict:
    """
    Compute portfolio-level weighted ESG metrics and flags.

    Parameters
    ----------
    esg_df : pd.DataFrame
        Output of build_esg_df.
    nav : float
        Fund NAV in EUR.

    Returns
    -------
    dict with keys:
        wav_esg, wav_env, wav_soc, wav_gov, wav_carbon,
        pct_low_esg, pct_controversy, controversies
    """
    scored = esg_df[esg_df['esg_score'].notna()].copy()
    total  = scored['esg_exposure_eur'].sum()

    if total == 0:
        return {}

    wav_esg   = (scored['esg_score'] *
                 scored['esg_exposure_eur']).sum() / total
    wav_env   = (scored['env_score'] *
                 scored['esg_exposure_eur']).sum() / total
    wav_soc   = (scored['soc_score'] *
                 scored['esg_exposure_eur']).sum() / total
    wav_gov   = (scored['gov_score'] *
                 scored['esg_exposure_eur']).sum() / total
    wav_carb  = (scored['carbon_intensity'].fillna(0) *
                 scored['esg_exposure_eur']).sum() / total

    low_esg      = scored[scored['esg_score'] < ESG_THRESHOLD]
    controversies = esg_df[esg_df['controversy_flag'] == True]

    pct_low_esg  = low_esg['esg_exposure_eur'].sum() / total * 100
    pct_controv  = (controversies['esg_exposure_eur'].sum() /
                    esg_df['esg_exposure_eur'].sum() * 100
                    if esg_df['esg_exposure_eur'].sum() > 0 else 0)

    return {
        'wav_esg'       : round(wav_esg, 1),
        'wav_env'       : round(wav_env, 1),
        'wav_soc'       : round(wav_soc, 1),
        'wav_gov'       : round(wav_gov, 1),
        'wav_carbon'    : round(wav_carb, 1),
        'pct_low_esg'   : round(pct_low_esg, 1),
        'pct_controversy': round(pct_controv, 1),
        'controversies' : controversies,
    }