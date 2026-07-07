"""
ucits_compliance_checks.py
==========================
UCITS position-level compliance validation.

Checks:
- Long-only constraint
- Position concentration (10% single position, ETF exempt)
- Eligible assets (liquidity)
- Portfolio weights sum
"""

import pandas as pd
from typing import Dict, List, Tuple


def check_long_only(positions: pd.DataFrame) -> Tuple[bool, Dict]:
    """
    Check that all positions are long (no shorts).

    Parameters
    ----------
    positions : pd.DataFrame
        Positions dataframe with 'market_value_eur' column

    Returns
    -------
    compliant : bool
    details : dict
        {'has_shorts': bool, 'short_positions': list}
    """
    has_shorts = (positions['market_value_eur'] < 0).any()
    short_positions = positions[positions['market_value_eur'] < 0]['instrument_name'].tolist() if has_shorts else []

    return not has_shorts, {
        'has_shorts': has_shorts,
        'short_positions': short_positions,
        'status': 'OK' if not has_shorts else 'FAIL'
    }


def check_position_concentration(positions: pd.DataFrame, nav: float) -> Tuple[bool, Dict]:
    """
    Check single-position 10% limit (ETFs exempt as diversified instruments).

    Parameters
    ----------
    positions : pd.DataFrame
        Positions dataframe
    nav : float
        Fund NAV in EUR

    Returns
    -------
    compliant : bool
    details : dict
        {'breaches': list of dicts, 'etf_exempt': bool, 'status': str}
    """
    positions['weight_abs'] = positions['market_value_eur'].abs() / nav * 100

    # ETFs are exempt
    non_etf = positions[positions['sub_asset_class'] != 'ETF'].copy()
    breaches = non_etf[non_etf['weight_abs'] > 10]

    breach_list = [
        {'instrument': row['instrument_name'], 'weight_pct': row['weight_abs']}
        for _, row in breaches.iterrows()
    ]

    compliant = len(breaches) == 0

    return compliant, {
        'breaches': breach_list,
        'breach_count': len(breaches),
        'etf_exempt': True,
        'status': 'OK' if compliant else f'FLAG - {len(breaches)} breaches'
    }


def check_eligible_assets(positions: pd.DataFrame) -> Tuple[bool, Dict]:
    """
    Check that all assets are UCITS eligible (listed, liquid).

    Currently: flag instruments with zero ADV (illiquid), excluding cash.

    Parameters
    ----------
    positions : pd.DataFrame
        Positions dataframe

    Returns
    -------
    compliant : bool
    details : dict
        {'illiquid': list of dicts, 'illiquid_count': int, 'status': str}
    """
    illiquid = positions[(positions['adv_eur'] == 0) & (positions['asset_class'] != 'Cash')]

    illiquid_list = [
        {'instrument': row['instrument_name'], 'asset_class': row['asset_class']}
        for _, row in illiquid.iterrows()
    ]

    compliant = len(illiquid_list) == 0

    return compliant, {
        'illiquid': illiquid_list,
        'illiquid_count': len(illiquid_list),
        'status': 'OK' if compliant else f'FLAG - {len(illiquid_list)} illiquid'
    }


def check_weights_sum(positions: pd.DataFrame) -> Tuple[bool, Dict]:
    """
    Check that position weights sum to 100% (within 1% tolerance).

    Parameters
    ----------
    positions : pd.DataFrame
        Positions dataframe with 'weight_pct' column

    Returns
    -------
    compliant : bool
    details : dict
        {'weight_sum_pct': float, 'tolerance': float, 'status': str}
    """
    weight_sum = positions['weight_pct'].sum()
    tolerance = 1.0
    compliant = abs(weight_sum - 100) < tolerance

    return compliant, {
        'weight_sum_pct': weight_sum,
        'tolerance': tolerance,
        'status': 'OK' if compliant else 'FLAG'
    }


def run_ucits_compliance_checks(positions: pd.DataFrame, nav: float) -> Dict:
    """
    Run all UCITS position-level compliance checks.

    Parameters
    ----------
    positions : pd.DataFrame
        Positions dataframe
    nav : float
        Fund NAV in EUR

    Returns
    -------
    dict with keys:
        {
            'long_only': {...},
            'concentration': {...},
            'eligible_assets': {...},
            'weights': {...},
            'overall_compliant': bool,
            'overall_status': str
        }
    """
    long_only_ok, long_only_details = check_long_only(positions)
    conc_ok, conc_details = check_position_concentration(positions, nav)
    assets_ok, assets_details = check_eligible_assets(positions)
    weights_ok, weights_details = check_weights_sum(positions)

    overall_compliant = long_only_ok and conc_ok and assets_ok and weights_ok

    return {
        'long_only': long_only_details,
        'concentration': conc_details,
        'eligible_assets': assets_details,
        'weights': weights_details,
        'overall_compliant': overall_compliant,
        'overall_status': 'PASS' if overall_compliant else 'REVIEW'
    }
