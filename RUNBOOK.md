# Runbook

## Environment setup

#### 1. Create and activate virtual environment
```bash 
python3.13 -m venv .venv
source .venv/bin/activate
```

#### 2. Install all dependencies (editable so src/ imports work)
```bash 
pip install -e .
```

#### 3. Install Playwright browser (required for save_table_png)
```bash 
playwright install chromium
```

#### 4. Database initialisation and synthetic data generation

Step 1 — rebuild schema, regenerate all fund data, reload and enrich positions
```bash 
python3 -m fund_risk_workflow.data.setup_db --force
```

Step 2 — generate daily fund-admin export slices (fake FA files per fund/date)
```bash 
python3 -m fund_risk_workflow.data.generate_daily_export
```

What `--force` does, in order:

- Drops and recreates the full schema
- Regenerates 250-day Excel position histories for the funds (HF, PD, RE, UCITS)
- Loads positions into positions table
- Enriches positions → positions_enriched (Bloomberg sensitivities, fund-admin data)
- Runs `generate_pe_fund` → PE tables
- Runs `generate_infra_fund` → infra tables (assets, NAV history, debt, covenants)
- The daily export is not part of `setup_db` — always run it separately after.

#### 5. Regenerating individual fund data
If you only need to regenerate one component without a full DB rebuild:


5.1. Liquid fund Excel files only (HF, PD, RE, UCITS)
```bash 
python3 -m fund_risk_workflow.data.generate_positions
```

5.2.  PE fund tables only (requires DB schema already exists)
```bash 
python3 -c "from fund_risk_workflow.data.database import get_engine; from fund_risk_workflow.data.generate_pe_fund import generate_pe_fund; generate_pe_fund(get_engine())"
```

5.3.  Infra fund tables only (requires DB schema already exists)
```bash 
python3 -c "from fund_risk_workflow.data.database import get_engine; from fund_risk_workflow.data.generate_infra_fund import generate_infra_fund; generate_infra_fund(get_engine())"
```

5.4. Validate the full pipeline
```bash
python3 -m fund_risk_workflow.pipeline.validate
```

#### 6. Cleaning generated outputs

To remove regenerated data outputs (positions, reports, daily exports) without touching the database or cache:

Dry-run (shows what would be deleted):
```bash
python3 scripts/clean_data_outputs.py
```

Confirm deletion:
```bash
python3 scripts/clean_data_outputs.py --confirm
```

This removes:
- `data/positions/`
- `data/reports/`
- `data/daily_exports/`

Protected (never deleted):
- `data/risk_management.db`
- `data/yf_cache/`


## Notebook execution sequence

Open notebooks from the project root with the virtual environment active.

Recommended entry points:

| Area | Notebook | Generated outputs |
| --- | --- | --- |
| Data workflow | [`notebooks/data_workflows/02_operational_checks.ipynb`](notebooks/data_workflows/02_operational_checks.ipynb) | database and enrichment checks |
| Hedge fund risk monitoring | [`notebooks/funds/aifm_hedge_fund.ipynb`](notebooks/funds/aifm_hedge_fund.ipynb) | [`fig/AIFM_HedgeFund`](fig/AIFM_HedgeFund) |
| UCITS balanced workflow | [`notebooks/funds/ucits_balanced.ipynb`](notebooks/funds/ucits_balanced.ipynb) | [`fig/UCITS_Balanced`](fig/UCITS_Balanced) |
| Liquidity management tools | [`notebooks/liquidity_management/liquidity_management.ipynb`](notebooks/liquidity_management/liquidity_management.ipynb) | [`fig/UCITS_Balanced_liquidity`](fig/UCITS_Balanced_liquidity) |
| Board risk report | [`notebooks/reports/board_risk_report.ipynb`](notebooks/reports/board_risk_report.ipynb) | board report output |

All notebooks use the static valuation date:

```text
2026-03-31
```

Charts, HTML tables and notebook-generated images are saved under `fig/<fund_id>/` or a workflow-specific `fig/` subfolder. 

## Testing

Run tests from the project root with the virtual environment active.

#### Install package for testing (recommended)
```bash
pip install -e .
```

This installs the package in editable/development mode, registering `fund_risk_workflow` in Python's path.

After editable install, run tests normally:
```bash
pytest tests/test_operational_checks.py -v
pytest tests/test_mock_bloomberg.py -v
python3 -m pytest tests/ -v  # Run all tests
```

#### Without editable install

If you haven't run `pip install -e .`, use `-m` flag to add current directory to Python path:
```bash
python3 -m pytest tests/test_operational_checks.py -v
```

#### Code compilation check
```bash
python3 -m compileall src
```

---

## Annex IV export

Run from a notebook or script to export all AIFM funds:

```python
from fund_risk_workflow.data.database import get_engine
from fund_risk_workflow.reporting.annex_iv import export_annex_iv_excel

ENGINE = get_engine()
quarter = '2026-03-31'

export_annex_iv_excel(ENGINE, quarter=quarter)
```

Output:
- `data/reports/annex_iv/2026Q1/all_funds.xlsx`
- `data/reports/annex_iv/2026Q1/AIFM_HedgeFund.xlsx` (single fund)

## Board risk report

The board risk report is generated from the board reporting notebook:

```text
notebooks/reports/board_risk_report.ipynb
```

The output is a self-contained PDF covering the AIFM-level risk view.

Output location:

```text
data/reports/board_risk/<valuation_date>/board_risk_<valuation_date>.pdf
```


## Common errors and fixes

#### Module not found
```bash
ModuleNotFoundError: fund_risk_workflow
```
Run from the project root with the `venv` active. Ensure you've run `pip install -e .` to register the package.

---

#### Table not found

```bash
no such table: positions
DB schema missing. 
```

Build the database by running:
```bash 
python3 -m fund_risk_workflow.data.setup_db --force
```
---

#### `yfinance` returns empty prices

Price cache may be stale or the ticker has changed. Delete the relevant file in
`data/yf_cache/` and rerun `python3 -m fund_risk_workflow.data.setup_db`. The data from `yfinance` will refetch automatically.

---

#### Playwright TimeoutError on `save_table_png`

Run `playwright install chromium` to ensure the browser binary is present.

---


#### nest_asyncio error in notebook

`nest_asyncio.apply()` is called at import time in `nb_utils.py`. If it errors,
ensure `nest_asyncio` is installed: `pip install nest_asyncio`.

---


#### Infra covenant breach count unexpected
`generate_infra_fund` uses a fixed random seed per asset. If you change noise
profiles or capital structure in `generate_infra_fund.py`, rerun
`python3 -m fund_risk_workflow.data.setup_db --force` to regenerate. 

The Example baked in the infra portfolio has "intentionally" 2 designed breaches: 
- INFRA_003 Q2 2020 DSCR
- INFRA_007 Q3 2023 LTV




