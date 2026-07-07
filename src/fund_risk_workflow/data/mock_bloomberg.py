"""
mock_bloomberg.py
=================
Simulates the Bloomberg API (blpapi) for development and testing.
Interface mirrors blpapi so switching to real Bloomberg requires
only changing the import:

    # development
    from mock_bloomberg import MockBloomberg as Bloomberg

    # production
    from real_bloomberg import RealBloomberg as Bloomberg

Supported methods:
    bdp: Bloomberg Data Point (static reference data)
    bdh: Bloomberg Data History (time series)
    bds: Bloomberg Data Set (bulk data)

Instrument coverage:
    Equities : SPY, AAPL, MSFT, JPM, GLD, TLT, HYG, TSLA, NVDA
    Bonds    : US Treasury, German Bund, IG corporate, HY corporate
    FX       : EURUSD, GBPUSD, USDJPY
    Indices  : SPX, SX5E, VIX

MRS-47: bdh returns real cached prices for instruments in YF_MAP.
        bdp returns real cached PX_LAST, BETA, EQY_DVD_YLD_IND,
        VOLUME_AVG_20D for instruments in YF_MAP.
        Rate series fetched from ECB API and yfinance.
        Cache lives in data/yf_cache/. Populated on first call,
        reused on all subsequent calls. Delete cache file to refresh.
"""

import json
import numpy as np
import pandas as pd
import requests
from pathlib import Path

_REF_DIR = Path(__file__).parent.parent.parent.parent / 'reference_data'


class MockBloomberg:
    """
    Simulates Bloomberg API with realistic financial data.

    Parameters
    ----------
    seed : int
        Random seed for reproducibility. Default 42.
    """

    # ----------------------------------------------------------------
    # MRS-47: yfinance ticker map for liquid instruments
    # PX_LAST, BETA, EQY_DVD_YLD_IND, VOLUME_AVG_20D are set to None
    # for these instruments and populated at runtime from yf cache.
    # If yfinance fails, bdp returns None for those fields.
    # To override manually, replace None with a hardcoded value.
    # ----------------------------------------------------------------

    YF_MAP = json.loads((_REF_DIR / 'instruments' / 'ticker_map.json').read_text())

    # Betas fixed by definition — never overridden by yfinance
    # necessary becase as of today, yfinance has beta=0 for these
    BETA_OVERRIDE = {
        'SPY US Equity' : 1.0,
        'SX5E Index'    : 1.0,
    }

    # MRS-47: ECB rate series — key: cache name, value: series id
    ECB_SERIES = {
        'ESTR'    : 'EST/B.EU000A2X2A25.WT',
        'EUR_2Y'  : 'YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y',
        'EUR_5Y'  : 'YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_5Y',
        'EUR_10Y' : 'YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y',
    }

    # MRS-47: yfinance rate tickers
    YF_RATES = {
        'USD_2Y'  : '^FVX',
        'USD_5Y'  : '^FVX',  # Note: ^FVX is 5Y, using as proxy for 2Y if 2Y unavailable
        'USD_10Y' : '^TNX',
        'USD_3M'  : '^IRX',
    }

    YF_CACHE_DIR = Path(__file__).parent.parent.parent.parent / 'data' / 'yf_cache'

    # ----------------------------------------------------------------
    # Static reference data
    # For instruments in YF_MAP: PX_LAST, BETA, EQY_DVD_YLD_IND,
    # VOLUME_AVG_20D are None — populated at runtime from yf cache.
    # All other fields (duration, ratings, ESG, spreads) are hardcoded.
    # ----------------------------------------------------------------
    _reference_data = {

    # ---- Section 1: Securities Not populated by yfinance

    # ---- US Treasuries ----
    'US912828YK09 Govt': {
        'NAME'            : 'T 2.875 05/15/28',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Bond',
        'CPN'             : 2.875,
        'MATURITY'        : '2028-05-15',
        'YLD_YTM_MID'     : 4.42,
        'DUR_ADJ_MID'     : 2.31,
        'CONVEXITY'       : 0.065,
        'PX_LAST'         : 96.42,
        'AMT_OUTSTANDING' : 45e9,
        'VOLUME_AVG_20D'  : 850e6,
        'RTG_MOODY'       : 'Aaa',
        'RTG_SP'          : 'AA+',
        'ESG_SCORE'       : 72, 'ENV_SCORE': 68, 'SOC_SCORE': 74, 'GOV_SCORE': 74,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': None, 'ESG_LOOK_THROUGH': None,
    },
    'US912810TM79 Govt': {
        'NAME'            : 'T 4.25 02/15/54',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Bond',
        'CPN'             : 4.25,
        'MATURITY'        : '2054-02-15',
        'YLD_YTM_MID'     : 4.78,
        'DUR_ADJ_MID'     : 17.82,
        'CONVEXITY'       : 3.94,
        'PX_LAST'         : 91.15,
        'AMT_OUTSTANDING' : 35e9,
        'VOLUME_AVG_20D'  : 420e6,
        'RTG_MOODY'       : 'Aaa',
        'RTG_SP'          : 'AA+',
        'ESG_SCORE'       : 72, 'ENV_SCORE': 68, 'SOC_SCORE': 74, 'GOV_SCORE': 74,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': None, 'ESG_LOOK_THROUGH': None,
    },

    # ---- European Government Bond ----
    'DBR 0 08/15/29 Govt': {
        'NAME'            : 'DBR 0 08/15/29',
        'CRNCY'           : 'EUR',
        'ASSET_CLASS'     : 'Bond',
        'CPN'             : 0.0,
        'MATURITY'        : '2029-08-15',
        'YLD_YTM_MID'     : 2.31,
        'DUR_ADJ_MID'     : 3.98,
        'CONVEXITY'       : 0.182,
        'PX_LAST'         : 90.87,
        'AMT_OUTSTANDING' : 28e9,
        'VOLUME_AVG_20D'  : 310e6,
        'RTG_MOODY'       : 'Aaa',
        'RTG_SP'          : 'AAA',
        'ESG_SCORE'       : 82, 'ENV_SCORE': 85, 'SOC_SCORE': 81, 'GOV_SCORE': 80,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': None, 'ESG_LOOK_THROUGH': None,
    },

    # ---- IG Corporate Bond ----
    'XS2543791470 Corp': {
        'NAME'            : 'LVMH 3.5 06/15/31',
        'CRNCY'           : 'EUR',
        'ASSET_CLASS'     : 'Bond',
        'CPN'             : 3.5,
        'MATURITY'        : '2031-06-15',
        'YLD_YTM_MID'     : 3.89,
        'DUR_ADJ_MID'     : 4.71,
        'CONVEXITY'       : 0.268,
        'PX_LAST'         : 98.32,
        'AMT_OUTSTANDING' : 1.5e9,
        'VOLUME_AVG_20D'  : 18e6,
        'RTG_MOODY'       : 'A1',
        'RTG_SP'          : 'A+',
        'Z_SPRD_MID'      : 58,
        'ESG_SCORE'       : 74, 'ENV_SCORE': 76, 'SOC_SCORE': 73, 'GOV_SCORE': 73,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 52.4, 'ESG_LOOK_THROUGH': None,
    },

    # ---- HY Corporate Bond ----
    'XS2341234567 Corp': {
        'NAME'            : 'Telecom Italia 5.25 03/15/29',
        'CRNCY'           : 'EUR',
        'ASSET_CLASS'     : 'Bond',
        'CPN'             : 5.25,
        'MATURITY'        : '2029-03-15',
        'YLD_YTM_MID'     : 6.82,
        'DUR_ADJ_MID'     : 2.89,
        'CONVEXITY'       : 0.098,
        'PX_LAST'         : 94.15,
        'AMT_OUTSTANDING' : 800e6,
        'VOLUME_AVG_20D'  : 8e6,
        'RTG_MOODY'       : 'B1',
        'RTG_SP'          : 'B+',
        'Z_SPRD_MID'      : 382,
        'ESG_SCORE'       : 54, 'ENV_SCORE': 51, 'SOC_SCORE': 56, 'GOV_SCORE': 55,
        'CONTROVERSY_FLAG': True, 'CARBON_INTENSITY': 189.7, 'ESG_LOOK_THROUGH': None,
    },

    # ---- Senior Secured Loan ----
    'XS9876543210 Loan': {
        'NAME'            : 'Acuris Finance 6.5 12/15/28',
        'CRNCY'           : 'EUR',
        'ASSET_CLASS'     : 'Loan',
        'CPN'             : 6.5,
        'MATURITY'        : '2028-12-15',
        'YLD_YTM_MID'     : 7.82,
        'DUR_ADJ_MID'     : 2.15,
        'CONVEXITY'       : 0.052,
        'PX_LAST'         : 97.50,
        'AMT_OUTSTANDING' : 500e6,
        'VOLUME_AVG_20D'  : 0,
        'RTG_MOODY'       : 'B2',
        'RTG_SP'          : 'B',
        'Z_SPRD_MID'      : 482,
        'ESG_SCORE'       : 38, 'ENV_SCORE': 35, 'SOC_SCORE': 40, 'GOV_SCORE': 39,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': None, 'ESG_LOOK_THROUGH': None,
    },

    # ---- CLO Tranche ----
    'XS1122334455 CLO': {
        'NAME'            : 'Cairn CLO AAA 2024-1',
        'CRNCY'           : 'EUR',
        'ASSET_CLASS'     : 'CLO',
        'CPN'             : 1.8,
        'MATURITY'        : '2037-04-15',
        'YLD_YTM_MID'     : 2.15,
        'DUR_ADJ_MID'     : 4.82,
        'CONVEXITY'       : 0.31,
        'PX_LAST'         : 99.10,
        'AMT_OUTSTANDING' : 250e6,
        'VOLUME_AVG_20D'  : 0,
        'RTG_MOODY'       : 'Aaa',
        'RTG_SP'          : 'AAA',
        'Z_SPRD_MID'      : 145,
        'ESG_SCORE'       : None, 'ENV_SCORE': None, 'SOC_SCORE': None, 'GOV_SCORE': None,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': None, 'ESG_LOOK_THROUGH': None,
    },

    # ---- Section 2: Securities Not populated by yfinance

    # ---- Equities in YF_MAP ----
    # PX_LAST, BETA, EQY_DVD_YLD_IND, VOLUME_AVG_20D: None
    # populated at runtime from yfinance cache via bdp/bdh.
    # To override manually replace None with a hardcoded value.
    'SPY US Equity': {
        'NAME'            : 'SPDR S&P 500 ETF',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : None,
        'BETA'            : None,
        'VOLUME_AVG_20D'  : None,
        'EQY_DVD_YLD_IND' : None,
        'PE_RATIO'        : None,
        'ESG_SCORE'       : 62, 'ENV_SCORE': 58, 'SOC_SCORE': 65, 'GOV_SCORE': 63,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 145.2, 'ESG_LOOK_THROUGH': None,
    },
    'AAPL US Equity': {
        'NAME'            : 'Apple Inc',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : None,
        'BETA'            : None,
        'VOLUME_AVG_20D'  : None,
        'EQY_DVD_YLD_IND' : None,
        'PE_RATIO'        : None,
        'ESG_SCORE'       : 78, 'ENV_SCORE': 82, 'SOC_SCORE': 75, 'GOV_SCORE': 77,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 28.4, 'ESG_LOOK_THROUGH': None,
    },
    'MSFT US Equity': {
        'NAME'            : 'Microsoft Corp',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : None,
        'BETA'            : None,
        'VOLUME_AVG_20D'  : None,
        'EQY_DVD_YLD_IND' : None,
        'PE_RATIO'        : None,
        'ESG_SCORE'       : 81, 'ENV_SCORE': 85, 'SOC_SCORE': 79, 'GOV_SCORE': 79,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 15.2, 'ESG_LOOK_THROUGH': None,
    },
    'JPM US Equity': {
        'NAME'            : 'JPMorgan Chase',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : None,
        'BETA'            : None,
        'VOLUME_AVG_20D'  : None,
        'EQY_DVD_YLD_IND' : None,
        'PE_RATIO'        : None,
        'ESG_SCORE'       : 58, 'ENV_SCORE': 52, 'SOC_SCORE': 61, 'GOV_SCORE': 61,
        'CONTROVERSY_FLAG': True, 'CARBON_INTENSITY': 312.5, 'ESG_LOOK_THROUGH': None,
    },
    'GLD US Equity': {
        'NAME'            : 'SPDR Gold Shares',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : None,
        'BETA'            : None,
        'VOLUME_AVG_20D'  : None,
        'EQY_DVD_YLD_IND' : None,
        'ESG_SCORE'       : 42, 'ENV_SCORE': 35, 'SOC_SCORE': 48, 'GOV_SCORE': 43,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 89.3, 'ESG_LOOK_THROUGH': None,
    },
    'TLT US Equity': {
        'NAME'            : 'iShares 20+ Year Treasury',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : None,
        'BETA'            : None,
        'DUR_ADJ_MID'     : 16.4,
        'VOLUME_AVG_20D'  : None,
        'EQY_DVD_YLD_IND' : None,
        'ESG_SCORE'       : 68, 'ENV_SCORE': 65, 'SOC_SCORE': 70, 'GOV_SCORE': 69,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 0.0, 'ESG_LOOK_THROUGH': None,
    },
    'HYG US Equity': {
        'NAME'            : 'iShares HY Corp Bond ETF',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : None,
        'BETA'            : None,
        'DUR_ADJ_MID'     : 3.82,
        'VOLUME_AVG_20D'  : None,
        'EQY_DVD_YLD_IND' : None,
        'ESG_SCORE'       : 52, 'ENV_SCORE': 48, 'SOC_SCORE': 54, 'GOV_SCORE': 54,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 0.0, 'ESG_LOOK_THROUGH': None,
    },
    'TSLA US Equity': {
        'NAME'            : 'Tesla Inc',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : None,
        'BETA'            : None,
        'VOLUME_AVG_20D'  : None,
        'EQY_DVD_YLD_IND' : None,
        'ESG_SCORE'       : 45, 'ENV_SCORE': 62, 'SOC_SCORE': 32, 'GOV_SCORE': 41,
        'CONTROVERSY_FLAG': True, 'CARBON_INTENSITY': 0.0, 'ESG_LOOK_THROUGH': None,
    },
    'NVDA US Equity': {
        'NAME'            : 'Nvidia Corp',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : None,
        'BETA'            : None,
        'VOLUME_AVG_20D'  : None,
        'EQY_DVD_YLD_IND' : None,
        'ESG_SCORE'       : 71, 'ENV_SCORE': 68, 'SOC_SCORE': 73, 'GOV_SCORE': 72,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 8.9, 'ESG_LOOK_THROUGH': None,
    },

    # ---- Other equities (not in YF_MAP, hardcoded) ----
    'IEAG LN Equity': {
        'NAME'            : 'iShares Core EUR Govt Bond ETF',
        'CRNCY'           : 'EUR',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : 112.45,
        'BETA'            : -0.15,
        'DUR_ADJ_MID'     : 7.82,
        'VOLUME_AVG_20D'  : 25e6,
        'EQY_DVD_YLD_IND' : 2.84,
        'ESG_SCORE'       : 72, 'ENV_SCORE': 70, 'SOC_SCORE': 74, 'GOV_SCORE': 72,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 0.0, 'ESG_LOOK_THROUGH': None,
    },
    'EXHE GY Equity': {
        'NAME'            : 'iShares Euro High Yield Corp Bond ETF',
        'CRNCY'           : 'EUR',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : 89.32,
        'BETA'            : 0.45,
        'DUR_ADJ_MID'     : 3.24,
        'VOLUME_AVG_20D'  : 8e6,
        'EQY_DVD_YLD_IND' : 5.82,
        'ESG_SCORE'       : 55, 'ENV_SCORE': 50, 'SOC_SCORE': 58, 'GOV_SCORE': 57,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 0.0, 'ESG_LOOK_THROUGH': None,
    },
    'VNA GY Equity': {
        'NAME'            : 'Vonovia SE',
        'CRNCY'           : 'EUR',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : 28.45,
        'BETA'            : 0.72,
        'VOLUME_AVG_20D'  : 4e6,
        'EQY_DVD_YLD_IND' : 4.82,
        'ESG_SCORE'       : 69, 'ENV_SCORE': 74, 'SOC_SCORE': 67, 'GOV_SCORE': 66,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 42.1, 'ESG_LOOK_THROUGH': None,
    },
    'URI FP Equity': {
        'NAME'            : 'Unibail-Rodamco-Westfield',
        'CRNCY'           : 'EUR',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : 68.32,
        'BETA'            : 1.12,
        'VOLUME_AVG_20D'  : 1.5e6,
        'EQY_DVD_YLD_IND' : 7.24,
        'ESG_SCORE'       : 61, 'ENV_SCORE': 58, 'SOC_SCORE': 63, 'GOV_SCORE': 62,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 78.3, 'ESG_LOOK_THROUGH': None,
    },

    # ---- Indices in YF_MAP ----
    'SX5E Index': {
        'NAME'            : 'Euro Stoxx 50',
        'CRNCY'           : 'EUR',
        'ASSET_CLASS'     : 'Equity',
        'PX_LAST'         : None,
        'BETA'            : 1.0,
        'VOLUME_AVG_20D'  : None,
        'EQY_DVD_YLD_IND' : None,
        'ESG_SCORE'       : 64, 'ENV_SCORE': 61, 'SOC_SCORE': 66, 'GOV_SCORE': 65,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 168.4, 'ESG_LOOK_THROUGH': None,
    },
    'VIX Index': {
        'NAME'            : 'CBOE Volatility Index',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Index',
        'PX_LAST'         : None,
        'ESG_SCORE'       : None, 'ENV_SCORE': None, 'SOC_SCORE': None, 'GOV_SCORE': None,
        'CONTROVERSY_FLAG': None, 'CARBON_INTENSITY': None, 'ESG_LOOK_THROUGH': None,
    },
    'SPX Index': {
        'NAME'            : 'S&P 500 Index',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Index',
        'PX_LAST'         : 5842.31,
        'BETA'            : 1.0,
        'ESG_SCORE'       : 62, 'ENV_SCORE': 58, 'SOC_SCORE': 65, 'GOV_SCORE': 63,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 145.2, 'ESG_LOOK_THROUGH': None,
    },

    # ---- FX in YF_MAP ----
    'EURUSD Curncy': {
        'NAME'            : 'Euro / US Dollar',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'FX',
        'PX_LAST'         : None,
        'ESG_SCORE'       : None, 'ENV_SCORE': None, 'SOC_SCORE': None, 'GOV_SCORE': None,
        'CONTROVERSY_FLAG': None, 'CARBON_INTENSITY': None, 'ESG_LOOK_THROUGH': None,
    },
    'GBPUSD Curncy': {
        'NAME'            : 'British Pound / US Dollar',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'FX',
        'PX_LAST'         : None,
        'ESG_SCORE'       : None, 'ENV_SCORE': None, 'SOC_SCORE': None, 'GOV_SCORE': None,
        'CONTROVERSY_FLAG': None, 'CARBON_INTENSITY': None, 'ESG_LOOK_THROUGH': None,
    },

    # ---- FX not in YF_MAP (hardcoded) ----
    'USDJPY Curncy': {
        'NAME'            : 'US Dollar / Japanese Yen',
        'CRNCY'           : 'JPY',
        'ASSET_CLASS'     : 'FX',
        'PX_LAST'         : 148.23,
        'ESG_SCORE'       : None, 'ENV_SCORE': None, 'SOC_SCORE': None, 'GOV_SCORE': None,
        'CONTROVERSY_FLAG': None, 'CARBON_INTENSITY': None, 'ESG_LOOK_THROUGH': None,
    },
    'USDEUR Curncy': {
        'NAME'            : 'US Dollar / Euro',
        'CRNCY'           : 'EUR',
        'ASSET_CLASS'     : 'FX',
        'PX_LAST'         : 0.8902,
        'ESG_SCORE'       : None, 'ENV_SCORE': None, 'SOC_SCORE': None, 'GOV_SCORE': None,
        'CONTROVERSY_FLAG': None, 'CARBON_INTENSITY': None, 'ESG_LOOK_THROUGH': None,
    },

    # ---- Listed Options (fully hardcoded, greeks not in yfinance) ----
    'SPXW 260619P05500 Index': {
        'NAME'            : 'SPX Put 5500 Jun26',
        'CRNCY'           : 'USD',
        'ASSET_CLASS'     : 'Derivative',
        'PX_LAST'         : 45.20,
        'DELTA'           : -0.28,
        'GAMMA'           : 0.0012,
        'VEGA'            : 2.85,
        'THETA'           : -1.24,
        'OPT_UNDL_PX'     : 5842.31,
        'CONTRACT_SIZE'   : 100,
        'IMPLIED_VOL'     : 0.182,
        'ESG_SCORE'       : 62, 'ENV_SCORE': 58, 'SOC_SCORE': 65, 'GOV_SCORE': 63,
        'CONTROVERSY_FLAG': False, 'CARBON_INTENSITY': 145.2, 'ESG_LOOK_THROUGH': 'SPX Index',
    },
    }

    def __init__(self, seed: int = 42):
        from fund_risk_workflow.config import REFERENCE_DATE
        self.VALUATION_DATE = pd.Timestamp(REFERENCE_DATE)
        np.random.seed(seed)

    # ----------------------------------------------------------------
    # BDP: Bloomberg Data Point
    # MRS-47: for YF_MAP instruments, PX_LAST, BETA, EQY_DVD_YLD_IND,
    # VOLUME_AVG_20D populated from yfinance info cache.
    # ----------------------------------------------------------------
    def bdp(
        self,
        securities: str | list,
        fields: str | list,
        date: str | None = None,
    ) -> pd.DataFrame:
        """
        Pull static reference data for one or more securities.

        Parameters
        ----------
        securities : str or list of str
        fields : str or list of str
        date : str, optional
            YYYY-MM-DD format. If provided, returns data for that date
            (using yfinance cache to interpolate/simulate). If None,
            returns latest/current data (default Bloomberg behavior).

        Returns
        -------
        pd.DataFrame indexed by security ticker
        """
        if isinstance(securities, str):
            securities = [securities]
        if isinstance(fields, str):
            fields = [fields]

        live_fields = {'PX_LAST', 'BETA', 'EQY_DVD_YLD_IND',
                       'VOLUME_AVG_20D', 'PE_RATIO'}
        needs_live  = any(f in live_fields for f in fields)

        rows = []
        for sec in securities:
            row  = {'security': sec}
            data = self._reference_data.get(sec, {}).copy()

            # MRS-47: overlay live fields from yfinance info cache
            if needs_live and sec in self.YF_MAP:
                if date:
                    # Get date-aligned price using bdh logic
                    hist = self.bdh([sec], 'PX_LAST', date, date)
                    if len(hist) > 0:
                        px = hist.iloc[0]['PX_LAST']
                        data['PX_LAST'] = px
                    # For other fields, use latest (bdp behavior)
                    live = self._fetch_yf_info(self.YF_MAP[sec])
                    for f in ['BETA', 'EQY_DVD_YLD_IND', 'VOLUME_AVG_20D']:
                        if f in fields and live.get(f) is not None:
                            data[f] = live[f]
                else:
                    # No date specified: return latest data
                    live = self._fetch_yf_info(self.YF_MAP[sec])
                    for f in live_fields:
                        if f in fields and live.get(f) is not None:
                            data[f] = live[f]

            # Beta fixed by definition for benchmark instruments
            if 'BETA' in fields and sec in self.BETA_OVERRIDE:
                data['BETA'] = self.BETA_OVERRIDE[sec]

            for field in fields:
                row[field] = data.get(field, np.nan)
            rows.append(row)

        return pd.DataFrame(rows).set_index('security')

    # ----------------------------------------------------------------
    # BDH: Bloomberg Data History
    # MRS-47: real prices from yfinance cache for mapped instruments
    # ----------------------------------------------------------------
    def bdh(
        self,
        securities: str | list,
        fields: str | list,
        start_date: str,
        end_date: str,
        freq: str = 'DAILY',
    ) -> pd.DataFrame:
        """
        Pull historical time series data.

        For instruments in YF_MAP, PX_LAST returns real closing prices
        from cache. All other instruments fall back to simulation.

        Parameters
        ----------
        securities : str or list of str
        fields : str or list of str
        start_date : str   YYYYMMDD or YYYY-MM-DD
        end_date : str     YYYYMMDD or YYYY-MM-DD
        freq : str         DAILY | WEEKLY | MONTHLY

        Returns
        -------
        pd.DataFrame
            Single security: DatetimeIndex, columns: fields
            Multiple securities: MultiIndex (date, security)
        """
        if isinstance(securities, str):
            securities = [securities]
        if isinstance(fields, str):
            fields = [fields]

        start = pd.to_datetime(start_date)
        end   = pd.to_datetime(end_date)

        if freq == 'WEEKLY':
            dates = pd.bdate_range(start, end, freq='W-FRI')
        elif freq == 'MONTHLY':
            dates = pd.bdate_range(start, end, freq='BMS')
        else:
            dates = pd.bdate_range(start, end)

        all_dfs = []
        for sec in securities:
            ref    = self._reference_data.get(sec, {})
            price  = ref.get('PX_LAST', 100.0)
            aclass = ref.get('ASSET_CLASS', 'Equity')

            yf_ticker = self.YF_MAP.get(sec)
            if yf_ticker and 'PX_LAST' in fields:
                prices = self._fetch_yf_prices(yf_ticker, dates, price or 100.0)
            else:
                prices = self._simulate_prices(sec, price or 100.0, dates, aclass)

            df_sec             = pd.DataFrame(index=dates)
            df_sec.index.name  = 'date'
            df_sec['security'] = sec

            for field in fields:
                if field == 'PX_LAST':
                    df_sec[field] = prices
                elif field == 'VOLUME':
                    adv = ref.get('VOLUME_AVG_20D', 1e6) or 1e6
                    df_sec[field] = np.random.lognormal(
                        np.log(max(adv, 1)), 0.3, len(dates))
                elif field == 'YLD_YTM_MID':
                    ytm = ref.get('YLD_YTM_MID', 3.0)
                    df_sec[field] = self._simulate_yield(ytm, dates)
                elif field == 'Z_SPRD_MID':
                    zsprd = ref.get('Z_SPRD_MID', 100)
                    df_sec[field] = self._simulate_spread(zsprd, dates)
                else:
                    df_sec[field] = ref.get(field, np.nan)

            all_dfs.append(df_sec)

        result = pd.concat(all_dfs).reset_index()
        result = result.set_index(['date', 'security'])

        if len(securities) == 1:
            return result.xs(securities[0], level='security')

        return result

    # ----------------------------------------------------------------
    # BDS: Bloomberg Data Set (bulk data)
    # ----------------------------------------------------------------
    def bds(
        self,
        security: str,
        field: str,
    ) -> pd.DataFrame:
        """
        Pull bulk data for a single security.

        Parameters
        ----------
        security : str
        field : str   CASH_FLOW | INDX_MEMBERS

        Returns
        -------
        pd.DataFrame
        """
        ref = self._reference_data.get(security, {})
        if field == 'CASH_FLOW':
            return self._simulate_cashflows(security, ref)
        elif field == 'INDX_MEMBERS':
            return self._simulate_index_members(security)
        return pd.DataFrame()

    # ----------------------------------------------------------------
    # Convenience: enrich positions DataFrame
    # ----------------------------------------------------------------
    def get_portfolio_data(
        self,
        positions_df: pd.DataFrame,
        fields: list | None = None,
    ) -> pd.DataFrame:
        """Enrich a positions DataFrame with Bloomberg reference data."""
        if fields is None:
            fields = [
                'NAME', 'CRNCY', 'ASSET_CLASS', 'PX_LAST',
                'DUR_ADJ_MID', 'CONVEXITY', 'YLD_YTM_MID',
                'BETA', 'VOLUME_AVG_20D', 'EQY_DVD_YLD_IND',
                'RTG_SP', 'RTG_MOODY', 'Z_SPRD_MID',
            ]

        liquid_mask = positions_df['bloomberg_ticker'].notna()
        tickers     = positions_df.loc[liquid_mask, 'bloomberg_ticker'].tolist()

        if not tickers:
            return positions_df

        bbg_data = self.bdp(tickers, fields).reset_index()
        bbg_data = bbg_data.rename(columns={'security': 'bloomberg_ticker'})

        return positions_df.merge(bbg_data, on='bloomberg_ticker', how='left')

    # ----------------------------------------------------------------
    # MRS-47: rate series access
    # ----------------------------------------------------------------
    def get_rate_series(
        self,
        series_name: str,
        start_date: str,
        end_date: str,
    ) -> pd.Series:
        """
        Return a daily rate series by name.

        Available series:
            ESTR      ECB Euro Short-Term Rate (overnight, %)
            EUR_10Y   ECB AAA EUR govt bond 10Y yield (%)
            USD_10Y   US 10Y Treasury yield (%, via yfinance ^TNX)
            USD_3M    US 3M T-bill yield (%, via yfinance ^IRX)

        Parameters
        ----------
        series_name : str
        start_date : str   YYYY-MM-DD
        end_date : str     YYYY-MM-DD

        Returns
        -------
        pd.Series with DatetimeIndex, values in percent (e.g. 3.5 = 3.5%)
        """
        start = pd.to_datetime(start_date)
        end   = pd.to_datetime(end_date)
        dates = pd.bdate_range(start, end)

        if series_name in self.ECB_SERIES:
            raw = self._fetch_ecb_rate(series_name)
        elif series_name in self.YF_RATES:
            raw = self._fetch_yf_rate(series_name)
        else:
            raise ValueError(
                f"Unknown rate series '{series_name}'. "
                f"Available: {list(self.ECB_SERIES) + list(self.YF_RATES)}"
            )

        series = raw.reindex(dates, method='ffill').bfill()
        return series

    # ----------------------------------------------------------------
    # Internal helpers — MRS-47 cache layer
    # ----------------------------------------------------------------
    def _fetch_yf_info(self, yf_ticker: str) -> dict:
        """
        Return live static fields from yfinance .info for a ticker.
        Cached as JSON in data/yf_cache/{ticker}_info.json.
        Fields returned: PX_LAST, BETA, EQY_DVD_YLD_IND,
                         VOLUME_AVG_20D, PE_RATIO.
        """
        self.YF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        safe_name  = yf_ticker.replace('^', '').replace('=', '_')
        cache_path = self.YF_CACHE_DIR / f'{safe_name}_info.json'

        if cache_path.exists():
            with open(cache_path) as f:
                return json.load(f)

        try:
            import yfinance as yf
            # PX_LAST from price cache — same source as bdh
            # ensures bdp and bdh are consistent
            price_cache = self.YF_CACHE_DIR / f'{safe_name}.csv'
            if not price_cache.exists():
                self._fetch_yf_prices(
                    yf_ticker,
                    pd.bdate_range('2018-01-01', self.VALUATION_DATE),
                    100.0,
                )
            if price_cache.exists():
                raw       = pd.read_csv(price_cache, index_col=0, parse_dates=True)
                raw.index = pd.to_datetime(raw.index).tz_localize(None)
                raw       = raw[raw.index <= self.VALUATION_DATE]
                px_last   = float(raw['Close'].dropna().iloc[-1]) if not raw.empty else None
            else:
                px_last = None

            info = yf.Ticker(yf_ticker).info
            result = {
                'PX_LAST'         : px_last,
                'BETA'            : info.get('beta'),
                'EQY_DVD_YLD_IND' : (info.get('dividendYield') or 0) * 100
                                    if info.get('dividendYield') else None,
                'VOLUME_AVG_20D'  : info.get('averageVolume'),
                'PE_RATIO'        : info.get('trailingPE'),
            }
            with open(cache_path, 'w') as f:
                json.dump(result, f)
            return result
        except Exception:
            return {}

    def _fetch_yf_prices(
        self,
        yf_ticker: str,
        dates: pd.DatetimeIndex,
        fallback_price: float,
    ) -> np.ndarray:
        """
        Return real closing prices from yfinance cache.

        Cache file: data/yf_cache/{ticker}.csv
        Falls back to simulation if download fails.

        Cache freshness:
        - If cached file exists and covers the requested date range, reuse it.
        - If cached file does not cover the range, redownload and overwrite.
        - This ensures prices are fresh without caching forever.
        """
        self.YF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        safe_name  = yf_ticker.replace('^', '').replace('=', '_')
        cache_path = self.YF_CACHE_DIR / f'{safe_name}.csv'

        # Check if cache exists and covers the requested date range
        cache_valid = False
        if cache_path.exists():
            try:
                raw = pd.read_csv(cache_path, index_col=0, parse_dates=True)
                raw.index = pd.to_datetime(raw.index).tz_localize(None)

                # Validate cache covers requested range
                cache_min = raw.index.min()
                cache_max = raw.index.max()
                req_min = dates[0]
                req_max = dates[-1]

                if cache_min <= req_min and cache_max >= req_max:
                    cache_valid = True
            except Exception:
                # Cache file is corrupted or unreadable; redownload
                cache_valid = False

        # If cache is invalid, redownload
        if not cache_valid:
            try:
                import yfinance as yf
                start = (dates[0]  - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
                end   = (dates[-1] + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
                raw   = yf.download(
                    yf_ticker, start=start, end=end,
                    auto_adjust=True, progress=False,
                )
                if raw.empty:
                    raise ValueError(f"Empty download for {yf_ticker}")
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = raw.columns.get_level_values(0)
                raw = raw[['Close']]
                raw.index = pd.to_datetime(raw.index).tz_localize(None)
                raw.to_csv(cache_path)
            except Exception:
                return self._simulate_prices(
                    yf_ticker, fallback_price, dates, 'Equity'
                )

        close = raw['Close'].squeeze()
        close = close.reindex(dates, method='ffill').bfill()

        if close.isna().all():
            return self._simulate_prices(
                yf_ticker, fallback_price, dates, 'Equity'
            )

        return close.values.astype(float)

    def _fetch_ecb_rate(self, series_name: str) -> pd.Series:
        """
        Fetch ECB rate series. Cached as CSV in data/yf_cache/.
        """
        self.YF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = self.YF_CACHE_DIR / f'ECB_{series_name}.csv'

        if cache_path.exists():
            raw = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            raw.index = pd.to_datetime(raw.index).tz_localize(None)
            return raw['rate']

        try:
            series_id = self.ECB_SERIES[series_name]
            url = (
                f'https://data-api.ecb.europa.eu/service/data/{series_id}'
                f'?format=csvdata&startPeriod=2018-01-01'
            )
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            from io import StringIO
            df  = pd.read_csv(StringIO(r.text))
            df  = df[['TIME_PERIOD', 'OBS_VALUE']].dropna()
            df['TIME_PERIOD'] = pd.to_datetime(df['TIME_PERIOD'])
            df  = df.set_index('TIME_PERIOD')
            df.index = df.index.tz_localize(None)
            df.columns = ['rate']
            df.to_csv(cache_path)
            return df['rate']
        except Exception:
            # Fallback: flat 3% series
            idx = pd.bdate_range('2018-01-01', self.VALUATION_DATE)
            return pd.Series(3.0, index=idx, name='rate')

    def _fetch_yf_rate(self, series_name: str) -> pd.Series:
        """
        Fetch rate series from yfinance. Cached as CSV in data/yf_cache/.
        """
        self.YF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = self.YF_CACHE_DIR / f'YF_{series_name}.csv'

        if cache_path.exists():
            raw = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            raw.index = pd.to_datetime(raw.index).tz_localize(None)
            return raw['rate']

        try:
            import yfinance as yf
            yf_ticker = self.YF_RATES[series_name]
            raw = yf.download(
                yf_ticker, start='2018-01-01', end='2026-05-14',
                auto_adjust=True, progress=False,
            )
            if raw.empty:
                raise ValueError(f"Empty download for {yf_ticker}")
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            df = raw[['Close']].rename(columns={'Close': 'rate'})
            df.index = pd.to_datetime(df.index).tz_localize(None)
            df.to_csv(cache_path)
            return df['rate']
        except Exception:
            idx = pd.bdate_range('2018-01-01', self.VALUATION_DATE)
            return pd.Series(4.0, index=idx, name='rate')

    # ----------------------------------------------------------------
    # Internal simulation helpers (fallback for non-YF_MAP instruments)
    # ----------------------------------------------------------------
    def _simulate_prices(
        self,
        sec: str,
        current_price: float,
        dates: pd.DatetimeIndex,
        asset_class: str,
    ) -> np.ndarray:
        """Simulate realistic price history ending at current_price."""
        n = len(dates)
        vol_map = {
            'FX'    : 0.006,
            'Bond'  : 0.003,
            'Loan'  : 0.001,
            'CLO'   : 0.002,
            'Index' : 0.012,
        }
        vol = vol_map.get(asset_class, 0.015)
        np.random.seed(hash(sec) % 2**31)
        log_returns = np.random.normal(-vol**2 / 2, vol, n)
        log_prices  = np.log(current_price) - np.cumsum(log_returns[::-1])
        prices      = np.exp(log_prices)[::-1]
        prices      = prices * current_price / prices[-1]
        return prices

    def _simulate_yield(
        self,
        current_ytm: float,
        dates: pd.DatetimeIndex,
    ) -> np.ndarray:
        """Simulate yield history ending at current level."""
        n       = len(dates)
        changes = np.random.normal(0, 0.002, n)
        yields  = current_ytm - np.cumsum(changes[::-1])
        yields  = yields[::-1]
        yields  = yields * current_ytm / yields[-1]
        return np.maximum(yields, 0.001)

    def _simulate_spread(
        self,
        current_spread: float,
        dates: pd.DatetimeIndex,
    ) -> np.ndarray:
        """Simulate credit spread history."""
        n       = len(dates)
        changes = np.random.normal(0, 5.0, n)
        spreads = current_spread - np.cumsum(changes[::-1])
        spreads = spreads[::-1]
        return np.maximum(spreads, 10)

    def _simulate_cashflows(
        self,
        security: str,
        ref: dict,
    ) -> pd.DataFrame:
        """Simulate bond cash flow schedule."""
        if ref.get('ASSET_CLASS') not in ('Bond', 'Loan', 'CLO'):
            return pd.DataFrame()

        maturity = pd.to_datetime(ref.get('MATURITY', '2030-01-01'))
        coupon   = ref.get('CPN', 0.0)
        face     = 100.0
        valuation_date = self.VALUATION_DATE

        dates = pd.date_range(valuation_date, maturity, freq='6MS')[1:].date
        if len(dates) == 0:
            return pd.DataFrame()

        cfs      = [coupon / 2 * face] * len(dates)
        cfs[-1] += face

        return pd.DataFrame({
            'cash_flow_date'  : dates,
            'cash_flow_amount': cfs,
        })

    def _simulate_index_members(self, security: str) -> pd.DataFrame:
        """Return simulated index members."""
        members = {
            'SPX Index' : [
                'AAPL US Equity', 'MSFT US Equity',
                'JPM US Equity',  'SPY US Equity',
            ],
            'SX5E Index': [
                'VNA GY Equity', 'URI FP Equity', 'LVMH FP Equity',
            ],
        }
        return pd.DataFrame({'member_ticker': members.get(security, [])})


# ----------------------------------------------------------------
# Usage example
# ----------------------------------------------------------------
if __name__ == '__main__':
    bbg = MockBloomberg()

    print('\n--- BDP: reference data (live from cache) ---')
    ref = bbg.bdp(
        ['SPY US Equity', 'AAPL US Equity', 'EURUSD Curncy'],
        ['NAME', 'PX_LAST', 'BETA', 'EQY_DVD_YLD_IND', 'VOLUME_AVG_20D']
    )
    print(ref)

    print('\n--- BDH: historical prices ---')
    hist = bbg.bdh('SPY US Equity', 'PX_LAST', '20240101', '20260513')
    print(hist.tail())

    from fund_risk_workflow.config import REFERENCE_DATE

    print('\n--- Rate series: ESTR ---')
    estr = bbg.get_rate_series('ESTR', '2024-01-01', REFERENCE_DATE)
    print(estr.tail())

    print('\n--- Rate series: USD_10Y ---')
    usd10y = bbg.get_rate_series('USD_10Y', '2024-01-01', REFERENCE_DATE)
    print(usd10y.tail())