"""
Data output path helpers.

Centralizes path construction for all generated outputs under /data.
Supports organized structure by content type and valuation/reporting date.

Structure:
    data/
    ├── positions/
    │   └── {valuation_date}/
    │       └── {fund_id}.xlsx
    ├── reports/
    │   ├── annex_iv/
    │   │   └── {quarter}/
    │   │       ├── all_funds.xlsx
    │   │       └── {fund_id}.xlsx
    │   └── board_risk/
    │       └── {valuation_date}/
    │           └── board_risk_{valuation_date}.pdf
    ├── daily_exports/
    │   └── {export_date}/
    │       └── {fund_id}_{export_date}.xlsx
    └── [yf_cache/, risk_management.db — not managed by this module]
"""

from pathlib import Path
from typing import Optional


def positions_dir(base_data_dir: str, valuation_date: str) -> Path:
    """
    Get positions directory for a valuation date.

    Parameters
    ----------
    base_data_dir : str
        Base data directory (usually 'data' or '/path/to/data')
    valuation_date : str
        Valuation date (YYYY-MM-DD format)

    Returns
    -------
    Path
        Directory path: {base_data_dir}/positions/{valuation_date}/
    """
    return Path(base_data_dir) / 'positions' / valuation_date


def position_file(
    base_data_dir: str,
    fund_id: str,
    valuation_date: str
) -> Path:
    """
    Get position file path for a fund on a valuation date.

    Parameters
    ----------
    base_data_dir : str
        Base data directory
    fund_id : str
        Fund identifier (e.g., 'AIFM_HedgeFund')
    valuation_date : str
        Valuation date (YYYY-MM-DD format)

    Returns
    -------
    Path
        File path: {base_data_dir}/positions/{valuation_date}/{fund_id}.xlsx
    """
    return positions_dir(base_data_dir, valuation_date) / f'{fund_id}.xlsx'


def annex_iv_dir(base_data_dir: str, quarter: str) -> Path:
    """
    Get Annex IV reports directory for a quarter.

    Parameters
    ----------
    base_data_dir : str
        Base data directory
    quarter : str
        Reporting quarter (e.g., '2026Q1')

    Returns
    -------
    Path
        Directory path: {base_data_dir}/reports/annex_iv/{quarter}/
    """
    return Path(base_data_dir) / 'reports' / 'annex_iv' / quarter


def annex_iv_file(
    base_data_dir: str,
    quarter: str,
    fund_id: Optional[str] = None
) -> Path:
    """
    Get Annex IV report file path.

    Parameters
    ----------
    base_data_dir : str
        Base data directory
    quarter : str
        Reporting quarter (e.g., '2026Q1')
    fund_id : str, optional
        Fund identifier. If None, returns 'all_funds.xlsx'.
        If provided, returns '{fund_id}.xlsx'.

    Returns
    -------
    Path
        File path: {base_data_dir}/reports/annex_iv/{quarter}/[all_funds|{fund_id}].xlsx
    """
    filename = f'{fund_id}.xlsx' if fund_id else 'all_funds.xlsx'
    return annex_iv_dir(base_data_dir, quarter) / filename


def board_risk_dir(base_data_dir: str, valuation_date: str) -> Path:
    """
    Get board risk reports directory for a valuation date.

    Parameters
    ----------
    base_data_dir : str
        Base data directory
    valuation_date : str
        Valuation date (YYYY-MM-DD format)

    Returns
    -------
    Path
        Directory path: {base_data_dir}/reports/board_risk/{valuation_date}/
    """
    return Path(base_data_dir) / 'reports' / 'board_risk' / valuation_date


def board_risk_file(base_data_dir: str, valuation_date: str) -> Path:
    """
    Get board risk report file path.

    Parameters
    ----------
    base_data_dir : str
        Base data directory
    valuation_date : str
        Valuation date (YYYY-MM-DD format)

    Returns
    -------
    Path
        File path: {base_data_dir}/reports/board_risk/{valuation_date}/board_risk_{valuation_date}.pdf
    """
    return board_risk_dir(base_data_dir, valuation_date) / f'board_risk_{valuation_date}.pdf'


def daily_export_dir(base_data_dir: str, export_date: str) -> Path:
    """
    Get daily exports directory for a date.

    Parameters
    ----------
    base_data_dir : str
        Base data directory
    export_date : str
        Export date (YYYY-MM-DD format)

    Returns
    -------
    Path
        Directory path: {base_data_dir}/daily_exports/{export_date}/
    """
    return Path(base_data_dir) / 'daily_exports' / export_date


def daily_export_file(
    base_data_dir: str,
    fund_id: str,
    export_date: str
) -> Path:
    """
    Get daily export file path for a fund on a date.

    Parameters
    ----------
    base_data_dir : str
        Base data directory
    fund_id : str
        Fund identifier (e.g., 'AIFM_HedgeFund')
    export_date : str
        Export date (YYYY-MM-DD format)

    Returns
    -------
    Path
        File path: {base_data_dir}/daily_exports/{export_date}/{fund_id}_{export_date}.xlsx
    """
    return daily_export_dir(base_data_dir, export_date) / f'{fund_id}_{export_date}.xlsx'
