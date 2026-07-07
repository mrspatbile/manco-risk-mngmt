"""
database.py
===========
Creates and manages the risk_management SQLite database.
Loads fund position Excel files into a structured database
with time series support for VaR backtesting.

Tables
------
    positions   : daily position snapshots (all funds, all dates)
    funds       : fund metadata
    instruments : instrument reference data

Usage
-----
    python3 database.py

    # or import in notebooks:
    from database import create_db, load_positions, query_positions
"""

import json
import pandas as pd
import numpy as np
import os
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String, Float, Integer, Date, Boolean
from datetime import date as date_type
from pathlib import Path


# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------

ROOT_DIR = Path(__file__).parent.parent.parent.parent  # src/fund_risk_workflow/data/ -> project root
DATA_DIR = str(ROOT_DIR / 'data')
DB_PATH  = str(ROOT_DIR / 'data' / 'risk_management.db')
_REF_DIR = ROOT_DIR / 'reference_data'

with open(_REF_DIR / 'platform' / 'fund_file_map.json') as _f:
    data = json.load(_f)
    FUND_FILES = {k: v for k, v in data.items() if k != 'schema_version'}


# ----------------------------------------------------------------
# SQLAlchemy ORM models
# ----------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class Fund(Base):
    """Fund metadata table."""
    __tablename__ = 'funds'

    fund_id        : Mapped[str]   = mapped_column(String, primary_key=True)
    fund_name      : Mapped[str]   = mapped_column(String)
    fund_type      : Mapped[str]   = mapped_column(String)
    currency       : Mapped[str]   = mapped_column(String)
    inception_date : Mapped[str]   = mapped_column(String)
    domicile       : Mapped[str]   = mapped_column(String)
    regulator      : Mapped[str]   = mapped_column(String)
    target_nav_eur : Mapped[float] = mapped_column(Float)


class Instrument(Base):
    """Instrument reference data table."""
    __tablename__ = 'instruments'

    isin             : Mapped[str] = mapped_column(String, primary_key=True)
    bloomberg_ticker : Mapped[str] = mapped_column(String, nullable=True)
    instrument_name  : Mapped[str] = mapped_column(String)
    asset_class      : Mapped[str] = mapped_column(String)
    sub_asset_class  : Mapped[str] = mapped_column(String, nullable=True)
    currency         : Mapped[str] = mapped_column(String)
    country          : Mapped[str] = mapped_column(String, nullable=True)


class Position(Base):
    """
    Daily position snapshots.
    One row per position per date per fund.
    Primary key: (fund_id, position_date, isin)
    """
    __tablename__ = 'positions'
    __table_args__ = (
        # composite index for joining positions to positions_enriched
        # and for looking up a specific instrument on a specific date
        sa.Index('ix_positions_fund_date_isin',
                 'fund_id', 'position_date', 'isin'),
        # composite index for the most common query:
        # all positions for a fund on a given date (daily snapshot)
        sa.Index('ix_positions_fund_date',
                 'fund_id', 'position_date'),
    )

    id                  : Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    fund_id             : Mapped[str]   = mapped_column(String, sa.ForeignKey('funds.fund_id'))
    fund_name           : Mapped[str]   = mapped_column(String)
    position_date       : Mapped[str]   = mapped_column(String)
    isin                : Mapped[str]   = mapped_column(String)
    bloomberg_ticker    : Mapped[str]   = mapped_column(String, nullable=True)
    instrument_name     : Mapped[str]   = mapped_column(String)
    asset_class         : Mapped[str]   = mapped_column(String)
    sub_asset_class     : Mapped[str]   = mapped_column(String, nullable=True)
    currency            : Mapped[str]   = mapped_column(String)
    quantity            : Mapped[float] = mapped_column(Float)
    price               : Mapped[float] = mapped_column(Float)
    market_value_local  : Mapped[float] = mapped_column(Float)
    market_value_eur    : Mapped[float] = mapped_column(Float)
    weight_pct          : Mapped[float] = mapped_column(Float)
    country             : Mapped[str]   = mapped_column(String, nullable=True)
    rating              : Mapped[str]   = mapped_column(String, nullable=True)
    maturity            : Mapped[str]   = mapped_column(String, nullable=True)
    sector              : Mapped[str]   = mapped_column(String, nullable=True)
    adv_eur             : Mapped[float] = mapped_column(Float, nullable=True)
    # real estate extras
    ltv_pct             : Mapped[float] = mapped_column(Float, nullable=True)
    rental_yield_pct    : Mapped[float] = mapped_column(Float, nullable=True)
    vacancy_rate_pct    : Mapped[float] = mapped_column(Float, nullable=True)
    property_type       : Mapped[str]   = mapped_column(String, nullable=True)
    valuation_date      : Mapped[str]   = mapped_column(String, nullable=True)
    is_direct_property  : Mapped[bool]  = mapped_column(Boolean, nullable=True)
    is_hedge            : Mapped[bool]  = mapped_column(Boolean, nullable=True)
    # ESG scores
    esg_score           : Mapped[float] = mapped_column(Float, nullable=True)
    env_score           : Mapped[float] = mapped_column(Float, nullable=True)
    soc_score           : Mapped[float] = mapped_column(Float, nullable=True)
    gov_score           : Mapped[float] = mapped_column(Float, nullable=True)
    controversy_flag    : Mapped[bool]  = mapped_column(Boolean, nullable=True)
    carbon_intensity    : Mapped[float] = mapped_column(Float, nullable=True)



# ----------------------------------------------------------------
# PE Fund Tables
# ----------------------------------------------------------------

class PEFund(Base):
    """PE fund metadata."""
    __tablename__ = 'pe_funds'

    id                    : Mapped[int]   = mapped_column(Integer, primary_key=True)
    fund_id               : Mapped[str]   = mapped_column(String, nullable=False, unique=True)
    fund_name             : Mapped[str]   = mapped_column(String, nullable=False)
    vintage_year          : Mapped[int]   = mapped_column(Integer, nullable=False)
    target_size_eur       : Mapped[float] = mapped_column(Float, nullable=False)
    investment_period_end : Mapped[str]   = mapped_column(String, nullable=True)
    fund_life_years       : Mapped[int]   = mapped_column(Integer, nullable=True)
    currency              : Mapped[str]   = mapped_column(String, nullable=True)
    domicile              : Mapped[str]   = mapped_column(String, nullable=True)
    strategy              : Mapped[str]   = mapped_column(String, nullable=True)


class PEPortfolioCompany(Base):
    """
    PE portfolio company master data.
    Independent of any fund - a company can be invested by multiple funds.
    Fund-specific investment data lives in PEFundInvestment.
    """
    __tablename__ = 'pe_portfolio_companies'

    id               : Mapped[int]   = mapped_column(Integer, primary_key=True)
    company_id       : Mapped[str]   = mapped_column(String, nullable=False, unique=True)
    company_name     : Mapped[str]   = mapped_column(String, nullable=False)
    sector           : Mapped[str]   = mapped_column(String, nullable=True)
    country          : Mapped[str]   = mapped_column(String, nullable=True)
    investment_stage : Mapped[str]   = mapped_column(String, nullable=True)
    status           : Mapped[str]   = mapped_column(String, nullable=True)
    description      : Mapped[str]   = mapped_column(String, nullable=True)


class PEFundInvestment(Base):
    """
    Link between a PE fund and a portfolio company.
    Stores fund-specific investment data: entry, ownership, exit.
    A company can appear in multiple funds at different terms.
    """
    __tablename__ = 'pe_fund_investments'
    __table_args__ = (
        sa.UniqueConstraint('fund_id', 'company_id',
                            name='uq_fund_company'),
    )

    id              : Mapped[int]   = mapped_column(Integer, primary_key=True)
    fund_id         : Mapped[str]   = mapped_column(String, nullable=False)
    company_id      : Mapped[str]   = mapped_column(String, nullable=False)
    investment_date : Mapped[str]   = mapped_column(String, nullable=False)
    entry_ev_ebitda : Mapped[float] = mapped_column(Float, nullable=True)
    entry_ev_sales  : Mapped[float] = mapped_column(Float, nullable=True)
    cost_basis_eur  : Mapped[float] = mapped_column(Float, nullable=False)
    ownership_pct   : Mapped[float] = mapped_column(Float, nullable=True)
    exit_date       : Mapped[str]   = mapped_column(String, nullable=True)
    exit_price_eur  : Mapped[float] = mapped_column(Float, nullable=True)
    exit_multiple   : Mapped[float] = mapped_column(Float, nullable=True)
    exit_ev_ebitda  : Mapped[float] = mapped_column(Float, nullable=True)



class PECashFlow(Base):
    """
    PE capital calls, distributions, fees and exit proceeds.
    Negative amounts: capital calls, fees.
    Positive amounts: distributions, exit proceeds.
    """
    __tablename__ = 'pe_cash_flows'

    id          : Mapped[int]   = mapped_column(Integer, primary_key=True)
    fund_id     : Mapped[str]   = mapped_column(String, nullable=False)
    company_id  : Mapped[str]   = mapped_column(String, nullable=True)
    cash_flow_date : Mapped[str]   = mapped_column(String, nullable=False)
    flow_type   : Mapped[str]   = mapped_column(String, nullable=False)
    amount_eur  : Mapped[float] = mapped_column(Float, nullable=False)
    description : Mapped[str]   = mapped_column(String, nullable=True)


class PENavHistory(Base):
    """
    Quarterly NAV per fund per portfolio company.
    Reflects independent appraisal valuation each quarter.
    """
    __tablename__ = 'pe_nav_history'

    id              : Mapped[int]   = mapped_column(Integer, primary_key=True)
    fund_id         : Mapped[str]   = mapped_column(String, nullable=False)
    company_id      : Mapped[str]   = mapped_column(String, nullable=True)
    nav_date        : Mapped[str]   = mapped_column(String, nullable=False)
    nav_eur         : Mapped[float] = mapped_column(Float, nullable=False)
    gross_multiple  : Mapped[float] = mapped_column(Float, nullable=True)
    unrealised_gain : Mapped[float] = mapped_column(Float, nullable=True)
    cost_basis_eur  : Mapped[float] = mapped_column(Float, nullable=True)

class PEValuationReport(Base):
    """
    Quarterly independent appraisal data per portfolio company.
    External input from valuation firm (KPMG, Duff & Phelps, etc).
    Not computed by the ManCo.
    """
    __tablename__ = 'pe_valuation_report'
    __table_args__ = (
        sa.UniqueConstraint('fund_id', 'company_id', 'valuation_date',
                            name='uq_valuation_report'),
    )

    id                  : Mapped[int]   = mapped_column(Integer, primary_key=True)
    fund_id             : Mapped[str]   = mapped_column(String, nullable=False)
    company_id          : Mapped[str]   = mapped_column(String, nullable=False)
    valuation_date      : Mapped[str]   = mapped_column(String, nullable=False)
    appraised_nav_eur   : Mapped[float] = mapped_column(Float, nullable=False)
    ebitda_ltm_eur      : Mapped[float] = mapped_column(Float, nullable=True)
    revenue_ltm_eur     : Mapped[float] = mapped_column(Float, nullable=True)
    ebitda_margin       : Mapped[float] = mapped_column(Float, nullable=True)
    net_debt_eur        : Mapped[float] = mapped_column(Float, nullable=True)
    ev_eur              : Mapped[float] = mapped_column(Float, nullable=True)
    ev_ebitda           : Mapped[float] = mapped_column(Float, nullable=True)
    interest_expense_eur: Mapped[float] = mapped_column(Float, nullable=True)
    discount_rate       : Mapped[float] = mapped_column(Float, nullable=True)
    valuation_basis     : Mapped[str]   = mapped_column(String, nullable=True)
    appraiser           : Mapped[str]   = mapped_column(String, nullable=True)
    key_risks           : Mapped[str]   = mapped_column(String, nullable=True)
    # covenant fields
    covenant_type       : Mapped[str]   = mapped_column(String, nullable=True)
    leverage_covenant   : Mapped[float] = mapped_column(Float, nullable=True)
    leverage_ratio      : Mapped[float] = mapped_column(Float, nullable=True)
    coverage_covenant   : Mapped[float] = mapped_column(Float, nullable=True)
    coverage_ratio      : Mapped[float] = mapped_column(Float, nullable=True)
    revenue_covenant_eur: Mapped[float] = mapped_column(Float, nullable=True)
    cash_covenant_eur   : Mapped[float] = mapped_column(Float, nullable=True)
    arr_eur             : Mapped[float] = mapped_column(Float, nullable=True)


class PEFundCashManagement(Base):
    """
    Quarterly fund-level treasury snapshot.
    Tracks cash reserve, subscription credit facility, and net interest.
    Distinct from pe_cash_flows which tracks company-level transactions.
    """
    __tablename__ = 'pe_fund_cash_management'

    id                    : Mapped[int]   = mapped_column(Integer, primary_key=True)
    fund_id               : Mapped[str]   = mapped_column(String, nullable=False)
    cash_management_date  : Mapped[str]   = mapped_column(String, nullable=False)

    # cash reserve
    cash_balance_eur      : Mapped[float] = mapped_column(Float, nullable=True)
    cash_interest_earned  : Mapped[float] = mapped_column(Float, nullable=True)
    cash_rate             : Mapped[float] = mapped_column(Float, nullable=True)

    # subscription credit facility
    sub_line_drawn        : Mapped[float] = mapped_column(Float, nullable=True)
    sub_line_limit        : Mapped[float] = mapped_column(Float, nullable=True)
    sub_line_interest     : Mapped[float] = mapped_column(Float, nullable=True)
    sub_line_rate         : Mapped[float] = mapped_column(Float, nullable=True)

    # net position
    net_cash_position     : Mapped[float] = mapped_column(Float, nullable=True)
    cumulative_interest_earned  : Mapped[float] = mapped_column(Float, nullable=True)
    cumulative_interest_paid    : Mapped[float] = mapped_column(Float, nullable=True)


# ----------------------------------------------------------------
# Infrastructure Fund Tables (MRS-74)
# ----------------------------------------------------------------

class InfraFund(Base):
    """
    Infrastructure fund metadata.
    Benchmark is typically CPI + absolute spread (e.g. CPI+4%) or
    an absolute return target, reflecting the inflation-linkage of the
    underlying assets.
    """
    __tablename__ = 'infra_funds'

    id                   : Mapped[int]   = mapped_column(Integer, primary_key=True)
    fund_id              : Mapped[str]   = mapped_column(String, unique=True, nullable=False)
    fund_name            : Mapped[str]   = mapped_column(String, nullable=False)
    vintage_year         : Mapped[int]   = mapped_column(Integer, nullable=False)
    target_size_eur      : Mapped[float] = mapped_column(Float, nullable=False)
    committed_eur        : Mapped[float] = mapped_column(Float, nullable=True)
    drawn_eur            : Mapped[float] = mapped_column(Float, nullable=True)
    fund_life_years      : Mapped[int]   = mapped_column(Integer, nullable=True)
    currency             : Mapped[str]   = mapped_column(String, nullable=True)
    domicile             : Mapped[str]   = mapped_column(String, nullable=True)
    benchmark            : Mapped[str]   = mapped_column(String, nullable=True)
    aifmd_classification : Mapped[str]   = mapped_column(String, nullable=True)


class InfraAsset(Base):
    """
    Infrastructure asset master.
    Independent of any fund — an asset can appear in multiple fund vehicles.
    Fund-specific terms (entry date, cost basis, ownership) live in
    InfraFundInvestment.
    """
    __tablename__ = 'infra_assets'

    id                   : Mapped[int]   = mapped_column(Integer, primary_key=True)
    asset_id             : Mapped[str]   = mapped_column(String, unique=True, nullable=False)
    asset_name           : Mapped[str]   = mapped_column(String, nullable=False)
    sector               : Mapped[str]   = mapped_column(String, nullable=True)
    sub_type             : Mapped[str]   = mapped_column(String, nullable=True)
    country              : Mapped[str]   = mapped_column(String, nullable=True)
    regulatory_framework : Mapped[str]   = mapped_column(String, nullable=True)
    concession_start     : Mapped[str]   = mapped_column(String, nullable=True)
    concession_end       : Mapped[str]   = mapped_column(String, nullable=True)
    inflation_linkage    : Mapped[float] = mapped_column(Float, nullable=True)


class InfraFundInvestment(Base):
    """Fund-asset link: investment terms and economics."""
    __tablename__ = 'infra_fund_investments'
    __table_args__ = (
        sa.UniqueConstraint('fund_id', 'asset_id', name='uq_infra_fund_asset'),
    )

    id               : Mapped[int]   = mapped_column(Integer, primary_key=True)
    fund_id          : Mapped[str]   = mapped_column(String, nullable=False)
    asset_id         : Mapped[str]   = mapped_column(String, nullable=False)
    entry_date       : Mapped[str]   = mapped_column(String, nullable=False)
    exit_date        : Mapped[str]   = mapped_column(String, nullable=True)
    ownership_pct    : Mapped[float] = mapped_column(Float, nullable=True)
    cost_basis_eur   : Mapped[float] = mapped_column(Float, nullable=False)
    committed_equity : Mapped[float] = mapped_column(Float, nullable=True)
    drawn_equity     : Mapped[float] = mapped_column(Float, nullable=True)


class InfraCashFlow(Base):
    """
    Infrastructure capital calls, distributions, management fees,
    interest received, and refinancing proceeds.
    Negative amounts: capital calls, management fees.
    Positive amounts: distributions, interest received, refinancing.
    """
    __tablename__ = 'infra_cash_flows'

    id          : Mapped[int]   = mapped_column(Integer, primary_key=True)
    fund_id     : Mapped[str]   = mapped_column(String, nullable=False)
    asset_id    : Mapped[str]   = mapped_column(String, nullable=True)
    cash_flow_date : Mapped[str]   = mapped_column(String, nullable=False)
    flow_type   : Mapped[str]   = mapped_column(String, nullable=False)
    amount_eur  : Mapped[float] = mapped_column(Float, nullable=False)
    currency    : Mapped[str]   = mapped_column(String, nullable=True)
    description : Mapped[str]   = mapped_column(String, nullable=True)


class InfraNavHistory(Base):
    """
    Quarterly NAV per fund per asset.
    Derived from InfraValuationReport. Never hardcoded directly.
    asset_id = None means fund-level aggregate.
    """
    __tablename__ = 'infra_nav_history'

    id       : Mapped[int]   = mapped_column(Integer, primary_key=True)
    fund_id  : Mapped[str]   = mapped_column(String, nullable=False)
    asset_id : Mapped[str]   = mapped_column(String, nullable=True)
    nav_date : Mapped[str]   = mapped_column(String, nullable=False)
    nav_eur  : Mapped[float] = mapped_column(Float, nullable=False)
    moic     : Mapped[float] = mapped_column(Float, nullable=True)


class InfraValuationReport(Base):
    """
    External appraiser inputs per asset per quarter.
    This is the governance boundary: the risk management layer consumes
    these reports from an independent appraiser; it does not produce them.
    Consistent with AIFMD Art. 19 and IPEV Valuation Guidelines.
    """
    __tablename__ = 'infra_valuation_report'
    __table_args__ = (
        sa.UniqueConstraint('fund_id', 'asset_id', 'valuation_date',
                            name='uq_infra_valuation'),
    )

    id                   : Mapped[int]   = mapped_column(Integer, primary_key=True)
    fund_id              : Mapped[str]   = mapped_column(String, nullable=False)
    asset_id             : Mapped[str]   = mapped_column(String, nullable=False)
    valuation_date       : Mapped[str]   = mapped_column(String, nullable=False)
    appraised_ev_eur     : Mapped[float] = mapped_column(Float, nullable=True)
    net_debt_eur         : Mapped[float] = mapped_column(Float, nullable=True)
    implied_equity_eur   : Mapped[float] = mapped_column(Float, nullable=False)
    ebitda_eur           : Mapped[float] = mapped_column(Float, nullable=True)
    revenue_eur          : Mapped[float] = mapped_column(Float, nullable=True)
    discount_rate        : Mapped[float] = mapped_column(Float, nullable=True)
    inflation_assumption : Mapped[float] = mapped_column(Float, nullable=True)
    terminal_value_eur   : Mapped[float] = mapped_column(Float, nullable=True)
    appraiser            : Mapped[str]   = mapped_column(String, nullable=True)
    valuation_basis      : Mapped[str]   = mapped_column(String, nullable=True)
    key_risks            : Mapped[str]   = mapped_column(String, nullable=True)


class InfraDebt(Base):
    """
    Project-level debt per asset.
    Infra debt is structured at asset (project finance) level, not fund level.
    DSCR and LTV covenants are defined here; quarterly readings in InfraCovenant.
    """
    __tablename__ = 'infra_debt'

    id                 : Mapped[int]   = mapped_column(Integer, primary_key=True)
    asset_id           : Mapped[str]   = mapped_column(String, nullable=False)
    tranche_name       : Mapped[str]   = mapped_column(String, nullable=False)
    lender             : Mapped[str]   = mapped_column(String, nullable=True)
    outstanding_eur    : Mapped[float] = mapped_column(Float, nullable=True)
    maturity           : Mapped[str]   = mapped_column(String, nullable=True)
    interest_rate_type : Mapped[str]   = mapped_column(String, nullable=True)
    margin_bps         : Mapped[float] = mapped_column(Float, nullable=True)
    amortisation_type  : Mapped[str]   = mapped_column(String, nullable=True)
    dscr_covenant      : Mapped[float] = mapped_column(Float, nullable=True)
    ltv_covenant       : Mapped[float] = mapped_column(Float, nullable=True)


class InfraCovenant(Base):
    """
    Quarterly covenant readings per asset.
    Breach flag is set when actual DSCR < covenant or actual LTV > covenant.
    Waiver flag indicates lender has granted a formal waiver.
    """
    __tablename__ = 'infra_covenants'
    __table_args__ = (
        sa.UniqueConstraint('asset_id', 'observation_date', name='uq_infra_covenant'),
    )

    id             : Mapped[int]   = mapped_column(Integer, primary_key=True)
    asset_id       : Mapped[str]   = mapped_column(String, nullable=False)
    fund_id        : Mapped[str]   = mapped_column(String, nullable=False)
    observation_date : Mapped[str]   = mapped_column(String, nullable=False)
    dscr_actual    : Mapped[float] = mapped_column(Float, nullable=True)
    dscr_covenant  : Mapped[float] = mapped_column(Float, nullable=True)
    dscr_headroom  : Mapped[float] = mapped_column(Float, nullable=True)
    ltv_actual     : Mapped[float] = mapped_column(Float, nullable=True)
    ltv_covenant   : Mapped[float] = mapped_column(Float, nullable=True)
    ltv_headroom   : Mapped[float] = mapped_column(Float, nullable=True)
    dscr_breach    : Mapped[bool]  = mapped_column(Boolean, nullable=True)
    ltv_breach     : Mapped[bool]  = mapped_column(Boolean, nullable=True)
    waiver_granted : Mapped[bool]  = mapped_column(Boolean, nullable=True)
    waiver_notes   : Mapped[str]   = mapped_column(String, nullable=True)


# ----------------------------------------------------------------
# Database functions
# ----------------------------------------------------------------

def get_engine(db_path: str = DB_PATH) -> sa.Engine:
    """Create SQLAlchemy engine for SQLite database."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return sa.create_engine(f'sqlite:///{db_path}', echo=False)


def create_db(db_path: str = DB_PATH) -> sa.Engine:
    """
    Create database and all tables.

    Parameters
    ----------
    db_path : str
        Path to SQLite database file.

    Returns
    -------
    sa.Engine
    """
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    rel_path = Path(db_path).relative_to(ROOT_DIR)
    print(f'Database created: {rel_path}')
    return engine


def load_fund_metadata(engine: sa.Engine) -> None:
    """Load ALL fund metadata from fund_profile.json files into funds table.

    Reads fund IDs from fund_registry.json, then for each fund_id loads
    reference_data/funds/<fund_id>/fund_profile.json and extracts metadata fields.

    Includes position-based funds, PE funds, and infrastructure funds.
    This is the single source of truth for fund-level metadata.
    """
    ref_dir = ROOT_DIR / 'reference_data' / 'funds'
    platform_dir = ROOT_DIR / 'reference_data' / 'platform'

    # Step 1: Load fund registry (list of fund IDs)
    with open(platform_dir / 'fund_registry.json') as f:
        registry = json.load(f)

    fund_ids = registry['funds']

    # Step 2: Load metadata from fund_profile.json for each fund
    with Session(engine) as session:
        for fund_id in fund_ids:
            profile_path = ref_dir / fund_id / 'fund_profile.json'

            # Load fund_profile.json
            with open(profile_path) as f:
                profile = json.load(f)

            # Extract metadata fields for funds table
            metadata = {
                'fund_id': fund_id,
                'fund_name': profile['fund_name'],
                'fund_type': profile['fund_type'],
                'currency': profile['currency'],
                'domicile': profile['domicile'],
                'regulator': profile['regulator'],
                'inception_date': profile['inception_date'],
                'target_nav_eur': profile['target_nav_eur'],
            }

            existing = session.get(Fund, fund_id)
            if existing is None:
                fund = Fund(**metadata)
                session.add(fund)

        session.commit()

    print(f'Loaded {len(fund_ids)} funds from fund_profile.json files into funds table.')


def load_positions(
    engine: sa.Engine,
    data_dir: str = DATA_DIR
) -> None:
    """
    Load all four fund position Excel files into positions table.
    Uses pandas to_sql for efficient bulk loading.

    Parameters
    ----------
    engine : sa.Engine
    data_dir : str
        Directory containing Excel files.
    """
    from fund_risk_workflow.data.paths import position_file
    from fund_risk_workflow.config import VALUATION_DATE

    all_positions = []

    for fund_id in FUND_FILES.keys():
        filepath = str(position_file(data_dir, fund_id, VALUATION_DATE))
        if not os.path.exists(filepath):
            print(f'Warning: {filepath} not found, skipping.')
            continue

        df = pd.read_excel(filepath)
        # Handle both old 'date' column name and new 'position_date' for backwards compatibility
        if 'date' in df.columns:
            df = df.rename(columns={'date': 'position_date'})
        df['position_date'] = df['position_date'].astype(str)

        # ensure RE columns exist for non-RE funds
        for col in ['ltv_pct', 'rental_yield_pct', 'vacancy_rate_pct',
                    'property_type', 'valuation_date', 'is_direct_property']:
            if col not in df.columns:
                df[col] = None

        all_positions.append(df)
        print(f'  loaded {len(df):,} rows for {fund_id}')

    if all_positions:
        combined = pd.concat(all_positions, ignore_index=True)

        # truncate without dropping table to preserve ORM indexes
        with engine.connect() as conn:
            conn.execute(text('DELETE FROM positions'))
            conn.commit()

        combined.to_sql(
            'positions', con=engine,
            if_exists='append', index=False
        )
        print(f'Total: {len(combined):,} rows loaded into positions table.')


def load_instruments(engine: sa.Engine) -> None:
    """
    Extract unique instruments from positions and load
    into instruments reference table.
    """
    with engine.connect() as conn:
        df = pd.read_sql(
            text('SELECT DISTINCT isin, bloomberg_ticker, '
                 'instrument_name, asset_class, sub_asset_class, '
                 'currency, country FROM positions'),
            conn
        )

    df.to_sql('instruments', con=engine,
              if_exists='replace', index=False)
    print(f'Loaded {len(df)} instruments into instruments table.')


# ----------------------------------------------------------------
# Query functions
# ----------------------------------------------------------------

def query_positions(
    engine: sa.Engine,
    fund_id: str,
    position_date: str | None = None
) -> pd.DataFrame:
    """
    Query positions for a specific fund, optionally filtered by position date.

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
        e.g. 'AIFM_HedgeFund'
    position_date : str, optional
        Filters positions.position_date column. e.g. '2026-03-31'. If None returns all dates.

    Returns
    -------
    pd.DataFrame

    Examples
    --------
    >>> engine = get_engine()
    >>> query_positions(engine, 'AIFM_HedgeFund', '2026-03-31')
    >>> query_positions(engine, 'UCITS_Balanced')  # all dates
    """
    if position_date:
        sql = text(
            'SELECT *, position_date as date FROM positions '
            'WHERE fund_id = :fund_id AND position_date = :position_date'
        )
        params = {'fund_id': fund_id, 'position_date': position_date}
    else:
        sql    = text(
            'SELECT *, position_date as date FROM positions WHERE fund_id = :fund_id'
        )
        params = {'fund_id': fund_id}

    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params=params)


def query_nav_history(
    engine: sa.Engine,
    fund_id: str
) -> pd.DataFrame:
    """
    Compute daily NAV from positions (sum of market values per date).

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str

    Returns
    -------
    pd.DataFrame with columns: date, nav_eur, pnl_eur, pnl_pct
    """
    sql = text(
        'SELECT position_date as date, SUM(market_value_eur) as nav_eur '
        'FROM positions '
        'WHERE fund_id = :fund_id '
        'GROUP BY position_date '
        'ORDER BY position_date'
    )
    with engine.connect() as conn:
        nav = pd.read_sql(sql, conn, params={'fund_id': fund_id})

    nav['date']    = pd.to_datetime(nav['date'])
    nav['pnl_eur'] = nav['nav_eur'].diff()
    nav['pnl_pct'] = nav['pnl_eur'] / nav['nav_eur'].shift(1)

    return nav


def query_asset_class_breakdown(
    engine: sa.Engine,
    fund_id: str,
    position_date: str
) -> pd.DataFrame:
    """
    Asset class breakdown for a fund on a specific position date.

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
    position_date : str
        Filters positions.position_date column. e.g. '2026-03-31'.

    Returns
    -------
    pd.DataFrame with columns: asset_class, market_value_eur, weight_pct
    """
    sql = text(
        'SELECT asset_class, '
        'SUM(market_value_eur) as market_value_eur, '
        'SUM(weight_pct) as weight_pct '
        'FROM positions '
        'WHERE fund_id = :fund_id AND position_date = :position_date '
        'GROUP BY asset_class '
        'ORDER BY market_value_eur DESC'
    )
    with engine.connect() as conn:
        return pd.read_sql(
            sql, conn,
            params={'fund_id': fund_id, 'position_date': position_date}
        )


def query_largest_positions(
    engine: sa.Engine,
    fund_id: str,
    position_date: str,
    n: int = 10
) -> pd.DataFrame:
    """
    Top N largest positions by absolute market value.

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
    position_date : str
        Filters positions.position_date column. e.g. '2026-03-31'.
    n : int
        Number of positions to return. Default 10.

    Returns
    -------
    pd.DataFrame
    """
    sql = text(
        'SELECT instrument_name, asset_class, currency, '
        'market_value_eur, weight_pct '
        'FROM positions '
        'WHERE fund_id = :fund_id AND position_date = :position_date '
        'ORDER BY ABS(market_value_eur) DESC '
        'LIMIT :n'
    )
    with engine.connect() as conn:
        return pd.read_sql(
            sql, conn,
            params={'fund_id': fund_id, 'position_date': position_date, 'n': n}
        )


def get_db_summary(engine: sa.Engine) -> None:
    """Print summary of database contents."""
    with engine.connect() as conn:

        funds = pd.read_sql(text('SELECT * FROM funds'), conn)
        print('\n--- Funds ---')
        print(funds[['fund_id', 'fund_type',
                      'currency', 'target_nav_eur']].to_string(index=False))

        print('\n--- Positions summary ---')
        summary = pd.read_sql(text(
            'SELECT fund_id, COUNT(*) as rows, '
            'COUNT(DISTINCT date) as dates, '
            'COUNT(DISTINCT isin) as instruments '
            'FROM positions GROUP BY fund_id'
        ), conn)
        print(summary.to_string(index=False))

        print('\n--- Instruments ---')
        instruments = pd.read_sql(
            text('SELECT COUNT(*) as total FROM instruments'), conn)
        print(f'Total unique instruments: '
              f'{instruments["total"].values[0]}')




# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------

if __name__ == '__main__':

    print('Creating database...')
    engine = create_db()

    print('\nLoading fund metadata...')
    load_fund_metadata(engine)

    print('\nLoading positions...')
    load_positions(engine)

    # recreate indexes after to_sql replace
    with engine.connect() as conn:
        conn.execute(sa.text(
            'CREATE INDEX IF NOT EXISTS ix_positions_fund_date_isin '
            'ON positions (fund_id, date, isin)'
        ))
        conn.execute(sa.text(
            'CREATE INDEX IF NOT EXISTS ix_positions_fund_date '
            'ON positions (fund_id, date)'
        ))
        conn.commit()
    print('Indexes created.')

    # print('\nCreating indexes...')
    # create_indexes(engine)

    print('\nLoading instruments...')
    load_instruments(engine)

    print('\nDatabase summary:')
    get_db_summary(engine)

    print('\n--- Example queries ---')

    print('\n1. Hedge fund positions on latest date:')
    df = query_positions(engine, 'AIFM_HedgeFund', '2026-03-31')
    print(df[['instrument_name', 'asset_class',
              'market_value_eur', 'weight_pct']].to_string(index=False))

    print('\n2. Asset class breakdown (UCITS, latest date):')
    breakdown = query_asset_class_breakdown(
        engine, 'UCITS_Balanced', '2026-03-31')
    print(breakdown.to_string(index=False))

    print('\n3. Top 5 positions (Private Debt, latest date):')
    top5 = query_largest_positions(
        engine, 'AIFM_PrivateDebt', '2026-03-31', n=5)
    print(top5.to_string(index=False))

    print('\n4. NAV history (Real Estate, last 5 days):')
    nav = query_nav_history(engine, 'AIFM_RealEstate')
    print(nav.tail().to_string(index=False))