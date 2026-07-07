# fund-risk-workflow

## What this project is

`fund-risk-workflow` is a structured finance and risk research project.

It simulates the workflow of a risk analyst working with UCITS and AIFs under Luxembourg / CSSF-style oversight. The project is structured as a fund risk workflow environment, with clear scope limits:

- it is not a production system
- the valuation date is static
- the data is controlled and partly simulated
- portfolio positions are mostly fixed by design
- valuation engines are simplified
- notebooks remain part of the research workflow

The project focuses on:
- fund data workflows
- risk analytics
- regulatory interpretation
- reporting workflows
- data enrichment
- Python package organisation
- notebook-to-code refactoring

The repository should be understandable from both a finance and technical perspective, with clear links between fund risk concepts, data workflows, calculations and generated outputs.

## Core design principle

Keep a clear separation between:

- raw computation
- data access and enrichment
- workflow orchestration
- fund risk monitoring
- regulatory reporting
- investor disclosures
- governance reporting
- notebook rendering

Prefer clear workflow separation over unnecessary abstraction. This is not a production platform.

## Current architecture direction

Use this structure as the guiding model:

```text
src/
├── computation/
├── pipeline/
├── reporting/
├── data/
├── risk/
├── ui/
└── tools/
```

### `src/computation/`

Raw calculations only.

Current modules:

```text
var.py                      # VaR, Expected Shortfall (historical and parametric)
stress.py                   # Stress testing and scenario analysis
liquidity.py                # Liquidity profiling and bucket classification
liquidity_calibration.py    # Liquidity weight calibration
leverage.py                 # Leverage calculation (notional, gross, net)
attribution.py              # P&L attribution by position and factor
derivatives.py              # Derivative exposure and Greeks computation
```

These modules should not perform database writes, file exports, notebook rendering, or regulatory interpretation.

### `src/pipeline/`

Reusable workflows that orchestrate data loading, enrichment, and computation.

Current pipelines:

```text
fixed_position_var.py           # VaR pipeline for position-based funds
liquidity_policy.py             # Liquidity profiling and calibration workflow
lmt_trigger_analysis.py         # LMT trigger evaluation for UCITS
validate.py                     # Pipeline input validation and data quality checks
```

Pipelines should produce raw or structured outputs. They should not silently impose fund-specific regulatory rules unless that is explicitly in scope.

See `src/pipeline/README.md` for detailed pipeline documentation.

### `src/reporting/`

Board reports, regulatory reports, and disclosure outputs.

Examples:

```text
board_report.py
annex_iv.py
annex_iv_export.py
annex_iv_workflow.py
```

Regulatory interpretation belongs here or in dedicated regulatory workflow modules, not inside raw computation.

### `src/data/`

Database access, mock Bloomberg, enrichment, generated data helpers, and reference-data loading helpers.

Current modules:

```text
database.py                 # SQLAlchemy ORM models and DB creation
setup_db.py                 # Idempotent database initialization
load_fund_metadata.py       # Fund metadata loading from reference data
load_positions.py           # Position data loading from Excel
enrichment.py               # Position enrichment (Bloomberg sensitivities, ESG)
mock_bloomberg.py           # Simulated market data and sensitivities
generate_positions.py       # Generate position Excel files for liquid funds
generate_pe_fund.py         # Generate PE portfolio company data
generate_infra_fund.py      # Generate infrastructure asset data
reference_data.py           # Loaders for reference data JSON files
benchmark_builder.py        # Reference portfolio loading
operational_checks.py       # Data quality and validation checks
generate_daily_export.py    # Fund-admin export simulation
paths.py                    # Data path utilities
```

### `src/risk/`

Risk aggregation, compliance orchestration, and asset-class-specific workflows.

**General-purpose:**
- `risk_utils.py` — risk aggregation and monitoring summaries
- `var_backtest.py` — VaR backtesting and exception reporting

**UCITS-specific regulatory workflows:**
- `ucits_var_monitoring.py` — UCITS VaR monitoring and limits
- `ucits_relative_var.py` — tracking error and relative VaR
- `ucits_srri.py` — Summary Risk Indicator (PRIIPs KID)
- `ucits_stress_scenarios.py` — UCITS stress testing

**Asset-class helpers:**
- `pe_utils.py` — private equity NAV projection, cash flows, covenant analysis
- `infra_utils.py` — infrastructure covenant monitoring, refinancing risk
- `esg_utils.py` — ESG score aggregation, SFDR PAI metrics

**Leverage monitoring:**
- `leverage_config.py` — AIFMD leverage classification mapping
- `leverage_computation.py` — leverage calculation and policy checks

**Other:**
- `pnl_attribution.py` — P&L decomposition by component
- `reg_constants.py` — regulatory thresholds and classification mappings

See `src/risk/README.md` for detailed module documentation and guidance on adding new functions.

### `src/ui/`

Notebook display helpers, chart helpers, and rendering utilities.

Examples:

```text
display_dark_table()
display_var_es()
display_ucits_monthly_report()
plot_var_backtest()
plot_liquidity_buckets()
plot_attribution()
annex_iv_display.py         # Annex IV report formatting
```

Display functions take computed results and render them as styled HTML tables or charts for notebooks.

### `src/tools/`

Data maintenance and utility scripts.

Current tools:

```text
clean_data_outputs.py       # Safe cleanup of regenerated data folders
```

These are operational utilities, not part of the core workflow.

## Current notebook structure direction

Organize notebooks by content domain and audience:

```text
notebooks/
├── data_workflows/              # Data access and validation (technical)
│   ├── 01_data_layer_workflow.ipynb
│   └── 02_operational_checks.ipynb
├── funds/                       # Fund-level risk monitoring (per fund)
│   ├── aifm_hedge_fund.ipynb
│   ├── aifm_pe_buyout.ipynb
│   ├── aifm_infra_fund.ipynb
│   ├── aifm_private_debt.ipynb
│   ├── aifm_real_estate.ipynb
│   └── ucits_balanced.ipynb
├── liquidity_management/        # LMT mechanics and stress testing
│   └── liquidity_management.ipynb
├── portfolio_management/        # Portfolio analysis notebooks
│   └── *.ipynb
└── reports/                     # Governance and regulatory reporting
    ├── board_risk_report.ipynb
    └── ucits_priips_kid.ipynb
```

**`data_workflows/`** contains technical notebooks explaining:
- Database access and structure
- Mock Bloomberg / market data loading
- Position enrichment workflow
- Reference data loaders
- How data flows into the computation layer

**`funds/`** contains fund-level risk monitoring notebooks organized by fund ID (not regulatory category). Each notebook demonstrates:
- Daily risk snapshot for a fund
- VaR, liquidity, and leverage monitoring (where applicable)
- Stress testing and scenario analysis
- Regulatory compliance checks (UCITS or AIFMD)

**`reports/`** contains governance and reporting outputs:
- Board risk report
- PRIIPs KID and investor disclosures
- Regulatory filings (AIFMD Annex IV)

Future notebooks should follow this pattern: start with `data_workflows/` to understand the data layer, then explore fund-specific notebooks.

## Static valuation date

`VALUATION_DATE` is intentionally static:

```text
2026-03-31
```

Do not make it dynamic.

Do not introduce date-range logic unless a ticket explicitly asks for it.

All analytics are point-in-time by design.

## Position behaviour

Portfolio positions are intentionally stable in the mock dataset, except where a specialised generator explicitly creates a different behaviour, such as PE cash flows.

Do not introduce live portfolio-update logic unless a ticket explicitly asks for it.

## Reference data direction

Reference data should be explicit and fund-level where appropriate.

Target structure:

```text
reference_data/
├── funds/
│   ├── fund_registry.json
│   └── <fund_id>/
│       ├── fund_profile.json
│       ├── risk_policy.json
│       ├── position_specs.json
│       └── asset_specs.json
├── regulation/
│   ├── ucits_regulatory_framework.json
│   ├── aifmd_annex_iv_framework.json
│   ├── priips_kid_framework.json
│   └── sfdr_disclosure_framework.json
├── instruments/
├── portfolios/
├── counterparties/
└── investors/
```

### `fund_registry.json`

Operational list only.

It tells the system which funds exist and should be loaded.

It should not contain detailed fund characteristics.

### `fund_profile.json`

Static fund facts and regulatory classification flags.

Examples:

```text
fund_id
fund_name
fund_type
strategy
currency
domicile
regulator
inception_date
target_nav_eur
is_ucits
is_aif
is_annex_iv_reportable
is_priips_kid_required
is_sfdr_article_6
is_sfdr_article_8
is_sfdr_article_9
```

### `risk_policy.json`

Fund-specific internal risk framework and monitoring choices.

Examples:

```text
redemption_terms
notice_period_days
lockup_days
liquidity_profile
valuation_frequency
internal leverage limits
internal concentration limits
LTV or covenant monitoring thresholds
stress scenario choices
VaR usage and parameters where explicitly applicable
```

### `reference_data/regulation/`

Central regulatory framework files.

Do not create fund-level `regulatory_limits.json`.

Regulatory rules should be centralised by framework and triggered by fund-level flags.

## Regulatory distinction

Do not treat all funds the same.

### AIFMD

AIFMD does not prescribe one universal VaR limit, confidence level, holding period, lookback window, or concentration limit for all AIFs.

For AIFs, methodology choices must be adequate, defined, documented, and supported by the fund strategy, risk profile, liquidity profile, and complexity.

AIFMD Annex IV is a reporting framework. It should be treated as a ManCo / AIFM-level reporting process covering all relevant AIFs.

Use:

```text
reference_data/regulation/aifmd_annex_iv_framework.json
```

for central Annex IV reporting structure and reporting-field logic.

Use this wording for Annex IV references:

```text
Delegated Regulation (EU) 231/2013 Article 110 and Annex IV reporting template
```

Do not use “AIFMD Annex VI reporting”.

### UCITS

UCITS is different.

UCITS global exposure, commitment approach, absolute VaR, relative VaR, and related limits or model assumptions must be treated as UCITS-specific regulatory logic.

Use:

```text
reference_data/regulation/ucits_regulatory_framework.json
```

for central UCITS rules and parameters.

Do not duplicate UCITS regulatory limits inside a fund-level `risk_policy.json`.

### PRIIPs

PRIIPs is a disclosure framework.

It relates to KID production, Summary Risk Indicator (SRI), performance scenarios, and costs.

Do not mix PRIIPs logic into AIFMD risk management logic.

Use:

```text
reference_data/regulation/priips_kid_framework.json
```

for central PRIIPs KID / SRI logic.

### SFDR

SFDR is a regulatory disclosure framework.

It should not be reduced to an ESG score.

Current ESG indicators should be treated as raw ESG or sustainability-risk indicators unless explicitly mapped to SFDR concepts such as:

- Article 6
- Article 8
- Article 9
- PAIs
- pre-contractual disclosures
- website disclosures
- periodic disclosures

Use:

```text
reference_data/regulation/sfdr_disclosure_framework.json
```

for central SFDR disclosure logic.

### EMIR

EMIR is relevant where funds use derivatives.

It should be handled as a dedicated derivatives regulatory reporting and controls workflow covering:

- derivatives reporting checks
- counterparty classification checks
- clearing obligation checks where applicable
- risk mitigation controls for non-cleared OTC derivatives
- collateral / margin workflow checks where applicable
- reconciliation and data quality checks

Do not mix EMIR logic into generic VaR, AIFMD Annex IV, UCITS global exposure, PRIIPs, or SFDR logic.

## Risk calculation rule

The repository has reusable calculators.

Risk is not computed automatically for every fund or every asset.

Notebooks and pipelines decide:

- which calculator to call
- for which fund
- for which asset sleeve
- with which assumptions

Do not assume that VaR applies to every fund or every asset class.

Do not automatically apply VaR to:

- real estate
- private equity
- infrastructure
- private debt

For mixed funds, separate the sleeves before interpreting the risk metrics.

For real estate, distinguish:

```text
direct properties
listed REITs
FX hedge
cash
```

Direct properties should not be treated as daily traded securities merely because the current mock data contains daily position snapshots.

Listed REITs, FX, and cash may still be treated as position-style holdings where appropriate.

## Fund treatment

Position-based AIFs may share a risk snapshot pipeline where appropriate.

Examples:

```text
AIFM_HedgeFund
AIFM_PrivateDebt
```

`AIFM_RealEstate` is currently a mixed fund and should not be blindly treated as a pure liquid position-based fund. It may eventually need a sleeve-based workflow.

UCITS may reuse computation functions, but UCITS regulatory interpretation must remain separate.

Private equity and infrastructure have different data models and should not be forced into a standard VaR-based pipeline.

The following funds are treated as closed-ended for fund-level policy configuration:

```text
AIFM_PE_Buyout
AIFM_Infra_Core
AIFM_RealEstate
```

## Reporting and disclosure distinction

Regulatory reporting includes:

```text
AIFMD Annex IV
UCITS global exposure monitoring
EMIR derivatives reporting and controls
regulatory reporting controls
```

Investor disclosures include:

```text
PRIIPs KID
SFDR disclosures
investor reporting packs
```

Governance reporting includes:

```text
board risk reports
monthly risk monitoring reports
risk committee packs
exception reports
```

AIFMD Annex IV reporting should be treated as a ManCo / AIFM-level process covering all relevant AIFs, not as a hedge fund notebook output.

SFDR disclosure monitoring should be cross-fund.

PRIIPs KID generation should cover only funds distributed to retail investors.

## How we work together

Do not make changes without checking with the user first.

Preferred flow for every task:

1. Read the relevant Linear issue before touching anything.
2. Explain your understanding of the task and proposed approach.
3. Wait for go-ahead before writing or changing code.
4. Make changes one logical step at a time.
5. After each step, explain what changed and why.
6. At the end, list changed files, validation performed, risks, and open questions.

The user manages commits manually in VS Code.

Do not commit.

Do not push.

Do not stage files unless explicitly asked.

Do not provide git commands unless explicitly asked.

Do not add Claude or any AI tool as co-author.

## Things to never do without explicit permission

- refactor across multiple files in one go
- change data structures or schemas
- delete or rename anything
- touch `.venv/`
- touch environment configuration
- create new Linear tickets
- edit notebooks unless the ticket says so
- change business logic unless the ticket says so
- change numerical outputs unless the ticket says so
- create empty modules
- move old notebook logic blindly into production code

## Validation expectations

For code changes, run:

```text
python3 -m compileall src
```

Run relevant tests where available.

For notebook-related work, confirm no notebooks were modified unless the ticket explicitly allowed it.

For documentation-only work, show:

```text
git diff --stat
```

## Display function pattern

Display functions in `src/ui/` follow this signature:

```python
def display_<report_name>(
    results: dict,                      # computed results from risk calculations
    risk_df: pd.DataFrame,              # enriched position data
    limits: dict,                       # risk limits/thresholds
    valuation_date: str,                # point-in-time valuation
    fund_id: str,                       # fund identifier
    col_widths: dict | None = None,     # optional styling overrides
):
    """Display structured report as HTML table."""
```

This pattern keeps computations separate from rendering. Notebooks import and call these functions with minimal code:

```python
from fund_risk_workflow.ui.print_html_utils import display_ucits_monthly_report

display_ucits_monthly_report(
    results={...},
    risk_df=...,
    limits={...},
    valuation_date=...,
    fund_id=...,
)
```

Minimize arguments by grouping related computed values into dicts. The function handles all formatting and rendering internally.

## Code style

- PEP 8 throughout.
- Type hints on public functions and methods.
- Docstrings on public classes and functions.
- State non-obvious conventions in docstrings, especially percent vs decimal and annualised vs daily.
- No new dependencies without flagging first.
- Prefer readable names and explicit function signatures.

## Current Linear issues

```text
MRS-178  Add Claude refactor playbook - done
MRS-179  Reorganize reference data and document the data workflow - done
MRS-194  Add fund-level reference data and risk policy configuration - done
MRS-180  Create risk snapshot pipeline for position-based AIFs - done
MRS-181  Extend standard/cleaning to UCITS notebook - done
MRS-182  Complete liquidity management nb - done

```

## Scope boundary

This project is a structured finance and risk workflow environment.
There is a separate project, `quant-risk-engine`, focused on production-grade OOP design, QuantLib integration, and regulatory capital calculations.

Do not import architectural patterns from that project unless explicitly requested.

If something works and is clear, it is good enough here.
