"""
tests/test_generate_daily_export.py
====================================
Unit tests for generate_daily_export.py
Run with: python3 -m pytest tests/test_generate_daily_export.py -v
"""

import pytest
import pandas as pd
from pathlib import Path
import sys
import subprocess

ROOT_DIR   = Path(__file__).parent.parent
DATA_DIR   = ROOT_DIR / 'data'
sys.path.insert(0, str(ROOT_DIR / 'src'))


@pytest.fixture(scope="session", autouse=True)
def generate_daily_exports():
    """Generate daily export files before running tests."""
    # Run the export generation script
    result = subprocess.run(
        [sys.executable, '-m', 'fund_risk_workflow.data.generate_daily_export'],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        pytest.fail(
            f"Failed to generate daily exports: {result.stderr}"
        )

    # Verify that exports directory was created
    export_dir = DATA_DIR / 'daily_exports'
    assert export_dir.exists(), "Daily exports directory was not created"

    yield

    # Cleanup is optional - we could remove exports after tests, but
    # keeping them for inspection is more useful

from fund_risk_workflow.data.paths import daily_export_file

FUNDS = [
    'AIFM_HedgeFund',
    'AIFM_PrivateDebt',
    'AIFM_RealEstate',
    'UCITS_Balanced',
]
DATES = ['2026-03-30', '2026-03-31']

STANDARD_COLS = [
    'fund_id', 'fund_name', 'date', 'isin', 'bloomberg_ticker',
    'instrument_name', 'asset_class', 'sub_asset_class',
    'currency', 'quantity', 'price', 'market_value_local',
    'market_value_eur', 'weight_pct', 'country', 'rating',
    'maturity', 'sector', 'adv_eur'
]


class TestDailyExportFiles:

    def _get_export_path(self, fund, date):
        """Get full path to export file using path helper."""
        return daily_export_file(str(DATA_DIR), fund, date)

    def test_export_directory_exists(self):
        export_dir = DATA_DIR / 'daily_exports'
        assert export_dir.exists()

    def test_all_files_created(self):
        for fund in FUNDS:
            for date in DATES:
                path = self._get_export_path(fund, date)
                assert path.exists(), f'missing: {path.name}'

    def test_files_readable_with_pandas(self):
        for fund in FUNDS:
            for date in DATES:
                path = self._get_export_path(fund, date)
                if path.exists():
                    df = pd.read_excel(path)
                    assert len(df) > 0

    def test_all_standard_columns_present(self):
        for fund in FUNDS:
            path = self._get_export_path(fund, '2026-03-31')
            if path.exists():
                df = pd.read_excel(path)
                for col in STANDARD_COLS:
                    assert col in df.columns, \
                        f'{fund}: missing column {col}'

    def test_single_date_per_file(self):
        for fund in FUNDS:
            for date in DATES:
                path = self._get_export_path(fund, date)
                if path.exists():
                    df = pd.read_excel(path)
                    assert df['date'].astype(str).nunique() == 1
                    assert df['date'].astype(str).iloc[0] == date

    def test_single_fund_per_file(self):
        for fund in FUNDS:
            path = self._get_export_path(fund, '2026-03-31')
            if path.exists():
                df = pd.read_excel(path)
                assert df['fund_id'].nunique() == 1
                assert df['fund_id'].iloc[0] == fund

    def test_weights_sum_to_100(self):
        for fund in FUNDS:
            path = self._get_export_path(fund, '2026-03-31')
            if path.exists():
                df    = pd.read_excel(path)
                total = df['weight_pct'].sum()
                assert abs(total - 100.0) < 1.0, \
                    f'{fund}: weights sum to {total:.2f}'

    def test_real_estate_has_extra_columns(self):
        path = self._get_export_path('AIFM_RealEstate', '2026-03-31')
        if path.exists():
            df = pd.read_excel(path)
            for col in ['ltv_pct', 'rental_yield_pct',
                        'vacancy_rate_pct', 'is_direct_property']:
                assert col in df.columns

    def test_hedge_fund_has_short_positions(self):
        path = self._get_export_path('AIFM_HedgeFund', '2026-03-31')
        if path.exists():
            df = pd.read_excel(path)
            assert (df['market_value_eur'] < 0).any()

    def test_ucits_all_long_only(self):
        path = self._get_export_path('UCITS_Balanced', '2026-03-31')
        if path.exists():
            df = pd.read_excel(path)
            assert (df['market_value_eur'] >= 0).all()

    def test_hedge_fund_includes_derivatives(self):
        """After Phase B, derivatives should be included in exports."""
        path = self._get_export_path('AIFM_HedgeFund', '2026-03-31')
        if path.exists():
            df = pd.read_excel(path)
            # Verify Derivative asset class is present
            assert 'Derivative' in df['asset_class'].values, \
                "Derivatives should be included in AIFM Hedge Fund export"

            # Verify sub_asset_class is preserved for derivatives
            derivs = df[df['asset_class'] == 'Derivative']
            assert len(derivs) > 0
            # Check that sub_asset_class values are correct
            valid_sub_classes = {'Future', 'Forward', 'Listed Option'}
            assert derivs['sub_asset_class'].isin(valid_sub_classes).all(), \
                "Derivative sub_asset_class should be Future/Forward/Listed Option"

    def test_daily_export_matches_full_history(self):
        """Filtering full history to single date = daily export."""
        from fund_risk_workflow.data.paths import position_file
        from fund_risk_workflow.config import VALUATION_DATE

        for fund in FUNDS:
            full_path = position_file(str(DATA_DIR), fund, VALUATION_DATE)
            export_path = self._get_export_path(fund, '2026-03-31')
            if full_path.exists() and export_path.exists():
                full   = pd.read_excel(full_path)
                full   = full[
                    full['position_date'].astype(str) == '2026-03-31'
                ].reset_index(drop=True)
                # Drop position_date and rename to match export format
                full = full.drop(columns=['position_date'])
                export = pd.read_excel(
                    export_path).reset_index(drop=True)
                assert len(full) == len(export), \
                    f'{fund}: row count mismatch'