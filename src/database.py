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

ROOT_DIR = Path(__file__).parent.parent  # src/ -> project root
DATA_DIR = str(ROOT_DIR / 'data')
DB_PATH  = str(ROOT_DIR / 'data' / 'risk_management.db')

FUND_FILES = {
    'AIFM_HedgeFund'  : 'fund_positions_AIFM_HedgeFund.xlsx',
    'AIFM_PrivateDebt': 'fund_positions_AIFM_PrivateDebt.xlsx',
    'AIFM_RealEstate' : 'fund_positions_AIFM_RealEstate.xlsx',
    'UCITS_Balanced'  : 'fund_positions_UCITS_Balanced.xlsx',
}

FUND_METADATA = {
    'AIFM_HedgeFund': {
        'fund_name'     : 'AIFM Hedge Fund',
        'fund_type'     : 'AIFM',
        'currency'      : 'EUR',
        'inception_date': '2018-01-15',
        'domicile'      : 'Luxembourg',
        'regulator'     : 'CSSF',
        'target_nav_eur': 250_000_000,
    },
    'AIFM_PrivateDebt': {
        'fund_name'     : 'AIFM Private Debt',
        'fund_type'     : 'AIFM',
        'currency'      : 'EUR',
        'inception_date': '2019-06-01',
        'domicile'      : 'Luxembourg',
        'regulator'     : 'CSSF',
        'target_nav_eur': 150_000_000,
    },
    'AIFM_RealEstate': {
        'fund_name'     : 'AIFM Real Estate',
        'fund_type'     : 'AIFM',
        'currency'      : 'EUR',
        'inception_date': '2017-03-01',
        'domicile'      : 'Luxembourg',
        'regulator'     : 'CSSF',
        'target_nav_eur': 200_000_000,
    },
    'UCITS_Balanced': {
        'fund_name'     : 'UCITS Balanced',
        'fund_type'     : 'UCITS',
        'currency'      : 'EUR',
        'inception_date': '2015-09-01',
        'domicile'      : 'Luxembourg',
        'regulator'     : 'CSSF',
        'target_nav_eur': 500_000_000,
    },
}


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
    Primary key: (fund_id, date, isin)
    """
    __tablename__ = 'positions'
    __table_args__ = (
        # composite index for joining positions to positions_enriched
        # and for looking up a specific instrument on a specific date
        sa.Index('ix_positions_fund_date_isin',
                 'fund_id', 'date', 'isin'),
        # composite index for the most common query:
        # all positions for a fund on a given date (daily snapshot)
        sa.Index('ix_positions_fund_date',
                 'fund_id', 'date'),
    )

    id                  : Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    fund_id             : Mapped[str]   = mapped_column(String, sa.ForeignKey('funds.fund_id'))
    fund_name           : Mapped[str]   = mapped_column(String)
    date                : Mapped[str]   = mapped_column(String)
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
    print(f'Database created: {db_path}')
    return engine


def load_fund_metadata(engine: sa.Engine) -> None:
    """Load fund metadata into funds table using ORM."""
    with Session(engine) as session:
        for fund_id, meta in FUND_METADATA.items():
            existing = session.get(Fund, fund_id)
            if existing is None:
                fund = Fund(fund_id=fund_id, **meta)
                session.add(fund)
        session.commit()
    print(f'Loaded {len(FUND_METADATA)} funds into funds table.')


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
    all_positions = []

    for fund_id, filename in FUND_FILES.items():
        filepath = os.path.join(data_dir, filename)
        if not os.path.exists(filepath):
            print(f'Warning: {filepath} not found, skipping.')
            continue

        df = pd.read_excel(filepath)
        df['date'] = df['date'].astype(str)

        # ensure RE columns exist for non-RE funds
        for col in ['ltv_pct', 'rental_yield_pct', 'vacancy_rate_pct',
                    'property_type', 'valuation_date', 'is_direct_property']:
            if col not in df.columns:
                df[col] = None

        all_positions.append(df)
        print(f'  loaded {len(df):,} rows from {filename}')

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
    date: str | None = None
) -> pd.DataFrame:
    """
    Query positions for a specific fund, optionally filtered by date.

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
        e.g. 'AIFM_HedgeFund'
    date : str, optional
        e.g. '2026-05-13'. If None returns all dates.

    Returns
    -------
    pd.DataFrame

    Examples
    --------
    >>> engine = get_engine()
    >>> query_positions(engine, 'AIFM_HedgeFund', '2026-05-13')
    >>> query_positions(engine, 'UCITS_Balanced')  # all dates
    """
    if date:
        sql = text(
            'SELECT * FROM positions '
            'WHERE fund_id = :fund_id AND date = :date'
        )
        params = {'fund_id': fund_id, 'date': date}
    else:
        sql    = text(
            'SELECT * FROM positions WHERE fund_id = :fund_id'
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
        'SELECT date, SUM(market_value_eur) as nav_eur '
        'FROM positions '
        'WHERE fund_id = :fund_id '
        'GROUP BY date '
        'ORDER BY date'
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
    date: str
) -> pd.DataFrame:
    """
    Asset class breakdown for a fund on a specific date.

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
    date : str

    Returns
    -------
    pd.DataFrame with columns: asset_class, market_value_eur, weight_pct
    """
    sql = text(
        'SELECT asset_class, '
        'SUM(market_value_eur) as market_value_eur, '
        'SUM(weight_pct) as weight_pct '
        'FROM positions '
        'WHERE fund_id = :fund_id AND date = :date '
        'GROUP BY asset_class '
        'ORDER BY market_value_eur DESC'
    )
    with engine.connect() as conn:
        return pd.read_sql(
            sql, conn,
            params={'fund_id': fund_id, 'date': date}
        )


def query_largest_positions(
    engine: sa.Engine,
    fund_id: str,
    date: str,
    n: int = 10
) -> pd.DataFrame:
    """
    Top N largest positions by absolute market value.

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
    date : str
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
        'WHERE fund_id = :fund_id AND date = :date '
        'ORDER BY ABS(market_value_eur) DESC '
        'LIMIT :n'
    )
    with engine.connect() as conn:
        return pd.read_sql(
            sql, conn,
            params={'fund_id': fund_id, 'date': date, 'n': n}
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

# def create_indexes(engine: sa.Engine) -> None:
#     """
#     Create indexes on positions table explicitly.
#     Required because to_sql replace drops ORM-defined indexes.
#     """
#     with engine.connect() as conn:
#         conn.execute(text(
#             'CREATE INDEX IF NOT EXISTS ix_positions_fund_date_isin '
#             'ON positions (fund_id, date, isin)'
#         ))
#         conn.execute(text(
#             'CREATE INDEX IF NOT EXISTS ix_positions_fund_date '
#             'ON positions (fund_id, date)'
#         ))
#         conn.commit()
#     print('Indexes created on positions table.')


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
    df = query_positions(engine, 'AIFM_HedgeFund', '2026-05-13')
    print(df[['instrument_name', 'asset_class',
              'market_value_eur', 'weight_pct']].to_string(index=False))

    print('\n2. Asset class breakdown (UCITS, latest date):')
    breakdown = query_asset_class_breakdown(
        engine, 'UCITS_Balanced', '2026-05-13')
    print(breakdown.to_string(index=False))

    print('\n3. Top 5 positions (Private Debt, latest date):')
    top5 = query_largest_positions(
        engine, 'AIFM_PrivateDebt', '2026-05-13', n=5)
    print(top5.to_string(index=False))

    print('\n4. NAV history (Real Estate, last 5 days):')
    nav = query_nav_history(engine, 'AIFM_RealEstate')
    print(nav.tail().to_string(index=False))