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
    Equities : SPY, AAPL, MSFT, JPM, GLD, TLT, HYG
    Bonds    : US Treasury, German Bund, IG corporate, HY corporate
    FX       : EURUSD, GBPUSD, USDJPY
    Indices  : SPX, SX5E, VIX
"""

import numpy as np
import pandas as pd
from datetime import datetime


class MockBloomberg:
    """
    Simulates Bloomberg API with realistic financial data.

    Parameters
    ----------
    seed : int
        Random seed for reproducibility. Default 42.

    Examples
    --------
    >>> bbg = MockBloomberg()
    >>> bbg.bdp('SPY US Equity', ['PX_LAST', 'BETA'])
    >>> bbg.bdh('SPY US Equity', 'PX_LAST', '20240101', '20260513')
    >>> bbg.bds('US912828YK09 Govt', 'CASH_FLOW')
    """

    # ----------------------------------------------------------------
    # Static reference data
    # Fields: PX_LAST, DUR_ADJ_MID, CONVEXITY, YLD_YTM_MID,
    #         BETA, VOLUME_AVG_20D, EQY_DVD_YLD_IND,
    #         CRNCY, ASSET_CLASS, RTG_SP, RTG_MOODY,
    #         CPN, MATURITY, AMT_OUTSTANDING, Z_SPRD_MID
    # ----------------------------------------------------------------
    _reference_data = {

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
        },

        # ---- Equities ----
        'SPY US Equity': {
            'NAME'            : 'SPDR S&P 500 ETF',
            'CRNCY'           : 'USD',
            'ASSET_CLASS'     : 'Equity',
            'PX_LAST'         : 523.42,
            'BETA'            : 1.00,
            'VOLUME_AVG_20D'  : 85e6,
            'EQY_DVD_YLD_IND' : 1.32,
            'PE_RATIO'        : 22.4,
        },
        'AAPL US Equity': {
            'NAME'            : 'Apple Inc',
            'CRNCY'           : 'USD',
            'ASSET_CLASS'     : 'Equity',
            'PX_LAST'         : 211.45,
            'BETA'            : 1.24,
            'VOLUME_AVG_20D'  : 52e6,
            'EQY_DVD_YLD_IND' : 0.48,
            'PE_RATIO'        : 31.2,
        },
        'MSFT US Equity': {
            'NAME'            : 'Microsoft Corp',
            'CRNCY'           : 'USD',
            'ASSET_CLASS'     : 'Equity',
            'PX_LAST'         : 415.32,
            'BETA'            : 0.91,
            'VOLUME_AVG_20D'  : 21e6,
            'EQY_DVD_YLD_IND' : 0.72,
            'PE_RATIO'        : 35.8,
        },
        'JPM US Equity': {
            'NAME'            : 'JPMorgan Chase',
            'CRNCY'           : 'USD',
            'ASSET_CLASS'     : 'Equity',
            'PX_LAST'         : 248.73,
            'BETA'            : 1.18,
            'VOLUME_AVG_20D'  : 8e6,
            'EQY_DVD_YLD_IND' : 2.11,
            'PE_RATIO'        : 12.4,
        },
        'GLD US Equity': {
            'NAME'            : 'SPDR Gold Shares',
            'CRNCY'           : 'USD',
            'ASSET_CLASS'     : 'Equity',
            'PX_LAST'         : 287.34,
            'BETA'            : 0.08,
            'VOLUME_AVG_20D'  : 12e6,
            'EQY_DVD_YLD_IND' : 0.0,
        },
        'TLT US Equity': {
            'NAME'            : 'iShares 20+ Year Treasury',
            'CRNCY'           : 'USD',
            'ASSET_CLASS'     : 'Equity',
            'PX_LAST'         : 84.23,
            'BETA'            : -0.31,
            'DUR_ADJ_MID'     : 16.4,
            'VOLUME_AVG_20D'  : 38e6,
            'EQY_DVD_YLD_IND' : 4.12,
        },
        'HYG US Equity': {
            'NAME'            : 'iShares HY Corp Bond ETF',
            'CRNCY'           : 'USD',
            'ASSET_CLASS'     : 'Equity',
            'PX_LAST'         : 76.43,
            'BETA'            : 0.52,
            'DUR_ADJ_MID'     : 3.82,
            'VOLUME_AVG_20D'  : 28e6,
            'EQY_DVD_YLD_IND' : 5.84,
        },
        'SX5E Index': {
            'NAME'            : 'Euro Stoxx 50',
            'CRNCY'           : 'EUR',
            'ASSET_CLASS'     : 'Equity',
            'PX_LAST'         : 5124.87,
            'BETA'            : 1.0,
            'VOLUME_AVG_20D'  : 2e9,
            'EQY_DVD_YLD_IND' : 3.12,
        },

        # ---- Listed REITs ----
        'VNA GY Equity': {
            'NAME'            : 'Vonovia SE',
            'CRNCY'           : 'EUR',
            'ASSET_CLASS'     : 'Equity',
            'PX_LAST'         : 28.45,
            'BETA'            : 0.72,
            'VOLUME_AVG_20D'  : 4e6,
            'EQY_DVD_YLD_IND' : 4.82,
        },
        'URI FP Equity': {
            'NAME'            : 'Unibail-Rodamco-Westfield',
            'CRNCY'           : 'EUR',
            'ASSET_CLASS'     : 'Equity',
            'PX_LAST'         : 68.32,
            'BETA'            : 1.12,
            'VOLUME_AVG_20D'  : 1.5e6,
            'EQY_DVD_YLD_IND' : 7.24,
        },

        # ---- FX ----
        'EURUSD Curncy': {
            'NAME'            : 'Euro / US Dollar',
            'CRNCY'           : 'USD',
            'ASSET_CLASS'     : 'FX',
            'PX_LAST'         : 1.1234,
        },
        'GBPUSD Curncy': {
            'NAME'            : 'British Pound / US Dollar',
            'CRNCY'           : 'USD',
            'ASSET_CLASS'     : 'FX',
            'PX_LAST'         : 1.3312,
        },
        'USDJPY Curncy': {
            'NAME'            : 'US Dollar / Japanese Yen',
            'CRNCY'           : 'JPY',
            'ASSET_CLASS'     : 'FX',
            'PX_LAST'         : 148.23,
        },
        'USDEUR Curncy': {
            'NAME'            : 'US Dollar / Euro',
            'CRNCY'           : 'EUR',
            'ASSET_CLASS'     : 'FX',
            'PX_LAST'         : 0.8902,
        },

        # ---- Indices and Vol ----
        'VIX Index': {
            'NAME'            : 'CBOE Volatility Index',
            'CRNCY'           : 'USD',
            'ASSET_CLASS'     : 'Index',
            'PX_LAST'         : 18.42,
        },
        'SPX Index': {
            'NAME'            : 'S&P 500 Index',
            'CRNCY'           : 'USD',
            'ASSET_CLASS'     : 'Index',
            'PX_LAST'         : 5842.31,
            'BETA'            : 1.0,
        },
    }

    def __init__(self, seed: int = 42):
        np.random.seed(seed)
        print('MockBloomberg: connected (simulation mode)')
        print('Swap import to RealBloomberg for production use.')

    # ----------------------------------------------------------------
    # BDP: Bloomberg Data Point
    # ----------------------------------------------------------------
    def bdp(
        self,
        securities: str | list,
        fields: str | list
    ) -> pd.DataFrame:
        """
        Pull static reference data for one or more securities.

        Parameters
        ----------
        securities : str or list of str
            Bloomberg tickers e.g. 'SPY US Equity'
        fields : str or list of str
            Bloomberg fields e.g. ['PX_LAST', 'BETA']

        Returns
        -------
        pd.DataFrame
            Index: security tickers, columns: requested fields

        Examples
        --------
        >>> bbg = MockBloomberg()
        >>> bbg.bdp('SPY US Equity', ['PX_LAST', 'BETA'])
        >>> bbg.bdp(
        ...     ['SPY US Equity', 'US912828YK09 Govt'],
        ...     ['PX_LAST', 'DUR_ADJ_MID', 'CRNCY']
        ... )
        """
        if isinstance(securities, str):
            securities = [securities]
        if isinstance(fields, str):
            fields = [fields]

        rows = []
        for sec in securities:
            row  = {'security': sec}
            data = self._reference_data.get(sec, {})
            for field in fields:
                row[field] = data.get(field, np.nan)
            rows.append(row)

        return pd.DataFrame(rows).set_index('security')

    # ----------------------------------------------------------------
    # BDH: Bloomberg Data History
    # ----------------------------------------------------------------
    def bdh(
        self,
        securities: str | list,
        fields: str | list,
        start_date: str,
        end_date: str,
        freq: str = 'DAILY'
    ) -> pd.DataFrame:
        """
        Pull historical time series data.

        Parameters
        ----------
        securities : str or list of str
            Bloomberg tickers
        fields : str or list of str
            Bloomberg fields e.g. 'PX_LAST', 'VOLUME'
        start_date : str
            Start date in 'YYYYMMDD' or 'YYYY-MM-DD' format
        end_date : str
            End date in 'YYYYMMDD' or 'YYYY-MM-DD' format
        freq : str
            Frequency: 'DAILY', 'WEEKLY', 'MONTHLY'

        Returns
        -------
        pd.DataFrame
            Single security: DatetimeIndex, columns: fields
            Multiple securities: MultiIndex (date, security)

        Examples
        --------
        >>> bbg = MockBloomberg()
        >>> bbg.bdh('SPY US Equity', 'PX_LAST', '20240101', '20260513')
        >>> bbg.bdh(
        ...     ['SPY US Equity', 'GLD US Equity'],
        ...     ['PX_LAST', 'VOLUME'],
        ...     '20240101', '20260513'
        ... )
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

            prices = self._simulate_prices(sec, price, dates, aclass)

            df_sec             = pd.DataFrame(index=dates)
            df_sec.index.name  = 'date'
            df_sec['security'] = sec

            for field in fields:
                if field == 'PX_LAST':
                    df_sec[field] = prices
                elif field == 'VOLUME':
                    adv = ref.get('VOLUME_AVG_20D', 1e6)
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
        field: str
    ) -> pd.DataFrame:
        """
        Pull bulk data for a single security.

        Parameters
        ----------
        security : str
            Bloomberg ticker
        field : str
            Bulk field: 'CASH_FLOW' or 'INDX_MEMBERS'

        Returns
        -------
        pd.DataFrame

        Examples
        --------
        >>> bbg = MockBloomberg()
        >>> bbg.bds('US912828YK09 Govt', 'CASH_FLOW')
        >>> bbg.bds('SPX Index', 'INDX_MEMBERS')
        """
        ref = self._reference_data.get(security, {})

        if field == 'CASH_FLOW':
            return self._simulate_cashflows(security, ref)
        elif field == 'INDX_MEMBERS':
            return self._simulate_index_members(security)
        else:
            return pd.DataFrame()

    # ----------------------------------------------------------------
    # Convenience: enrich positions DataFrame with Bloomberg data
    # ----------------------------------------------------------------
    def get_portfolio_data(
        self,
        positions_df: pd.DataFrame,
        fields: list | None = None
    ) -> pd.DataFrame:
        """
        Enrich a positions DataFrame with Bloomberg reference data.
        Skips rows where bloomberg_ticker is None or NaN
        (illiquid instruments: direct properties, private loans).

        Parameters
        ----------
        positions_df : pd.DataFrame
            Must contain column 'bloomberg_ticker'
        fields : list of str, optional
            Bloomberg fields to pull. Defaults to standard
            risk fields.

        Returns
        -------
        pd.DataFrame
            Original positions enriched with Bloomberg data

        Examples
        --------
        >>> bbg = MockBloomberg()
        >>> enriched = bbg.get_portfolio_data(positions_df)
        """
        if fields is None:
            fields = [
                'NAME', 'CRNCY', 'ASSET_CLASS', 'PX_LAST',
                'DUR_ADJ_MID', 'CONVEXITY', 'YLD_YTM_MID',
                'BETA', 'VOLUME_AVG_20D', 'EQY_DVD_YLD_IND',
                'RTG_SP', 'RTG_MOODY', 'Z_SPRD_MID'
            ]

        # only enrich liquid instruments with a Bloomberg ticker
        liquid_mask = positions_df['bloomberg_ticker'].notna()
        tickers     = positions_df.loc[
            liquid_mask, 'bloomberg_ticker'
        ].tolist()

        if not tickers:
            return positions_df

        bbg_data = self.bdp(tickers, fields).reset_index()
        bbg_data = bbg_data.rename(
            columns={'security': 'bloomberg_ticker'})

        enriched = positions_df.merge(
            bbg_data, on='bloomberg_ticker', how='left')

        return enriched

    # ----------------------------------------------------------------
    # Internal simulation helpers
    # ----------------------------------------------------------------
    def _simulate_prices(
        self,
        sec: str,
        current_price: float,
        dates: pd.DatetimeIndex,
        asset_class: str
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
        log_prices  = np.log(current_price) - np.cumsum(
            log_returns[::-1])
        prices      = np.exp(log_prices)[::-1]
        prices      = prices * current_price / prices[-1]

        return prices

    def _simulate_yield(
        self,
        current_ytm: float,
        dates: pd.DatetimeIndex
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
        dates: pd.DatetimeIndex
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
        ref: dict
    ) -> pd.DataFrame:
        """Simulate bond cash flow schedule."""
        if ref.get('ASSET_CLASS') not in ('Bond', 'Loan', 'CLO'):
            return pd.DataFrame()

        maturity = pd.to_datetime(
            ref.get('MATURITY', '2030-01-01'))
        coupon   = ref.get('CPN', 0.0)
        face     = 100.0
        today    = pd.Timestamp.today()

        dates = pd.date_range(today, maturity, freq='6MS')[1:].date        
        if len(dates) == 0:
            return pd.DataFrame()

        cfs        = [coupon / 2 * face] * len(dates)
        cfs[-1]   += face

        return pd.DataFrame({
            'cash_flow_date'  : dates,
            'cash_flow_amount': cfs
        })

    def _simulate_index_members(
        self,
        security: str
    ) -> pd.DataFrame:
        """Return simulated index members."""
        members = {
            'SPX Index' : [
                'AAPL US Equity', 'MSFT US Equity',
                'JPM US Equity',  'SPY US Equity'
            ],
            'SX5E Index': [
                'VNA GY Equity', 'URI FP Equity',
                'LVMH FP Equity'
            ],
        }
        tickers = members.get(security, [])
        return pd.DataFrame({'member_ticker': tickers})


# ----------------------------------------------------------------
# Usage example (run as script)
# ----------------------------------------------------------------
if __name__ == '__main__':

    bbg = MockBloomberg()

    print('\n--- BDP: reference data ---')
    ref = bbg.bdp(
        ['SPY US Equity', 'US912828YK09 Govt', 'EURUSD Curncy'],
        ['NAME', 'PX_LAST', 'DUR_ADJ_MID', 'BETA', 'CRNCY']
    )
    print(ref)

    print('\n--- BDH: historical prices ---')
    hist = bbg.bdh(
        'SPY US Equity', 'PX_LAST',
        '20240101', '20260513'
    )
    print(hist.tail())

    print('\n--- BDS: bond cash flows ---')
    cfs = bbg.bds('US912828YK09 Govt', 'CASH_FLOW')
    print(cfs.head())

    print('\n--- get_portfolio_data: enrich positions ---')
    positions = pd.DataFrame({
        'bloomberg_ticker': [
            'SPY US Equity',
            'US912828YK09 Govt',
            'EURUSD Curncy',
            None,             # direct property: skip Bloomberg
        ],
        'instrument_name' : [
            'SPDR S&P 500',
            'US Treasury 2.875 2028',
            'EUR/USD Forward',
            'Office Luxembourg City',
        ],
        'market_value_eur': [5234200, 4821000, 2246800, 12500000],
    })
    enriched = bbg.get_portfolio_data(positions)
    print(enriched[['instrument_name', 'PX_LAST',
                     'DUR_ADJ_MID', 'BETA', 'CRNCY']])