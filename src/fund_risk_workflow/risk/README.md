# src/risk/

Risk aggregation, compliance orchestration, and asset-class-specific helpers. This module provides functions for translating computed risk metrics into actionable monitoring summaries, regulatory outputs, and asset-class workflows.

## Module Organization

### General-Purpose Risk Utilities

**`risk_utils.py`**  
Risk aggregation and monitoring summaries. Central module for extracting computed results and formatting them for reporting.

- `compute_var_monitoring_summary()` — aggregate VaR results across positions
- `compute_liquidity_summary()` — position-level liquidity profiling
- `aggregate_concentration()` — issuer and sector concentration rollups
- `compute_redemption_pressure()` — fund-level redemption flows

**When to use:** Call from reporting pipelines to translate computed risk dictionaries into dataframes ready for output.

---

### UCITS-Specific Regulatory Logic

UCITS Directive 2009/65/EC prescribes specific VaR methodologies, SRI calculation, and global exposure limits. These modules handle UCITS regulatory compliance independently from AIF workflows.

**`ucits_var_monitoring.py`**  
UCITS VaR monitoring under Annex X of the UCITS Directive.

- `compute_ucits_absolute_var()` — absolute VaR at UCITS confidence level (99%)
- `compute_ucits_relative_var()` — relative VaR vs. benchmark
- `apply_ucits_var_limits()` — check against fund-specific limits from `risk_policy.json`
- `ucits_var_monitoring_summary()` — formatted monitoring output

**When to use:** UCITS_Balanced or any UCITS fund requiring regulatory VaR monitoring.

**`ucits_relative_var.py`**  
Relative VaR (fund returns vs. benchmark returns) for UCITS tracking-focused funds.

- `compute_relative_var()` — tracking error and relative VaR calculation
- `compute_benchmark_returns()` — reference portfolio return series

**When to use:** Relative VaR workflows; typically for index-tracking or low-volatility UCITS.

**`ucits_srri.py`**  
Summary Risk Indicator (SRI) for UCITS PRIIPs KID disclosures.

- `compute_srri()` — derive SRI (1-7 scale) from volatility or VaR
- `map_volatility_to_srri()` — classification mapping
- `srri_performance_scenarios()` — forward-looking scenarios for KID

**When to use:** PRIIPs KID generation for UCITS distributed to retail investors.

**`ucits_stress_scenarios.py`**  
UCITS regulatory stress scenarios (interest rates, equity shocks, etc.).

- `apply_ucits_stress_scenarios()` — scenario-based stress testing
- `ucits_scenario_library()` — load and manage scenario definitions
- `compute_stress_pnl()` — P&L impact per scenario

**When to use:** Stress testing workflows and regulatory reporting for UCITS.

---

### Asset-Class-Specific Helpers

**`pe_utils.py`**  
Private equity fund utilities: capital call forecasting, valuation tracking, and covenant monitoring.

- `compute_pe_nav_projection()` — forecast NAV based on exit assumptions
- `compute_pe_cash_flow_waterfall()` — LP-level IRR and return projection
- `compute_pe_covenant_status()` — portfolio-level covenant breach summary
- `compute_pe_liquidity_pressure()` — capital call pressure analysis

**When to use:** PE fund monitoring workflows (AIFM_PE_Buyout).

**`infra_utils.py`**  
Infrastructure fund utilities: concession term analysis, debt coverage monitoring, and inflation assumption tracking.

- `compute_infra_nav_trajectory()` — NAV projection based on cash flows and terminal value
- `compute_covenant_coverage()` — DSCR and LTV headroom tracking
- `compute_refinancing_pressure()` — debt maturity ladder and refinancing risk
- `compute_inflation_impact()` — sensitivity to inflation linkage assumptions

**When to use:** Infrastructure fund monitoring workflows (AIFM_Infra_Core).

**`esg_utils.py`**  
ESG and sustainability risk utilities for SFDR and ESG monitoring.

- `compute_pai_metrics()` — Principal Adverse Impact indicators per SFDR
- `aggregate_esg_scores()` — fund-level ESG score rollup
- `identify_esg_controversies()` — flag positions with ESG concerns
- `compute_carbon_intensity()` — portfolio carbon footprint
- `classify_sfdr_article()` — Article 6/8/9 classification and monitoring

**When to use:** SFDR periodic disclosure generation and ESG monitoring workflows.

---

### Leverage Monitoring

**`leverage_config.py`**  
AIFMD leverage classification mapping (EU 231/2013 Art. 7).

- Leverage type classification: Cash, Synthetic, Embedded, Repo, Excluded
- Instrument-level AIFMD categorization
- Leverage calculation methods per asset type

**`leverage_computation.py`**  
Leverage calculation and monitoring.

- `compute_leverage_gross()` — gross leverage (sum of long and short exposures)
- `compute_leverage_net()` — net leverage (long - short)
- `compute_notional_leverage()` — derivatives notional exposure
- `check_leverage_limits()` — compare against fund risk policy thresholds

**When to use:** Leverage monitoring for AIFs (most common for hedge funds).

**Note:** This is separate from UCITS global exposure, which is handled in `ucits_*.py` modules.

---

### P&L & Attribution

**`pnl_attribution.py`**  
P&L decomposition: price, quantity, and FX attribution.

- `compute_pnl_attribution()` — decompose realized P&L by component
- `compute_factor_attribution()` — attribute returns to risk factors

**When to use:** Performance analysis and risk decomposition workflows.

---

### Computation Layers (Legacy / Coordination)

**`var.py` (legacy)**  
Deprecated. VaR computation has moved to `computation/var.py`. This file remains for backward compatibility and orchestration.

**`var_backtest.py`**  
VaR backtesting: exception reporting and PIT (Profit-in-Time) analysis.

- `compute_var_backtest()` — test historical VaR against realized P&L
- `compute_pit_exceptions()` — identify backtest failures (exceedances)
- `backtest_summary()` — reporting format for backtest results

**When to use:** Post-trade VaR validation and governance reporting.

---

### Regulatory Constants

**`reg_constants.py`**  
Central registry of regulatory thresholds and classification mappings.

- AIFMD leverage buckets and thresholds
- UCITS global exposure parameters
- SFDR classification mapping
- PRIIPs SRI classification table

**Note:** Do not duplicate these constants in `risk_policy.json`. Fund-specific overrides belong in `risk_policy.json`; regulatory defaults belong here.

---

## Adding New Risk Functions

### Decision: Computation vs. Risk

**Add to `src/computation/`** if the function:
- Computes a raw metric (VaR, ES, leverage ratio) from positions/prices
- Has no regulatory interpretation embedded
- Would apply to any fund or asset type

**Examples:** `var.py`, `stress.py`, `leverage.py`

**Add to `src/risk/`** if the function:
- Aggregates computed results for reporting
- Applies regulatory logic or asset-class workflows
- Wraps computation functions to produce actionable summaries
- Translates fund-specific policy into monitoring checks

**Examples:** `ucits_var_monitoring.py`, `leverage_computation.py`, `pe_utils.py`

### Naming Convention

- Module names reflect asset class or regulatory domain: `ucits_*.py`, `pe_*.py`, `infra_*.py`
- Function names are verb + object: `compute_*()`, `apply_*()`, `check_*()`, `aggregate_*()`
- Avoid single-letter module suffixes or abbreviations; be explicit

### Documentation

Every new module should start with a docstring summarizing:
1. Regulatory or business domain covered
2. Main public functions (with 1-line purpose)
3. When to call (which funds, workflows, scenarios)

Example:
```python
"""
pe_utils.py
===========
Private equity fund utilities: capital call forecasting, NAV projection, and covenant monitoring.

Public functions:
- compute_pe_nav_projection() — forecast NAV based on exit assumptions
- compute_pe_cash_flow_waterfall() — LP-level IRR projection
- compute_pe_covenant_status() — covenant breach summary

When to use: PE fund monitoring workflows (AIFM_PE_Buyout).
"""
```

---

## Related Modules

- **`src/computation/`** — Raw risk calculations (VaR, ES, leverage, stress)
- **`src/pipeline/`** — Orchestration (fixed_position_var, liquidity_policy, lmt_trigger_analysis)
- **`src/reporting/`** — Output generation (board_report, annex_iv, regulatory filings)
- **`src/data/reference_data.py`** — Loaders for risk policies and regulatory frameworks
