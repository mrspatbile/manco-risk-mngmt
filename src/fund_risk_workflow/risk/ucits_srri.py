"""
ucits_srri.py
============
UCITS Summary Risk Indicator (SRI) computation per CESR/10-673.

The SRRI is computed from 5 years of weekly NAV returns and mapped to a 1-7
category per the CESR/10-673 guidelines. The category is displayed on the KIID
and used for PRIIPs disclosure.

Key principles:
- 260 weekly observations (5 years)
- Annualised volatility computed as: sigma_weekly * sqrt(52)
- 7 volatility buckets (1-7) with fixed boundaries
- KID update triggered if SRI changes for 4 consecutive months
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple


# CESR/10-673 SRI bucket boundaries (annualised volatility %)
SRRI_BOUNDARIES = {
    1: (0.0, 0.5),
    2: (0.5, 2.0),
    3: (2.0, 5.0),
    4: (5.0, 10.0),
    5: (10.0, 15.0),
    6: (15.0, 25.0),
    7: (25.0, np.inf),
}


def compute_srri_from_returns(
    returns: pd.Series,
    annualisation_factor: int = 52,
) -> dict:
    """
    Compute SRRI category and volatility metrics from return series.

    Parameters
    ----------
    returns : pd.Series
        Weekly returns (decimal, e.g., 0.01 for 1%)
    annualisation_factor : int, default 52
        Number of periods per year (52 for weekly, 252 for daily)

    Returns
    -------
    dict
        {
            'sri_bucket': int (1-7),
            'volatility_weekly_pct': float,
            'volatility_annual_pct': float,
            'observation_count': int,
            'time_window_years': float,
        }
    """
    if returns.empty:
        raise ValueError("Returns series cannot be empty")

    volatility_weekly = returns.std()
    volatility_annual = volatility_weekly * np.sqrt(annualisation_factor)
    sri_bucket = map_volatility_to_srri_bucket(volatility_annual * 100)

    time_window_years = len(returns) / annualisation_factor

    return {
        'sri_bucket': sri_bucket,
        'volatility_weekly_pct': volatility_weekly * 100,
        'volatility_annual_pct': volatility_annual * 100,
        'observation_count': len(returns),
        'time_window_years': time_window_years,
    }


def map_volatility_to_srri_bucket(annualised_volatility_pct: float) -> int:
    """
    Map annualised volatility to SRRI category per CESR/10-673.

    SRRI boundaries:
        1: < 0.5%
        2: 0.5% - 2%
        3: 2% - 5%
        4: 5% - 10%
        5: 10% - 15%
        6: 15% - 25%
        7: >= 25%

    Parameters
    ----------
    annualised_volatility_pct : float
        Annualised volatility as percentage (e.g., 12.5 for 12.5%)

    Returns
    -------
    int
        SRRI category 1-7
    """
    for bucket, (lower, upper) in SRRI_BOUNDARIES.items():
        if lower <= annualised_volatility_pct < upper:
            return bucket

    # Fallback (should not reach here if boundaries are complete)
    return 7


def compute_srri_from_nav_history(
    nav_series: pd.Series,
    window_weeks: int = 260,
) -> dict:
    """
    Compute SRRI from NAV history using a rolling 5-year window.

    Parameters
    ----------
    nav_series : pd.Series
        Daily or weekly NAV values, indexed by date
    window_weeks : int, default 260
        Window size in weeks (standard is 260 for 5 years)

    Returns
    -------
    dict
        {
            'sri_bucket': int,
            'volatility_annual_pct': float,
            'window_weeks': int,
            'data_points': int,
            'status': str,  # 'OK' if sufficient data, 'INSUFFICIENT_DATA' otherwise
        }

    Raises
    ------
    ValueError
        If nav_series is empty or all NaN
    """
    if nav_series.empty or nav_series.isna().all():
        raise ValueError("NAV series cannot be empty or all NaN")

    # Ensure index is datetime
    if not isinstance(nav_series.index, pd.DatetimeIndex):
        nav_series.index = pd.to_datetime(nav_series.index)

    # Resample to weekly (last value of each week)
    nav_weekly = nav_series.resample('W').last()

    # Get trailing window
    if len(nav_weekly) < window_weeks:
        status = 'INSUFFICIENT_DATA'
        actual_window = len(nav_weekly)
    else:
        status = 'OK'
        actual_window = window_weeks
        nav_weekly = nav_weekly.iloc[-actual_window:]

    # Compute returns
    returns_weekly = nav_weekly.pct_change().dropna()

    # Compute SRRI
    result = compute_srri_from_returns(returns_weekly, annualisation_factor=52)
    result['window_weeks'] = actual_window
    result['status'] = status

    return result


def check_srri_change_trigger(
    current_bucket: int,
    bucket_history: pd.Series,
    persistence_months: int = 4,
) -> Tuple[bool, dict]:
    """
    Check if SRRI has changed for persistence_months consecutive months.

    Per CESR/10-673, a KID update is triggered if the SRI changes category for
    4 consecutive months.

    Parameters
    ----------
    current_bucket : int
        Current SRRI bucket (1-7)
    bucket_history : pd.Series
        Historical SRRI buckets, indexed by month-end dates
    persistence_months : int, default 4
        Number of consecutive months required to trigger update

    Returns
    -------
    tuple
        (trigger: bool, details: dict)
        Details includes: months_at_current, consecutive_months_different, status

    Raises
    ------
    ValueError
        If bucket_history is empty
    """
    if bucket_history.empty:
        raise ValueError("bucket_history cannot be empty")

    # Count consecutive months at current level vs initial level
    initial_bucket = bucket_history.iloc[0]
    consecutive_at_current = 0

    for bucket in bucket_history.iloc[-persistence_months:]:
        if bucket == current_bucket:
            consecutive_at_current += 1
        else:
            break

    # Check if we have persistence_months of the new bucket
    # (meaning the bucket CHANGED and stayed changed for persistence_months)
    changed = current_bucket != initial_bucket
    trigger = changed and consecutive_at_current >= persistence_months

    return trigger, {
        'initial_bucket': initial_bucket,
        'current_bucket': current_bucket,
        'changed': changed,
        'consecutive_months_at_current': consecutive_at_current,
        'persistence_threshold_months': persistence_months,
        'trigger': trigger,
    }


def srri_as_string(bucket: int) -> str:
    """Convert SRRI bucket number to descriptive string."""
    descriptions = {
        1: 'Very Low Risk',
        2: 'Low Risk',
        3: 'Low to Medium Risk',
        4: 'Medium Risk',
        5: 'Medium to High Risk',
        6: 'High Risk',
        7: 'Very High Risk',
    }
    return descriptions.get(bucket, f'Category {bucket}')


def compute_srri_from_fund(engine, fund_id: str) -> dict:
    """Compute SRRI from fund NAV history."""
    from fund_risk_workflow.data.database import query_nav_history

    nav_history_full = query_nav_history(engine, fund_id)
    nav_history_full['date'] = pd.to_datetime(nav_history_full['date'])
    nav_history_full = nav_history_full.set_index('date')

    cutoff = nav_history_full.index.max() - pd.DateOffset(weeks=260)
    nav_history_5y = nav_history_full[nav_history_full.index >= cutoff]

    weekly_nav = nav_history_5y['nav_eur'].resample('W').last()
    weekly_ret = weekly_nav.pct_change().dropna()
    sigma_weekly = weekly_ret.std()
    sigma_ann = sigma_weekly * np.sqrt(52)

    sri_bucket = map_volatility_to_srri_bucket(sigma_ann * 100)

    return {
        'sri_bucket': sri_bucket,
        'volatility_annual_pct': sigma_ann * 100,
        'observation_count': len(weekly_ret),
        'description': srri_as_string(sri_bucket),
    }


def compute_srri_rolling_monthly(
    engine,
    fund_id: str,
    as_of_date: str,
    current_disclosed_srri: int = None,
    window_weeks: int = 260,
    persistence_months: int = 4,
) -> dict:
    """
    Compute rolling monthly SRRI and check KIID update trigger.

    Queries NAV history from positions table, resamples to weekly, and computes SRRI at each
    month-end using a trailing 260-week window. Checks for 4-month persistence of SRRI
    category change versus the officially disclosed SRRI to determine KIID update trigger.

    Parameters
    ----------
    engine : sqlalchemy.Engine
    fund_id : str
    as_of_date : str
        Valuation date (YYYY-MM-DD), used to determine "current" status
    current_disclosed_srri : int, required
        The officially disclosed/current SRRI category (1-7).
        KIID update is triggered only if computed SRRI differs from this baseline
        and persists for the configured number of months.
        Must be explicitly provided; will not be inferred from history.
    window_weeks : int, default 260
        Rolling window size in weeks (standard: 260 for 5 years)
    persistence_months : int, default 4
        Number of consecutive months required for KIID update trigger

    Returns
    -------
    dict
        {
            'rolling_srri_df': pd.DataFrame with columns [date, srri, volatility_pct],
            'current_srri': int (1-7),
            'current_disclosed_srri': int (1-7) or None,
            'current_volatility_pct': float,
            'baseline_missing': bool, True if current_disclosed_srri was not provided,
            'kiid_update_required': bool, False if baseline_missing is True,
            'trigger_dates': list of dates where trigger occurred,
            'window_weeks': int,
            'persistence_months': int,
        }

    Notes
    -----
    - A 260-week NAV window produces 259 weekly returns (pct_change drops first NaT)
    - Month-end rows are filtered to on_or_before as_of_date (no future month-ends)
    - If current_disclosed_srri is None, baseline_missing=True and kiid_update_required=False
    """
    from fund_risk_workflow.data.database import query_nav_history

    # Query NAV history (computed from positions table)
    nav_df = query_nav_history(engine, fund_id)

    if nav_df.empty:
        raise ValueError(f"No NAV history found for {fund_id}")

    nav_df['date'] = pd.to_datetime(nav_df['date'])
    as_of_date_ts = pd.Timestamp(as_of_date)
    nav_series = nav_df.set_index('date')['nav_eur']

    # Resample to weekly (last value of each week)
    nav_weekly = nav_series.resample('W').last()

    # Month-end dates from the weekly series, filtered to on-or-before as_of_date
    all_monthly_ends = nav_weekly.resample('ME').last().index
    monthly_ends = all_monthly_ends[all_monthly_ends <= as_of_date_ts]

    # Compute SRRI at each month-end
    rolling_srri_records = []
    for month_end in monthly_ends:
        # Get trailing 260 weeks from this month-end
        window_start = month_end - pd.DateOffset(weeks=window_weeks)
        window_data = nav_weekly[(nav_weekly.index > window_start) & (nav_weekly.index <= month_end)]

        if len(window_data) < 52:  # At least 1 year of data
            continue

        # Compute weekly returns and SRRI
        # 260-week window -> 259 weekly returns (pct_change drops first NaT)
        weekly_ret = window_data.pct_change().dropna()
        return_observation_count = len(weekly_ret)

        if return_observation_count < 52:
            continue

        sigma_weekly = weekly_ret.std()
        sigma_ann = sigma_weekly * np.sqrt(52)
        sri_bucket = map_volatility_to_srri_bucket(sigma_ann * 100)

        # User-facing record (no observation count in display)
        rolling_srri_records.append({
            'date': month_end,
            'srri': sri_bucket,
            'volatility_pct': sigma_ann * 100,
            # Internal validation: return_observation_count is ~259 for 260-week window
            # Not included in display table per user request
        })

    rolling_srri_df = pd.DataFrame(rolling_srri_records)

    if rolling_srri_df.empty:
        raise ValueError(f"Insufficient data to compute rolling SRRI for {fund_id}")

    # Extract current SRRI (most recent month-end)
    current_row = rolling_srri_df.iloc[-1]
    current_srri = current_row['srri']
    current_volatility = current_row['volatility_pct']

    # Check if disclosed SRRI baseline was provided
    baseline_missing = current_disclosed_srri is None

    # Check KIID update trigger: current SRRI differs from disclosed AND persists
    # If baseline is missing, do not trigger and return baseline_missing flag
    trigger_dates = []
    kiid_update_required = False

    if not baseline_missing:
        # KIID update is required only if:
        # 1. Current SRRI != disclosed SRRI, AND
        # 2. Current SRRI has persisted for configured months (from recent backwards)
        if current_srri != current_disclosed_srri and len(rolling_srri_df) >= persistence_months:
            # Count consecutive recent months at current_srri (from end backwards)
            consecutive_at_current = 0
            for idx in range(len(rolling_srri_df) - 1, -1, -1):
                if rolling_srri_df.iloc[idx]['srri'] == current_srri:
                    consecutive_at_current += 1
                else:
                    break

            if consecutive_at_current >= persistence_months:
                kiid_update_required = True
                # Record when trigger was satisfied (when persistence threshold reached)
                trigger_dates = [rolling_srri_df.iloc[len(rolling_srri_df) - consecutive_at_current]['date']]

    return {
        'rolling_srri_df': rolling_srri_df,
        'current_srri': int(current_srri),
        'current_disclosed_srri': int(current_disclosed_srri) if current_disclosed_srri is not None else None,
        'current_volatility_pct': float(current_volatility),
        'baseline_missing': baseline_missing,
        'kiid_update_required': kiid_update_required,
        'trigger_dates': trigger_dates,
        'window_weeks': window_weeks,
        'persistence_months': persistence_months,
    }
