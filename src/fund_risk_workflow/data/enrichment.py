"""
enrichment.py
=============
Enriches raw fund positions with risk sensitivities from two sources:

Source 1: Bloomberg (via MockBloomberg)
    For liquid instruments with a bloomberg_ticker:
    - bonds    : DUR_ADJ_MID, CONVEXITY, YLD_YTM_MID, RTG_SP
    - equities : BETA, VOLUME_AVG_20D, EQY_DVD_YLD_IND
    - FX       : PX_LAST
    - all      : NAME, CRNCY, ASSET_CLASS

Source 2: Fund administrator (already in positions table)
    For illiquid instruments where bloomberg_ticker is None:
    - direct properties : ltv_pct, rental_yield_pct, vacancy_rate_pct
    - private loans     : loan-level data already loaded from Excel

The raw positions table is never modified.
Enriched data is saved to positions_enriched table.

Usage
-----
    python3 enrichment.py

    # or import in notebooks:
    from enrichment import enrich_positions, query_enriched
"""
import pandas as pd
import numpy as np
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
from sqlalchemy import String, Float, Integer, Boolean
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg
from fund_risk_workflow.data.database import get_engine


# ----------------------------------------------------------------
# Bloomberg fields to pull per asset class
# ----------------------------------------------------------------
BBG_FIELDS_ALL = [
    'NAME', 'CRNCY', 'ASSET_CLASS',
]

BBG_FIELDS_BOND = [
    'DUR_ADJ_MID', 'CONVEXITY', 'YLD_YTM_MID',
    'RTG_SP', 'RTG_MOODY', 'Z_SPRD_MID',
]

BBG_FIELDS_EQUITY = [
    'BETA', 'VOLUME_AVG_20D', 'EQY_DVD_YLD_IND',
]

BBG_FIELDS_FX = [
    'PX_LAST',
]

ALL_BBG_FIELDS = (
    BBG_FIELDS_ALL +
    BBG_FIELDS_BOND +
    BBG_FIELDS_EQUITY +
    BBG_FIELDS_FX
)


# ----------------------------------------------------------------
# ORM model for positions_enriched
# ----------------------------------------------------------------

class Base(DeclarativeBase):
    pass


class PositionEnriched(Base):
    """
    Enriched positions table.
    Join key: (fund_id, position_date, isin) -> matches positions table.
    Only stores join key + enrichment columns.
    Raw position data stays in positions table.
    """
    __tablename__ = 'positions_enriched'
    __table_args__ = (
        # composite index matching positions table join key
        sa.Index('ix_enriched_fund_date_isin',
                 'fund_id', 'position_date', 'isin'),
    )

    id               : Mapped[int]   = mapped_column(
        Integer, primary_key=True, autoincrement=True)

    # join key
    fund_id          : Mapped[str]   = mapped_column(String)
    position_date    : Mapped[str]   = mapped_column(String)
    isin             : Mapped[str]   = mapped_column(String)

    # source flag
    enrichment_source: Mapped[str]   = mapped_column(
        String, nullable=True)
    # 'bloomberg': data from MockBloomberg
    # 'fund_admin': data already in positions (illiquid assets)
    # 'none': no enrichment available

    # Bloomberg enrichment fields
    bbg_name         : Mapped[str]   = mapped_column(String, nullable=True)
    bbg_crncy        : Mapped[str]   = mapped_column(String, nullable=True)
    bbg_asset_class  : Mapped[str]   = mapped_column(String, nullable=True)

    # bond sensitivities
    dur_adj_mid      : Mapped[float] = mapped_column(Float, nullable=True)
    convexity        : Mapped[float] = mapped_column(Float, nullable=True)
    ytm              : Mapped[float] = mapped_column(Float, nullable=True)
    rtg_sp           : Mapped[str]   = mapped_column(String, nullable=True)
    rtg_moody        : Mapped[str]   = mapped_column(String, nullable=True)
    z_sprd_mid       : Mapped[float] = mapped_column(Float, nullable=True)

    # equity sensitivities
    beta             : Mapped[float] = mapped_column(Float, nullable=True)
    volume_avg_20d   : Mapped[float] = mapped_column(Float, nullable=True)
    dividend_yield   : Mapped[float] = mapped_column(Float, nullable=True)

    # FX
    px_last          : Mapped[float] = mapped_column(Float, nullable=True)

    # fund admin sensitivities (illiquid assets only)
    ltv_pct          : Mapped[float] = mapped_column(Float, nullable=True)
    rental_yield_pct : Mapped[float] = mapped_column(Float, nullable=True)
    vacancy_rate_pct : Mapped[float] = mapped_column(Float, nullable=True)
    property_type    : Mapped[str]   = mapped_column(String, nullable=True)
    valuation_date   : Mapped[str]   = mapped_column(String, nullable=True)


# ----------------------------------------------------------------
# Enrichment functions
# ----------------------------------------------------------------

def get_latest_date(engine: sa.Engine, fund_id: str) -> str:
    """Get the latest date available in positions for a fund."""
    with engine.connect() as conn:
        result = pd.read_sql(
            text('SELECT MAX(position_date) as max_date FROM positions '
                 'WHERE fund_id = :fund_id'),
            conn, params={'fund_id': fund_id}
        )
    return result['max_date'].values[0]


def enrich_positions(
    engine: sa.Engine,
    fund_id: str,
    position_date: str | None = None,
    bbg: MockBloomberg | None = None
) -> pd.DataFrame:
    """
    Enrich positions for a fund on a given position date.
    Saves results to positions_enriched table.

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
        e.g. 'AIFM_HedgeFund'
    position_date : str, optional
        Filters positions.position_date column. e.g. '2026-03-31'. If None uses latest available date.
    bbg : MockBloomberg, optional
        Bloomberg client. Creates new instance if None.

    Returns
    -------
    pd.DataFrame
        Enriched positions ready for risk calculations.

    Examples
    --------
    >>> engine = get_engine()
    >>> df = enrich_positions(engine, 'AIFM_HedgeFund', '2026-03-31')
    """
    if bbg is None:
        bbg = MockBloomberg()

    if position_date is None:
        position_date = get_latest_date(engine, fund_id)

    # load raw positions for this fund and date
    with engine.connect() as conn:
        positions = pd.read_sql(
            text('SELECT * FROM positions '
                 'WHERE fund_id = :fund_id AND position_date = :position_date'),
            conn, params={'fund_id': fund_id, 'position_date': position_date}
        )

    if positions.empty:
        return pd.DataFrame()

    # ---- Source 1: Bloomberg enrichment ----
    # only for liquid instruments with a bloomberg_ticker
    # exclude currency/cash positions (ticker ends with 'Curncy')
    liquid_mask = (positions['bloomberg_ticker'].notna() &
                   ~positions['bloomberg_ticker'].str.endswith('Curncy', na=False))
    liquid      = positions[liquid_mask].copy()
    illiquid    = positions[~liquid_mask].copy()

    enriched_rows = []

    if not liquid.empty:
        tickers  = liquid['bloomberg_ticker'].unique().tolist()
        bbg_data = bbg.bdp(tickers, ALL_BBG_FIELDS).reset_index()
        bbg_data = bbg_data.rename(
            columns={'security': 'bloomberg_ticker'})

        liquid = liquid.merge(
            bbg_data, on='bloomberg_ticker', how='left')

        for _, row in liquid.iterrows():
            enriched_rows.append({
                'fund_id'          : row['fund_id'],
                'position_date'    : row['position_date'],
                'isin'             : row['isin'],
                'enrichment_source': 'bloomberg',
                'bbg_name'         : row.get('NAME'),
                'bbg_crncy'        : row.get('CRNCY'),
                'bbg_asset_class'  : row.get('ASSET_CLASS'),
                'dur_adj_mid'      : row.get('DUR_ADJ_MID'),
                'convexity'        : row.get('CONVEXITY'),
                'ytm'              : row.get('YLD_YTM_MID'),
                'rtg_sp'           : row.get('RTG_SP'),
                'rtg_moody'        : row.get('RTG_MOODY'),
                'z_sprd_mid'       : row.get('Z_SPRD_MID'),
                'beta'             : row.get('BETA'),
                'volume_avg_20d'   : row.get('VOLUME_AVG_20D'),
                'dividend_yield'   : row.get('EQY_DVD_YLD_IND'),
                'px_last'          : row.get('PX_LAST'),
                'ltv_pct'          : None,
                'rental_yield_pct' : None,
                'vacancy_rate_pct' : None,
                'property_type'    : None,
                'valuation_date'   : None,
            })

    # ---- Source 2: fund admin enrichment ----
    # illiquid instruments: sensitivities already in positions table
    for _, row in illiquid.iterrows():
        is_re = row.get('is_direct_property') == True

        enriched_rows.append({
            'fund_id'          : row['fund_id'],
            'position_date'    : row['position_date'],
            'isin'             : row['isin'],
            'enrichment_source': 'fund_admin' if is_re else 'none',
            'bbg_name'         : None,
            'bbg_crncy'        : None,
            'bbg_asset_class'  : None,
            'dur_adj_mid'      : None,
            'convexity'        : None,
            'ytm'              : None,
            'rtg_sp'           : None,
            'rtg_moody'        : None,
            'z_sprd_mid'       : None,
            'beta'             : None,
            'volume_avg_20d'   : None,
            'dividend_yield'   : None,
            'px_last'          : None,
            'ltv_pct'          : row.get('ltv_pct'),
            'rental_yield_pct' : row.get('rental_yield_pct'),
            'vacancy_rate_pct' : row.get('vacancy_rate_pct'),
            'property_type'    : row.get('property_type'),
            'valuation_date'   : row.get('valuation_date'),
        })

    enriched_df = pd.DataFrame(enriched_rows)

    # save to positions_enriched table
    _save_enriched(engine, enriched_df, fund_id, position_date)

    # return merged: raw positions + enrichment
    result = positions.merge(
        enriched_df[['isin', 'enrichment_source',
                     'dur_adj_mid', 'convexity', 'ytm',
                     'beta', 'volume_avg_20d', 'dividend_yield',
                     'rtg_sp', 'rtg_moody', 'z_sprd_mid',
                     'px_last']],
        on='isin', how='left'
    )

    return result


def enrich_all_funds(
    engine: sa.Engine,
    position_date: str | None = None,
    bbg: MockBloomberg | None = None
) -> dict:
    """
    Enrich positions for all four funds on a given position date.

    Parameters
    ----------
    engine : sa.Engine
    position_date : str, optional
        Filters positions.position_date column. If None uses latest available date per fund.
    bbg : MockBloomberg, optional

    Returns
    -------
    dict: {fund_id: enriched_df}
    """
    if bbg is None:
        bbg = MockBloomberg()

    fund_ids = [
        'AIFM_HedgeFund',
        'AIFM_PrivateDebt',
        'AIFM_RealEstate',
        'UCITS_Balanced',
    ]

    results = {}
    for fund_id in fund_ids:
        print(f'\n--- {fund_id} ---')
        results[fund_id] = enrich_positions(
            engine, fund_id, position_date, bbg)

    return results


def _save_enriched(
    engine: sa.Engine,
    enriched_df: pd.DataFrame,
    fund_id: str,
    position_date: str
) -> None:
    """
    Save enriched positions to positions_enriched table.
    Deletes existing rows for this fund/position_date before inserting.
    Raw positions table is never touched.
    """
    # create table if not exists
    Base.metadata.create_all(engine)

    # delete existing rows for this fund/position_date
    with engine.connect() as conn:
        conn.execute(
            text('DELETE FROM positions_enriched '
                 'WHERE fund_id = :fund_id AND position_date = :position_date'),
            {'fund_id': fund_id, 'position_date': position_date}
        )
        conn.commit()

    # insert new enriched rows
    enriched_df.to_sql(
        'positions_enriched', con=engine,
        if_exists='append', index=False
    )


# ----------------------------------------------------------------
# Query enriched positions
# ----------------------------------------------------------------

def query_enriched(
    engine: sa.Engine,
    fund_id: str,
    position_date: str
) -> pd.DataFrame:
    """
    Query enriched positions joining positions and
    positions_enriched tables.

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
    position_date : str
        Filters positions.position_date column. e.g. '2026-03-31'.

    Returns
    -------
    pd.DataFrame: full enriched position view

    Examples
    --------
    >>> engine = get_engine()
    >>> df = query_enriched(engine, 'AIFM_HedgeFund', '2026-03-31')
    """
    sql = text('''
        SELECT
            p.fund_id, p.position_date as date, p.isin,
            p.instrument_name, p.asset_class, p.bloomberg_ticker,
            p.currency, p.quantity, p.price,
            p.market_value_eur, p.weight_pct,
            p.adv_eur,
            -- Bloomberg sensitivities
            e.enrichment_source,
            e.dur_adj_mid, e.convexity, e.ytm,
            e.beta, e.volume_avg_20d, e.dividend_yield,
            e.rtg_sp, e.rtg_moody, e.z_sprd_mid,
            -- fund admin sensitivities
            e.ltv_pct, e.rental_yield_pct,
            e.vacancy_rate_pct, e.property_type,
            e.valuation_date
        FROM positions p
        LEFT JOIN positions_enriched e
            ON  p.fund_id = e.fund_id
            AND p.position_date = e.position_date
            AND p.isin    = e.isin
        WHERE p.fund_id = :fund_id
          AND p.position_date = :position_date
        ORDER BY ABS(p.market_value_eur) DESC
    ''')

    with engine.connect() as conn:
        return pd.read_sql(
            sql, conn,
            params={'fund_id': fund_id, 'position_date': position_date}
        )


def get_risk_ready_df(
    engine: sa.Engine,
    fund_id: str,
    position_date: str
) -> pd.DataFrame:
    """
    Returns a risk-ready DataFrame with all columns needed
    for stress testing, VaR, and liquidity calculations.

    Parameters
    ----------
    engine : sa.Engine
    fund_id : str
    position_date : str
        Filters positions.position_date column. e.g. '2026-03-31'.

    Returns
    -------
    pd.DataFrame with columns:
        position columns  : fund_id, date, isin, instrument_name,
                           asset_class, currency, quantity, price,
                           market_value_eur, weight_pct, adv_eur
        stress testing    : beta, dur_adj_mid, convexity, z_sprd_mid
        VaR               : market_value_eur, weight_pct
        liquidity         : adv_eur, is_direct_property
        real estate       : ltv_pct, rental_yield_pct,
                           vacancy_rate_pct, property_type
    """
    sql = text('''
        SELECT
            p.fund_id, p.position_date as date, p.isin,
            p.instrument_name, p.asset_class, p.sub_asset_class,
            p.currency, p.quantity, p.price,
            p.market_value_eur, p.weight_pct,
            p.adv_eur, p.is_direct_property, p.is_hedge,
            p.country, p.rating, p.maturity, p.sector,
            -- stress testing sensitivities
            e.beta,
            e.dur_adj_mid,
            e.convexity,
            e.z_sprd_mid,
            e.ytm,
            -- ratings
            e.rtg_sp, e.rtg_moody,
            -- real estate
            e.ltv_pct, e.rental_yield_pct,
            e.vacancy_rate_pct, e.property_type,
            e.valuation_date,
            -- enrichment source for audit trail
            e.enrichment_source
        FROM positions p
        LEFT JOIN positions_enriched e
            ON  p.fund_id = e.fund_id
            AND p.position_date = e.position_date
            AND p.isin    = e.isin
        WHERE p.fund_id = :fund_id
          AND p.position_date = :position_date
        ORDER BY ABS(p.market_value_eur) DESC
    ''')

    with engine.connect() as conn:
        return pd.read_sql(
            sql, conn,
            params={'fund_id': fund_id, 'position_date': position_date}
        )


# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------

if __name__ == '__main__':

    engine = get_engine()
    bbg    = MockBloomberg()

    print('Enriching all funds on latest date...')
    results = enrich_all_funds(engine, position_date='2026-03-31', bbg=bbg)

    print('\n--- Risk-ready DataFrame: AIFM Hedge Fund ---')
    df = get_risk_ready_df(engine, 'AIFM_HedgeFund', '2026-03-31')
    print(df[['instrument_name', 'asset_class',
              'market_value_eur', 'beta',
              'dur_adj_mid', 'enrichment_source']].to_string(
                  index=False))

    print('\n--- Risk-ready DataFrame: AIFM Real Estate ---')
    df_re = get_risk_ready_df(
        engine, 'AIFM_RealEstate', '2026-03-31')
    print(df_re[['instrument_name', 'asset_class',
                 'market_value_eur', 'ltv_pct',
                 'rental_yield_pct', 'enrichment_source']].to_string(
                     index=False))

    print('\n--- Enrichment source summary ---')
    for fund_id, df in results.items():
        sources = df['enrichment_source'].value_counts()
        print(f'\n{fund_id}:')
        print(sources.to_string())