"""
risk_utils.py
=============
Shared risk utility functions for AIFM and UCITS risk notebooks.
Implements VaR, ES, backtesting, stress scenarios and liquidity
functions in compliance with AIFMD, UCITS and ESMA guidelines.

Regulatory context
------------------
    AIFMD        : Directive 2011/61/EU
    UCITS        : Directive 2009/65/EC
    AIFMD II     : Directive 2024/927/EU (LMT tools — Art. 16a)
    ESMA LST     : ESMA34-39-897 (liquidity stress testing)
    ESMA backt.  : ESMA34-43-392 (VaR backtesting)
    Annex VI     : AIFMD Level 2 stress testing framework

Usage
-----
    from risk_utils import (
        var_historical, var_parametric, var_scale,
        es_historical, es_parametric, es_scale,
        kupiec_test, christoffersen_test,
        exception_report, full_backtest_report,
        stress_equity, stress_rates, stress_credit,
        stress_fx, stress_combined, stress_historical,
        stress_property, stress_rental, stress_ltv,
        days_to_liquidate, liquidity_buckets,
        redemption_stress, lmt_trigger_analysis,
        investor_concentration, load_investor_register,
        'load_counterparty',
        liquidity_adjusted_var, 'compute_pnl_attribution',
        'pre_trade_check',
    )
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm, t as student_t
from typing import Optional
from pathlib import Path

# Import canonical VaR functions from fund_risk_workflow.computation.var
from fund_risk_workflow.computation.var import (
    var_historical,
    var_parametric,
    var_scale,
    es_historical,
    es_parametric,
    es_scale,
    es_from_var,
    kupiec_test,
    christoffersen_test,
)

# Import canonical stress functions from fund_risk_workflow.computation.stress
from fund_risk_workflow.computation.stress import (
    HISTORICAL_SCENARIOS,
    stress_equity,
    stress_rates,
    stress_credit,
    stress_fx,
    stress_combined,
    stress_historical,
    stress_property,
    stress_rental,
    stress_ltv,
)

# Import canonical liquidity functions from fund_risk_workflow.computation.liquidity
from fund_risk_workflow.computation.liquidity import (
    days_to_liquidate,
    liquidity_buckets,
    compute_liquidity_profile,
    redemption_stress,
    lmt_trigger_analysis,
    investor_concentration,
    liquidity_adjusted_var,
)

# Import canonical leverage computation from fund_risk_workflow.computation.leverage
from fund_risk_workflow.computation.leverage import compute_leverage

# Import canonical P&L attribution from fund_risk_workflow.computation.attribution
from fund_risk_workflow.computation.attribution import compute_pnl_attribution

# HISTORICAL_SCENARIOS is now imported from fund_risk_workflow.computation.stress above

_DIR = Path(__file__).parent.parent.parent.parent  # src/fund_risk_workflow/risk/ -> project root 


# ================================================================
# VaR, ES, and Backtesting functions
# ================================================================
# NOTE: These functions are now imported from fund_risk_workflow.computation.var
# (the canonical pure VaR module). This section is preserved for
# backward compatibility; all implementations have been moved.


def exception_report(
    returns_series: pd.Series,
    var_series: pd.Series,
    confidence: float = 0.99,
    dates: Optional[pd.DatetimeIndex] = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    ESMA exception report: documents each VaR breach.
    For funds the regulatory standard is exception-based,
    not the Basel traffic light capital multiplier framework.

    Breach rate thresholds (ESMA/CSSF standard):
    - < 1% at 99% : model acceptable
    - 1-2% at 99% : review assumptions, document
    - > 2% at 99% : model review required, notify board

    Parameters
    ----------
    returns_series : pd.Series
        Daily P&L in decimal.
    var_series : pd.Series
        Daily VaR estimates as positive numbers.
    confidence : float
        Confidence level. Default 0.99.
    dates : pd.DatetimeIndex, optional
        Dates corresponding to returns and var series.

    Returns
    -------
    pd.DataFrame
        One row per breach with columns:
        date, returns, var, excess_loss, action_required
    """
    ret = np.asarray(returns_series)
    var = np.asarray(var_series)

    mask         = ~(np.isnan(ret) | np.isnan(var))
    breach_mask  = (ret < -var) & mask
    breach_idx   = np.where(breach_mask)[0]

    n            = mask.sum()
    n_breaches   = breach_mask.sum()
    breach_rate  = n_breaches / n if n > 0 else 0

    if breach_rate < 0.01:
        action = 'Model acceptable'
    elif breach_rate < 0.02:
        action = 'Review assumptions, document'
    else:
        action = 'Model review required, notify board'

    rows = []
    for idx in breach_idx:
        rows.append({
            'date'       : dates[idx] if dates is not None
                           else idx,
            'return'        : round(float(ret[idx]), 6),
            'var'        : round(float(var[idx]), 6),
            'excess_loss': round(float(-ret[idx] - var[idx]), 6),
            'action'     : action,
        })

    report = pd.DataFrame(rows)
    if verbose:
        print(f'Exception report ({confidence*100:.0f}% VaR):')
        print(f'  observations : {n}')
        print(f'  breaches     : {n_breaches}')
        print(f'  breach rate  : {breach_rate*100:.2f}%'
            f' (expected {(1-confidence)*100:.1f}%)')
        print(f'  action       : {action}')

    return report


def full_backtest_report(
    returns_series: pd.Series,
    var_dict: dict,
    dates: Optional[pd.DatetimeIndex] = None
) -> pd.DataFrame:
    """
    Full backtesting report running all tests for all
    confidence levels and models.

    Parameters
    ----------
    returns_series : pd.Series
        Daily returns in decimal.
    var_dict : dict
        Dictionary of {model_name: var_series}.
        e.g. {'historical': var_hist, 'parametric': var_param}
    dates : pd.DatetimeIndex, optional

    Returns
    -------
    pd.DataFrame
        Rows: models x confidence levels
        Columns: n_obs, n_breaches, breach_rate, expected,
                 kupiec_p, christoffersen_p, result

    Examples
    --------
    >>> report = full_backtest_report(
    ...     return,
    ...     {'historical': var_hist, 'parametric': var_param}
    ... )
    """
    rows = []
    for model_name, var_series in var_dict.items():
        for confidence in [0.99, 0.975, 0.95]:
            kup  = kupiec_test(returns_series, var_series, confidence)
            chri = christoffersen_test(
                returns_series, var_series, confidence)

            rows.append({
                'model'            : model_name,
                'confidence'       : f'{confidence*100:.1f}%',
                'n_obs'            : kup['n_obs'],
                'n_breaches'       : kup['n_breaches'],
                'breach_rate'      : kup['breach_rate'],
                'expected'         : kup['expected'],
                'kupiec_p'         : kup['p_value'],
                'christoffersen_p' : chri['p_value'],
                'result'           : (
                    'PASS'
                    if kup['result'] == 'PASS' and
                       chri['result'] == 'PASS'
                    else 'FAIL'
                ),
            })

    return pd.DataFrame(rows)


# ================================================================
# Stress, Liquidity, and Investor Concentration Functions
# ================================================================
# NOTE: All implementations moved to canonical locations:
# - stress_equity, stress_rates, stress_credit, stress_fx, stress_combined,
#   stress_historical, stress_property, stress_rental, stress_ltv
#   → from fund_risk_workflow.computation.stress
# - days_to_liquidate, liquidity_buckets, compute_liquidity_profile,
#   redemption_stress, lmt_trigger_analysis, investor_concentration,
#   liquidity_adjusted_var
#   → from fund_risk_workflow.computation.liquidity
# Functions are imported above and re-exported for backward compatibility.


# compute_pnl_attribution() is now imported from fund_risk_workflow.computation.attribution (see line 85)
# Canonical implementation: sensitivity-based daily P&L attribution (equity, rates, FX)


# ================================================================
# Pre-trade compliance
# ================================================================

_SIGMA_MARKET   = 0.010    # daily equity market vol (1%)
_SIGMA_RATES    = 0.005    # daily rate vol (50bps)
_Z99            = 2.3263   # norm.ppf(0.99)
_HOLDING_DAYS   = 20       # UCITS holding period (days)

_UCITS_INELIGIBLE = frozenset({
    'Loan', 'CLO', 'ABS', 'MBS', 'CMBS', 'CDO',
    'Real Estate', 'Property', 'Private Equity',
})

_HY_SUB_CLASSES = frozenset({
    'HY Corporate', 'Second Lien', 'Mezzanine', 'CLO BB', 'CLO Equity',
})
_HY_RATINGS = frozenset({
    'BB+', 'BB', 'BB-', 'B+', 'B', 'B-',
    'CCC+', 'CCC', 'CCC-', 'CC', 'C', 'D',
})


def _ptc_apply_trade(positions: pd.DataFrame, trade: dict) -> pd.DataFrame:
    """Return pro-forma positions after applying the proposed trade.

    pct_financed (0.0–1.0) in the trade dict controls how much of the notional
    is prime-broker financed vs cash-funded. 1.0 = fully leveraged (no cash
    reduction); 0.0 = fully cash-funded (cash reduced by full notional).
    Defaults to 1.0 so calls without the field behave as before.
    """
    direction = trade['direction'].lower()
    mv_delta  = float(trade['quantity']) * float(trade['price_eur'])
    if direction in ('sell', 'short'):
        mv_delta = -mv_delta

    pro_forma = positions.copy()
    mask = pro_forma['isin'] == trade['isin']

    if mask.any():
        pro_forma.loc[mask, 'market_value_eur'] += mv_delta
    else:
        new_row = {col: None for col in pro_forma.columns}
        new_row.update({
            'isin'              : trade['isin'],
            'asset_class'       : trade.get('asset_class', 'Equity'),
            'sub_asset_class'   : trade.get('sub_asset_class', ''),
            'market_value_eur'  : mv_delta,
            'beta'              : trade.get('beta', 1.0),
            'dur_adj_mid'       : trade.get('dur_adj_mid', 0.0),
            'currency'          : trade.get('currency', 'EUR'),
            'adv_eur'           : trade.get('adv_eur', 0.0),
            'is_direct_property': False,
            'sector'            : trade.get('sector', None),
        })
        pro_forma = pd.concat(
            [pro_forma, pd.DataFrame([new_row])], ignore_index=True
        )

    # pct_financed=0.0: cash-funded (cash reduced, no new borrowing)
    # pct_financed=1.0: fully PB financed (cash unchanged, borrowing created)
    pct_financed   = float(trade.get('pct_financed', 1.0))
    cash_reduction = mv_delta * (1.0 - pct_financed)
    if cash_reduction != 0.0:
        cash_mask = pro_forma['asset_class'] == 'Cash'
        if cash_mask.any():
            pro_forma.loc[cash_mask, 'market_value_eur'] -= cash_reduction

    # Leveraged portion creates a PB borrowing (EU231/2013 Recital 13: included in
    # both gross and commitment at absolute value). Modelled as a 'Borrowing' row
    # with negative market_value_eur so compute_leverage can pick it up.
    borrowing_notional = mv_delta * pct_financed
    if borrowing_notional > 0.0:
        borrow_mask = pro_forma['asset_class'] == 'Borrowing'
        if borrow_mask.any():
            pro_forma.loc[borrow_mask, 'market_value_eur'] -= borrowing_notional
        else:
            borrow_row = {col: None for col in pro_forma.columns}
            borrow_row.update({
                'asset_class'       : 'Borrowing',
                'sub_asset_class'   : 'PB Financing',
                'instrument_name'   : 'Prime Broker Financing',
                'market_value_eur'  : -borrowing_notional,
                'adv_eur'           : 0.0,
                'is_direct_property': False,
                'is_hedge'          : False,
            })
            pro_forma = pd.concat(
                [pro_forma, pd.DataFrame([borrow_row])], ignore_index=True
            )

    return pro_forma


def _ptc_portfolio_var(pro_forma: pd.DataFrame, nav: float) -> float:
    """
    20-day 99% parametric VaR as decimal fraction of NAV.
    Equity: beta-weighted. Rates: duration-weighted. Components independent.
    """
    if nav == 0:
        return 0.0
    eq = pro_forma[pro_forma['asset_class'] == 'Equity']
    bd = pro_forma[pro_forma['asset_class'] == 'Bond']
    port_beta = (eq['beta'].fillna(0) * eq['market_value_eur']).sum() / nav
    port_dur  = (bd['dur_adj_mid'].fillna(0) * bd['market_value_eur']).sum() / nav
    sigma = np.sqrt(
        (port_beta * _SIGMA_MARKET) ** 2 +
        (port_dur  * _SIGMA_RATES)  ** 2
    )
    return float(sigma * np.sqrt(_HOLDING_DAYS) * _Z99)


def _ptc_reference_var() -> float:
    """20-day 99% VaR for 60/40 reference portfolio (beta=1, 5yr duration)."""
    sigma = np.sqrt(
        (0.60 * _SIGMA_MARKET)       ** 2 +
        (0.40 * 5.0 * _SIGMA_RATES)  ** 2
    )
    return float(sigma * np.sqrt(_HOLDING_DAYS) * _Z99)


def _ptc_issuer_exposure(pro_forma: pd.DataFrame, nav: float) -> pd.Series:
    """
    Issuer exposure as % of NAV. Corporate issuer / single-name concentration.

    Excludes derivatives (FX forwards, index futures/options) which are not
    corporate issuers. Only includes direct positions with issuer metadata
    (equities, bonds, loans, CLOs) and single-name derivatives if explicit
    issuer look-through exists.

    Uses 'issuer' column if present, else 'isin'.
    """
    # Filter to non-derivative positions (corporate issuers only)
    issuer_universe = pro_forma[pro_forma['asset_class'] != 'Derivative']

    if len(issuer_universe) == 0:
        return pd.Series(dtype=float)

    key = 'issuer' if 'issuer' in issuer_universe.columns else 'isin'
    return (
        issuer_universe
        .groupby(issuer_universe[key].fillna(issuer_universe['isin']))['market_value_eur']
        .sum() / nav * 100
    )


def _breach(check: str, limit: float, actual: float,
            unit: str, message: str) -> dict:
    return {
        'check'  : check,
        'limit'  : limit,
        'actual' : round(actual, 4),
        'unit'   : unit,
        'message': message,
    }


def _check_ucits(
    pro_forma: pd.DataFrame, nav: float, trade: dict
) -> tuple:
    breaches: list = []
    metrics:  dict = {}

    # [1] Absolute VaR < 20% NAV (UCITS 20-day, 99%)
    abs_var = _ptc_portfolio_var(pro_forma, nav)
    metrics['absolute_var_pct'] = abs_var
    if abs_var > 0.20:
        breaches.append(_breach(
            'absolute_var_limit', 0.20, abs_var, '% NAV (decimal)',
            f'Post-trade absolute VaR {abs_var:.2%} exceeds UCITS limit 20.00% NAV '
            f'(UCITS SRRI, 20-day, 99%)'
        ))

    # [2] Relative VaR < 2x reference portfolio
    ref_var  = _ptc_reference_var()
    rel_mult = abs_var / ref_var if ref_var > 0 else 0.0
    metrics['relative_var_multiplier'] = rel_mult
    metrics['reference_var_pct']       = ref_var
    if rel_mult > 2.0:
        breaches.append(_breach(
            'relative_var_limit', 2.0, rel_mult, 'x reference',
            f'Post-trade VaR is {rel_mult:.2f}x reference portfolio '
            f'(60/40 benchmark), limit 2.0x'
        ))

    # [3] 5/10/40 rule (UCITSD Art. 52)
    # Scope: excludes government securities and ETFs/funds (apply look-through for ETFs).
    # Government bonds: sovereign risk monitored separately.
    # ETFs/funds: are vehicles, not issuers; constituent look-through applies.
    if 'sector' in pro_forma.columns:
        conc_universe = pro_forma[
            ((pro_forma['sector'].isna()) | (pro_forma['sector'] != 'Government')) &
            (~pro_forma['sub_asset_class'].isin(['ETF', 'Fund']))
        ]
    else:
        conc_universe = pro_forma[
            ~pro_forma['sub_asset_class'].isin(['ETF', 'Fund'])
        ]

    issuer_exp = _ptc_issuer_exposure(conc_universe, nav)
    above_10   = issuer_exp[issuer_exp > 10.0]
    above_5    = issuer_exp[issuer_exp >  5.0]
    sum_above_5 = float(above_5.sum())
    metrics['max_issuer_pct']      = float(issuer_exp.max()) if len(issuer_exp) else 0.0
    metrics['sum_above_5pct_issuers'] = sum_above_5
    for issuer, pct in above_10.items():
        breaches.append(_breach(
            '5_10_40_single_issuer_hard', 10.0, float(pct), '% NAV',
            f'Issuer {issuer}: {pct:.1f}% NAV — exceeds 10% hard limit (5/10/40 rule)'
        ))
    if sum_above_5 > 40.0:
        breaches.append(_breach(
            '5_10_40_bucket_limit', 40.0, sum_above_5, '% NAV',
            f'Positions >5% NAV aggregate to {sum_above_5:.1f}% — exceeds 40% bucket limit'
        ))

    # [4] Eligible assets (UCITSD Art. 50)
    asset_class = trade.get('asset_class', '')
    metrics['trade_eligible'] = asset_class not in _UCITS_INELIGIBLE
    if asset_class in _UCITS_INELIGIBLE:
        breaches.append(_breach(
            'eligible_assets_article_50', 1.0, 0.0, 'flag',
            f'{asset_class} ({trade.get("sub_asset_class","")}) is ineligible '
            f'under UCITSD Art. 50 — fund cannot hold this instrument'
        ))

    # [5] Counterparty exposure (OTC derivatives)
    cpty       = trade.get('counterparty')
    cpty_type  = trade.get('counterparty_type', 'non_credit_institution')
    cpty_limit = 0.10 if cpty_type == 'credit_institution' else 0.05
    if cpty and trade.get('asset_class') == 'Derivative':
        trade_mv_pct = abs(trade['quantity'] * trade['price_eur']) / nav if nav else 0.0
        metrics[f'counterparty_{cpty}_pct'] = trade_mv_pct
        if trade_mv_pct > cpty_limit:
            breaches.append(_breach(
                'counterparty_exposure', cpty_limit * 100,
                trade_mv_pct * 100, '% NAV',
                f'OTC counterparty {cpty} ({cpty_type}): {trade_mv_pct:.1%} NAV — '
                f'exceeds {cpty_limit:.0%} limit'
            ))

    # [6] Borrowing limit < 10% NAV (UCITSD Art. 83 — temporary borrowing only)
    # Proxy: negative cash balances. Real borrowing tracked via prime broker/custodian.
    cash_borrow = pro_forma.loc[
        (pro_forma['asset_class'] == 'Cash') &
        (pro_forma['market_value_eur'] < 0),
        'market_value_eur'
    ].sum()
    borrow_pct = abs(cash_borrow) / nav if nav else 0.0
    metrics['borrowing_pct'] = borrow_pct
    if borrow_pct > 0.10:
        breaches.append(_breach(
            'borrowing_limit', 10.0, borrow_pct * 100, '% NAV',
            f'Temporary borrowing {borrow_pct:.1%} NAV exceeds UCITSD Art. 83 limit 10%'
        ))

    return breaches, metrics


# compute_leverage() is now imported from fund_risk_workflow.computation.leverage (see line 81)
# Canonical implementation: EU231/2013 leverage calculation (Articles 7-8)


def _check_aifm_hf(
    pro_forma: pd.DataFrame,
    nav: float,
    trade: dict,
    counterparties_df=None,
    bbg=None,
    deriv_bbg_map: dict | None = None,
    currency_bbg_map: dict | None = None,
    positions_before: pd.DataFrame | None = None,
    nav_before: float | None = None,
    rmp: dict | None = None,
) -> tuple:
    breaches: list = []
    metrics:  dict = {}

    # [1] & [2] Gross and commitment leverage — EU231/2013 Articles 7-8
    lev = compute_leverage(pro_forma, nav, bbg=bbg,
                           deriv_bbg_map=deriv_bbg_map,
                           currency_bbg_map=currency_bbg_map)
    metrics.update({
        'gross_leverage'            : lev['gross_leverage'],
        'commitment_leverage'       : lev['commitment_leverage'],
        'gross_exposure'            : lev['gross_exposure'],
        'commitment_exposure'       : lev['commitment_exposure'],
        'net_eq'                    : lev['net_eq'],
        'bonds'                     : lev['bonds'],
        'fx_exposure'               : lev['fx_exposure'],
        'deriv_notional_commitment' : lev['deriv_notional_commitment'],
        'borrowings'                : lev['borrowings'],
    })
    # Leverage limits from RMP or defaults
    gross_lev_max = rmp['leverage_limits_internal']['gross_leverage_max'] if rmp else 3.00
    commit_lev_max = rmp['leverage_limits_internal']['commitment_leverage_max'] if rmp else 2.00

    if lev['gross_leverage'] > gross_lev_max:
        breaches.append(_breach(
            'gross_leverage', gross_lev_max, lev['gross_leverage'], 'x NAV',
            f"Post-trade gross leverage {lev['gross_leverage']:.2f}x exceeds {gross_lev_max*100:.0f}% NAV RMP limit"
        ))
    if lev['commitment_leverage'] > commit_lev_max:
        breaches.append(_breach(
            'commitment_leverage', commit_lev_max, lev['commitment_leverage'], 'x NAV',
            f"Post-trade commitment leverage {lev['commitment_leverage']:.2f}x exceeds {commit_lev_max*100:.0f}% NAV RMP limit"
        ))

    # [3] Single-issuer concentration — 25% NAV RMP limit
    # Only flag if the trade worsened the breach (pre-existing breaches are not the trade's fault).
    issuer_exp = _ptc_issuer_exposure(pro_forma, nav)
    pre_issuer_exp = _ptc_issuer_exposure(positions_before, nav) if positions_before is not None else pd.Series(dtype=float)
    metrics['max_issuer_pct'] = float(issuer_exp.max()) if len(issuer_exp) else 0.0

    # Add exposure % for the specific issuer in this trade
    # Use same grouping key as issuer_exp
    issuer_key = 'issuer' if 'issuer' in pro_forma.columns else 'isin'
    trade_issuer = trade.get(issuer_key) or trade.get('underlying_risk') or trade.get('issuer')
    if trade_issuer:
        metrics['trade_issuer_pct'] = float(issuer_exp.get(trade_issuer, 0.0))
    else:
        metrics['trade_issuer_pct'] = 0.0

    # Single-issuer concentration limit from RMP or default
    issuer_conc_max = rmp['concentration_limits_internal']['single_issuer_max_pct'] if rmp else 25.0

    for issuer, pct in issuer_exp[issuer_exp > issuer_conc_max].items():
        pre_pct = float(pre_issuer_exp.get(issuer, 0.0))
        if pct > pre_pct:
            breaches.append(_breach(
                'issuer_concentration', issuer_conc_max, float(pct), '% NAV',
                f'Issuer {issuer}: {pct:.1f}% NAV exceeds RMP single-issuer limit {issuer_conc_max}% (was {pre_pct:.1f}%)'
            ))

    # [4] Sector concentration — 30% NAV internal RMP limit
    # Scope: equities and corporate bonds/loans/CLOs by GICS sector.
    # Government bonds are excluded (sovereign risk monitored separately via country exposure).
    # FX, derivatives, and cash are excluded as cross-sectoral instruments.
    # Only flag if trade worsened the breach (pre-existing breaches are not the trade's fault).
    if 'sector' in pro_forma.columns:
        sector_universe = pro_forma[
            pro_forma['asset_class'].isin(['Equity', 'Bond', 'Loan', 'CLO']) &
            pro_forma['sector'].notna() &
            (pro_forma['sector'] != 'Government')
        ]
    else:
        sector_universe = pro_forma[pro_forma['asset_class'] == 'Equity']

    # Sector concentration: net sector weight as % of NAV
    # Uses signed market_value_eur (preserves long/short balance per sector)
    sector_exp = (
        sector_universe.groupby('sector')['market_value_eur'].sum() / nav * 100
    ) if len(sector_universe) else pd.Series(dtype=float)

    # Compute pre-trade sector exposure for comparison
    if positions_before is not None and 'sector' in positions_before.columns:
        pre_sector_universe = positions_before[
            positions_before['asset_class'].isin(['Equity', 'Bond', 'Loan', 'CLO']) &
            positions_before['sector'].notna() &
            (positions_before['sector'] != 'Government')
        ]
    else:
        pre_sector_universe = positions_before[positions_before['asset_class'] == 'Equity'] if positions_before is not None else None

    # Pre-trade sector concentration: net sector weight as % of NAV
    # Uses signed market_value_eur (preserves long/short balance per sector)
    pre_sector_exp = (
        pre_sector_universe.groupby('sector')['market_value_eur'].sum() / nav * 100
    ) if (pre_sector_universe is not None and len(pre_sector_universe)) else pd.Series(dtype=float)

    metrics['max_sector_pct'] = float(sector_exp.max()) if len(sector_exp) else 0.0

    # Add exposure % for the specific sector in this trade
    trade_sector = trade.get('sector')
    if trade_sector:
        metrics['trade_sector_pct'] = float(sector_exp.get(trade_sector, 0.0))
    else:
        metrics['trade_sector_pct'] = 0.0

    for sector, pct in sector_exp[sector_exp > 30.0].items():
        pre_pct = float(pre_sector_exp.get(sector, 0.0))
        if pct > pre_pct:  # Only flag if trade worsened it
            breaches.append(_breach(
                'sector_concentration', 30.0, float(pct), '% NAV',
                f'Sector {sector}: {pct:.1f}% NAV exceeds internal RMP limit 30% (was {pre_pct:.1f}%)'
            ))

    # [5] Counterparty concentration
    # Checks existing register exposure + new trade exposure against limit.
    # Limit: 10% NAV for credit institutions, 5% for others (EU231/2013 Art. 43).
    cpty       = trade.get('counterparty')
    cpty_type  = trade.get('counterparty_type', 'non_credit_institution')
    cpty_limit = 0.10 if cpty_type == 'credit_institution' else 0.05
    if cpty and trade.get('asset_class') == 'Derivative':
        trade_pct    = abs(trade['quantity'] * trade['price_eur']) / nav if nav else 0.0
        existing_pct = 0.0
        if counterparties_df is not None:
            mask = counterparties_df['counterparty'] == cpty
            if mask.any():
                existing_pct = float(counterparties_df.loc[mask, 'exposure_pct'].iloc[0])
        total_pct = existing_pct + trade_pct
        metrics[f'counterparty_{cpty}_existing_pct'] = existing_pct
        metrics[f'counterparty_{cpty}_trade_pct']    = trade_pct
        metrics[f'counterparty_{cpty}_total_pct']    = total_pct
        if total_pct > cpty_limit:
            breaches.append(_breach(
                'counterparty_exposure', cpty_limit * 100, total_pct * 100, '% NAV',
                f'Counterparty {cpty} ({cpty_type}): existing {existing_pct:.1%} '
                f'+ trade {trade_pct:.1%} = {total_pct:.1%} NAV — '
                f'exceeds {cpty_limit:.0%} limit'
            ))

    # [6] Short selling — EU236/2012: net short > 0.2% NAV is reportable
    # Only flag positions that are new or increased by this trade.
    # Pre-existing reportable shorts are already known and managed separately.
    key       = 'issuer' if 'issuer' in pro_forma.columns else 'isin'
    net_pos   = pro_forma.groupby(pro_forma[key].fillna(pro_forma['isin']))['market_value_eur'].sum()
    net_short = net_pos[net_pos < 0]
    metrics['max_net_short_pct'] = float(
        net_short.min() / nav * 100
    ) if (len(net_short) and nav) else 0.0

    if positions_before is not None:
        pre_net = positions_before.groupby(
            positions_before[key].fillna(positions_before['isin'])
        )['market_value_eur'].sum()
    else:
        pre_net = pd.Series(dtype=float)

    for issuer, mv in net_short.items():
        short_pct  = abs(mv) / nav * 100 if nav else 0.0
        pre_mv     = float(pre_net.get(issuer, 0.0))
        trade_made_worse = mv < pre_mv  # more negative than before
        if short_pct > 0.2 and trade_made_worse:
            breaches.append(_breach(
                'short_selling_eu_236', 0.2, short_pct, '% NAV',
                f'Net short {issuer}: {short_pct:.2f}% NAV — reportable under EU236/2012'
            ))

    # [7] Liquidity impact — weighted avg days-to-liquidate vs 30-day redemption horizon
    REDEMPTION_HORIZON = 30
    if 'adv_eur' in pro_forma.columns:
        liq_df     = days_to_liquidate(pro_forma.assign(adv_eur=pro_forma['adv_eur'].fillna(0)))
        finite_liq = liq_df[np.isfinite(liq_df['days_to_liquidate'])]
        total_abs  = finite_liq['market_value_eur'].abs().sum()
        wtd_days   = (
            (finite_liq['days_to_liquidate'] * finite_liq['market_value_eur'].abs()).sum()
            / total_abs if total_abs > 0 else 0.0
        )
        metrics['wtd_avg_days_to_liquidate'] = round(wtd_days, 1)
        if wtd_days > REDEMPTION_HORIZON:
            breaches.append(_breach(
                'liquidity_impact', float(REDEMPTION_HORIZON), wtd_days, 'days',
                f'Post-trade weighted avg days-to-liquidate {wtd_days:.1f} exceeds '
                f'{REDEMPTION_HORIZON}-day redemption horizon'
            ))

    return breaches, metrics


def _check_aifm_pd(
    pro_forma: pd.DataFrame, nav: float, trade: dict
) -> tuple:
    breaches: list = []
    metrics:  dict = {}

    # [1] Single borrower concentration < 20% NAV
    issuer_exp = _ptc_issuer_exposure(pro_forma, nav)
    metrics['max_borrower_pct'] = float(issuer_exp.max()) if len(issuer_exp) else 0.0
    for issuer, pct in issuer_exp[issuer_exp > 20.0].items():
        breaches.append(_breach(
            'single_borrower_concentration', 20.0, float(pct), '% NAV',
            f'Borrower {issuer}: {pct:.1f}% NAV exceeds 20% single-borrower limit'
        ))

    # [2] HY exposure < 50% NAV
    sub_cls = (
        pro_forma['sub_asset_class']
        if 'sub_asset_class' in pro_forma.columns
        else pd.Series('', index=pro_forma.index)
    )
    rating = (
        pro_forma['rating']
        if 'rating' in pro_forma.columns
        else pd.Series('', index=pro_forma.index)
    )
    hy_mask   = sub_cls.isin(_HY_SUB_CLASSES) | rating.fillna('').isin(_HY_RATINGS)
    hy_exp_pct = pro_forma.loc[hy_mask, 'market_value_eur'].sum() / nav * 100 if nav else 0.0
    metrics['hy_exposure_pct'] = hy_exp_pct
    if hy_exp_pct > 50.0:
        breaches.append(_breach(
            'hy_exposure_limit', 50.0, hy_exp_pct, '% NAV',
            f'HY exposure {hy_exp_pct:.1f}% NAV exceeds 50% limit'
        ))

    # [3] Unrated exposure < 10% NAV
    unrated_mask = (sub_cls == 'Unrated') | rating.fillna('NR').isin({'NR', ''})
    unrated_pct  = pro_forma.loc[unrated_mask, 'market_value_eur'].sum() / nav * 100 if nav else 0.0
    metrics['unrated_exposure_pct'] = unrated_pct
    if unrated_pct > 10.0:
        breaches.append(_breach(
            'unrated_exposure_limit', 10.0, unrated_pct, '% NAV',
            f'Unrated exposure {unrated_pct:.1f}% NAV exceeds 10% limit'
        ))

    return breaches, metrics


def pre_trade_check(
    proposed_trade: dict,
    engine,
    fund_id: str,
    date: str,
    counterparties_df=None,
    bbg=None,
    deriv_bbg_map: dict | None = None,
    currency_bbg_map: dict | None = None,
    rmp: dict | None = None,
) -> dict:
    """
    Pre-trade compliance check for UCITS and AIFM funds.

    Loads the current enriched portfolio, applies the proposed trade
    to produce a pro-forma positions DataFrame, then runs fund-type-specific
    compliance checks. Returns a pass/fail result with breach detail and
    all post-trade metrics.

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
        One of: 'UCITS_Balanced', 'AIFM_HedgeFund', 'AIFM_PrivateDebt'.
    proposed_trade : dict
        Required keys: isin, direction ('buy'|'sell'|'short'),
                       quantity, price_eur, asset_class, sub_asset_class.
        Optional keys: rating, beta, dur_adj_mid, currency, issuer,
                       counterparty, counterparty_type, adv_eur.
    date : str
        Valuation date for loading current positions.

    Returns
    -------
    dict with keys:
        passed             bool
        fund_id            str
        fund_type          str   — 'ucits' | 'aifm_hf' | 'aifm_pd'
        proposed_trade     dict
        breaches           list[dict]  — empty if passed
        post_trade_metrics dict        — all computed values

    Regulatory context
    ------------------
    UCITS checks: UCITSD Articles 50, 52, 83; CSSF SRRI framework.
    AIFM HF:      AIFMD Art. 15, EU231/2013 Articles 6-8.
    AIFM PD:      AIFMD Art. 15, internal RMP concentration limits.
    Short selling: EU Regulation 236/2012.
    """
    from fund_risk_workflow.data.enrichment import get_risk_ready_df

    _FUND_TYPE = {
        'UCITS_Balanced'   : 'ucits',
        'AIFM_HedgeFund'   : 'aifm_hf',
        'AIFM_PrivateDebt' : 'aifm_pd',
    }
    fund_type = _FUND_TYPE.get(fund_id)
    if fund_type is None:
        raise ValueError(
            f"pre_trade_check: '{fund_id}' not supported. "
            f"Supported fund_ids: {list(_FUND_TYPE)}"
        )

    positions = get_risk_ready_df(engine, fund_id, date)
    nav       = float(positions['market_value_eur'].sum())
    pro_forma = _ptc_apply_trade(positions, proposed_trade)
    nav_post  = float(pro_forma['market_value_eur'].sum())  # NAV after adding the trade

    if fund_type == 'ucits':
        breaches, metrics = _check_ucits(pro_forma, nav_post, proposed_trade)
        # Pre-trade baseline metrics for UCITS (excluding government bonds and ETFs, per Art. 52).
        if 'sector' in positions.columns:
            pre_conc_universe = positions[
                ((positions['sector'].isna()) | (positions['sector'] != 'Government')) &
                (~positions['sub_asset_class'].isin(['ETF', 'Fund']))
            ]
        else:
            pre_conc_universe = positions[
                ~positions['sub_asset_class'].isin(['ETF', 'Fund'])
            ]
        _pre_iss = _ptc_issuer_exposure(pre_conc_universe, nav)
        _pre_above_5 = _ptc_issuer_exposure(pre_conc_universe, nav)
        _pre_above_5 = _pre_above_5[_pre_above_5 > 5.0]
        pre_metrics = {
            'absolute_var_pct'        : _ptc_portfolio_var(positions, nav),
            'relative_var_multiplier' : _ptc_portfolio_var(positions, nav) / _ptc_reference_var() if _ptc_reference_var() > 0 else 0.0,
            'reference_var_pct'       : _ptc_reference_var(),
            'max_issuer_pct'          : float(_pre_iss.max()) if len(_pre_iss) else 0.0,
            'sum_above_5pct_issuers'  : float(_pre_above_5.sum()),
        }
    elif fund_type == 'aifm_hf':
        breaches, metrics = _check_aifm_hf(
            pro_forma, nav_post, proposed_trade,
            counterparties_df=counterparties_df,
            bbg=bbg,
            deriv_bbg_map=deriv_bbg_map,
            currency_bbg_map=currency_bbg_map,
            positions_before=positions,
            nav_before=nav,
            rmp=rmp,
        )
        # Pre-trade baseline metrics for side-by-side comparison in reports.
        _pre_lev = compute_leverage(positions, nav, bbg=bbg,
                                    deriv_bbg_map=deriv_bbg_map,
                                    currency_bbg_map=currency_bbg_map)
        _pre_iss = _ptc_issuer_exposure(positions, nav)

        # Pre-trade sector exposure
        if 'sector' in positions.columns:
            _pre_sector_universe = positions[
                positions['asset_class'].isin(['Equity', 'Bond', 'Loan', 'CLO']) &
                positions['sector'].notna() &
                (positions['sector'] != 'Government')
            ]
        else:
            _pre_sector_universe = positions[positions['asset_class'] == 'Equity']
        # Pre-trade net sector weights as % of NAV (signed, preserves long/short balance)
        _pre_sector_exp = (
            _pre_sector_universe.groupby('sector')['market_value_eur'].sum() / nav * 100
        ) if len(_pre_sector_universe) else pd.Series(dtype=float)

        # Pre-trade net short
        _key = 'issuer' if 'issuer' in positions.columns else 'isin'
        _pre_net_pos = positions.groupby(positions[_key].fillna(positions['isin']))['market_value_eur'].sum()
        _pre_net_short = _pre_net_pos[_pre_net_pos < 0]

        # Pre-trade weighted days to liquidate
        _pre_wtd_days = 0.0
        if 'adv_eur' in positions.columns:
            _pre_liq_df = days_to_liquidate(positions.assign(adv_eur=positions['adv_eur'].fillna(0)))
            _pre_finite_liq = _pre_liq_df[np.isfinite(_pre_liq_df['days_to_liquidate'])]
            _pre_total_abs = _pre_finite_liq['market_value_eur'].abs().sum()
            _pre_wtd_days = (
                (_pre_finite_liq['days_to_liquidate'] * _pre_finite_liq['market_value_eur'].abs()).sum()
                / _pre_total_abs if _pre_total_abs > 0 else 0.0
            )

        # Pre-trade trade issuer/sector exposure
        _issuer_key = 'issuer' if 'issuer' in positions.columns else 'isin'
        _trade_issuer = proposed_trade.get(_issuer_key) or proposed_trade.get('underlying_risk') or proposed_trade.get('issuer')
        _trade_issuer_pct = float(_pre_iss.get(_trade_issuer, 0.0)) if _trade_issuer else 0.0

        _trade_sector = proposed_trade.get('sector')
        _trade_sector_pct = float(_pre_sector_exp.get(_trade_sector, 0.0)) if _trade_sector else 0.0

        pre_metrics = {
            'gross_leverage'            : _pre_lev['gross_leverage'],
            'commitment_leverage'       : _pre_lev['commitment_leverage'],
            'gross_exposure'            : _pre_lev['gross_exposure'],
            'commitment_exposure'       : _pre_lev['commitment_exposure'],
            'net_eq'                    : _pre_lev['net_eq'],
            'bonds'                     : _pre_lev['bonds'],
            'fx_exposure'               : _pre_lev['fx_exposure'],
            'deriv_notional_commitment' : _pre_lev['deriv_notional_commitment'],
            'borrowings'                : _pre_lev['borrowings'],
            'max_issuer_pct'            : float(_pre_iss.max()) if len(_pre_iss) else 0.0,
            'trade_issuer_pct'          : _trade_issuer_pct,
            'absolute_var_pct'          : _ptc_portfolio_var(positions, nav),
            'max_sector_pct'            : float(_pre_sector_exp.max()) if len(_pre_sector_exp) else 0.0,
            'trade_sector_pct'          : _trade_sector_pct,
            'max_net_short_pct'         : float(_pre_net_short.min() / nav * 100) if (len(_pre_net_short) and nav) else 0.0,
            'wtd_avg_days_to_liquidate' : round(_pre_wtd_days, 1),
        }
    else:
        breaches, metrics = _check_aifm_pd(pro_forma, nav_post, proposed_trade)
        pre_metrics = {}

    # Build issuer and sector exposure breakdowns for display
    issuer_exp = _ptc_issuer_exposure(pro_forma, nav_post)
    issuer_exposures_post = issuer_exp[issuer_exp > 0].round(1).to_dict()

    pre_issuer_exp = _ptc_issuer_exposure(positions, nav) if len(positions) else pd.Series(dtype=float)
    issuer_exposures_pre = pre_issuer_exp[pre_issuer_exp > 0].round(1).to_dict()

    # Sector exposures (only for AIFM HF which has sectors)
    sector_exposures_post = {}
    sector_exposures_pre = {}
    if fund_type == 'aifm_hf' and 'sector' in pro_forma.columns:
        sector_universe_post = pro_forma[
            pro_forma['asset_class'].isin(['Equity', 'Bond', 'Loan', 'CLO']) &
            pro_forma['sector'].notna() &
            (pro_forma['sector'] != 'Government')
        ]
        # Net sector weights as % of NAV (signed, preserves long/short balance)
        sector_exp_post = (
            sector_universe_post.groupby('sector')['market_value_eur'].sum() / nav_post * 100
        ) if len(sector_universe_post) else pd.Series(dtype=float)
        sector_exposures_post = sector_exp_post[sector_exp_post > 0].round(1).to_dict()

        sector_universe_pre = positions[
            positions['asset_class'].isin(['Equity', 'Bond', 'Loan', 'CLO']) &
            positions['sector'].notna() &
            (positions['sector'] != 'Government')
        ]
        # Net sector weights as % of NAV (signed, preserves long/short balance)
        sector_exp_pre = (
            sector_universe_pre.groupby('sector')['market_value_eur'].sum() / nav * 100
        ) if len(sector_universe_pre) else pd.Series(dtype=float)
        sector_exposures_pre = sector_exp_pre[sector_exp_pre > 0].round(1).to_dict()

    return {
        'passed'                  : len(breaches) == 0,
        'fund_id'                 : fund_id,
        'fund_type'               : fund_type,
        'proposed_trade'          : proposed_trade,
        'breaches'                : breaches,
        'pre_trade_metrics'       : pre_metrics,
        'post_trade_metrics'      : metrics,
        'issuer_exposures_pre'    : issuer_exposures_pre,
        'issuer_exposures_post'   : issuer_exposures_post,
        'sector_exposures_pre'    : sector_exposures_pre,
        'sector_exposures_post'   : sector_exposures_post,
    }


def load_counterparty(fund_id: str) -> pd.DataFrame:
    """
    Load counterparty register for a fund from reference data.

    Parameters
    ----------
    fund_id : str
        Fund identifier.

    Returns
    -------
    pd.DataFrame
        Counterparty register with columns: counterparty, type, exposure_pct, collateral_cover.
    """
    import json
    from pathlib import Path

    ref_data_path = Path(__file__).parent.parent.parent.parent / 'reference_data' / 'funds' / fund_id
    cp_file = ref_data_path / 'counterparties.json'

    with open(cp_file, 'r') as f:
        data = json.load(f)

    # Validate fund_id matches
    if data.get('fund_id') != fund_id:
        raise ValueError(
            f"counterparties.json fund_id mismatch: "
            f"file contains '{data.get('fund_id')}' but requested '{fund_id}'"
        )

    cp_list = data.get('counterparties', [])
    return pd.DataFrame(cp_list)


def compute_counterparty_stress(fund_id: str, engine, nav: float) -> dict:
    """
    Compute counterparty stress metrics: exposures, collateral, net exposure, and worst case.

    Parameters
    ----------
    fund_id : str
        Fund identifier.
    engine : sa.Engine
        SQLAlchemy engine for database access.
    nav : float
        Net asset value.

    Returns
    -------
    dict with keys:
        'cp_df' : pd.DataFrame - counterparty register with computed columns
        'worst_cp' : pd.Series - worst counterparty row
        'loss_eur' : float - net exposure of worst counterparty (EUR)
        'loss_pct' : float - net exposure of worst counterparty (% NAV)
    """
    # Load counterparty register
    cp_df = load_counterparty(fund_id)

    # Compute exposure and collateral columns
    cp_df['exposure_eur'] = cp_df['exposure_pct'] * nav
    cp_df['collateral_eur'] = cp_df['exposure_eur'] * cp_df['collateral_cover']
    cp_df['net_exposure_eur'] = cp_df['exposure_eur'] * (1 - cp_df['collateral_cover'])
    cp_df['net_pct_nav'] = cp_df['net_exposure_eur'] / nav

    # Find worst counterparty
    worst_cp = cp_df.loc[cp_df['net_exposure_eur'].idxmax()]
    loss_eur = worst_cp['net_exposure_eur']
    loss_pct = worst_cp['net_pct_nav']

    return {
        'cp_df': cp_df,
        'worst_cp': worst_cp,
        'loss_eur': loss_eur,
        'loss_pct': loss_pct,
    }


# ================================================================
# Public API
# ================================================================

__all__ = [
    'HISTORICAL_SCENARIOS',
    # VaR
    'var_historical',
    'var_parametric',
    'var_scale',
    # ES
    'es_historical',
    'es_parametric',
    'es_scale',
    # backtesting
    'kupiec_test',
    'christoffersen_test',
    'exception_report',
    'full_backtest_report',
    # stress scenarios
    'stress_equity',
    'stress_rates',
    'stress_credit',
    'stress_fx',
    'stress_combined',
    'stress_historical',
    'stress_property',
    'stress_rental',
    'stress_ltv',
    # liquidity
    'days_to_liquidate',
    'liquidity_buckets',
    'redemption_stress',
    'compute_leverage',
    'investor_concentration',
    'load_investor_register',
    'load_counterparty',
    'liquidity_adjusted_var',
    # attribution
    'compute_pnl_attribution',
    # pre-trade compliance
    'pre_trade_check',
    # counterparty stress
    'compute_counterparty_stress',
]