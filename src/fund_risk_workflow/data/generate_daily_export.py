"""
generate_daily_export.py
========================
Generates single-day position Excel files mimicking the daily
export sent by the fund administrator. Extracts a specific date
from the full position history and saves as a standalone file.

Usage
-----
    python3 -m fund_risk_workflow.data.generate_daily_export
"""

import pandas as pd
from pathlib import Path
import sys

ROOT_DIR   = Path(__file__).parent.parent.parent.parent  # src/fund_risk_workflow/data/ -> project root
sys.path.insert(0, str(ROOT_DIR / 'src'))

from fund_risk_workflow.data.paths import position_file, daily_export_file
from fund_risk_workflow.config import VALUATION_DATE

DATA_DIR   = ROOT_DIR / 'data'
EXPORT_DIR = ROOT_DIR / 'data' / 'daily_exports'
EXPORT_DIR.mkdir(exist_ok=True)

FUND_IDS = [
    'AIFM_HedgeFund',
    'AIFM_PrivateDebt',
    'AIFM_RealEstate',
    'UCITS_Balanced',
]

DATES = ['2026-03-30', '2026-03-31']  # Last two business days of available data


if __name__ == '__main__':
    for fund_id in FUND_IDS:
        filepath = position_file(str(DATA_DIR), fund_id, VALUATION_DATE)
        if not filepath.exists():
            print(f'Warning: {filepath} not found, skipping.')
            continue

        df = pd.read_excel(filepath)
        df['position_date'] = df['position_date'].astype(str)

        for date in DATES:
            daily = df[df['position_date'] == date].copy()
            if daily.empty:
                print(f'Warning: no data for {fund_id} on {date}')
                continue

            # Export boundary: rename position_date to generic 'date' for external format
            # (mimics fund administrator daily export files)
            daily = daily.rename(columns={'position_date': 'date'})

            out_file = daily_export_file(str(DATA_DIR), fund_id, date)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            daily.to_excel(out_file, index=False)
            print(f'Exported: {out_file.name} '
                  f'({len(daily)} positions)')