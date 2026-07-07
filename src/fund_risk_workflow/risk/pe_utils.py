"""
pe_utils.py
===========
PE fund performance metrics and risk utilities.

Functions
---------
xirr(cash_flows, dates, guess)
    Extended IRR for irregular cash flows.

fund_irr(engine, fund_id, as_of_date, fee_rate, carry_rate)
    Gross and net IRR for a PE fund.

pe_multiples(engine, fund_id, as_of_date)
    DPI, RVPI, TVPI at fund level.

pe_multiples_by_company(engine, fund_id, as_of_date)
    DPI, RVPI, TVPI per portfolio company.

pe_multiples_timeseries(engine, fund_id)
    Quarterly TVPI evolution over fund life.

pme_long_nickels(cash_flows, dates, index_prices, terminal_nav, valuation_date)
    Long-Nickels PME: PE IRR vs public market equivalent IRR and alpha.

Regulatory basis
----------------
IPEV Valuation Guidelines (International Private Equity Valuation)
ILPA reporting standards
AIFMD Art. 19 (independent valuation)
EU231/2013 Articles 46-49 (risk management)
"""

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from typing import Optional
import sqlalchemy as sa
from sqlalchemy.orm import Session

from fund_risk_workflow.data.database import (
    PEFund, PEPortfolioCompany, PEFundInvestment,
    PECashFlow, PENavHistory, PEValuationReport
)


__all__ = [
    'xirr',
    'fund_irr',
    'pe_multiples',
    'pe_multiples_by_company',
    'pe_multiples_timeseries',
    'pe_value_bridge',
    'pme_long_nickels',
]


def xirr(
    cash_flows: list,
    dates: list,
    guess: float = 0.10
) -> Optional[float]:
    """
    Extended Internal Rate of Return for irregular cash flows.
    Finds rate r such that NPV of all cash flows equals zero.

    $$\\sum_{i=0}^{n} \\frac{CF_i}{(1+r)^{d_i/365}} = 0$$

    Parameters
    ----------
    cash_flows : list of float
        Cash flows. Negative = outflows (capital calls).
        Positive = inflows (distributions, exit proceeds).
    dates : list of str or datetime
        Dates corresponding to each cash flow.
    guess : float
        Initial guess for IRR. Default 0.10 (10%).

    Returns
    -------
    float or None
        IRR as decimal (e.g. 0.20 = 20%).
        Returns None if no solution found.

    Examples
    --------
    >>> cfs   = [-100, 50, 80]
    >>> dates = ['2018-01-01', '2021-01-01', '2023-01-01']
    >>> irr   = xirr(cfs, dates)
    """
    dates = pd.to_datetime(dates)
    d0    = dates[0]
    days  = [(d - d0).days for d in dates]
    cfs   = np.array(cash_flows, dtype=float)

    def npv(r):
        return sum(cf / (1 + r) ** (d / 365)
                   for cf, d in zip(cfs, days))

    try:
        return float(brentq(npv, -0.999, 100.0, maxiter=1000))
    except (ValueError, RuntimeError):
        return None


def fund_irr(
    engine: sa.Engine,
    fund_id: str,
    as_of_date: str,
    fee_rate: float = 0.02,
    carry_rate: float = 0.20,
) -> dict:
    """
    Compute gross and net IRR for a PE fund.

    Gross IRR: based on raw cash flows plus terminal NAV.
    Net IRR: after management fees (fee_rate) and carried interest (carry_rate).

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
    as_of_date : str
        Valuation date. Terminal NAV added as final cash flow.
    fee_rate : float
        Annual management fee. Default 0.02 (2%).
    carry_rate : float
        Carried interest. Default 0.20 (20%).

    Returns
    -------
    dict with keys:
        gross_irr, net_irr, cash_flows, dates
    """
    with Session(engine) as session:
        cfs = session.query(PECashFlow).filter(
            PECashFlow.fund_id == fund_id,
            PECashFlow.cash_flow_date   <= as_of_date
        ).order_by(PECashFlow.cash_flow_date).all()

        nav = session.query(PENavHistory).filter(
            PENavHistory.fund_id    == fund_id,
            PENavHistory.company_id == None,
            PENavHistory.nav_date       <= as_of_date
        ).order_by(PENavHistory.nav_date.desc()).first()

    cf_amounts = [cf.amount_eur for cf in cfs]
    cf_dates   = [cf.cash_flow_date for cf in cfs]

    if nav:
        cf_amounts.append(nav.nav_eur)
        cf_dates.append(as_of_date)

    gross_irr = xirr(cf_amounts, cf_dates)

    # net IRR: approximate fee and carry deduction
    paid_in       = abs(sum(a for a in cf_amounts if a < 0))
    distributions = sum(a for a in cf_amounts if a > 0)
    fees          = paid_in * fee_rate
    profit        = max(0, distributions - paid_in)
    carry         = profit * carry_rate
    n_positive    = max(1, sum(1 for a in cf_amounts if a > 0))
    net_cf        = [
        a - fees / max(1, sum(1 for x in cf_amounts if x < 0)) if a < 0
        else a - carry / n_positive
        for a in cf_amounts
    ]
    net_irr = xirr(net_cf, cf_dates)

    return {
        'gross_irr'  : gross_irr,
        'net_irr'    : net_irr,
        'cash_flows' : cf_amounts,
        'dates'      : cf_dates,
    }


def pe_multiples(
    engine: sa.Engine,
    fund_id: str,
    as_of_date: str,
) -> dict:
    """
    Compute DPI, RVPI and TVPI for a PE fund.

    DPI  = Total distributions / Paid-in capital
    RVPI = Residual NAV / Paid-in capital
    TVPI = DPI + RVPI

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
    as_of_date : str

    Returns
    -------
    dict with keys:
        dpi, rvpi, tvpi, paid_in, distributions, nav
    """
    with Session(engine) as session:
        cfs = session.query(PECashFlow).filter(
            PECashFlow.fund_id == fund_id,
            PECashFlow.cash_flow_date   <= as_of_date
        ).all()

        nav = session.query(PENavHistory).filter(
            PENavHistory.fund_id    == fund_id,
            PENavHistory.company_id == None,
            PENavHistory.nav_date       <= as_of_date
        ).order_by(PENavHistory.nav_date.desc()).first()

    paid_in       = abs(sum(cf.amount_eur for cf in cfs if cf.amount_eur < 0))
    distributions = sum(cf.amount_eur for cf in cfs if cf.amount_eur > 0)
    nav_eur       = nav.nav_eur if nav else 0.0

    dpi  = distributions / paid_in if paid_in > 0 else 0.0
    rvpi = nav_eur / paid_in       if paid_in > 0 else 0.0
    tvpi = dpi + rvpi

    return {
        'dpi'          : round(dpi, 3),
        'rvpi'         : round(rvpi, 3),
        'tvpi'         : round(tvpi, 3),
        'paid_in'      : round(paid_in, 2),
        'distributions': round(distributions, 2),
        'nav'          : round(nav_eur, 2),
    }


def pe_multiples_by_company(
    engine: sa.Engine,
    fund_id: str,
    as_of_date: str,
) -> pd.DataFrame:
    """
    Compute DPI, RVPI and TVPI per portfolio company.

    Returns
    -------
    pd.DataFrame with columns:
        company_id, company_name, cost_basis, distributions,
        nav, dpi, rvpi, tvpi, status
    """
    with Session(engine) as session:
        investments = session.query(PEFundInvestment).filter_by(
            fund_id=fund_id).all()
        companies   = {c.company_id: c.company_name
                       for c in session.query(PEPortfolioCompany).all()}
        cfs         = session.query(PECashFlow).filter(
            PECashFlow.fund_id    == fund_id,
            PECashFlow.cash_flow_date       <= as_of_date,
            PECashFlow.company_id != None
        ).all()
        navs        = session.query(PENavHistory).filter(
            PENavHistory.fund_id    == fund_id,
            PENavHistory.nav_date       <= as_of_date,
            PENavHistory.company_id != None
        ).all()

    nav_map = {}
    for n in sorted(navs, key=lambda x: x.nav_date):
        nav_map[n.company_id] = n.nav_eur

    dist_map = {}
    for cf in cfs:
        if cf.amount_eur > 0 and cf.company_id:
            dist_map[cf.company_id] = dist_map.get(cf.company_id, 0) + cf.amount_eur

    rows = []
    for inv in investments:
        cid          = inv.company_id
        cost         = inv.cost_basis_eur
        distributions= dist_map.get(cid, 0)
        nav_eur      = nav_map.get(cid, 0) if inv.exit_date is None else 0
        dpi          = distributions / cost if cost > 0 else 0
        rvpi         = nav_eur / cost       if cost > 0 else 0
        tvpi         = dpi + rvpi
        rows.append({
            'company_id'   : cid,
            'company_name' : companies.get(cid, cid),
            'cost_basis'   : cost,
            'distributions': distributions,
            'nav'          : nav_eur,
            'dpi'          : round(dpi, 3),
            'rvpi'         : round(rvpi, 3),
            'tvpi'         : round(tvpi, 3),
            'status'       : 'Exited' if inv.exit_date else 'Active',
        })

    return pd.DataFrame(rows)


def pe_multiples_timeseries(
    engine: sa.Engine,
    fund_id: str,
) -> pd.DataFrame:
    """
    Quarterly TVPI evolution over fund life.

    Returns
    -------
    pd.DataFrame with columns: date, paid_in, dpi, rvpi, tvpi
    """
    with Session(engine) as session:
        cfs  = session.query(PECashFlow).filter_by(fund_id=fund_id).all()
        navs = session.query(PENavHistory).filter(
            PENavHistory.fund_id    == fund_id,
            PENavHistory.company_id == None
        ).order_by(PENavHistory.nav_date).all()

    rows = []
    for nav in navs:
        date          = nav.nav_date
        paid_in       = abs(sum(cf.amount_eur for cf in cfs
                               if cf.amount_eur < 0 and cf.cash_flow_date <= date))
        distributions = sum(cf.amount_eur for cf in cfs
                            if cf.amount_eur > 0 and cf.cash_flow_date <= date)
        nav_eur       = nav.nav_eur
        dpi           = distributions / paid_in if paid_in > 0 else 0
        rvpi          = nav_eur / paid_in       if paid_in > 0 else 0
        rows.append({
            'date'   : pd.Timestamp(date),
            'paid_in': paid_in,
            'dpi'    : round(dpi, 3),
            'rvpi'   : round(rvpi, 3),
            'tvpi'   : round(dpi + rvpi, 3),
        })

    return pd.DataFrame(rows)


def pme_long_nickels(
    cash_flows: list,
    dates: list,
    index_prices: pd.Series,
    terminal_nav: float = 0.0,
    valuation_date: str = None,
) -> dict:
    """
    Long-Nickels Public Market Equivalent (PME) analysis.

    Replicates the PE fund's capital call and distribution schedule by
    buying/selling a public index at the same dates and amounts. Compares
    the resulting index portfolio value (PME terminal NAV) to the PE fund
    NAV to determine whether public markets outperformed PE.

    Algorithm
    ---------
    For each capital call (cf < 0): buy |cf| / price index units.
    For each distribution (cf > 0): sell cf / price index units
        (floored at zero — cannot sell more units than held).
    PME terminal NAV = remaining units × index price at valuation_date.

    If PME IRR > PE IRR: public markets outperformed (negative alpha).
    If PE IRR > PME IRR: PE outperformed (positive alpha).

    Parameters
    ----------
    cash_flows : list of float
        PE cash flows. Negative = capital calls. Positive = distributions.
    dates : list of str or datetime
        Dates corresponding to each cash flow.
    index_prices : pd.Series
        Daily index prices with DatetimeIndex. Nearest prior price used
        via .asof() for each cash flow date.
    terminal_nav : float
        Current PE fund NAV. Added at valuation_date to compute PE IRR.
        Default 0.0 (fully realised fund).
    valuation_date : str or None
        Terminal date for NAV and PME computations. If None, uses the
        last date in dates.

    Returns
    -------
    dict with keys:
        pme_multiple     float — (distributions + PME NAV) / paid-in capital
        pme_irr          float or None
        pe_irr           float or None — computed from cash_flows + terminal_nav
        alpha            float or None — PE IRR minus PME IRR
        pme_terminal_nav float — simulated index portfolio value at valuation_date
        units            float — index units held at termination
        simulated_nav    pd.Series — index portfolio value after each cash flow
    """
    dates_pd  = pd.to_datetime(dates)
    term_date = pd.Timestamp(valuation_date) if valuation_date else dates_pd[-1]
    prices    = index_prices.sort_index()

    units      = 0.0
    nav_points = {}

    for cf, date in zip(cash_flows, dates_pd):
        price = float(prices.asof(date))
        if np.isnan(price) or price <= 0:
            continue
        if cf < 0:
            units += abs(cf) / price
        else:
            units = max(0.0, units - cf / price)
        nav_points[date] = units * price

    term_price       = float(prices.asof(term_date))
    pme_terminal_nav = units * term_price if not np.isnan(term_price) else 0.0

    paid_in       = sum(abs(cf) for cf in cash_flows if cf < 0)
    distributions = sum(cf for cf in cash_flows if cf > 0)

    pme_multiple = (
        (distributions + pme_terminal_nav) / paid_in if paid_in > 0 else float('nan')
    )

    terminal_dates = list(dates_pd) + [term_date]
    pme_irr = xirr(list(cash_flows) + [pme_terminal_nav], terminal_dates)
    pe_irr  = xirr(list(cash_flows) + [terminal_nav],     terminal_dates)

    alpha = (
        pe_irr - pme_irr
        if pe_irr is not None and pme_irr is not None
        else None
    )

    return {
        'pme_multiple'    : round(pme_multiple, 3) if not np.isnan(pme_multiple) else None,
        'pme_irr'         : pme_irr,
        'pe_irr'          : pe_irr,
        'alpha'           : alpha,
        'pme_terminal_nav': round(pme_terminal_nav, 2),
        'units'           : units,
        'simulated_nav'   : pd.Series(nav_points),
    }


def pe_value_bridge(
    engine: sa.Engine,
    fund_id: str,
    company_id: Optional[str] = None,
    ) -> dict:
    """
    PE return attribution: value bridge decomposition.

    Decomposes total equity value created into four sources:
    EBITDA growth, multiple expansion, leverage effect, and
    interim distributions.

    Regulatory context
    ------------------
    AIFMD Annex IV and CSSF circular 18/698 expect performance
    attribution that distinguishes operational value creation from
    financial engineering. The value bridge is the standard LP
    reporting methodology (ILPA guidelines) and is consistent with
    CSSF expectations for the internal governance report (MRS-37).

    Attribution formulas
    --------------------

    For exited companies all inputs are realised. Gap should be near zero.
    For active companies inputs are current appraiser values from
    pe_valuation_report. Attribution is partially unrealised. Gap may be
    non-zero due to DCF assumptions, minority discounts, and other
    appraiser inputs outside the EV/EBITDA bridge. Shown, not suppressed.

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
    company_id : str or None
        If None, returns aggregation across all companies in the fund.

    Returns
    -------
    dict with keys:
        fund_id         str
        company_id      str or None
        rows            list[dict]  one per company
        fund_totals     dict        summed EUR and % of total value created
    """
    GAP_THRESHOLD = 0.05

    with Session(engine) as session:

        inv_query = session.query(PEFundInvestment).filter(
            PEFundInvestment.fund_id == fund_id
        )
        if company_id is not None:
            inv_query = inv_query.filter(
                PEFundInvestment.company_id == company_id
            )
        investments = inv_query.all()

        if not investments:
            raise ValueError(
                f"No investments found for fund_id={fund_id}"
                + (f", company_id={company_id}" if company_id else "")
            )

        company_ids = [inv.company_id for inv in investments]

        companies = {
            c.company_id: c.company_name
            for c in session.query(PEPortfolioCompany).filter(
                PEPortfolioCompany.company_id.in_(company_ids)
            ).all()
        }

        # All valuation reports for these companies in this fund
        all_vr = session.query(PEValuationReport).filter(
            PEValuationReport.fund_id    == fund_id,
            PEValuationReport.company_id.in_(company_ids)
        ).order_by(PEValuationReport.valuation_date).all()

        # Interim distributions only — exit proceeds are captured in
        # exit_price_eur and must not be double-counted here
        all_cf = session.query(PECashFlow).filter(
            PECashFlow.fund_id    == fund_id,
            PECashFlow.company_id.in_(company_ids),
            PECashFlow.flow_type  == 'distribution'
        ).all()

    # Build per-company valuation maps
    entry_vr_map = {}   # company_id -> earliest valuation report
    exit_vr_map  = {}   # company_id -> latest valuation report
    for vr in all_vr:
        cid = vr.company_id
        if cid not in entry_vr_map:
            entry_vr_map[cid] = vr
        exit_vr_map[cid] = vr   # keeps overwriting, ends on latest

    dist_map = {}
    for cf in all_cf:
        cid = cf.company_id
        dist_map[cid] = dist_map.get(cid, 0.0) + cf.amount_eur

    rows = []
    for inv in investments:
        cid       = inv.company_id
        entry_vr  = entry_vr_map.get(cid)
        exit_vr   = exit_vr_map.get(cid)
        is_exited = inv.exit_date is not None

        if entry_vr is None or exit_vr is None:
            continue

        ebitda_entry    = entry_vr.ebitda_ltm_eur
        ev_ebitda_entry = entry_vr.ev_ebitda
        net_debt_entry  = entry_vr.net_debt_eur
        entry_equity    = entry_vr.appraised_nav_eur

        if is_exited:
            ebitda_exit    = exit_vr.ebitda_ltm_eur
            ev_ebitda_exit = inv.exit_ev_ebitda or exit_vr.ev_ebitda
            net_debt_exit  = exit_vr.net_debt_eur
            exit_equity    = inv.exit_price_eur or exit_vr.appraised_nav_eur
        else:
            ebitda_exit    = exit_vr.ebitda_ltm_eur
            ev_ebitda_exit = exit_vr.ev_ebitda
            net_debt_exit  = exit_vr.net_debt_eur
            exit_equity    = exit_vr.appraised_nav_eur

        if any(v is None for v in [
            ebitda_entry, ev_ebitda_entry, net_debt_entry, entry_equity,
            ebitda_exit, ev_ebitda_exit, net_debt_exit, exit_equity,
        ]):
            continue

        distributions = dist_map.get(cid, 0.0)

        ebitda_growth      = (ebitda_exit - ebitda_entry) * ev_ebitda_entry
        multiple_expansion = (ev_ebitda_exit - ev_ebitda_entry) * ebitda_exit
        leverage_effect    = net_debt_entry - net_debt_exit
        total_attributed   = (
            ebitda_growth + multiple_expansion + leverage_effect + distributions
        )
        actual_value_created = exit_equity + distributions - entry_equity
        reconciliation_gap   = total_attributed - actual_value_created
        reconciliation_gap_pct = (
            reconciliation_gap / actual_value_created
            if actual_value_created != 0 else float('nan')
        )

        rows.append({
            'company_id':             cid,
            'company_name':           companies.get(cid, cid),
            'is_realised':            is_exited,
            'cost_basis':             inv.cost_basis_eur,
            'entry_equity_value':     entry_equity,
            'exit_equity_value':      exit_equity,
            'ebitda_growth':          ebitda_growth,
            'multiple_expansion':     multiple_expansion,
            'leverage_effect':        leverage_effect,
            'distributions':          distributions,
            'total_attributed':       total_attributed,
            'actual_value_created':   actual_value_created,
            'reconciliation_gap':     reconciliation_gap,
            'reconciliation_gap_pct': reconciliation_gap_pct,
            'gap_is_material':        abs(reconciliation_gap_pct) > GAP_THRESHOLD
                                        if not np.isnan(reconciliation_gap_pct) else False,
        })
       
    # Fund-level aggregation
    total_value_created = sum(r['actual_value_created'] for r in rows)
    total_cost          = sum(r['cost_basis'] for r in rows)

    component_cols = [
        'ebitda_growth', 'multiple_expansion', 'leverage_effect',
        'distributions', 'total_attributed', 'actual_value_created',
        'reconciliation_gap',
    ]
    fund_totals = {'total_cost_basis': total_cost}
    for col in component_cols:
        eur = sum(r[col] for r in rows)
        fund_totals[f'{col}_eur'] = eur
        fund_totals[f'{col}_pct'] = (
            eur / total_value_created if total_value_created != 0 else float('nan')
        )

    return {
        'fund_id':     fund_id,
        'company_id':  company_id,
        'rows':        rows,
        'fund_totals': fund_totals,
    }

# ══════════════════════════════════════════════════════════════════════════
# MRS-198: notebook-extracted aggregations for the PE monitoring workflow
# ══════════════════════════════════════════════════════════════════════════

def pe_portfolio_overview(engine: sa.Engine, fund_id: str) -> pd.DataFrame:
    """Portfolio company overview from the PE tables.

    One row per investment: company, sector, country, stage, status,
    investment date, cost basis, ownership, entry multiples, exit date,
    and exit multiple. The exit multiple is derived from the latest
    independent appraisal at or before the exit date over cost basis.
    """
    with Session(engine) as session:
        investments = session.query(PEFundInvestment).filter_by(
            fund_id=fund_id).all()
        if not investments:
            raise ValueError(f'No PE investments found for {fund_id}')
        companies = {c.company_id: c
                     for c in session.query(PEPortfolioCompany).all()}
        reports = session.query(PEValuationReport).filter_by(
            fund_id=fund_id).order_by(PEValuationReport.valuation_date).all()

    def _exit_multiple(inv) -> float | None:
        if not inv.exit_date:
            return None
        if inv.exit_multiple:
            return float(inv.exit_multiple)
        company_reports = [r for r in reports
                           if r.company_id == inv.company_id
                           and r.valuation_date <= inv.exit_date]
        if not company_reports or not inv.cost_basis_eur:
            return None
        return company_reports[-1].appraised_nav_eur / inv.cost_basis_eur

    rows = []
    for inv in investments:
        co = companies.get(inv.company_id)
        rows.append({
            'company_name': co.company_name if co else inv.company_id,
            'sector': co.sector if co else None,
            'country': co.country if co else None,
            'stage': co.investment_stage if co else None,
            'status': co.status if co else None,
            'investment_date': inv.investment_date,
            'cost_basis_eur': inv.cost_basis_eur,
            'ownership_pct': inv.ownership_pct,
            'entry_ev_ebitda': inv.entry_ev_ebitda,
            'entry_ev_sales': inv.entry_ev_sales,
            'exit_date': inv.exit_date,
            'exit_multiple': _exit_multiple(inv),
        })
    return pd.DataFrame(rows).sort_values('investment_date').reset_index(drop=True)


def pe_covenant_summary(engine: sa.Engine, fund_id: str,
                        as_of_date: str) -> pd.DataFrame:
    """Latest independent appraisal and covenant headroom per company.

    Headroom % = (covenant - actual) / covenant x 100. A leverage ratio
    above 50x is treated as not meaningful (negative EBITDA convention
    in the mock data) and reported as NaN.
    """
    with Session(engine) as session:
        reports = session.query(PEValuationReport).filter(
            PEValuationReport.fund_id == fund_id,
            PEValuationReport.valuation_date <= as_of_date,
        ).order_by(PEValuationReport.valuation_date).all()
        if not reports:
            raise ValueError(
                f'No PE valuation reports for {fund_id} at {as_of_date}')
        companies = {c.company_id: c
                     for c in session.query(PEPortfolioCompany).all()}

    latest = {}
    for r in reports:
        latest[r.company_id] = r

    rows = []
    for cid, r in sorted(latest.items()):
        co = companies.get(cid)
        lev = r.leverage_ratio
        lev_valid = lev is not None and lev <= 50
        headroom = None
        if lev_valid and r.leverage_covenant:
            headroom = (r.leverage_covenant - lev) / r.leverage_covenant * 100
        rows.append({
            'company_name': co.company_name if co else cid,
            'status': co.status if co else None,
            'valuation_date': r.valuation_date,
            'appraised_nav_eur': r.appraised_nav_eur,
            'ebitda_ltm_eur': r.ebitda_ltm_eur,
            'ev_ebitda': r.ev_ebitda,
            'leverage_ratio': lev if lev_valid else None,
            'leverage_covenant': r.leverage_covenant,
            'headroom_pct': headroom,
            'covenant_type': r.covenant_type,
            'appraiser': r.appraiser,
            'key_risks': r.key_risks,
        })
    return pd.DataFrame(rows)


def pe_quarterly_cashflow_frame(engine: sa.Engine, fund_id: str) -> pd.DataFrame:
    """Quarterly J-curve frame: calls, fees, distributions, NAV, multiples.

    Net cash flow = distributions - capital called - management fees.
    DPI/RVPI/TVPI are computed against cumulative paid-in capital.
    """
    with Session(engine) as session:
        cfs = session.query(PECashFlow).filter_by(fund_id=fund_id).all()
        navs = session.query(PENavHistory).filter(
            PENavHistory.fund_id == fund_id,
            PENavHistory.company_id != None,  # noqa: E711
        ).all()
    if not cfs:
        raise ValueError(f'No PE cash flows found for {fund_id}')

    cf_df = pd.DataFrame([{
        'date': pd.Timestamp(c.cash_flow_date),
        'flow_type': c.flow_type,
        'amount_eur': c.amount_eur,
    } for c in cfs])
    cf_df['quarter'] = cf_df['date'].dt.to_period('Q').dt.to_timestamp('Q')

    nav_df = pd.DataFrame([{
        'quarter': pd.Timestamp(n.nav_date).to_period('Q').to_timestamp('Q'),
        'nav_eur': n.nav_eur,
    } for n in navs])
    nav_q = nav_df.groupby('quarter')['nav_eur'].sum().rename('nav')

    called = (cf_df[cf_df['flow_type'] == 'capital_call']
              .groupby('quarter')['amount_eur'].sum().abs()
              .rename('capital_called'))
    dists = (cf_df[cf_df['flow_type'].isin(['distribution', 'exit_proceeds'])]
             .groupby('quarter')['amount_eur'].sum().rename('distributions'))
    fees = (cf_df[cf_df['flow_type'] == 'management_fee']
            .groupby('quarter')['amount_eur'].sum().abs().rename('mgmt_fees'))

    quarters = nav_q.index.union(called.index).union(dists.index).union(fees.index)
    out = pd.DataFrame(index=quarters).join(called).join(dists).join(fees)
    out = out.join(nav_q).fillna(0.0).sort_index()
    out.index.name = 'quarter'

    out['ncf'] = out['distributions'] - out['capital_called'] - out['mgmt_fees']
    out['cncf'] = out['ncf'].cumsum()
    out['pic'] = out['capital_called'].cumsum()
    out['cum_dist'] = out['distributions'].cumsum()
    out['dpi'] = out['cum_dist'] / out['pic'].replace(0, float('nan'))
    out['rvpi'] = out['nav'] / out['pic'].replace(0, float('nan'))
    out['tvpi'] = out['dpi'] + out['rvpi']
    return out


def pe_exit_waterfalls(engine: sa.Engine, fund_id: str,
                       hurdle_rate: float, carry_rate: float) -> list[dict]:
    """European-style exit waterfall allocation per realised company.

    Sequence: return of capital, preferred return at the hurdle rate,
    GP catch-up to the carry share of total profit, then an
    (1-carry)/carry LP/GP split of the remainder. Gross exit value is
    the latest independent appraisal at or before the exit date; fees
    are allocated equally across companies invested at each fee date.
    """
    with Session(engine) as session:
        investments = session.query(PEFundInvestment).filter_by(
            fund_id=fund_id).all()
        reports = session.query(PEValuationReport).filter_by(
            fund_id=fund_id).order_by(PEValuationReport.valuation_date).all()
        cfs = session.query(PECashFlow).filter_by(fund_id=fund_id).all()
        companies = {c.company_id: c
                     for c in session.query(PEPortfolioCompany).all()}

    exited = [inv for inv in investments if inv.exit_date]
    if not exited:
        raise ValueError(f'No exited PE investments found for {fund_id}')

    call_flows = [c for c in cfs if c.flow_type == 'capital_call']
    fee_flows = [c for c in cfs if c.flow_type == 'management_fee']
    invest_dates = {inv.company_id: inv.investment_date for inv in investments}

    waterfalls = []
    for inv in exited:
        cid = inv.company_id
        exit_date = inv.exit_date
        company_reports = [r for r in reports
                           if r.company_id == cid
                           and r.valuation_date <= exit_date]
        if not company_reports:
            raise ValueError(f'No valuation report before exit for {cid}')
        gross = company_reports[-1].appraised_nav_eur

        contributed = sum(abs(c.amount_eur) for c in call_flows
                          if c.company_id == cid)
        fees_paid = 0.0
        for f in fee_flows:
            if f.cash_flow_date > exit_date:
                continue
            n_active = sum(1 for d in invest_dates.values()
                           if d <= f.cash_flow_date)
            fees_paid += abs(f.amount_eur) / max(1, n_active)
        total_contributed = contributed + fees_paid

        first_call = min((c.cash_flow_date for c in call_flows
                          if c.company_id == cid), default=inv.investment_date)
        years = ((pd.Timestamp(exit_date) - pd.Timestamp(first_call)).days
                 / 365)
        preferred = total_contributed * ((1 + hurdle_rate) ** years - 1)

        remaining = gross
        steps = []
        roc = min(remaining, total_contributed)
        steps.append({'label': 'Return of Capital', 'amount_eur': roc,
                      'party': 'LP'})
        remaining -= roc
        if remaining > 0:
            pref = min(remaining, preferred)
            steps.append({
                'label': f'Preferred Return {hurdle_rate:.0%}',
                'amount_eur': pref, 'party': 'LP'})
            remaining -= pref
        if remaining > 0:
            gp_target = (gross - total_contributed) * carry_rate
            catchup = min(remaining, max(0.0, gp_target))
            steps.append({'label': 'GP Catch-up', 'amount_eur': catchup,
                          'party': 'GP'})
            remaining -= catchup
        if remaining > 0:
            steps.append({'label': f'LP {1 - carry_rate:.0%} Split',
                          'amount_eur': remaining * (1 - carry_rate),
                          'party': 'LP'})
            steps.append({'label': f'GP {carry_rate:.0%} Split',
                          'amount_eur': remaining * carry_rate,
                          'party': 'GP'})

        co = companies.get(cid)
        waterfalls.append({
            'company_id': cid,
            'company_name': co.company_name if co else cid,
            'exit_date': exit_date,
            'gross_exit_value_eur': gross,
            'total_contributed_eur': total_contributed,
            'steps': steps,
        })
    return waterfalls


def pe_cash_management_frame(engine: sa.Engine, fund_id: str) -> pd.DataFrame:
    """Fund-level cash, subscription line, and interest series."""
    from fund_risk_workflow.data.database import PEFundCashManagement
    with Session(engine) as session:
        rows = session.query(PEFundCashManagement).filter_by(
            fund_id=fund_id).order_by(
            PEFundCashManagement.cash_management_date).all()
    if not rows:
        raise ValueError(f'No PE cash management rows for {fund_id}')
    out = pd.DataFrame([{
        'date': pd.Timestamp(r.cash_management_date),
        'cash_balance_eur': r.cash_balance_eur,
        'sub_line_drawn': r.sub_line_drawn,
        'sub_line_limit': r.sub_line_limit,
        'net_cash_position': r.net_cash_position,
        'cumulative_interest_earned': r.cumulative_interest_earned,
        'cumulative_interest_paid': r.cumulative_interest_paid,
    } for r in rows])
    return out


def pe_commitment_liquidity(engine: sa.Engine, fund_id: str,
                            valuation_date: str,
                            stress_call_pct: float) -> dict:
    """Closed-ended funding-liquidity profile.

    Coverage ratio = (cash + sub-line headroom + trailing-12m
    distributions) / (trailing-12m capital calls + fees). The stress
    call assumes an accelerated drawdown of stress_call_pct of unfunded
    commitments against cash plus sub-line headroom.
    """
    if not 0 < stress_call_pct <= 1:
        raise ValueError(
            f'stress_call_pct must be in (0, 1], got {stress_call_pct}')
    from fund_risk_workflow.data.database import PEFundCashManagement
    with Session(engine) as session:
        fund = session.query(PEFund).filter_by(fund_id=fund_id).first()
        if fund is None:
            raise ValueError(f'PE fund not found: {fund_id}')
        cfs = session.query(PECashFlow).filter(
            PECashFlow.fund_id == fund_id,
            PECashFlow.cash_flow_date <= valuation_date).all()
        cm = session.query(PEFundCashManagement).filter(
            PEFundCashManagement.fund_id == fund_id,
            PEFundCashManagement.cash_management_date <= valuation_date,
        ).order_by(PEFundCashManagement.cash_management_date.desc()).first()
        nav_row = session.query(PENavHistory).filter(
            PENavHistory.fund_id == fund_id,
            PENavHistory.company_id == None,  # noqa: E711
            PENavHistory.nav_date <= valuation_date,
        ).order_by(PENavHistory.nav_date.desc()).first()

    committed = float(fund.target_size_eur)
    drawn = sum(abs(c.amount_eur) for c in cfs
                if c.flow_type == 'capital_call')
    unfunded = max(0.0, committed - drawn)
    cash = float(cm.cash_balance_eur) if cm else 0.0
    sub_drawn = float(cm.sub_line_drawn) if cm else 0.0
    sub_limit = float(cm.sub_line_limit) if cm else 0.0
    headroom = sub_limit - sub_drawn
    nav = float(nav_row.nav_eur) if nav_row else 0.0

    window_start = (pd.Timestamp(valuation_date)
                    - pd.DateOffset(months=12)).strftime('%Y-%m-%d')
    in_window = [c for c in cfs if c.cash_flow_date >= window_start]
    dist_12m = sum(c.amount_eur for c in in_window
                   if c.flow_type == 'distribution')
    calls_12m = sum(abs(c.amount_eur) for c in in_window
                    if c.flow_type == 'capital_call')
    fees_12m = sum(abs(c.amount_eur) for c in in_window
                   if c.flow_type == 'management_fee')

    liquid_resources = cash + headroom + dist_12m
    obligations_12m = calls_12m + fees_12m
    coverage = (liquid_resources / obligations_12m
                if obligations_12m > 0 else float('inf'))
    stress_call = unfunded * stress_call_pct
    shortfall = max(0.0, stress_call - (cash + headroom))

    illiquid = max(0.0, nav - cash)
    buckets = pd.DataFrame([
        {'liquidity_bucket': '1 day', 'abs_exposure': cash},
        {'liquidity_bucket': '2-7 days', 'abs_exposure': 0.0},
        {'liquidity_bucket': '8-30 days', 'abs_exposure': 0.0},
        {'liquidity_bucket': '31-90 days', 'abs_exposure': 0.0},
        {'liquidity_bucket': '91-365 days', 'abs_exposure': 0.0},
        {'liquidity_bucket': '> 1 year', 'abs_exposure': illiquid},
    ])
    buckets['pct_nav_abs'] = (buckets['abs_exposure'] / nav * 100
                              if nav else 0.0)

    return {
        'committed_eur': committed,
        'drawn_eur': drawn,
        'unfunded_eur': unfunded,
        'cash_eur': cash,
        'sub_line_drawn_eur': sub_drawn,
        'sub_line_limit_eur': sub_limit,
        'sub_line_headroom_eur': headroom,
        'nav_eur': nav,
        'distributions_12m_eur': dist_12m,
        'capital_calls_12m_eur': calls_12m,
        'fees_12m_eur': fees_12m,
        'coverage_ratio': coverage,
        'stress_call_pct': stress_call_pct,
        'stress_call_eur': stress_call,
        'stress_shortfall_eur': shortfall,
        'liquidity_buckets': buckets,
    }


def pe_lp_cash_flows(engine: sa.Engine, fund_id: str,
                     valuation_date: str) -> dict:
    """LP net cash flows and terminal NAV for the PME comparison.

    Includes capital calls, management fees, distributions, and exit
    proceeds — the full LP net experience. Returns the first actual
    cash-flow date so the benchmark series can be requested from that
    date (cache-only path).
    """
    with Session(engine) as session:
        cfs = session.query(PECashFlow).filter(
            PECashFlow.fund_id == fund_id,
            PECashFlow.cash_flow_date <= valuation_date,
            PECashFlow.flow_type.in_([
                'capital_call', 'management_fee',
                'distribution', 'exit_proceeds']),
        ).order_by(PECashFlow.cash_flow_date).all()
        nav_row = session.query(PENavHistory).filter(
            PENavHistory.fund_id == fund_id,
            PENavHistory.company_id == None,  # noqa: E711
            PENavHistory.nav_date <= valuation_date,
        ).order_by(PENavHistory.nav_date.desc()).first()
    if not cfs:
        raise ValueError(f'No LP cash flows found for {fund_id}')
    if nav_row is None:
        raise ValueError(f'No fund-level NAV found for {fund_id}')
    return {
        'cash_flows': [c.amount_eur for c in cfs],
        'dates': [pd.Timestamp(c.cash_flow_date) for c in cfs],
        'terminal_nav': float(nav_row.nav_eur),
        'first_flow_date': cfs[0].cash_flow_date,
    }


def pe_stress_scenarios(engine: sa.Engine, fund_id: str, quarter: str,
                        params: dict) -> dict:
    """PE NAV-sensitivity stress set on active companies.

    Scenarios (parameters from the fund risk policy, migrated notebook
    assumptions):
        S1 uniform NAV markdown, S2 exit-multiple compression,
        S3 revenue/EBITDA stress, S4 sector concentration,
        S5 historical GFC proxy.
    Multiples-based shocks use dNAV = dMultiple x EBITDA and
    dNAV = dEBITDA x Multiple respectively.
    """
    required = ('nav_markdown_pct', 'multiple_compression_x',
                'revenue_stress_pct', 'sector_concentration_sector',
                'sector_concentration_shock_pct', 'historical_gfc_proxy_pct')
    missing = [k for k in required if params.get(k) is None]
    if missing:
        raise ValueError(f'PE stress parameters missing: {missing}')

    with Session(engine) as session:
        reports = session.query(PEValuationReport).filter(
            PEValuationReport.fund_id == fund_id,
            PEValuationReport.valuation_date <= quarter,
        ).order_by(PEValuationReport.valuation_date).all()
        companies = {c.company_id: c
                     for c in session.query(PEPortfolioCompany).all()}
    latest = {}
    for r in reports:
        co = companies.get(r.company_id)
        if co is not None and co.status == 'Active':
            latest[r.company_id] = r
    if not latest:
        raise ValueError(f'No active PE valuations for {fund_id} at {quarter}')

    sector_target = params['sector_concentration_sector']
    rows = []
    for cid, r in sorted(latest.items()):
        co = companies[cid]
        nav = r.appraised_nav_eur or 0.0
        ebitda = r.ebitda_ltm_eur or 0.0
        mult = r.ev_ebitda or 0.0
        rows.append({
            'company_name': co.company_name,
            'sector': co.sector,
            'nav_eur': nav,
            's1_nav_markdown': params['nav_markdown_pct'] * nav,
            's2_multiple_compression': params['multiple_compression_x'] * ebitda,
            's3_revenue_stress': params['revenue_stress_pct'] * ebitda * mult,
            's4_sector_concentration': (
                params['sector_concentration_shock_pct'] * nav
                if co.sector == sector_target else 0.0),
            's5_gfc_proxy': params['historical_gfc_proxy_pct'] * nav,
        })
    by_company = pd.DataFrame(rows)
    base_nav = by_company['nav_eur'].sum()

    labels = {
        's1_nav_markdown':
            f'S1 — NAV markdown {params["nav_markdown_pct"]:.0%}',
        's2_multiple_compression':
            f'S2 — Multiple compression {params["multiple_compression_x"]:+.1f}x',
        's3_revenue_stress':
            f'S3 — Revenue stress {params["revenue_stress_pct"]:.0%}',
        's4_sector_concentration':
            f'S4 — {sector_target} concentration '
            f'{params["sector_concentration_shock_pct"]:.0%}',
        's5_gfc_proxy':
            f'S5 — 2008 GFC proxy {params["historical_gfc_proxy_pct"]:.0%}',
    }
    summary = pd.DataFrame([
        {'scenario': label,
         'delta_nav_eur': by_company[col].sum(),
         'pct_nav': by_company[col].sum() / base_nav * 100}
        for col, label in labels.items()
    ])
    return {
        'by_company': by_company,
        'summary': summary,
        'base_nav_eur': base_nav,
        'params': dict(params),
    }
