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

Regulatory basis
----------------
IPEV Valuation Guidelines (International Private Equity Valuation)
ILPA reporting standards
AIFMD Article 19 (independent valuation)
EU 231/2013 Articles 46-49 (risk management)
"""

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from typing import Optional
import sqlalchemy as sa
from sqlalchemy.orm import Session

from src.database import (
    PEFund, PEPortfolioCompany, PEFundInvestment,
    PECashFlow, PENavHistory, PEValuationReport
)


__all__ = [
    'xirr',
    'fund_irr',
    'pe_multiples',
    'pe_multiples_by_company',
    'pe_multiples_timeseries',
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
            PECashFlow.date   <= as_of_date
        ).order_by(PECashFlow.date).all()

        nav = session.query(PENavHistory).filter(
            PENavHistory.fund_id    == fund_id,
            PENavHistory.company_id == None,
            PENavHistory.date       <= as_of_date
        ).order_by(PENavHistory.date.desc()).first()

    cf_amounts = [cf.amount_eur for cf in cfs]
    cf_dates   = [cf.date for cf in cfs]

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
            PECashFlow.date   <= as_of_date
        ).all()

        nav = session.query(PENavHistory).filter(
            PENavHistory.fund_id    == fund_id,
            PENavHistory.company_id == None,
            PENavHistory.date       <= as_of_date
        ).order_by(PENavHistory.date.desc()).first()

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
            PECashFlow.date       <= as_of_date,
            PECashFlow.company_id != None
        ).all()
        navs        = session.query(PENavHistory).filter(
            PENavHistory.fund_id    == fund_id,
            PENavHistory.date       <= as_of_date,
            PENavHistory.company_id != None
        ).all()

    nav_map = {}
    for n in sorted(navs, key=lambda x: x.date):
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
        ).order_by(PENavHistory.date).all()

    rows = []
    for nav in navs:
        date          = nav.date
        paid_in       = abs(sum(cf.amount_eur for cf in cfs
                               if cf.amount_eur < 0 and cf.date <= date))
        distributions = sum(cf.amount_eur for cf in cfs
                            if cf.amount_eur > 0 and cf.date <= date)
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