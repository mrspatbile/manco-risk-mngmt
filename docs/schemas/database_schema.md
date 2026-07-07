# Database Schema

## Overview

The `risk_management.db` SQLite database contains fund, position, instrument, and alternative asset data across four schema layers:

1. **Core holdings** — positions and instruments for liquid funds
2. **Private equity** — PE fund structures, portfolio companies, cash flows, and valuations
3. **Infrastructure** — infra fund structures, assets, debt, and covenants
4. **Enriched data** — market risk and ESG enhancements applied to core holdings

All dates are stored as ISO 8601 strings (`YYYY-MM-DD`).

---

## Core Tables

### `funds`

Fund metadata, loaded from `reference_data/funds/<fund_id>/fund_profile.json`.

| Column | Type | Notes |
|--------|------|-------|
| `fund_id` | String (PK) | Unique identifier (e.g., AIFM_HedgeFund, UCITS_Balanced) |
| `fund_name` | String | Display name |
| `fund_type` | String | UCITS or AIF |
| `currency` | String | Reporting currency (typically EUR) |
| `inception_date` | String | Fund launch date (ISO 8601) |
| `domicile` | String | Fund domicile (e.g., Luxembourg, Ireland) |
| `regulator` | String | Regulatory authority (e.g., CSSF, CBI) |
| `target_nav_eur` | Float | Target fund size in EUR |

**Populated by:** `load_fund_metadata()` during setup.  
**Source:** `reference_data/funds/<fund_id>/fund_profile.json`

---

### `instruments`

Instrument reference data (securities, bonds, equities, etc.).

| Column | Type | Notes |
|--------|------|-------|
| `isin` | String (PK) | International Securities Identification Number |
| `bloomberg_ticker` | String (nullable) | Bloomberg identifier for pricing |
| `instrument_name` | String | Security description |
| `asset_class` | String | Broad classification (Equity, Fixed Income, Alternative, etc.) |
| `sub_asset_class` | String (nullable) | Finer classification (Government Bond, Corporate Bond, etc.) |
| `currency` | String | Instrument currency |
| `country` | String (nullable) | Country of issuance or domicile |

**Populated by:** `load_positions()` from Excel position files; referenced by `positions`.  
**Note:** Instruments are loaded as positions are loaded; no independent instrument loader.

---

### `positions`

Daily position snapshots for all liquid funds. One row per position per date.

**Composite Primary Key:** Auto-increment `id` (internal).  
**Business Key:** `(fund_id, position_date, isin)`.  
**Indexes:**
- `ix_positions_fund_date_isin` — lookup specific position on a date
- `ix_positions_fund_date` — retrieve daily snapshot for a fund

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented row ID |
| `fund_id` | String (FK→funds) | Fund identifier |
| `fund_name` | String | Denormalized fund name |
| `position_date` | String | Snapshot date (ISO 8601) |
| `isin` | String | Security identifier |
| `bloomberg_ticker` | String (nullable) | Bloomberg ticker for pricing |
| `instrument_name` | String | Security description |
| `asset_class` | String | Broad asset class |
| `sub_asset_class` | String (nullable) | Finer asset class |
| `currency` | String | Position currency |
| `quantity` | Float | Units held |
| `price` | Float | Unit price in local currency |
| `market_value_local` | Float | Position value in local currency |
| `market_value_eur` | Float | Position value in EUR |
| `weight_pct` | Float | Percentage of fund NAV |
| `country` | String (nullable) | Country exposure |
| `rating` | String (nullable) | Credit rating (if applicable) |
| `maturity` | String (nullable) | Maturity date (if applicable) |
| `sector` | String (nullable) | Industry sector |
| `adv_eur` | Float (nullable) | Average daily volume in EUR (liquidity) |
| `ltv_pct` | Float (nullable) | Loan-to-value (real estate only) |
| `rental_yield_pct` | Float (nullable) | Annual rental yield (real estate only) |
| `vacancy_rate_pct` | Float (nullable) | Vacancy rate (real estate only) |
| `property_type` | String (nullable) | Type of property (real estate only) |
| `valuation_date` | String (nullable) | Valuation date (real estate only) |
| `is_direct_property` | Boolean (nullable) | True if direct property holding (vs. REIT) |
| `is_hedge` | Boolean (nullable) | True if hedging position |
| `esg_score` | Float (nullable) | ESG score (0-100) |
| `env_score` | Float (nullable) | Environmental sub-score |
| `soc_score` | Float (nullable) | Social sub-score |
| `gov_score` | Float (nullable) | Governance sub-score |
| `controversy_flag` | Boolean (nullable) | True if ESG controversy detected |
| `carbon_intensity` | Float (nullable) | tCO2e per EUR invested |

**Populated by:** `load_positions()` from Excel position files; enriched into `positions_enriched`.  
**Typical query:** All positions for a fund on a date: `SELECT * FROM positions WHERE fund_id = ? AND position_date = ? ORDER BY weight_pct DESC`.

---

### `positions_enriched`

Enriched positions with market risk sensitivities and ESG data. One row per position per date (mirrors `positions` structure with added columns).

**Business Key:** `(fund_id, position_date, isin)`.  
**Note:** Subset of columns shown; inherits all `positions` columns.

| Column (added) | Type | Notes |
|----------------|------|-------|
| `ir_oas_01` | Float (nullable) | Fixed income: interest rate sensitivity (OAS duration) |
| `ir_duration` | Float (nullable) | Fixed income: modified duration |
| `cr_oas_01` | Float (nullable) | Credit spread sensitivity |
| `fx_delta` | Float (nullable) | FX sensitivity (delta equivalent) |
| `equity_beta` | Float (nullable) | Equity beta (relative to index) |
| `option_delta` | Float (nullable) | Derivatives: option delta |
| `option_vega` | Float (nullable) | Derivatives: option vega |
| `implied_vol` | Float (nullable) | Derivatives: implied volatility |

**Populated by:** `enrich_positions()` which appends Bloomberg sensitivities to `positions` table.  
**Source:** `fund_risk_workflow.data.enrichment` module (Bloomberg mock data, reference_data ESG scores).  
**Note:** Enrichment is idempotent; existing rows are replaced.

---

## Private Equity Tables

### `pe_funds`

PE fund metadata.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `fund_id` | String (unique, not null) | Fund identifier (e.g., AIFM_PE_Buyout) |
| `fund_name` | String | Fund name |
| `vintage_year` | Integer | Vintage year (e.g., 2020) |
| `target_size_eur` | Float | Target fund size in EUR |
| `investment_period_end` | String (nullable) | Investment period end date |
| `fund_life_years` | Integer (nullable) | Expected fund life in years |
| `currency` | String (nullable) | Reporting currency |
| `domicile` | String (nullable) | Fund domicile |
| `strategy` | String (nullable) | Strategy description (Buyout, Growth, etc.) |

---

### `pe_portfolio_companies`

Portfolio company master data (independent of funds).

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `company_id` | String (unique, not null) | Company identifier (e.g., PE_001) |
| `company_name` | String | Company name |
| `sector` | String (nullable) | Industry sector |
| `country` | String (nullable) | Country of operation |
| `investment_stage` | String (nullable) | Stage (Growth, Buyout, etc.) |
| `status` | String (nullable) | Investment status (Active, Exited, etc.) |
| `description` | String (nullable) | Business description |

---

### `pe_fund_investments`

Link table: PE fund to portfolio company investment terms.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `fund_id` | String | PE fund ID |
| `company_id` | String | Portfolio company ID |
| `investment_date` | String | Entry date (ISO 8601) |
| `entry_ev_ebitda` | Float (nullable) | Entry valuation multiple |
| `entry_ev_sales` | Float (nullable) | Entry sales multiple |
| `cost_basis_eur` | Float | Initial investment amount |
| `ownership_pct` | Float (nullable) | Ownership percentage |
| `exit_date` | String (nullable) | Exit date (ISO 8601) |
| `exit_price_eur` | Float (nullable) | Exit proceeds |
| `exit_multiple` | Float (nullable) | Exit MOIC |
| `exit_ev_ebitda` | Float (nullable) | Exit valuation multiple |

**Constraint:** Unique `(fund_id, company_id)`.

---

### `pe_cash_flows`

PE fund-level cash flows: capital calls, distributions, fees, exit proceeds.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `fund_id` | String | PE fund ID |
| `company_id` | String (nullable) | Portfolio company ID (company-level flow) or NULL (fund-level fee) |
| `cash_flow_date` | String | Cash flow date (ISO 8601) |
| `flow_type` | String | Type (Capital Call, Distribution, Fee, Refinancing, etc.) |
| `amount_eur` | Float | Amount in EUR; negative for calls/fees, positive for distributions |
| `description` | String (nullable) | Flow description |

---

### `pe_nav_history`

Quarterly NAV history per fund (derived from independent appraisals).

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `fund_id` | String | PE fund ID |
| `company_id` | String (nullable) | Company ID (company-level NAV) or NULL (fund-level NAV) |
| `nav_date` | String | NAV date (ISO 8601) |
| `nav_eur` | Float | Net asset value in EUR |
| `gross_multiple` | Float (nullable) | Gross MOIC |
| `unrealised_gain` | Float (nullable) | Unrealised gain amount |
| `cost_basis_eur` | Float (nullable) | Cost basis |

---

### `pe_valuation_report`

Quarterly independent appraisal reports (external input).

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `fund_id` | String | PE fund ID |
| `company_id` | String | Portfolio company ID |
| `valuation_date` | String | Valuation date (ISO 8601) |
| `appraised_nav_eur` | Float | Appraised equity value |
| `ebitda_ltm_eur` | Float (nullable) | Last twelve months EBITDA |
| `revenue_ltm_eur` | Float (nullable) | LTM revenue |
| `ebitda_margin` | Float (nullable) | EBITDA margin % |
| `net_debt_eur` | Float (nullable) | Net debt |
| `ev_eur` | Float (nullable) | Enterprise value |
| `ev_ebitda` | Float (nullable) | EV/EBITDA multiple |
| `interest_expense_eur` | Float (nullable) | Annual interest expense |
| `discount_rate` | Float (nullable) | WACC or discount rate |
| `valuation_basis` | String (nullable) | Valuation method (DCF, Comps, etc.) |
| `appraiser` | String (nullable) | Appraiser firm name |
| `key_risks` | String (nullable) | Risk summary |
| `covenant_type` | String (nullable) | Covenant type (Leverage, Coverage, etc.) |
| `leverage_covenant` | Float (nullable) | Max leverage ratio threshold |
| `leverage_ratio` | Float (nullable) | Current leverage ratio |
| `coverage_covenant` | Float (nullable) | Min coverage ratio threshold |
| `coverage_ratio` | Float (nullable) | Current coverage ratio |
| `revenue_covenant_eur` | Float (nullable) | Revenue covenant threshold |
| `cash_covenant_eur` | Float (nullable) | Cash covenant threshold |
| `arr_eur` | Float (nullable) | Annual Recurring Revenue |

**Constraint:** Unique `(fund_id, company_id, valuation_date)`.  
**Governance:** External appraiser input; not computed by the ManCo.

---

### `pe_fund_cash_management`

Quarterly PE fund-level treasury snapshots: cash reserve and subscription credit facility.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `fund_id` | String | PE fund ID |
| `cash_management_date` | String | Observation date (ISO 8601) |
| `cash_balance_eur` | Float (nullable) | Cash reserve balance |
| `cash_interest_earned` | Float (nullable) | Interest earned this period |
| `cash_rate` | Float (nullable) | Cash deposit rate |
| `sub_line_drawn` | Float (nullable) | Subscription credit line drawn |
| `sub_line_limit` | Float (nullable) | Subscription credit line limit |
| `sub_line_interest` | Float (nullable) | Interest paid this period |
| `sub_line_rate` | Float (nullable) | Subscription line interest rate |
| `net_cash_position` | Float (nullable) | Net cash (reserve less drawn line) |
| `cumulative_interest_earned` | Float (nullable) | Cumulative interest earned to date |
| `cumulative_interest_paid` | Float (nullable) | Cumulative interest paid to date |

---

## Infrastructure Tables

### `infra_funds`

Infrastructure fund metadata.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `fund_id` | String (unique, not null) | Fund identifier |
| `fund_name` | String | Fund name |
| `vintage_year` | Integer | Vintage year |
| `target_size_eur` | Float | Target fund size |
| `committed_eur` | Float (nullable) | Total commitments |
| `drawn_eur` | Float (nullable) | Drawn equity to date |
| `fund_life_years` | Integer (nullable) | Expected fund life |
| `currency` | String (nullable) | Reporting currency |
| `domicile` | String (nullable) | Fund domicile |
| `benchmark` | String (nullable) | Performance benchmark (e.g., CPI+4%) |
| `aifmd_classification` | String (nullable) | AIFMD leverage classification |

---

### `infra_assets`

Infrastructure asset master data (independent of funds).

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `asset_id` | String (unique, not null) | Asset identifier (e.g., INFRA_001) |
| `asset_name` | String | Asset name |
| `sector` | String (nullable) | Sector (Transport, Energy, Telecom, etc.) |
| `sub_type` | String (nullable) | Sub-type (Toll Road, Wind Farm, etc.) |
| `country` | String (nullable) | Country of operation |
| `regulatory_framework` | String (nullable) | Regulatory regime |
| `concession_start` | String (nullable) | Concession start date (ISO 8601) |
| `concession_end` | String (nullable) | Concession end date (ISO 8601) |
| `inflation_linkage` | Float (nullable) | Inflation linkage % (e.g., 0.80 = CPI × 80%) |

---

### `infra_fund_investments`

Link table: infrastructure fund to asset investment terms.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `fund_id` | String | Infra fund ID |
| `asset_id` | String | Asset ID |
| `entry_date` | String | Entry date (ISO 8601) |
| `exit_date` | String (nullable) | Exit date (ISO 8601) if exited |
| `ownership_pct` | Float (nullable) | Ownership percentage |
| `cost_basis_eur` | Float | Initial investment amount |
| `committed_equity` | Float (nullable) | Committed equity |
| `drawn_equity` | Float (nullable) | Drawn equity to date |

**Constraint:** Unique `(fund_id, asset_id)`.

---

### `infra_cash_flows`

Infrastructure capital calls, distributions, management fees, interest, and refinancing.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `fund_id` | String | Infra fund ID |
| `asset_id` | String (nullable) | Asset ID (asset-level flow) or NULL (fund-level flow) |
| `cash_flow_date` | String | Cash flow date (ISO 8601) |
| `flow_type` | String | Flow type (Capital Call, Distribution, Fee, Interest, Refinancing, etc.) |
| `amount_eur` | Float | Amount in EUR; negative for calls/fees, positive for distributions/proceeds |
| `currency` | String (nullable) | Original currency |
| `description` | String (nullable) | Flow description |

---

### `infra_nav_history`

Quarterly NAV history per fund and per asset (derived from independent appraisals).

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `fund_id` | String | Infra fund ID |
| `asset_id` | String (nullable) | Asset ID (asset-level NAV) or NULL (fund-level aggregate) |
| `nav_date` | String | NAV date (ISO 8601) |
| `nav_eur` | Float | Net asset value in EUR |
| `moic` | Float (nullable) | Multiple on Invested Capital |

---

### `infra_valuation_report`

Quarterly independent appraiser reports per asset (external input).

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `fund_id` | String | Infra fund ID |
| `asset_id` | String | Asset ID |
| `valuation_date` | String | Valuation date (ISO 8601) |
| `appraised_ev_eur` | Float (nullable) | Appraised enterprise value |
| `net_debt_eur` | Float (nullable) | Net debt |
| `implied_equity_eur` | Float | Implied equity value (EV - net debt) |
| `ebitda_eur` | Float (nullable) | Annual EBITDA |
| `revenue_eur` | Float (nullable) | Annual revenue |
| `discount_rate` | Float (nullable) | Discount rate / WACC |
| `inflation_assumption` | Float (nullable) | Inflation assumption % |
| `terminal_value_eur` | Float (nullable) | Terminal value (DCF method) |
| `appraiser` | String (nullable) | Appraiser firm name |
| `valuation_basis` | String (nullable) | Valuation method (DCF, Market, etc.) |
| `key_risks` | String (nullable) | Risk summary |

**Constraint:** Unique `(fund_id, asset_id, valuation_date)`.  
**Governance:** External appraiser input; not computed by the ManCo.

---

### `infra_debt`

Project-level debt per asset (project finance structure).

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `asset_id` | String | Asset ID |
| `tranche_name` | String | Debt tranche name (e.g., Senior, Mezzanine) |
| `lender` | String (nullable) | Lender name |
| `outstanding_eur` | Float (nullable) | Outstanding balance in EUR |
| `maturity` | String (nullable) | Maturity date (ISO 8601) |
| `interest_rate_type` | String (nullable) | Fixed, Floating, or Mixed |
| `margin_bps` | Float (nullable) | Spread / margin in basis points |
| `amortisation_type` | String (nullable) | Amortisation schedule type |
| `dscr_covenant` | Float (nullable) | Debt service coverage ratio covenant threshold |
| `ltv_covenant` | Float (nullable) | Loan-to-value ratio covenant threshold |

---

### `infra_covenants`

Quarterly covenant observations per asset.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer (PK) | Auto-incremented ID |
| `asset_id` | String | Asset ID |
| `fund_id` | String | Fund ID (for rollup queries) |
| `observation_date` | String | Observation date (ISO 8601) |
| `dscr_actual` | Float (nullable) | Actual DSCR |
| `dscr_covenant` | Float (nullable) | DSCR covenant threshold |
| `dscr_headroom` | Float (nullable) | Headroom vs. covenant (DSCR - covenant) |
| `ltv_actual` | Float (nullable) | Actual LTV |
| `ltv_covenant` | Float (nullable) | LTV covenant threshold |
| `ltv_headroom` | Float (nullable) | Headroom vs. covenant (covenant - LTV) |
| `dscr_breach` | Boolean (nullable) | True if DSCR < covenant |
| `ltv_breach` | Boolean (nullable) | True if LTV > covenant |
| `waiver_granted` | Boolean (nullable) | True if lender granted formal waiver |
| `waiver_notes` | String (nullable) | Waiver details |

**Constraint:** Unique `(asset_id, observation_date)`.

---

## Data Population Flow

```
reference_data/
├── platform/fund_registry.json
│   └── FUNDS = [AIFM_HedgeFund, UCITS_Balanced, ...]
│
├── funds/<fund_id>/fund_profile.json
│   └── load_fund_metadata() → funds table
│
├── funds/<fund_id>/position_specs.json
│   └── generate_positions() → Excel → load_positions() → positions table
│
└── (enrichment)
    └── enrich_positions() + ESG loaders → positions_enriched table

reference_data/
├── portfolios/pe_companies.json
│   └── generate_pe_fund() → pe_portfolio_companies, pe_fund_investments, pe_cash_flows, pe_nav_history tables
│
└── portfolios/infra_assets.json
    └── generate_infra_fund() → infra_assets, infra_fund_investments, infra_cash_flows, infra_covenants tables
```

---

## Key Constraints & Indexes

| Table | Constraint | Purpose |
|-------|-----------|---------|
| positions | ix_positions_fund_date_isin | Fast lookup: position on date |
| positions | ix_positions_fund_date | Fast daily snapshot retrieval |
| pe_fund_investments | uq_fund_company | One investment per fund-company pair |
| pe_valuation_report | uq_valuation_report | One appraisal per asset-date |
| infra_fund_investments | uq_infra_fund_asset | One investment per fund-asset pair |
| infra_covenants | uq_infra_covenant | One covenant reading per asset-date |

---

## Common Queries

### Daily fund snapshot at valuation date
```sql
SELECT * FROM positions 
WHERE fund_id = 'AIFM_HedgeFund' 
AND position_date = '2026-03-31'
ORDER BY weight_pct DESC;
```

### 250-day time series for a position
```sql
SELECT position_date, market_value_eur, weight_pct 
FROM positions
WHERE fund_id = 'UCITS_Balanced' 
AND isin = 'US0378331005'
ORDER BY position_date;
```

### Liquidity profiling (ADV coverage)
```sql
SELECT isin, instrument_name, weight_pct, adv_eur,
       ROUND(market_value_eur / NULLIF(adv_eur, 0), 2) AS days_to_liquidity
FROM positions_enriched
WHERE fund_id = 'AIFM_HedgeFund' 
AND position_date = '2026-03-31'
ORDER BY days_to_liquidity DESC;
```

### Covenant breaches (infrastructure)
```sql
SELECT asset_id, observation_date, dscr_actual, dscr_covenant, 
       ltv_actual, ltv_covenant
FROM infra_covenants
WHERE dscr_breach = TRUE OR ltv_breach = TRUE
ORDER BY observation_date DESC;
```

### PE fund performance (MOIC)
```sql
SELECT fund_id, nav_date, nav_eur, gross_multiple
FROM pe_nav_history
WHERE company_id IS NULL
ORDER BY fund_id, nav_date DESC;
```

---

## Notes

- All dates are ISO 8601 strings; no datetime type is used.
- EUR is the reporting currency; local currency values are preserved in `market_value_local`.
- Enriched tables are regenerated via idempotent functions (existing rows are replaced).
- PE and infrastructure appraisal data are external inputs; not computed by internal systems.
- Real estate properties can be direct holdings or listed REITs; filter by `is_direct_property`.
