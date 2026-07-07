# AIFM PE Buyout Fund Notes

This note collects supporting fund context, methodology notes, and interpretation guidance for the `AIFM_PE_Buyout` notebook.

## Fund Information

`AIFM_PE_Buyout` is a simulated private equity AIF invested in European mid-market buyout portfolio companies across technology, healthcare, industrials, consumer, and energy transition sectors.

The fund is modelled as a closed-ended buyout strategy with portfolio-company exposures, capital calls, distributions, quarterly NAV appraisals, unfunded commitments, performance metrics, valuation bridge analysis, and selected sustainability indicators.

The monitoring workflow focuses on private-capital indicators rather than daily-priced position risk.

Key fund characteristics used in the notebook:

* Fund ID: `AIFM_PE_Buyout`
* Strategy: European mid-market buyout
* Asset type: private equity portfolio companies
* Structure: closed-ended AIF
* Vintage: 2018
* Target size: EUR 200m
* Fund life: 10 years
* Main sectors: technology, healthcare, industrials, consumer, energy transition
* Valuation basis: quarterly NAV appraisals
* Main monitoring indicators: IRR, MOIC, DPI, RVPI, PME, unfunded commitments, capital calls, valuation bridge, sector exposure, and selected sustainability indicators


## Fund Data Structure

The PE workflow uses a private-capital data model rather than a liquid-position data model.

Data is organised around:

* portfolio companies
* fund-specific investments
* capital calls
* distributions
* fees
* exit proceeds
* quarterly NAV appraisals

The data flow used in the notebook is:

```text
generate_pe_fund.py → SQLite PE tables → notebook
```

The PE tables are:

* `pe_funds`: fund metadata, including vintage, size, and investment period
* `pe_portfolio_companies`: company master data, including sector, country, and stage
* `pe_fund_investments`: fund-specific investment data, including cost basis, ownership, and exit status
* `pe_cash_flows`: capital calls, distributions, fees, and exit proceeds
* `pe_nav_history`: quarterly NAV by portfolio company and at fund level

In this repository, `generate_pe_fund.py` provides the simulated data source for the PE tables.

## Independent Appraisal and Valuation Reports

Private equity portfolio companies are valued quarterly using independent appraisal inputs rather than daily market prices.

The valuation report used in the notebook is stored in `pe_valuation_report`.

The report includes:

* appraised NAV
* LTM financials
* enterprise value
* EV/EBITDA multiple
* net debt
* leverage ratio
* discount rate used in income-approach valuations
* covenant status and headroom
* key risks identified by the appraiser

### Covenant types

Buyout companies are monitored using maintenance-style financial covenants tested against LTM EBITDA.

```text
Leverage ratio = net debt / LTM EBITDA
Coverage ratio = LTM EBITDA / interest expense
Leverage headroom = (leverage covenant - leverage ratio) / leverage covenant
```

Growth companies may use revenue and liquidity covenants where EBITDA is negative or not yet stable.

```text
Revenue covenant = LTM revenue above minimum threshold
Cash covenant = cash balance above minimum cash threshold
```

For SaaS and subscription models, ARR is tracked as a growth metric alongside liquidity indicators.

### Valuation risk interpretation

Direct PE valuations are quarterly and depend on appraiser judgement, company financials, market multiples, and income-approach assumptions.

Valuation risk is therefore treated as model and appraisal risk, distinct from market risk in liquid portfolios.


**Move to PE notes:**

```markdown
## J-Curve Analysis

The J-curve illustrates the typical cash-flow pattern of a PE fund. Capital is called early to fund investments, fees, and expenses, which creates negative cumulative net cash flow in the first years.

As portfolio companies mature, are recapitalised, or are sold, distributions flow back to investors. The fund exits the J-curve when cumulative distributions begin to offset cumulative capital called.

Key metrics:

```text
Net cash flow = distributions - capital called
Cumulative net cash flow = cumulative distributions - cumulative capital called

## Exit Waterfall

When a portfolio company is sold, exit proceeds are allocated through a waterfall before reaching LPs and the GP.

The simulated workflow uses a European-style waterfall, where LPs receive contributed capital and preferred return before the GP participates in profits.

Waterfall order:

1. Return of capital
2. Preferred return
3. GP catch-up
4. Carried-interest split

This structure supports the notebook output by showing how gross exit proceeds translate into LP and GP economics.
## Fund Cash Management and Subscription Credit Facility

The simulated fund uses two treasury tools: a cash reserve and a subscription credit facility.

The cash reserve is used to pay management fees and fund expenses before LP capital is called.

The subscription credit facility is a revolving facility backed by unfunded LP commitments. It can bridge investment funding before capital is called from investors.

In the notebook, the facility affects:

- timing of capital calls
- interest expense
- liquidity coverage
- temporary financing of investments
- fund-level cash movements

The facility is treated as fund-level treasury management, not as portfolio-company leverage.

## Return Attribution: Value Bridge

The value bridge explains how equity value changed between entry and current valuation or exit.

The methodology decomposes value creation into:

- EBITDA growth
- multiple expansion or contraction
- deleveraging
- FX movement
- other adjustments where applicable

This distinction helps separate operational performance from valuation effects and capital-structure effects.

For a buyout fund, EBITDA growth and deleveraging are usually treated as operating or execution-driven value creation. Multiple expansion is more market-sensitive because it depends on valuation conditions at entry and exit.

## ESG Risk Indicators

PE ESG data is assessed at portfolio-company level rather than by listed ISIN.

The notebook uses `build_private_esg_df` to produce a dataset with the same column structure as the listed-asset ESG workflow. This allows `esg_portfolio_summary` to be reused while keeping PE-specific data sourcing visible.

The `esg_reporter` column identifies the data source, such as a third-party assessor or management estimate.

For PE portfolio companies, ESG indicators should be treated as sustainability-risk inputs unless they are explicitly mapped to SFDR concepts such as Article 6, Article 8, Article 9, PAIs, pre-contractual disclosures, or periodic disclosures.

