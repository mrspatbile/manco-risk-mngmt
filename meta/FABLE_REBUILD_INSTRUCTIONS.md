# Fable Execution Instructions: Rebuild `fund-risk-workflow` as a Clean Analytical Product

## Role

You are the execution agent.

You are working from an existing repository called `fund-risk-workflow`.

Treat this repository as the working product and source of truth.

Your job is to rebuild it into a cleaner, software-engineered version while preserving the outputs, notebooks, reports, plots, tables, datasets, and workflow experience that already exist.

This is not a research task.

This is not an architecture brainstorming task.

This is not a redesign from scratch.

This is not a generic risk-library exercise.

The final product should be a Python analytical application for investment fund risk workflows, where the package code is clean, tested, and reusable, and the notebooks remain simple, visual, and useful.

The product exists to let a user open a notebook and review a fund risk workflow with professional outputs.

The notebooks are not just examples. They are part of the product.

---

## Core Product Principle

The current notebooks and outputs define the product.

The clean implementation must support those outputs, not replace them with abstract engineering demos.

The rebuilt project must preserve this style:

- simple notebook calls
- clear sections
- readable outputs
- management-style tables
- regulatory-style tables
- charts and plots
- compact workflow functions
- no long manual construction of engines, providers, repositories, or configuration chains inside notebooks

The rebuilt project should expose workflow-level functions that hide internal implementation details.

Target notebook experience:

```python
workflow = build_hedge_fund_workflow(
    fund_id="AIFM_HedgeFund",
    valuation_date="2026-03-31",
)
display_hedge_fund_workflow(workflow)
```

```python
workflow = build_ucits_workflow(
    fund_id="UCITS_Balanced",
    valuation_date="2026-03-31",
)
display_ucits_workflow(workflow)
```

```python
report = build_annex_iv_report(
    fund_id="AIFM_HedgeFund",
    reporting_date="2026-03-31",
)
display_annex_iv_report(report)
```

```python
report = build_liquidity_report(
    fund_id="UCITS_Balanced",
    valuation_date="2026-03-31",
)
display_liquidity_report(report)
```

Internal architecture is allowed, but it must serve these workflows. It must not leak into the notebooks.

---

## Final Product Scope

The rebuilt project must support the core workflows already demonstrated in `fund-risk-workflow`.

Only preserve and clean what is already useful and demonstrable. Do not invent large new modules merely because a topic sounds relevant.

### 1. Hedge Fund Risk Workflow

Must include, where already present in the working repository:

- fund summary
- positions and exposures
- market risk analytics
- VaR
- Expected Shortfall
- VaR backtesting
- stress testing
- leverage analytics
- derivative exposure
- liquidity outputs
- management-style reporting tables
- charts and visual summaries

### 2. UCITS Balanced Workflow

Must include, where already present:

- UCITS fund summary
- portfolio composition
- market risk
- VaR / Expected Shortfall
- VaR backtesting
- SRRI
- UCITS global exposure / leverage monitoring
- UCITS stress scenarios
- liquidity monitoring
- regulatory-style summary outputs
- charts and formatted tables

### 3. Liquidity and LMT Workflow

Must include, where already present:

- asset liquidity profile
- redemption scenarios
- time-to-liquidation style outputs if available
- redemption path analysis
- LMT mechanics
- gates
- swing pricing
- suspension logic where already represented
- before / after LMT comparison
- NAV and liquidity impact charts
- clear visual outputs

### 4. Annex IV-Style Reporting

Must include, where already present:

- fund identification
- asset breakdown
- risk measures
- leverage
- liquidity profile
- formatted Annex IV-style tables
- export-oriented report objects where already implemented

### 5. PRIIPs / UCITS Reporting Outputs

Must include, where already present:

- PRIIPs-style result objects
- UCITS monitoring outputs
- risk indicators
- performance / stress style outputs where already implemented

### 6. Alternative Asset Analytics

If already present and useful, preserve outputs for:

- private equity
- infrastructure
- real estate
- private debt

Only preserve what is already useful and demonstrable. Do not invent large new modules.

---

## Output-First Rule

The rebuilt project must be output-first.

For every workflow, success means:

- the notebook runs
- the notebook is readable
- the same or better tables appear
- the same or better plots appear
- the same or better report sections appear
- calculations are moved into package code
- business logic is testable
- the notebook does not contain hidden business logic

---

## Data Rule

Use the data already used by `fund-risk-workflow`.

Do not invent alternative data sources.

Do not introduce new external market data systems unless they are already part of the working product.

Do not replace working enriched datasets with new generated data.

The rebuilt product should keep the current working data path unless there is a clear reason to simplify it.

If data is already enriched and sufficient for the workflow, use it directly.

---

## Notebook Rule

Notebooks must remain product-facing.

They should:

- explain the workflow briefly
- call high-level package functions
- display outputs
- show charts
- show tables
- remain readable by a finance/risk user

They should not:

- contain core calculations
- manually wire many low-level classes
- expose internal infrastructure
- become engineering demos
- require the user to understand the package internals

---

## Package Rule

Reusable logic should move into package modules.

The package should contain:

- data loading
- validation
- methodology configuration
- calculations
- report builders
- table formatters
- plotting helpers
- workflow builders

A reasonable target structure is:

```text
src/
  fund_risk/
    data/
      loaders.py
      validation.py
      schemas.py

    methodology/
      policies.py
      scenarios.py
      limits.py

    analytics/
      var.py
      expected_shortfall.py
      backtesting.py
      stress.py
      leverage.py
      liquidity.py
      lmt.py
      ucits.py
      derivatives.py
      alternatives.py

    reporting/
      management.py
      annex_iv.py
      priips.py
      ucits_monitoring.py
      liquidity_report.py

    visuals/
      tables.py
      plots.py
      styling.py

    workflows/
      hedge_fund.py
      ucits_balanced.py
      liquidity_lmt.py
      annex_iv.py
      alternatives.py

notebooks/
  hedge_fund_workflow.ipynb
  ucits_balanced_workflow.ipynb
  liquidity_lmt_workflow.ipynb
  annex_iv_workflow.ipynb
  alternatives_workflow.ipynb

data/
  existing working datasets and enriched inputs

tests/
  test_data_loaders.py
  test_var.py
  test_expected_shortfall.py
  test_backtesting.py
  test_stress.py
  test_leverage.py
  test_liquidity.py
  test_lmt.py
  test_reporting.py
  test_workflows.py
```

This structure is a guide, not an invitation to redesign endlessly. If the existing repository already has a better local convention, follow it.

---

## Implementation Approach

Work one complete workflow at a time.

For each workflow:

1. Open the existing working notebook.
2. Identify the actual outputs it produces.
3. Trace the functions and data used to produce those outputs.
4. Extract reusable calculation logic into package modules.
5. Extract reusable reporting and display logic into reporting / visuals modules.
6. Create one workflow builder function.
7. Rewrite the notebook so it calls the workflow builder and display helpers.
8. Add tests for the extracted logic.
9. Run the notebook and compare the output to the original.
10. Only then move to the next workflow.

Do not create broad scaffolding across the whole project before one workflow works end to end.

---

## Expected Workflow Builder Style

Each workflow module should return structured objects or dictionaries that are easy to display.

Example:

```python
workflow = build_ucits_workflow(
    fund_id="UCITS_Balanced",
    valuation_date="2026-03-31",
)
```

The returned object should contain:

- fund summary
- position summary
- risk metrics
- stress results
- leverage results
- liquidity results
- charts or chart-ready data
- report tables
- data quality notes

Display functions should be separate:

```python
display_ucits_summary(workflow)
display_market_risk(workflow)
display_stress_results(workflow)
display_leverage_results(workflow)
display_liquidity_results(workflow)
```

This keeps the notebook clear and lets the package remain testable.

---

# Software Engineering Requirements

The rebuilt project must not only reproduce the outputs. It must reproduce them through maintainable, tested package code.

The product description defines what must be preserved.

The engineering requirements define how it must be implemented.

Both are mandatory.

If there is a conflict, preserve the user-facing output, but implement it through the cleanest minimal package code needed.

---

## 1. Clear Separation of Responsibilities

Business logic must live in package modules, not notebooks.

Required separation:

- data loading and validation in data modules
- methodology assumptions and limits in methodology modules
- calculations in analytics modules
- report assembly in reporting modules
- plots and display helpers in visuals modules
- workflow orchestration in workflows modules
- notebooks only call workflows and display outputs

Notebooks may contain explanations and calls. They must not contain core formulas, data transformations, or business rules.

---

## 2. Workflow-Level Public API

Every notebook must be backed by one or more public workflow functions.

Examples:

- `build_hedge_fund_workflow(...)`
- `build_ucits_workflow(...)`
- `build_liquidity_lmt_workflow(...)`
- `build_annex_iv_report(...)`

The notebook must not manually instantiate low-level classes or pass long lists of raw attributes.

---

## 3. Typed Data Structures

Use typed objects where they improve clarity and safety.

Use dataclasses or Pydantic models for:

- fund summary objects
- position records where useful
- risk result objects
- stress result objects
- leverage result objects
- liquidity result objects
- report section objects
- workflow result objects

Avoid passing anonymous dictionaries everywhere unless the structure is very small and local.

---

## 4. Explicit Data Contracts

Every loader must define the fields it expects.

For every important input dataset, document:

- required columns
- date field
- fund identifier
- currency conventions
- percentage / decimal conventions
- monetary fields
- nullable fields
- expected granularity

If a required field is missing, raise a clear error.

---

## 5. No Hidden Global State

Do not make calculations depend on notebook variables, execution order, current working directory hacks, or implicit globals.

Workflow functions must accept explicit inputs such as:

- `fund_id`
- `valuation_date`
- `reporting_date`
- `data_dir`
- config path where needed

---

## 6. Reproducibility

The same function call with the same input data must produce the same result.

No random generation unless a seed is fixed and documented.

No live external data calls for core workflow outputs.

---

## 7. Tests

Add tests for extracted business logic.

Minimum test coverage per workflow:

- data loader test
- calculation test
- report builder test
- workflow smoke test

Tests should verify business outputs, not only that code runs.

Example checks:

- VaR is positive loss magnitude
- ES is greater than or equal to VaR
- leverage ratio uses NAV denominator correctly
- stress losses aggregate correctly
- report contains required sections
- workflow builder returns all required outputs

Do not over-test visual styling.

---

## 8. Golden-Output Checks Where Practical

For important migrated outputs, compare against known outputs from the current working repository.

Use small stable checks such as:

- expected number of rows
- expected report section names
- expected key metrics within tolerance
- expected chart-ready data columns
- expected scenario names

Do not rely only on visual inspection.

---

## 9. No Duplicate Calculations

Before adding a calculation, check whether the same calculation already exists.

If it exists:

- reuse it, or
- refactor it into a shared module

Do not create parallel versions of VaR, stress, leverage, liquidity, or reporting calculations unless there is a documented reason.

---

## 10. Minimal Abstraction

Do not add abstract base classes, provider layers, repositories, service layers, factories, or dependency injection unless they are needed by an actual workflow.

Prefer simple, readable functions until repeated workflow needs justify abstraction.

---

## 11. No Infrastructure Without a Workflow

A module is acceptable only if at least one notebook, report, workflow, or test uses it.

Do not create empty architecture scaffolding.

---

## 12. Configuration and Methodology Separation

Hardcoded methodology assumptions should be moved out of notebooks.

Where practical, store or centralise:

- VaR confidence level
- VaR horizon
- stress scenario definitions
- leverage limits
- liquidity thresholds
- LMT thresholds
- reporting dates
- fund-specific policies

These may be simple Python config objects or JSON files. Do not build a large configuration system unless needed.

---

## 13. Naming and Units

Names must make units clear.

Examples:

- `var_rate` for decimal percentage of NAV
- `var_amount` for currency amount
- `spread_bps` for basis points
- `haircut_rate` for decimal haircut
- `nav` for monetary NAV
- `exposure_amount` for currency exposure

Percentages must be stored as decimals, for example `0.05` for 5%.

VaR and Expected Shortfall should be positive loss magnitudes.

Returns and P&L remain signed.

---

## 14. Error Handling

Raise clear domain errors for:

- missing input file
- missing required columns
- unsupported fund ID
- unsupported valuation date
- insufficient price history
- invalid NAV
- invalid exposure
- invalid scenario configuration

Do not fail with obscure pandas `KeyError` or `IndexError` inside notebooks.

---

## 15. Documentation

Each workflow module should have a short docstring explaining:

- what workflow it builds
- expected inputs
- returned outputs
- major methodology assumptions

Each calculation module should document:

- formula or method
- units
- sign convention
- limitations

---

## 16. Code Quality Checks

At the end of each workflow implementation, run targeted tests.

At the end of the rebuild, run:

- ruff
- mypy if configured
- pytest

If full strict typing is not realistic immediately, document remaining typing gaps clearly.

---

## 17. Implementation Order

Do not create all folders first.

For each workflow, implement a vertical slice:

- loader
- calculation
- report object
- visual output
- notebook
- tests

Only add shared abstractions after two or more workflows need the same pattern.

---

## 18. Definition of Done Per Workflow

A workflow is done only when:

- the notebook runs end to end
- the notebook contains no hidden business logic
- the key outputs match the original working repository
- extracted calculations have tests
- the workflow can be called from one high-level function
- the code is readable and located in the correct modules
- no unnecessary infrastructure was added

---

# Execution Rules for Fable

## Do Not Redesign the Product

Do not create a new architecture proposal.

Do not debate scope.

Do not add alternative approaches.

Do not stop at analysis.

Implement the rebuild according to this instruction file and the existing working outputs.

---

## Execution Loop

For each workflow:

1. Read the current notebook and identify its outputs.
2. Trace only the files and functions needed for that workflow.
3. Extract reusable logic into package code.
4. Keep the notebook readable and output-facing.
5. Add focused tests.
6. Run targeted checks.
7. Report changed files and remaining gaps.
8. Move to the next workflow only after the current one works.

---

## Stop Conditions

Do not ask routine questions.

Only stop if:

- a required input file is missing
- two existing outputs contradict each other
- deleting code could lose unique business logic
- the instruction conflicts with the working notebook
- a calculation cannot be reproduced because the source logic is absent

Otherwise, proceed with the smallest clean implementation that preserves the output.

---

## What Not To Do

Do not create a generic risk engine library detached from the notebooks.

Do not start by designing infrastructure.

Do not replace the product with abstractions.

Do not build unused providers, repositories, or services.

Do not create alternative datasets.

Do not remove useful outputs because the old code is messy.

Do not preserve messy notebook code when it can be extracted cleanly.

Do not change the user-facing workflow style unless the result is simpler.

Do not spend time on perfect architecture before the first workflow works.

Do not create broad scaffolding that is not used by a current workflow.

Do not duplicate calculations already present in the repository.

---

# Final Deliverable

A rebuilt `fund-risk-workflow` project where:

- the same analytical workflows exist
- the notebooks are still pleasant to use
- the outputs are preserved or improved
- the implementation is cleaner
- calculations are reusable and tested
- data loading uses the existing working data path
- workflow-level APIs hide internal complexity
- the project remains focused on fund risk analytics, reporting, and review workflows

The final product should feel like `fund-risk-workflow` professionally rebuilt, not like a different abstract system.
