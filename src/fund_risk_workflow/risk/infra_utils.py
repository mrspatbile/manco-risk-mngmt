"""
infra_utils.py
==============
Risk calculation functions for the AIFM Infrastructure Core fund.

Infrastructure risk is not VaR-based. The core metrics are duration
(weighted remaining concession life), inflation sensitivity, leverage
ratios (DSCR, LTV), and cashflow coverage. Stress testing operates
on the discount rate and inflation assumptions that drive yield-
capitalised valuations.

Functions
---------
fund_nav_timeseries(engine, fund_id)
asset_nav_breakdown(engine, fund_id, quarter)
infra_multiples(engine, fund_id)
infra_irr(engine, fund_id)
dscr_profile(engine, asset_id)
ltv_profile(engine, asset_id)
concentration_by_sector(engine, fund_id, quarter)
cashflow_coverage(engine, fund_id)
inflation_sensitivity(engine, fund_id)
duration_profile(engine, fund_id)
stress_nav(engine, fund_id, discount_rate_shock_bps, inflation_shock_pct)

Regulatory basis
----------------
AIFMD Art. 15 — liquidity management
AIFMD Art. 19 — independent valuation (appraiser inputs boundary)
EU231/2013 Articles 46-49 — risk management
IPEV Valuation Guidelines — yield capitalisation for infra
"""

import numpy as np
import pandas as pd
from typing import Optional
import sqlalchemy as sa
from sqlalchemy.orm import Session

from fund_risk_workflow.data.database import (
    InfraFund, InfraAsset, InfraFundInvestment,
    InfraCashFlow, InfraNavHistory, InfraValuationReport,
    InfraDebt, InfraCovenant,
)
from fund_risk_workflow.config import VALUATION_DATE
from fund_risk_workflow.risk.pe_utils import xirr

PROJECT_VALUATION_DATE = pd.Timestamp(VALUATION_DATE)


def fund_nav_timeseries(
    engine: sa.Engine,
    fund_id: str,
) -> pd.DataFrame:
    """
    Aggregate quarterly NAV across all assets.

    Returns
    -------
    pd.DataFrame with columns: date, nav_eur
        Sorted by date ascending.
    """
    with Session(engine) as session:
        rows = session.query(InfraNavHistory).filter(
            InfraNavHistory.fund_id  == fund_id,
            InfraNavHistory.asset_id == None,
        ).order_by(InfraNavHistory.nav_date).all()

    df = pd.DataFrame([{
        'date'   : pd.Timestamp(r.nav_date),
        'nav_eur': r.nav_eur,
    } for r in rows])

    return df.reset_index(drop=True)


def asset_nav_breakdown(
    engine: sa.Engine,
    fund_id: str,
    quarter: str,
) -> pd.DataFrame:
    """
    NAV by asset for a given quarter with sector and sub-type labels.

    Parameters
    ----------
    quarter : str
        Quarter-end date string, e.g. '2026-03-31'.

    Returns
    -------
    pd.DataFrame with columns:
        asset_id, asset_name, sector, sub_type, country,
        nav_eur, nav_pct, moic
    """
    with Session(engine) as session:
        nav_rows = session.query(InfraNavHistory).filter(
            InfraNavHistory.fund_id  == fund_id,
            InfraNavHistory.nav_date     == quarter,
            InfraNavHistory.asset_id != None,
        ).all()

        assets = {a.asset_id: a
                  for a in session.query(InfraAsset).all()}

    rows = []
    total_nav = sum(r.nav_eur for r in nav_rows)
    for r in nav_rows:
        a = assets.get(r.asset_id)
        rows.append({
            'asset_id'  : r.asset_id,
            'asset_name': a.asset_name if a else r.asset_id,
            'sector'    : a.sector     if a else None,
            'sub_type'  : a.sub_type   if a else None,
            'country'   : a.country    if a else None,
            'nav_eur'   : r.nav_eur,
            'nav_pct'   : round(r.nav_eur / total_nav * 100, 2) if total_nav else 0.0,
            'moic'      : r.moic,
        })

    return pd.DataFrame(rows).sort_values('nav_eur', ascending=False).reset_index(drop=True)


def infra_multiples(
    engine: sa.Engine,
    fund_id: str,
) -> dict:
    """
    Compute MOIC, DPI, RVPI for the infrastructure fund.

    MOIC = (distributions + residual NAV) / drawn capital
    DPI  = distributions / drawn capital
    RVPI = residual NAV / drawn capital

    Returns
    -------
    dict with keys: moic, dpi, rvpi, drawn_capital, distributions, nav
    """
    with Session(engine) as session:
        cfs = session.query(InfraCashFlow).filter(
            InfraCashFlow.fund_id == fund_id
        ).all()

        nav_row = session.query(InfraNavHistory).filter(
            InfraNavHistory.fund_id  == fund_id,
            InfraNavHistory.asset_id == None,
        ).order_by(InfraNavHistory.nav_date.desc()).first()

    drawn_capital = abs(sum(cf.amount_eur for cf in cfs
                            if cf.amount_eur < 0
                            and cf.flow_type == 'capital_call'))
    distributions = sum(cf.amount_eur for cf in cfs
                        if cf.amount_eur > 0
                        and cf.flow_type == 'distribution')
    nav_eur       = nav_row.nav_eur if nav_row else 0.0

    dpi  = distributions / drawn_capital if drawn_capital > 0 else 0.0
    rvpi = nav_eur / drawn_capital       if drawn_capital > 0 else 0.0
    moic = dpi + rvpi

    return {
        'moic'         : round(moic, 3),
        'dpi'          : round(dpi, 3),
        'rvpi'         : round(rvpi, 3),
        'drawn_capital': round(drawn_capital, 2),
        'distributions': round(distributions, 2),
        'nav'          : round(nav_eur, 2),
    }


def infra_irr(
    engine: sa.Engine,
    fund_id: str,
) -> Optional[float]:
    """
    XIRR on all cash flows with residual NAV as terminal value.

    Reuses xirr() from pe_utils for consistency.

    Returns
    -------
    float or None — IRR as decimal (e.g. 0.12 = 12%)
    """
    with Session(engine) as session:
        cfs = session.query(InfraCashFlow).filter(
            InfraCashFlow.fund_id == fund_id,
        ).order_by(InfraCashFlow.cash_flow_date).all()

        nav_row = session.query(InfraNavHistory).filter(
            InfraNavHistory.fund_id  == fund_id,
            InfraNavHistory.asset_id == None,
        ).order_by(InfraNavHistory.nav_date.desc()).first()

    cf_amounts = [cf.amount_eur for cf in cfs]
    cf_dates   = [cf.cash_flow_date for cf in cfs]

    if nav_row:
        cf_amounts.append(nav_row.nav_eur)
        cf_dates.append(nav_row.nav_date)

    return xirr(cf_amounts, cf_dates)


def dscr_profile(
    engine: sa.Engine,
    asset_id: str,
) -> pd.DataFrame:
    """
    Quarterly DSCR timeseries for an asset.

    Includes breach flags, headroom to covenant, and a rolling trend
    classification based on the last four quarters:
        'improving'    — DSCR rising over last 4Q
        'deteriorating'— DSCR falling over last 4Q
        'stable'       — change within ±2%

    Returns
    -------
    pd.DataFrame with columns:
        date, dscr_actual, dscr_covenant, dscr_headroom,
        dscr_breach, waiver_granted, trend
    """
    with Session(engine) as session:
        rows = session.query(InfraCovenant).filter(
            InfraCovenant.asset_id == asset_id,
        ).order_by(InfraCovenant.observation_date).all()

    df = pd.DataFrame([{
        'date'          : pd.Timestamp(r.observation_date),
        'dscr_actual'   : r.dscr_actual,
        'dscr_covenant' : r.dscr_covenant,
        'dscr_headroom' : r.dscr_headroom,
        'dscr_breach'   : r.dscr_breach,
        'waiver_granted': r.waiver_granted,
    } for r in rows])

    if df.empty:
        return df

    # rolling 4-quarter trend
    dscr_s = df['dscr_actual'].astype(float)
    trend  = []
    for i in range(len(df)):
        if i < 3:
            trend.append('insufficient history')
        else:
            window = dscr_s.iloc[i-3:i+1].dropna()
            if len(window) < 4:
                trend.append('insufficient history')
            else:
                change = (window.iloc[-1] - window.iloc[0]) / window.iloc[0]
                if change > 0.02:
                    trend.append('improving')
                elif change < -0.02:
                    trend.append('deteriorating')
                else:
                    trend.append('stable')
    df['trend'] = trend

    return df.reset_index(drop=True)


def ltv_profile(
    engine: sa.Engine,
    asset_id: str,
) -> pd.DataFrame:
    """
    Quarterly LTV timeseries for an asset.

    Same structure as dscr_profile. Trend logic is inverted:
        'improving'     — LTV falling (more headroom)
        'deteriorating' — LTV rising (less headroom)

    Returns
    -------
    pd.DataFrame with columns:
        date, ltv_actual, ltv_covenant, ltv_headroom,
        ltv_breach, waiver_granted, trend
    """
    with Session(engine) as session:
        rows = session.query(InfraCovenant).filter(
            InfraCovenant.asset_id == asset_id,
        ).order_by(InfraCovenant.observation_date).all()

    df = pd.DataFrame([{
        'date'          : pd.Timestamp(r.observation_date),
        'ltv_actual'    : r.ltv_actual,
        'ltv_covenant'  : r.ltv_covenant,
        'ltv_headroom'  : r.ltv_headroom,
        'ltv_breach'    : r.ltv_breach,
        'waiver_granted': r.waiver_granted,
    } for r in rows])

    if df.empty:
        return df

    ltv_s = df['ltv_actual'].astype(float)
    trend = []
    for i in range(len(df)):
        if i < 3:
            trend.append('insufficient history')
        else:
            window = ltv_s.iloc[i-3:i+1].dropna()
            if len(window) < 4:
                trend.append('insufficient history')
            else:
                change = (window.iloc[-1] - window.iloc[0]) / window.iloc[0]
                if change < -0.02:
                    trend.append('improving')
                elif change > 0.02:
                    trend.append('deteriorating')
                else:
                    trend.append('stable')
    df['trend'] = trend

    return df.reset_index(drop=True)


def concentration_by_sector(
    engine: sa.Engine,
    fund_id: str,
    quarter: str,
) -> pd.DataFrame:
    """
    NAV concentration by sector for a given quarter.

    Flags any sector that exceeds 40% of total NAV — the threshold
    used internally for concentration monitoring (not a regulatory
    bright-line, but consistent with ESMA stress testing guidance).

    Returns
    -------
    pd.DataFrame with columns:
        sector, nav_eur, nav_pct, concentrated (bool)
    """
    breakdown = asset_nav_breakdown(engine, fund_id, quarter)
    if breakdown.empty:
        return pd.DataFrame(columns=['sector', 'nav_eur', 'nav_pct', 'concentrated'])

    by_sector = (
        breakdown.groupby('sector')['nav_eur']
        .sum()
        .reset_index()
        .rename(columns={'nav_eur': 'nav_eur'})
    )
    total = by_sector['nav_eur'].sum()
    by_sector['nav_pct']     = (by_sector['nav_eur'] / total * 100).round(2)
    by_sector['concentrated'] = by_sector['nav_pct'] > 40.0

    return by_sector.sort_values('nav_eur', ascending=False).reset_index(drop=True)


def cashflow_coverage(
    engine: sa.Engine,
    fund_id: str,
) -> pd.DataFrame:
    """
    Quarterly distributions received vs management fees and fund expenses.

    Coverage ratio = distributions / management fees per quarter.
    Periods with no distributions show ratio of 0.

    Returns
    -------
    pd.DataFrame with columns:
        date, distributions, management_fees, coverage_ratio
    """
    with Session(engine) as session:
        cfs = session.query(InfraCashFlow).filter(
            InfraCashFlow.fund_id == fund_id,
            InfraCashFlow.flow_type.in_(['distribution', 'management_fee']),
        ).all()

    rows_dist = {}
    rows_fee  = {}
    for cf in cfs:
        if cf.flow_type == 'distribution':
            rows_dist[cf.cash_flow_date] = rows_dist.get(cf.cash_flow_date, 0.0) + cf.amount_eur
        elif cf.flow_type == 'management_fee':
            rows_fee[cf.cash_flow_date]  = rows_fee.get(cf.cash_flow_date, 0.0) + abs(cf.amount_eur)

    all_dates = sorted(set(rows_dist) | set(rows_fee))
    records   = []
    for d in all_dates:
        dist = rows_dist.get(d, 0.0)
        fees = rows_fee.get(d, 0.0)
        records.append({
            'date'            : pd.Timestamp(d),
            'distributions'   : dist,
            'management_fees' : fees,
            'coverage_ratio'  : round(dist / fees, 3) if fees > 0 else 0.0,
        })

    return pd.DataFrame(records).sort_values('date').reset_index(drop=True)


def inflation_sensitivity(
    engine: sa.Engine,
    fund_id: str,
) -> dict:
    """
    Weighted average inflation linkage across the portfolio.

    Uses the most recent quarter NAV weights and the inflation_linkage
    field from infra_assets (proportion of revenue that is CPI-linked).

    Classification:
        fully linked   : linkage >= 0.80
        partially linked: 0.30 <= linkage < 0.80
        unlinked       : linkage < 0.30

    Returns
    -------
    dict with keys:
        weighted_avg_linkage,
        pct_fully_linked,
        pct_partially_linked,
        pct_unlinked,
        asset_detail (DataFrame)
    """
    # latest quarter available
    with Session(engine) as session:
        latest = session.query(InfraNavHistory).filter(
            InfraNavHistory.fund_id  == fund_id,
            InfraNavHistory.asset_id == None,
        ).order_by(InfraNavHistory.nav_date.desc()).first()

    if latest is None:
        return {}

    quarter   = latest.nav_date
    breakdown = asset_nav_breakdown(engine, fund_id, quarter)

    with Session(engine) as session:
        asset_map = {a.asset_id: a
                     for a in session.query(InfraAsset).all()}

    total_nav = breakdown['nav_eur'].sum()
    rows = []
    for _, row in breakdown.iterrows():
        a       = asset_map.get(row['asset_id'])
        linkage = a.inflation_linkage if a else 0.0
        weight  = row['nav_eur'] / total_nav if total_nav > 0 else 0.0
        rows.append({
            'asset_id'        : row['asset_id'],
            'asset_name'      : row['asset_name'],
            'inflation_linkage': linkage,
            'nav_weight'      : round(weight, 4),
            'linkage_class'   : (
                'fully linked'    if linkage >= 0.80 else
                'partially linked' if linkage >= 0.30 else
                'unlinked'
            ),
        })

    detail = pd.DataFrame(rows)
    wa     = float((detail['inflation_linkage'] * detail['nav_weight']).sum())

    fully    = detail.loc[detail['linkage_class'] == 'fully linked',    'nav_weight'].sum()
    partial  = detail.loc[detail['linkage_class'] == 'partially linked','nav_weight'].sum()
    unlinked = detail.loc[detail['linkage_class'] == 'unlinked',        'nav_weight'].sum()

    return {
        'weighted_avg_linkage' : round(wa, 4),
        'pct_fully_linked'     : round(fully * 100, 2),
        'pct_partially_linked' : round(partial * 100, 2),
        'pct_unlinked'         : round(unlinked * 100, 2),
        'asset_detail'         : detail,
    }


def duration_profile(
    engine: sa.Engine,
    fund_id: str,
) -> pd.DataFrame:
    """
    Weighted average remaining concession life by NAV weight.

    Flags assets with concession expiry within 3 years of VALUATION_DATE.

    Returns
    -------
    pd.DataFrame with columns:
        asset_id, asset_name, concession_end, remaining_years,
        nav_eur, nav_weight, near_expiry (bool)
    """
    with Session(engine) as session:
        latest = session.query(InfraNavHistory).filter(
            InfraNavHistory.fund_id  == fund_id,
            InfraNavHistory.asset_id == None,
        ).order_by(InfraNavHistory.nav_date.desc()).first()

    if latest is None:
        return pd.DataFrame()

    quarter   = latest.nav_date
    breakdown = asset_nav_breakdown(engine, fund_id, quarter)

    with Session(engine) as session:
        asset_map = {a.asset_id: a
                     for a in session.query(InfraAsset).all()}

    total_nav = breakdown['nav_eur'].sum()
    rows = []
    for _, row in breakdown.iterrows():
        a = asset_map.get(row['asset_id'])
        if a and a.concession_end:
            end_date       = pd.Timestamp(a.concession_end)
            remaining      = (end_date - PROJECT_VALUATION_DATE).days / 365.25
            near_expiry    = remaining < 3.0
        else:
            remaining   = None
            near_expiry = None

        rows.append({
            'asset_id'       : row['asset_id'],
            'asset_name'     : row['asset_name'],
            'concession_end' : a.concession_end if a else None,
            'remaining_years': round(remaining, 2) if remaining is not None else None,
            'nav_eur'        : row['nav_eur'],
            'nav_weight'     : round(row['nav_eur'] / total_nav, 4) if total_nav > 0 else 0.0,
            'near_expiry'    : near_expiry,
        })

    df = pd.DataFrame(rows)

    valid = df.dropna(subset=['remaining_years'])
    if not valid.empty:
        wa_duration = (valid['remaining_years'] * valid['nav_weight']).sum()
        df.attrs['weighted_avg_remaining_years'] = round(wa_duration, 2)

    return df.sort_values('remaining_years').reset_index(drop=True)


def stress_nav(
    engine: sa.Engine,
    fund_id: str,
    discount_rate_shock_bps: float,
    inflation_shock_pct: float,
) -> dict:
    """
    Stress NAV by applying a parallel shift to discount rate and inflation
    assumptions across all valuation reports.

    Yield capitalisation stress formula per asset:
        EBITDA_stressed = EBITDA * (1 + linkage * inflation_shock_pct)
        EV_stressed     = EBITDA_stressed / (dr + discount_rate_shock_bps / 10000)
        equity_stressed = max(0, EV_stressed - net_debt)

    A positive discount_rate_shock (e.g. +100 bps) always reduces EV and
    thus NAV, because the duration effect dominates the partial inflation
    pass-through for realistic inflation_linkage values below 1.

    Parameters
    ----------
    discount_rate_shock_bps : float
        Parallel shift in discount rate, in basis points (e.g. 100 = +1%).
    inflation_shock_pct : float
        Change in inflation assumption as a percentage (e.g. 0.01 = +1%).

    Returns
    -------
    dict with keys:
        base_nav, stressed_nav, nav_change, nav_change_pct,
        discount_rate_shock_bps, inflation_shock_pct,
        asset_detail (DataFrame)
    """
    dr_shock = discount_rate_shock_bps / 10_000

    with Session(engine) as session:
        # latest valuation report per asset
        all_vr = session.query(InfraValuationReport).filter(
            InfraValuationReport.fund_id == fund_id,
        ).order_by(InfraValuationReport.valuation_date).all()

        asset_map = {a.asset_id: a
                     for a in session.query(InfraAsset).all()}

    # keep only the most recent report per asset
    latest_vr = {}
    for vr in all_vr:
        latest_vr[vr.asset_id] = vr

    rows = []
    for aid, vr in latest_vr.items():
        a       = asset_map.get(aid)
        linkage = a.inflation_linkage if a else 0.0

        base_ebitda     = vr.ebitda_eur or 0.0
        base_dr         = vr.discount_rate or 0.08
        net_debt        = vr.net_debt_eur or 0.0

        stressed_ebitda = base_ebitda * (1 + linkage * inflation_shock_pct)
        stressed_dr     = base_dr + dr_shock
        stressed_ev     = (stressed_ebitda / stressed_dr
                           if stressed_dr > 0 else 0.0)
        stressed_equity = max(0.0, stressed_ev - net_debt)

        rows.append({
            'asset_id'       : aid,
            'asset_name'     : a.asset_name if a else aid,
            'base_nav'       : vr.implied_equity_eur,
            'stressed_nav'   : round(stressed_equity, 2),
            'nav_change'     : round(stressed_equity - vr.implied_equity_eur, 2),
        })

    detail      = pd.DataFrame(rows)
    base_total  = detail['base_nav'].sum()
    stress_total= detail['stressed_nav'].sum()
    nav_change  = stress_total - base_total

    return {
        'base_nav'               : round(base_total, 2),
        'stressed_nav'           : round(stress_total, 2),
        'nav_change'             : round(nav_change, 2),
        'nav_change_pct'         : round(nav_change / base_total * 100, 2) if base_total > 0 else 0.0,
        'discount_rate_shock_bps': discount_rate_shock_bps,
        'inflation_shock_pct'    : inflation_shock_pct,
        'asset_detail'           : detail,
    }


# ══════════════════════════════════════════════════════════════════════════
# MRS-198: notebook-extracted aggregations for the infrastructure workflow
# ══════════════════════════════════════════════════════════════════════════

def infra_portfolio_overview(engine: sa.Engine, fund_id: str,
                             quarter: str) -> dict:
    """Fund metadata plus the asset-level portfolio table.

    Returns dict with keys: fund_metadata (DataFrame of field/value rows),
    assets (DataFrame with sector, sub-type, country, concession end,
    ownership, drawn equity, appraised equity, and NAV weight),
    total_nav_eur, total_drawn_eur.
    """
    with Session(engine) as session:
        fund = session.query(InfraFund).filter_by(fund_id=fund_id).first()
        if fund is None:
            raise ValueError(f'Infrastructure fund not found: {fund_id}')
        assets = session.query(InfraAsset).all()
        investments = session.query(InfraFundInvestment).filter_by(
            fund_id=fund_id).all()

    breakdown = asset_nav_breakdown(engine, fund_id, quarter)
    if breakdown.empty:
        raise ValueError(
            f'No asset NAV rows for {fund_id} at {quarter}')
    nav_map = dict(zip(breakdown['asset_id'], breakdown['nav_eur']))

    asset_map = {a.asset_id: a for a in assets}
    rows = []
    for inv in investments:
        a = asset_map.get(inv.asset_id)
        rows.append({
            'asset_name': a.asset_name if a else inv.asset_id,
            'sector': a.sector if a else None,
            'sub_type': a.sub_type if a else None,
            'country': a.country if a else None,
            'concession_end': a.concession_end if a else None,
            'ownership_pct': inv.ownership_pct,
            'drawn_equity_eur': inv.drawn_equity,
            'appraised_equity_eur': nav_map.get(inv.asset_id, 0.0),
        })
    out = pd.DataFrame(rows)
    total_nav = float(out['appraised_equity_eur'].sum())
    out['nav_pct'] = out['appraised_equity_eur'] / total_nav * 100
    out = out.sort_values('appraised_equity_eur',
                          ascending=False).reset_index(drop=True)

    metadata = pd.DataFrame([
        {'field': 'Fund name', 'value': fund.fund_name},
        {'field': 'Vintage year', 'value': str(fund.vintage_year)},
        {'field': 'Fund life', 'value': f'{fund.fund_life_years} years'},
        {'field': 'Target size',
         'value': f'EUR {fund.target_size_eur / 1e6:,.0f}M'},
        {'field': 'Committed capital',
         'value': f'EUR {fund.committed_eur / 1e6:,.0f}M'},
        {'field': 'Drawn capital',
         'value': (f'EUR {fund.drawn_eur / 1e6:,.0f}M  '
                   f'({fund.drawn_eur / fund.committed_eur * 100:.1f}% '
                   'of committed)')},
        {'field': 'Currency', 'value': fund.currency},
        {'field': 'Domicile', 'value': fund.domicile},
        {'field': 'AIFMD classification',
         'value': fund.aifmd_classification},
    ])
    return {
        'fund_metadata': metadata,
        'assets': out,
        'total_nav_eur': total_nav,
        'total_drawn_eur': float(out['drawn_equity_eur'].sum()),
    }


def covenant_monitor(engine: sa.Engine, fund_id: str, metric: str,
                     n_quarters: int = 12,
                     watch_headroom_pct: float = 0.10) -> pd.DataFrame:
    """Combined per-asset covenant monitor for DSCR or LTV.

    One row per asset with the latest actual, covenant, headroom,
    headroom %, breach count over the window, trend, waiver flag,
    status ('Breach' / 'Watch' / 'OK'), and the metric history lists
    used by the display sparklines. DSCR breaches sit below covenant;
    LTV breaches sit above covenant.
    """
    if metric not in ('dscr', 'ltv'):
        raise ValueError(f"metric must be 'dscr' or 'ltv', got {metric!r}")
    profile_fn = dscr_profile if metric == 'dscr' else ltv_profile
    metric_col = f'{metric}_actual'
    covenant_col = f'{metric}_covenant'
    breach_col = f'{metric}_breach'

    with Session(engine) as session:
        asset_ids = [inv.asset_id for inv in
                     session.query(InfraFundInvestment).filter_by(
                         fund_id=fund_id).all()]
        asset_names = {a.asset_id: a.asset_name
                       for a in session.query(InfraAsset).all()}
    if not asset_ids:
        raise ValueError(f'No infrastructure investments for {fund_id}')

    rows = []
    for asset_id in asset_ids:
        df = profile_fn(engine, asset_id)
        if df.empty:
            continue
        df = df.sort_values('date').tail(n_quarters)
        latest = float(df[metric_col].iloc[-1])
        cov = float(df[covenant_col].iloc[-1])
        headroom = (latest - cov) if metric == 'dscr' else (cov - latest)
        headroom_pct = headroom / cov if cov else float('nan')
        breach = bool(df[breach_col].iloc[-1])
        status = ('Breach' if breach
                  else 'Watch' if headroom_pct < watch_headroom_pct
                  else 'OK')
        rows.append({
            'asset_name': asset_names.get(asset_id, asset_id),
            'actual': latest,
            'covenant': cov,
            'headroom': headroom,
            'headroom_pct': headroom_pct * 100,
            'breach_count': int(df[breach_col].sum()),
            'trend': df['trend'].iloc[-1],
            'waiver': bool(df['waiver_granted'].any()),
            'status': status,
            'history': df[metric_col].astype(float).tolist(),
            'breach_history': df[breach_col].astype(bool).tolist(),
        })
    return pd.DataFrame(rows)


def discount_rate_movement(engine: sa.Engine, fund_id: str, quarter: str,
                           flag_threshold_bps: float = 50.0) -> pd.DataFrame:
    """Quarter-on-quarter appraiser discount-rate movement per asset.

    Compares the requested quarter with the immediately preceding
    valuation date in the data. Movements beyond flag_threshold_bps
    (absolute) are flagged for risk committee review.
    """
    with Session(engine) as session:
        reports = session.query(InfraValuationReport).filter(
            InfraValuationReport.fund_id == fund_id,
            InfraValuationReport.valuation_date <= quarter,
        ).order_by(InfraValuationReport.valuation_date).all()
        asset_names = {a.asset_id: a.asset_name
                       for a in session.query(InfraAsset).all()}

    dates = sorted({r.valuation_date for r in reports})
    if quarter not in dates or len(dates) < 2:
        raise ValueError(
            f'Need two valuation dates up to {quarter} for {fund_id}')
    prev_quarter = dates[-2]

    curr = {r.asset_id: r for r in reports if r.valuation_date == quarter}
    prev = {r.asset_id: r for r in reports
            if r.valuation_date == prev_quarter}
    rows = []
    for aid, r in sorted(curr.items()):
        p = prev.get(aid)
        dr_prev = p.discount_rate if p else None
        chg_bps = ((r.discount_rate - dr_prev) * 10_000
                   if dr_prev is not None else None)
        rows.append({
            'asset_name': asset_names.get(aid, aid),
            'dr_prev': dr_prev,
            'dr_curr': r.discount_rate,
            'dr_chg_bps': chg_bps,
            'inflation_assumption': r.inflation_assumption,
            'flagged': (abs(chg_bps) > flag_threshold_bps
                        if chg_bps is not None else False),
        })
    out = pd.DataFrame(rows)
    out.attrs['prev_quarter'] = prev_quarter
    out.attrs['quarter'] = quarter
    out.attrs['flag_threshold_bps'] = flag_threshold_bps
    return out


def concentration_detail(engine: sa.Engine, fund_id: str,
                         quarter: str) -> dict:
    """Country, sub-type, and sector concentration views.

    Sector view reuses concentration_by_sector (including its internal
    40% NAV flag).
    """
    breakdown = asset_nav_breakdown(engine, fund_id, quarter)
    if breakdown.empty:
        raise ValueError(f'No asset NAV rows for {fund_id} at {quarter}')
    total = breakdown['nav_eur'].sum()

    def _group(col: str) -> pd.DataFrame:
        out = (breakdown.groupby(col)['nav_eur'].sum()
               .sort_values(ascending=False).reset_index())
        out['nav_pct'] = out['nav_eur'] / total * 100
        return out

    return {
        'country': _group('country'),
        'sub_type': _group('sub_type'),
        'sector': concentration_by_sector(engine, fund_id, quarter),
    }


def infra_quarterly_cashflow_frame(engine: sa.Engine,
                                   fund_id: str) -> pd.DataFrame:
    """Quarterly capital calls, fees, distributions, NCF, CNCF, and DPI."""
    with Session(engine) as session:
        cfs = session.query(InfraCashFlow).filter_by(fund_id=fund_id).all()
    if not cfs:
        raise ValueError(f'No infrastructure cash flows for {fund_id}')

    df = pd.DataFrame([{
        'quarter': (pd.Timestamp(c.cash_flow_date)
                    .to_period('Q').to_timestamp('Q')),
        'flow_type': c.flow_type,
        'amount_eur': c.amount_eur,
    } for c in cfs])

    calls = (df[df['flow_type'] == 'capital_call']
             .groupby('quarter')['amount_eur'].sum().abs().rename('calls'))
    fees = (df[df['flow_type'] == 'management_fee']
            .groupby('quarter')['amount_eur'].sum().abs().rename('fees'))
    dist = (df[df['flow_type'] == 'distribution']
            .groupby('quarter')['amount_eur'].sum().rename('distributions'))

    quarters = calls.index.union(fees.index).union(dist.index)
    out = (pd.DataFrame(index=quarters)
           .join(calls).join(fees).join(dist).fillna(0.0).sort_index())
    out.index.name = 'quarter'
    out['ncf'] = out['distributions'] - out['calls'] - out['fees']
    out['cncf'] = out['ncf'].cumsum()
    out['cum_calls'] = out['calls'].cumsum()
    out['cum_dist'] = out['distributions'].cumsum()
    out['dpi'] = out['cum_dist'] / out['cum_calls'].replace(0, float('nan'))
    return out


def infra_stress_summary(engine: sa.Engine, fund_id: str,
                         scenarios: list[dict]) -> dict:
    """Run the documented valuation-input stress scenarios.

    Each scenario dict needs name, discount_rate_shock_bps, and
    inflation_shock_pct (policy-migrated notebook assumptions).

    Returns dict with keys: summary (DataFrame), results (name -> full
    stress_nav result), base_nav_eur.
    """
    if not scenarios:
        raise ValueError('No stress scenarios provided')
    required = {'name', 'discount_rate_shock_bps', 'inflation_shock_pct'}
    results = {}
    for scen in scenarios:
        missing = required - set(scen)
        if missing:
            raise ValueError(
                f'Stress scenario missing fields: {sorted(missing)}')
        results[scen['name']] = stress_nav(
            engine, fund_id,
            scen['discount_rate_shock_bps'],
            scen['inflation_shock_pct'])

    summary = pd.DataFrame([{
        'scenario': name,
        'base_nav_eur': res['base_nav'],
        'stressed_nav_eur': res['stressed_nav'],
        'nav_change_eur': res['nav_change'],
        'nav_change_pct': res['nav_change_pct'],
    } for name, res in results.items()])
    return {
        'summary': summary,
        'results': results,
        'base_nav_eur': float(summary['base_nav_eur'].iloc[0]),
    }
