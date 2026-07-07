# src/pipeline/

Reusable workflows that orchestrate data loading, computation, and output formatting. Pipelines translate business requirements into step-by-step execution: retrieve positions, apply enrichment, run calculations, aggregate results.

## Pipeline Overview

### `fixed_position_var.py`

**Purpose:** VaR calculation pipeline for funds with fixed or slowly-changing position snapshots.

**Main functions:**
- `compute_fixed_position_pnl_series()` — reconstruct 250-day P&L history from daily position snapshots
- `compute_var_from_pnl()` — extract VaR (historical or parametric) at specified confidence level
- `compute_es()` — expected shortfall (conditional VaR)

**Inputs:**
- Daily position snapshots from database: `positions_enriched`
- Market prices and sensitivities: enriched columns (ir_duration, equity_beta, fx_delta, etc.)
- Valuation date: point-in-time for risk calculation

**Outputs:**
- Dictionary: `{'var_95': float, 'var_99': float, 'es_95': float, 'es_99': float, ...}`
- Can be used as-is or passed to reporting pipelines

**When to use:**
- Hedge fund risk monitoring (AIFM_HedgeFund)
- UCITS balanced fund monitoring (UCITS_Balanced)
- Any liquid AIF where VaR is appropriate

**When NOT to use:**
- Real estate funds (illiquid; use direct property valuation)
- Private equity funds (use NAV-based risk, not position-based VaR)
- Infrastructure funds (use covenant and debt structure risk, not position-based VaR)

**Example:**
```python
from fund_risk_workflow.pipeline.fixed_position_var import compute_fixed_position_pnl_series, compute_var_from_pnl
from fund_risk_workflow.data.database import get_engine
from fund_risk_workflow.config import VALUATION_DATE

engine = get_engine()
fund_id = 'AIFM_HedgeFund'

# Step 1: Build P&L history
pnl_series = compute_fixed_position_pnl_series(engine, fund_id, VALUATION_DATE)

# Step 2: Calculate VaR
var_results = compute_var_from_pnl(pnl_series, confidence=0.99, horizon=1)
print(f"VaR 99%: {var_results['var_99']:.2f}")
```

---

### `liquidity_policy.py`

**Purpose:** Liquidity profiling and calibration for position-based funds.

**Main functions:**
- `compute_liquidity_buckets()` — classify positions by liquidity profile (1-day, 1-week, 1-month, etc.)
- `compute_asset_level_liquidity()` — per-position average daily volume (ADV) analysis
- `calibrate_liquidity_assumptions()` — load fund-specific calibration inputs
- `compute_liquid_asset_coverage()` — fund-level percentage of holdings liquid within thresholds

**Inputs:**
- Positions with ADV and market value: `positions_enriched`
- Liquidity calibration parameters: `reference_data/funds/<fund_id>/liquidity_calibration_inputs.json`
- Fund risk policy: `reference_data/funds/<fund_id>/risk_policy.json`

**Outputs:**
- Dictionary: `{'bucket_1d': float, 'bucket_1w': float, 'bucket_1m': float, 'illiquid': float}`
- Can be used to inform LMT thresholds or redemption stress assumptions

**When to use:**
- Liquidity management and stress testing workflows
- UCITS LMT (Liquidity Management Tool) mechanics
- Redemption pressure analysis under stress

**Example:**
```python
from fund_risk_workflow.pipeline.liquidity_policy import (
    calibrate_liquidity_assumptions,
    compute_liquidity_buckets
)
from fund_risk_workflow.data.reference_data import load_liquidity_calibration_inputs

calibration = load_liquidity_calibration_inputs(
    reference_data_dir, 'UCITS_Balanced'
)
buckets = compute_liquidity_buckets(risk_df, calibration)
```

---

### `lmt_trigger_analysis.py`

**Purpose:** Liquidity Management Tool (LMT) trigger evaluation for UCITS funds under redemption stress.

**Main functions:**
- `evaluate_lmt_triggers()` — check gate, swing pricing, and deferred redemption triggers
- `compute_redemption_backlog()` — forecast pending redemption queue
- `compute_swing_pricing_trigger()` — check if swing pricing threshold breached
- `apply_gates()` — simulate redemption gating under stress

**Inputs:**
- Current fund NAV and daily liquidity bucket data
- Redemption pressure (inflows/outflows): fund-specific parameter
- LMT thresholds: `risk_policy.json`
- Stress scenario assumptions (redemption intensity, liquidity stress)

**Outputs:**
- Dictionary: `{'gate_triggered': bool, 'swing_triggered': bool, 'backlog_days': int, ...}`
- Redemption flow timeline showing when investors receive proceeds

**When to use:**
- UCITS liquidity stress testing (ESMA guidelines)
- LMT mechanics examples and governance reporting
- Redemption gating analysis

**Note:** LMT triggers are illustrative thresholds for this example; consult fund documentation and ESMA guidelines for regulatory requirements.

**Example:**
```python
from fund_risk_workflow.pipeline.lmt_trigger_analysis import evaluate_lmt_triggers
from fund_risk_workflow.data.reference_data import load_rmp

risk_policy = load_rmp(reference_data_dir, 'UCITS_Balanced')
lmt_status = evaluate_lmt_triggers(
    nav=fund_nav,
    liquidity_buckets=buckets,
    redemption_flow=outflows_millions,
    risk_policy=risk_policy
)
```

---

### `validate.py`

**Purpose:** Data quality and schema validation for the pipeline.

**Main functions:**
- `validate_positions_table()` — check positions table structure and completeness
- `validate_enriched_data()` — verify enriched columns present and valid
- `validate_reference_data()` — check fund profiles, risk policies loaded
- `validate_pipeline_inputs()` — end-to-end pipeline input validation

**Inputs:**
- Database connection
- Fund ID and valuation date
- Optional: reference data directory

**Outputs:**
- Validation report dictionary: `{'status': 'pass|warn|fail', 'messages': [...]}`
- Raises `ValidationError` if critical issues found

**When to use:**
- Before running risk workflows (sanity check after setup)
- CI/CD pipeline validation
- Debugging data issues

**Example:**
```python
from fund_risk_workflow.pipeline.validate import validate_pipeline_inputs

report = validate_pipeline_inputs(
    engine=engine,
    fund_id='AIFM_HedgeFund',
    valuation_date='2026-03-31'
)
if report['status'] != 'pass':
    print("Validation issues:", report['messages'])
```

---

## Pipeline Design Principles

### 1. No Silent Regulatory Assumptions

Pipelines should not automatically apply regulatory rules (e.g., "all funds get VaR limits") unless explicitly scoped. Instead:

- Call the appropriate pipeline based on fund type / strategy
- Let notebooks and scripts decide which pipeline to invoke
- Fund-specific thresholds come from `risk_policy.json`, not hardcoded in pipeline

### 2. Inputs and Outputs Are Dictionaries or DataFrames

**Inputs:**
- Dictionary of configuration/assumptions (loaded from reference data)
- DataFrame of positions (from database)
- Scalar parameters (confidence level, horizon, fund ID, date)

**Outputs:**
- Dictionary of computed results (can be serialized, passed to reporting)
- DataFrame for tabular outputs (positions enriched with results)

Avoid side effects like direct file writes or database updates.

### 3. Idempotent

Running the same pipeline twice with identical inputs should produce identical outputs. No random state, no time-dependent behavior.

### 4. Composable

Pipelines are built from computation functions. A pipeline orchestrates:
1. Load positions
2. Filter/aggregate
3. Call `computation/` functions
4. Format and return results

Do not bury computation logic inside pipelines. Separate computation from orchestration.

---

## Adding New Pipelines

### When to Create a Pipeline

Create a new pipeline when:
- A multi-step workflow repeats across notebooks or scripts
- The workflow involves data loading, filtering, and multiple computation steps
- The output is reusable (dictionary or DataFrame)
- A non-technical user needs to understand the workflow

### Template

```python
"""
my_workflow.py
==============
Brief description of the workflow.

Main functions:
- function_1() — does X
- function_2() — does Y

When to use: (which funds, scenarios, regulatory contexts)

Example:
    from fund_risk_workflow.pipeline.my_workflow import main_function
    results = main_function(engine, fund_id, VALUATION_DATE, config)
"""

from typing import Dict, Any
import pandas as pd
from sqlalchemy.engine import Engine

def main_function(
    engine: Engine,
    fund_id: str,
    valuation_date: str,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Execute the workflow.
    
    Parameters
    ----------
    engine : Engine
        Database connection
    fund_id : str
        Fund identifier
    valuation_date : str
        Point-in-time valuation date (ISO 8601)
    config : dict
        Configuration dictionary (assumptions, thresholds, etc.)
    
    Returns
    -------
    dict
        Results dictionary with keys: result_1, result_2, ...
    """
    # Step 1: Load data
    risk_df = pd.read_sql(...)
    
    # Step 2: Filter/prepare
    risk_df = risk_df[...]
    
    # Step 3: Call computation functions
    from fund_risk_workflow.computation import some_function
    results = some_function(risk_df, config)
    
    # Step 4: Format and return
    return {
        'results': results,
        'metadata': {'fund_id': fund_id, 'date': valuation_date}
    }
```

---

## Related Modules

- **`src/computation/`** — Raw calculation functions called by pipelines
- **`src/risk/`** — Asset-class and regulatory workflow helpers
- **`src/reporting/`** — Output generation (board reports, Annex IV, etc.)
- **`src/data/`** — Database and reference data loaders
