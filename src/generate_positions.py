"""
generate_positions.py
=====================
Generates realistic fund position Excel files for all four funds,
mimicking the daily export format of a fund administrator system
(SimCorp, Geneva, Advent).

Each file contains 250 trading days of daily position snapshots.
Filtering to a single date reproduces the daily fund admin export.

Usage
-----
    python3 generate_positions.py

Output
------
    data/fund_positions_AIFM_HedgeFund.xlsx
    data/fund_positions_AIFM_PrivateDebt.xlsx
    data/fund_positions_AIFM_RealEstate.xlsx
    data/fund_positions_UCITS_Balanced.xlsx
"""

import numpy as np
import pandas as pd
from datetime import date
import os
from pathlib import Path

# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------

ROOT_DIR   = Path(__file__).parent.parent
OUTPUT_DIR = str(ROOT_DIR / 'data')

TRADING_DAYS  = 2000
END_DATE      = pd.Timestamp('2026-05-13')
DATES         = pd.bdate_range(end=END_DATE, periods=TRADING_DAYS)
np.random.seed(42)

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ----------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------

def simulate_prices(
    start_price: float,
    n: int,
    vol: float = 0.01,
    seed: int = 0
) -> np.ndarray:
    """Simulate price path ending at start_price."""
    np.random.seed(seed)
    log_returns = np.random.normal(-vol**2 / 2, vol, n)
    log_prices  = np.log(start_price) - np.cumsum(log_returns[::-1])
    prices      = np.exp(log_prices)[::-1]
    prices      = prices * start_price / prices[-1]
    return prices


def make_positions_df(rows: list, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Expand a list of position definitions across all dates.
    Each row is a dict defining a single position (instrument).
    Prices evolve realistically over time.
    """
    all_rows = []

    for i, row in enumerate(rows):
        base_price = row['price']
        vol        = row.get('price_vol', 0.01)
        prices     = simulate_prices(base_price, len(dates),
                                     vol=vol, seed=i)
        quantities = row['quantity']

        asset_class = row.get('asset_class', 'Equity')

        for j, dt in enumerate(dates):
            price    = prices[j]

            # bonds, loans, CLOs: price is per 100 face value
            if asset_class in ('Bond', 'Loan', 'CLO'):
                mv_local = quantities * price / 100
            # options: price is per share, contract size = 100
            elif asset_class == 'Derivative':
                mv_local = quantities * price * 100
            else:
                mv_local = price * quantities

            mv_eur = mv_local * row.get('fx_rate', 1.0)

            position = {
                'fund_id'           : row['fund_id'],
                'fund_name'         : row['fund_name'],
                'date'              : dt.date(),
                'isin'              : row['isin'],
                'bloomberg_ticker'  : row.get('bloomberg_ticker'),
                'instrument_name'   : row['instrument_name'],
                'asset_class'       : row['asset_class'],
                'sub_asset_class'   : row.get('sub_asset_class', ''),
                'currency'          : row['currency'],
                'quantity'          : quantities,
                'price'             : round(price, 4),
                'market_value_local': round(mv_local, 2),
                'market_value_eur'  : round(mv_eur, 2),
                'weight_pct'        : 0.0,  # computed below
                'country'           : row.get('country', ''),
                'rating'            : row.get('rating', ''),
                'maturity'          : row.get('maturity', ''),
                'sector'            : row.get('sector', ''),
                'adv_eur'           : row.get('adv_eur', 0),
                'esg_score'         : row.get('esg_score'),
                'env_score'         : row.get('env_score'),
                'soc_score'         : row.get('soc_score'),
                'gov_score'         : row.get('gov_score'),
                'controversy_flag'  : row.get('controversy_flag'),
                'carbon_intensity'  : row.get('carbon_intensity'),
                'is_hedge'          : row.get('is_hedge', False),
            }

            # real estate extra columns
            for col in ['ltv_pct', 'rental_yield_pct',
                        'vacancy_rate_pct', 'property_type',
                        'valuation_date', 'is_direct_property']:
                if col in row:
                    position[col] = row[col]

            all_rows.append(position)

    df = pd.DataFrame(all_rows)

    # compute weight_pct per fund per date
    nav_by_date = (
        df.groupby(['fund_id', 'date'])['market_value_eur']
        .sum()
        .abs()
        .reset_index()
        .rename(columns={'market_value_eur': 'nav'})
    )

    df = df.merge(nav_by_date, on=['fund_id', 'date'], how='left')
    df['weight_pct'] = (df['market_value_eur'] / df['nav'] * 100).round(4)
    df = df.drop(columns=['nav'])

    return df


# ----------------------------------------------------------------
# Fund 1: AIFM Hedge Fund
# NAV: EUR 250m, long/short equity, bonds, FX, options
# ----------------------------------------------------------------

def generate_hedge_fund() -> pd.DataFrame:

    positions = [
        # --- Long equities ---
        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='US78462F1030', bloomberg_ticker='SPY US Equity',
             instrument_name='SPDR S&P 500 ETF',
             asset_class='Equity', sub_asset_class='ETF',
             currency='USD', quantity=50000, price=523.42,
             price_vol=0.012, fx_rate=0.89, country='US',
             sector='Diversified', adv_eur=75e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='US0378331005', bloomberg_ticker='AAPL US Equity',
             instrument_name='Apple Inc',
             asset_class='Equity', sub_asset_class='Large Cap',
             currency='USD', quantity=80000, price=211.45,
             price_vol=0.015, fx_rate=0.89, country='US',
             sector='Technology', adv_eur=45e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='US5949181045', bloomberg_ticker='MSFT US Equity',
             instrument_name='Microsoft Corp',
             asset_class='Equity', sub_asset_class='Large Cap',
             currency='USD', quantity=60000, price=415.32,
             price_vol=0.013, fx_rate=0.89, country='US',
             sector='Technology', adv_eur=18e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='US46625H1005', bloomberg_ticker='JPM US Equity',
             instrument_name='JPMorgan Chase',
             asset_class='Equity', sub_asset_class='Large Cap',
             currency='USD', quantity=40000, price=248.73,
             price_vol=0.014, fx_rate=0.89, country='US',
             sector='Financials', adv_eur=7e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='EU0009658145', bloomberg_ticker='SX5E Index',
             instrument_name='Euro Stoxx 50 Future',
             asset_class='Equity', sub_asset_class='Future',
             currency='EUR', quantity=200, price=5124.87,
             price_vol=0.013, fx_rate=1.0, country='EU',
             sector='Diversified', adv_eur=500e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- Short equities: index hedge ---
        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='FUT_SPY_SHORT_001', bloomberg_ticker='SPY US Equity',
             instrument_name='S&P 500 Future (Short Hedge)',
             asset_class='Equity', sub_asset_class='Future',
             currency='USD', quantity=-30000, price=523.42,
             price_vol=0.012, fx_rate=0.89, country='US',
             sector='Diversified', adv_eur=75e6, is_hedge=True,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='FUT_SX5E_SHORT_001', bloomberg_ticker='SX5E Index',
             instrument_name='Euro Stoxx 50 Future (Short Hedge)',
             asset_class='Equity', sub_asset_class='Future',
             currency='EUR', quantity=-100, price=5124.87,
             price_vol=0.013, fx_rate=1.0, country='EU',
             sector='Diversified', adv_eur=500e6, is_hedge=True,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- Short equities: speculative ---
        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='US88160R1014', bloomberg_ticker='TSLA US Equity',
             instrument_name='Tesla Inc (Short)',
             asset_class='Equity', sub_asset_class='Large Cap',
             currency='USD', quantity=-15000, price=175.34,
             price_vol=0.025, fx_rate=0.89, country='US',
             sector='Consumer Discretionary', adv_eur=30e6, is_hedge=False,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='US67066G1040', bloomberg_ticker='NVDA US Equity',
             instrument_name='Nvidia Corp (Short)',
             asset_class='Equity', sub_asset_class='Large Cap',
             currency='USD', quantity=-10000, price=892.54,
             price_vol=0.022, fx_rate=0.89, country='US',
             sector='Technology', adv_eur=40e6, is_hedge=False,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- Government bonds ---
        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='US912828YK09', bloomberg_ticker='US912828YK09 Govt',
             instrument_name='T 2.875 05/15/28',
             asset_class='Bond', sub_asset_class='Government',
             currency='USD', quantity=5000000, price=96.42,
             price_vol=0.003, fx_rate=0.89, country='US',
             rating='AA+', maturity='2028-05-15', adv_eur=750e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='DE0001102481', bloomberg_ticker='DBR 0 08/15/29 Govt',
             instrument_name='DBR 0 08/15/29',
             asset_class='Bond', sub_asset_class='Government',
             currency='EUR', quantity=3000000, price=90.87,
             price_vol=0.002, fx_rate=1.0, country='DE',
             rating='AAA', maturity='2029-08-15', adv_eur=280e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- IG Corporate bond ---
        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='XS2543791470', bloomberg_ticker='XS2543791470 Corp',
             instrument_name='LVMH 3.5 06/15/31',
             asset_class='Bond', sub_asset_class='IG Corporate',
             currency='EUR', quantity=2000000, price=98.32,
             price_vol=0.004, fx_rate=1.0, country='FR',
             rating='A+', maturity='2031-06-15', adv_eur=16e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- FX Forwards ---
        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='FWD_EURUSD_001', bloomberg_ticker='EURUSD Curncy',
             instrument_name='EUR/USD Forward 3M',
             asset_class='FX', sub_asset_class='Forward',
             currency='USD', quantity=10000000, price=1.1234,
             price_vol=0.006, fx_rate=0.89, country='', adv_eur=0,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='FWD_GBPUSD_001', bloomberg_ticker='GBPUSD Curncy',
             instrument_name='GBP/USD Forward 3M',
             asset_class='FX', sub_asset_class='Forward',
             currency='USD', quantity=5000000, price=1.3312,
             price_vol=0.007, fx_rate=0.89, country='', adv_eur=0,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- Listed options ---
        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='OPT_SPX_PUT_001', bloomberg_ticker='SPXW 260619P05500 Index',
             instrument_name='SPX Put 5500 Jun26',
             asset_class='Derivative', sub_asset_class='Listed Option',
             currency='USD', quantity=-100, price=45.20,
             price_vol=0.035, fx_rate=0.89, country='US',
             sector='', adv_eur=0,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- Cash ---
        dict(fund_id='AIFM_HedgeFund', fund_name='AIFM Hedge Fund',
             isin='CASH_EUR_001', bloomberg_ticker=None,
             instrument_name='Cash EUR',
             asset_class='Cash', sub_asset_class='Cash',
             currency='EUR', quantity=10000000, price=1.0,
             price_vol=0.0, fx_rate=1.0, country='LU', adv_eur=0,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),
    ]

    return make_positions_df(positions, DATES)


# ----------------------------------------------------------------
# Fund 2: AIFM Private Debt
# NAV: EUR 150m, senior loans, HY bonds, CLOs, cash
# ----------------------------------------------------------------

def generate_private_debt() -> pd.DataFrame:

    positions = [
        # --- Senior secured loans ---
        dict(fund_id='AIFM_PrivateDebt', fund_name='AIFM Private Debt',
             isin='XS9876543210', bloomberg_ticker=None,
             instrument_name='Acuris Finance 6.5 2028',
             asset_class='Loan', sub_asset_class='Senior Secured',
             currency='EUR', quantity=5000000, price=97.50,
             price_vol=0.002, fx_rate=1.0, country='GB',
             rating='B', maturity='2028-12-15', adv_eur=0,
             esg_score=38, env_score=35, soc_score=40, gov_score=39,
             carbon_intensity=45.2, controversy_flag=False,),

        dict(fund_id='AIFM_PrivateDebt', fund_name='AIFM Private Debt',
             isin='XS9876543211', bloomberg_ticker=None,
             instrument_name='Techem 7.0 2029',
             asset_class='Loan', sub_asset_class='Senior Secured',
             currency='EUR', quantity=4000000, price=98.25,
             price_vol=0.002, fx_rate=1.0, country='DE',
             rating='B+', maturity='2029-06-30', adv_eur=0,
             esg_score=45, env_score=42, soc_score=47, gov_score=46,
             carbon_intensity=98.3, controversy_flag=False,),

        dict(fund_id='AIFM_PrivateDebt', fund_name='AIFM Private Debt',
             isin='XS9876543212', bloomberg_ticker=None,
             instrument_name='Ineos 6.75 2028',
             asset_class='Loan', sub_asset_class='Senior Secured',
             currency='USD', quantity=5000000, price=96.75,
             price_vol=0.003, fx_rate=0.89, country='GB',
             rating='B', maturity='2028-09-15', adv_eur=0,
             esg_score=32, env_score=28, soc_score=35, gov_score=33,
             carbon_intensity=892.5, controversy_flag=True),

        # --- HY Bonds EUR ---
        dict(fund_id='AIFM_PrivateDebt', fund_name='AIFM Private Debt',
             isin='XS2341234567', bloomberg_ticker='XS2341234567 Corp',
             instrument_name='Telecom Italia 5.25 2029',
             asset_class='Bond', sub_asset_class='HY Corporate',
             currency='EUR', quantity=3000000, price=94.15,
             price_vol=0.006, fx_rate=1.0, country='IT',
             rating='B+', maturity='2029-03-15', adv_eur=7e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='AIFM_PrivateDebt', fund_name='AIFM Private Debt',
             isin='XS2341234568', bloomberg_ticker=None,
             instrument_name='Loxam 5.75 2027',
             asset_class='Bond', sub_asset_class='HY Corporate',
             currency='EUR', quantity=2500000, price=96.50,
             price_vol=0.007, fx_rate=1.0, country='FR',
             rating='B', maturity='2027-07-15', adv_eur=3e6,
             esg_score=41, env_score=38, soc_score=43, gov_score=42,
             carbon_intensity=245.6, controversy_flag=False),

        # --- HY Bonds USD ---
        dict(fund_id='AIFM_PrivateDebt', fund_name='AIFM Private Debt',
             isin='US345370AK28', bloomberg_ticker=None,
             instrument_name='Ford Motor 6.1 2032',
             asset_class='Bond', sub_asset_class='HY Corporate',
             currency='USD', quantity=3000000, price=98.75,
             price_vol=0.006, fx_rate=0.89, country='US',
             rating='BB-', maturity='2032-08-19', adv_eur=5e6,
             esg_score=48, env_score=44, soc_score=51, gov_score=49,
             controversy_flag=True, carbon_intensity=285.4,
          ),

        # --- CLO Tranches ---
        dict(fund_id='AIFM_PrivateDebt', fund_name='AIFM Private Debt',
             isin='XS1122334455', bloomberg_ticker=None,
             instrument_name='Cairn CLO AAA 2024-1',
             asset_class='CLO', sub_asset_class='CLO AAA',
             currency='EUR', quantity=5000000, price=99.10,
             price_vol=0.001, fx_rate=1.0, country='IE',
             rating='AAA', maturity='2037-04-15', adv_eur=0,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=False, carbon_intensity=None),

        dict(fund_id='AIFM_PrivateDebt', fund_name='AIFM Private Debt',
             isin='XS1122334456', bloomberg_ticker=None,
             instrument_name='Blackstone CLO AA 2023-2',
             asset_class='CLO', sub_asset_class='CLO AA',
             currency='EUR', quantity=3000000, price=97.50,
             price_vol=0.002, fx_rate=1.0, country='IE',
             rating='AA', maturity='2036-10-15', adv_eur=0,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=False, carbon_intensity=None),

        dict(fund_id='AIFM_PrivateDebt', fund_name='AIFM Private Debt',
             isin='XS1122334457', bloomberg_ticker=None,
             instrument_name='Apollo CLO A 2024-1',
             asset_class='CLO', sub_asset_class='CLO A',
             currency='EUR', quantity=2000000, price=95.25,
             price_vol=0.003, fx_rate=1.0, country='IE',
             rating='A', maturity='2037-01-15', adv_eur=0,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=False, carbon_intensity=None),

        # --- Cash and Money Market ---
        dict(fund_id='AIFM_PrivateDebt', fund_name='AIFM Private Debt',
             isin='CASH_EUR_002', bloomberg_ticker=None,
             instrument_name='Cash EUR',
             asset_class='Cash', sub_asset_class='Cash',
             currency='EUR', quantity=8000000, price=1.0,
             price_vol=0.0, fx_rate=1.0, country='LU',
             adv_eur=0,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='AIFM_PrivateDebt', fund_name='AIFM Private Debt',
             isin='MMF_EUR_001', bloomberg_ticker=None,
             instrument_name='BlackRock ICS EUR Liquidity',
             asset_class='Cash', sub_asset_class='Money Market',
             currency='EUR', quantity=10000000, price=1.0,
             price_vol=0.0, fx_rate=1.0, country='IE',
             rating='AAA', adv_eur=0,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),
    ]

    return make_positions_df(positions, DATES)


def generate_real_estate() -> pd.DataFrame:

    positions = [
        # --- Direct Properties ---
        dict(fund_id='AIFM_RealEstate', fund_name='AIFM Real Estate',
             isin='PROP_LU_001', bloomberg_ticker=None,
             instrument_name='Office Tower Luxembourg City',
             asset_class='Real Estate', sub_asset_class='Direct Property',
             currency='EUR', quantity=1, price=45000000,
             price_vol=0.0, fx_rate=1.0, country='LU',
             adv_eur=0,
             ltv_pct=42.5, rental_yield_pct=4.2,
             vacancy_rate_pct=8.5, property_type='Office',
             valuation_date='2026-03-31', is_direct_property=True,
             esg_score=72, env_score=78, soc_score=70, gov_score=68,
             controversy_flag=False, carbon_intensity=85.2),

        dict(fund_id='AIFM_RealEstate', fund_name='AIFM Real Estate',
             isin='PROP_DE_001', bloomberg_ticker=None,
             instrument_name='Logistics Park Frankfurt',
             asset_class='Real Estate', sub_asset_class='Direct Property',
             currency='EUR', quantity=1, price=32000000,
             price_vol=0.0, fx_rate=1.0, country='DE',
             adv_eur=0,
             ltv_pct=38.2, rental_yield_pct=5.1,
             vacancy_rate_pct=2.0, property_type='Logistics',
             valuation_date='2026-03-31', is_direct_property=True,
             esg_score=65, env_score=70, soc_score=63, gov_score=62,
             controversy_flag=False, carbon_intensity=125.8),

        dict(fund_id='AIFM_RealEstate', fund_name='AIFM Real Estate',
             isin='PROP_FR_001', bloomberg_ticker=None,
             instrument_name='Retail Centre Paris',
             asset_class='Real Estate', sub_asset_class='Direct Property',
             currency='EUR', quantity=1, price=28000000,
             price_vol=0.0, fx_rate=1.0, country='FR',
             adv_eur=0,
             ltv_pct=55.0, rental_yield_pct=3.8,
             vacancy_rate_pct=15.0, property_type='Retail',
             valuation_date='2026-03-31', is_direct_property=True,
             esg_score=51, env_score=48, soc_score=53, gov_score=52,
             controversy_flag=False, carbon_intensity=118.3),

        dict(fund_id='AIFM_RealEstate', fund_name='AIFM Real Estate',
             isin='PROP_NL_001', bloomberg_ticker=None,
             instrument_name='Residential Complex Amsterdam',
             asset_class='Real Estate', sub_asset_class='Direct Property',
             currency='EUR', quantity=1, price=22000000,
             price_vol=0.0, fx_rate=1.0, country='NL',
             adv_eur=0,
             ltv_pct=48.0, rental_yield_pct=3.2,
             vacancy_rate_pct=3.5, property_type='Residential',
             valuation_date='2026-03-31', is_direct_property=True,
             esg_score=68, env_score=74, soc_score=66, gov_score=64,
             controversy_flag=False, carbon_intensity=38.1),

        # --- Listed REITs ---
        dict(fund_id='AIFM_RealEstate', fund_name='AIFM Real Estate',
             isin='DE000A1ML7J1', bloomberg_ticker='VNA GY Equity',
             instrument_name='Vonovia SE',
             asset_class='Real Estate', sub_asset_class='Listed REIT',
             currency='EUR', quantity=500000, price=28.45,
             price_vol=0.018, fx_rate=1.0, country='DE',
             adv_eur=3.5e6, is_direct_property=False,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='AIFM_RealEstate', fund_name='AIFM Real Estate',
             isin='FR0013326246', bloomberg_ticker='URI FP Equity',
             instrument_name='Unibail-Rodamco-Westfield',
             asset_class='Real Estate', sub_asset_class='Listed REIT',
             currency='EUR', quantity=120000, price=68.32,
             price_vol=0.020, fx_rate=1.0, country='FR',
             adv_eur=1.2e6, is_direct_property=False,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- FX Forward ---
        dict(fund_id='AIFM_RealEstate', fund_name='AIFM Real Estate',
             isin='FWD_USDEUR_001', bloomberg_ticker='USDEUR Curncy',
             instrument_name='USD/EUR Forward 6M',
             asset_class='FX', sub_asset_class='Forward',
             currency='EUR', quantity=5000000, price=0.8902,
             price_vol=0.006, fx_rate=1.0, country='',
             adv_eur=0, is_direct_property=False,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- Cash ---
        dict(fund_id='AIFM_RealEstate', fund_name='AIFM Real Estate',
             isin='CASH_EUR_003', bloomberg_ticker=None,
             instrument_name='Cash EUR',
             asset_class='Cash', sub_asset_class='Cash',
             currency='EUR', quantity=15000000, price=1.0,
             price_vol=0.0, fx_rate=1.0, country='LU',
             adv_eur=0, is_direct_property=False,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),
    ]

    return make_positions_df(positions, DATES)


# ----------------------------------------------------------------
# Fund 4: UCITS Balanced
# NAV: EUR 500m, equity ETFs, IG bonds, government bonds, gold
# ----------------------------------------------------------------

def generate_ucits_balanced() -> pd.DataFrame:

    positions = [
        # --- Equity ETFs ---
        dict(fund_id='UCITS_Balanced', fund_name='UCITS Balanced',
             isin='US78462F1030', bloomberg_ticker='SPY US Equity',
             instrument_name='SPDR S&P 500 ETF',
             asset_class='Equity', sub_asset_class='ETF',
             currency='USD', quantity=375000, price=523.42,
             price_vol=0.012, fx_rate=0.89, country='US',
             sector='Diversified', adv_eur=75e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='UCITS_Balanced', fund_name='UCITS Balanced',
             isin='EU0009658145', bloomberg_ticker='SX5E Index',
             instrument_name='Euro Stoxx 50 ETF',
             asset_class='Equity', sub_asset_class='ETF',
             currency='EUR', quantity=24400, price=5124.87,
             price_vol=0.013, fx_rate=1.0, country='EU',
             sector='Diversified', adv_eur=200e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- Gold ETF ---
        dict(fund_id='UCITS_Balanced', fund_name='UCITS Balanced',
             isin='US78463V1070', bloomberg_ticker='GLD US Equity',
             instrument_name='SPDR Gold Shares',
             asset_class='Commodity', sub_asset_class='ETF',
             currency='USD', quantity=97700, price=287.34,
             price_vol=0.009, fx_rate=0.89, country='US',
             sector='Commodities', adv_eur=10e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- Government Bonds ---
        dict(fund_id='UCITS_Balanced', fund_name='UCITS Balanced',
             isin='US912828YK09', bloomberg_ticker='US912828YK09 Govt',
             instrument_name='T 2.875 05/15/28',
             asset_class='Bond', sub_asset_class='Government',
             currency='USD', quantity=873000, price=96.42,
             price_vol=0.003, fx_rate=0.89, country='US',
             rating='AA+', maturity='2028-05-15', adv_eur=750e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='UCITS_Balanced', fund_name='UCITS Balanced',
             isin='DE0001102481', bloomberg_ticker='DBR 0 08/15/29 Govt',
             instrument_name='DBR 0 08/15/29',
             asset_class='Bond', sub_asset_class='Government',
             currency='EUR', quantity=45000000, price=90.87,
             price_vol=0.002, fx_rate=1.0, country='DE',
             rating='AAA', maturity='2029-08-15', adv_eur=280e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- IG Corporate Bonds ---
        dict(fund_id='UCITS_Balanced', fund_name='UCITS Balanced',
             isin='XS2543791470', bloomberg_ticker='XS2543791470 Corp',
             instrument_name='LVMH 3.5 06/15/31',
             asset_class='Bond', sub_asset_class='IG Corporate',
             currency='EUR', quantity=15255000, price=98.32,
             price_vol=0.004, fx_rate=1.0, country='FR',
             rating='A+', maturity='2031-06-15', adv_eur=16e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        dict(fund_id='UCITS_Balanced', fund_name='UCITS Balanced',
             isin='XS2543791471', bloomberg_ticker=None,
             instrument_name='Nestle 2.75 04/15/30',
             asset_class='Bond', sub_asset_class='IG Corporate',
             currency='CHF', quantity=5000000, price=97.15,
             price_vol=0.003, fx_rate=0.98, country='CH',
             rating='AA-', maturity='2030-04-15', adv_eur=12e6,
             esg_score=76, env_score=78, soc_score=75, gov_score=75,
             controversy_flag=False, carbon_intensity=32.1),

        # --- Treasury ETF ---
        dict(fund_id='UCITS_Balanced', fund_name='UCITS Balanced',
             isin='US4642874329', bloomberg_ticker='TLT US Equity',
             instrument_name='iShares 20+ Year Treasury ETF',
             asset_class='Bond', sub_asset_class='ETF',
             currency='USD', quantity=333000, price=84.23,
             price_vol=0.008, fx_rate=0.89, country='US',
             rating='AA+', adv_eur=33e6,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),

        # --- Cash ---
        dict(fund_id='UCITS_Balanced', fund_name='UCITS Balanced',
             isin='CASH_EUR_004', bloomberg_ticker=None,
             instrument_name='Cash EUR',
             asset_class='Cash', sub_asset_class='Cash',
             currency='EUR', quantity=25000000, price=1.0,
             price_vol=0.0, fx_rate=1.0, country='LU', adv_eur=0,
             esg_score=None, env_score=None, soc_score=None, gov_score=None,
             controversy_flag=None, carbon_intensity=None),
    ]

    return make_positions_df(positions, DATES)

# ----------------------------------------------------------------
# Main: generate all four files
# ----------------------------------------------------------------

if __name__ == '__main__':

    funds = {
        'AIFM_HedgeFund' : generate_hedge_fund,
        'AIFM_PrivateDebt': generate_private_debt,
        'AIFM_RealEstate' : generate_real_estate,
        'UCITS_Balanced'  : generate_ucits_balanced,
    }

    for fund_name, generator in funds.items():
        print(f'Generating {fund_name}...')
        df       = generator()
        filename = f'{OUTPUT_DIR}/fund_positions_{fund_name}.xlsx'
        df.to_excel(filename, index=False)

        # summary
        latest = df[df['date'] == df['date'].max()]
        nav    = latest['market_value_eur'].sum()
        print(f'  positions : {len(latest)}')
        print(f'  NAV (EUR) : {nav:,.0f}')
        print(f'  date range: {df["date"].min()} to {df["date"].max()}')
        print(f'  saved to  : {filename}')
        print()

    print('All four fund position files generated successfully.')