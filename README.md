# fund-risk-workflow

![Python](https://img.shields.io/badge/Python-3.13-blue)
![SQLite](https://img.shields.io/badge/DB-SQLite-003B57?logo=sqlite\&logoColor=white)
[![AIFMD II](https://img.shields.io/badge/Reg-AIFMD%20II-orange)](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024L0927)
[![UCITS VI](https://img.shields.io/badge/Reg-UCITS%20VI-blue)](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32024L0927)


`fund-risk-workflow` is a Python and notebook-led repository for fund risk workflows using simulated UCITS and AIFM-style fund data. It covers market risk, liquidity risk, redemption pressure, private-asset monitoring, leverage monitoring, pre-trade checks, LMT mechanics and reporting outputs.

---

## Current Coverage

| Workflow | Scope |
| --- | --- |
| AIFM Hedge Fund Long/Short | VaR, Expected Shortfall, backtesting, LVaR, stress testing, redemption stress, leverage, pre-trade checks, ESG, Annex IV-style outputs |
| UCITS Balanced | UCITS eligibility, global exposure, VaR and ES, relative VaR, SRRI, stress testing, liquidity and redemption monitoring, counterparty checks, pre-trade checks, ESG |
| AIFM PE Buyout | Portfolio-company appraisals, covenant monitoring, J-curve, waterfalls, value bridge, funding liquidity, PME, PE stress, ESG, Annex IV-style outputs |
| AIFM Infrastructure | Asset-level NAV, DSCR and LTV covenants, concentration, inflation and duration, cash-flow liquidity, stress testing, ESG, Annex IV-style outputs |
| AIFM Private Debt | Credit profile, maturity ladder, leverage, credit and rate stress, borrower default stress, closed-ended investor concentration, ESG, Annex IV-style outputs |
| AIFM Real Estate | Sleeve separation, direct-property monitoring, LTV stress, tenant concentration and default stress, ESG, Annex IV-style outputs |
| Liquidity and LMT mechanics | Point-in-time redemption stress, dynamic redemption path, gates, swing-pricing trigger, suspension indicator, deferred redemption backlog |
| Data and reporting workflows | Data-layer inspection, operational checks, Board risk report, UCITS investor-disclosure notebook |


## Example outputs

<div style="text-align: center;">
    <img src="fig/AIFM_HedgeFund/09_var_backtest.png" width="80%">
</div>

<br>

---
<br>
<div style="text-align: center;">
    <img src="fig/UCITS_Balanced_liquidity/09_redemption_path_after_lmt.png" width="80%">
</div>
<br>

---

<br>
<div style="text-align: center;">
    <img src="fig/UCITS_Balanced/10_srri_monitoring.png" width="80%">
</div>
<br>


---

<br>
<div style="text-align: center;">
    <img src="fig/AIFM_HedgeFund/21_pre_trade_check.png" width="60%">
</div>
<br>



## Where to start

|  |  |  |
| --- | --- | --- |
| Data layer workflow | [`notebook`](notebooks/data_workflows/01_data_layer_workflow.ipynb) | database, market-data and enrichment context |
| Operational checks | [`notebook`](notebooks/data_workflows/02_operational_checks.ipynb) | database and enrichment checks |
| Hedge fund risk workflow | [`notebook`](notebooks/funds/aifm_hedge_fund.ipynb) | [`outputs`](fig/AIFM_HedgeFund) |
| UCITS balanced workflow | [`notebook`](notebooks/funds/ucits_balanced.ipynb) | [`outputs`](fig/UCITS_Balanced) |
| PE buyout workflow | [`notebook`](notebooks/funds/aifm_pe_buyout.ipynb) | [`outputs`](fig/AIFM_PE_Buyout) |
| Infrastructure workflow | [`notebook`](notebooks/funds/aifm_infra_fund.ipynb) | [`outputs`](fig/AIFM_Infra_Core) |
| Private debt workflow | [`notebook`](notebooks/funds/aifm_private_debt.ipynb) | [`outputs`](fig/AIFM_PrivateDebt) |
| Real estate workflow | [`notebook`](notebooks/funds/aifm_real_estate.ipynb) | [`outputs`](fig/AIFM_RealEstate) |
| Liquidity and LMT mechanics | [`notebook`](notebooks/liquidity_management/liquidity_management.ipynb) | [`outputs`](fig/UCITS_Balanced_liquidity) |
| Board risk report | [`notebook`](notebooks/reports/board_risk_report.ipynb) | PDF report output |
| UCITS investor disclosure | [`notebook`](notebooks/reports/ucits_priips_kid.ipynb) | UCITS / PRIIPs-style internal disclosure workflow |

---

## Risk analytics examples



### Market risk

* VaR
* Expected Shortfall
* VaR backtesting
* P&L attribution
* stress scenarios
* private-asset valuation sensitivity

### Liquidity risk

* liquidity profiling
* redemption pressure
* investor concentration
* liquidity-adjusted VaR
* selected liquidity stress assumptions
* closed-ended funding liquidity
* asset-level cash-flow liquidity

### Leverage and constraints

* leverage monitoring
* issuer and sector concentration examples
* property and project covenant monitoring
* portfolio-company covenant monitoring
* pre-trade checks

### Liquidity Management Tools

The repository includes a simplified LMT mechanics example for a UCITS-style fund under a 12-month redemption scenario. It shows how redemption pressure, liquid asset coverage and tool triggers can be represented in Python.

* redemption gate threshold
* deferred redemption backlog
* swing pricing threshold
* behavioral feedback


---

## Data and assumptions

The repository uses simulated fund, position and market data. Fund data are stored in SQLite. Market data use a Bloomberg-style local pipeline.

Key assumptions:

* fund holdings are simulated
* liquidity buckets are assumption-driven
* LMT thresholds are illustrative
* outputs are reporting-oriented examples, not filing-ready reports

---

## Status and limitations

This repository uses simulated data and simplified assumptions.
Regulatory context: [UCITS Directive 2009/65/EC](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0065), [AIFMD 2011/61/EU](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32011L0061), [Commission Delegated Regulation (EU) No 231/2013](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32013R0231), [Directive (EU) 2024/927](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024L0927), [ESMA liquidity stress testing guidelines](https://www.esma.europa.eu/sites/default/files/library/esma34-39-897_guidelines_on_liquidity_stress_testing_in_ucits_and_aifs_en.pdf), [ESMA LMT guidelines](https://www.esma.europa.eu/sites/default/files/2025-04/ESMA34-1985693317-1095_Final_Report_on_the_Guidelines_on_LMTs_of_UCITS_and_open-ended_AIFs.pdf).

Implemented areas include:

* hedge fund market risk and liquidity monitoring
* UCITS-style risk and eligibility examples
* private equity, infrastructure, private debt and real estate AIF examples
* LMT mechanics under redemption pressure
* Annex IV-style reporting outputs
* board and investor-disclosure notebooks
* local data and output generation

Current limitations:

* simulated fund, position and market data
* simplified risk and liquidity assumptions
* illustrative LMT thresholds

A more structured package implementation is under development in `manco-risk`.


---

## Setup

```bash
git clone https://github.com/mrspatbile/fund-risk-workflow
cd fund-risk-workflow
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .
python3 -m fund_risk_workflow.data.setup_db --force
python3 -m fund_risk_workflow.data.generate_daily_export
```

### Cleaning regenerated outputs

Use the cleanup script to remove regenerated output folders when you want to rerun the workflow from generated source files.

The script removes:

- `data/positions/`
- `data/reports/`
- `data/daily_exports/`

It does not remove:

- `data/risk_management.db`
- `data/yf_cache/`

This means the database is preserved. If you delete positions and want the database to reflect regenerated position files, rerun the position generation and database setup workflow afterwards.

```bash
# Dry-run: shows what would be deleted
python3 scripts/clean_data_outputs.py

# Confirm deletion
python3 scripts/clean_data_outputs.py --confirm
```
