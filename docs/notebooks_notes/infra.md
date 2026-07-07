# AIFM Infrastructure Fund Notes

This note collects supporting fund context, methodology notes, and interpretation guidance for the `AIFM_Infra_Core` notebook.

## Fund Information

`AIFM_Infra_Core` is a simulated core infrastructure AIF invested in long-duration real-asset projects across utilities, energy transition, transport, and social infrastructure.

The fund is modelled as a closed-ended infrastructure strategy with project-level exposures, appraised valuations, leverage monitoring, concession duration analysis, inflation sensitivity, and cash-flow stress testing.

Exposures are held through regulated concessions and contracted structures. The monitoring workflow therefore focuses on project and asset-level indicators rather than daily-priced position risk.

Key fund characteristics used in the notebook:

- Fund ID: `AIFM_Infra_Core`
- Strategy: core infrastructure
- Asset type: long-duration real assets
- Structure: closed-ended AIF
- Main sectors: utilities, energy transition, transport, social infrastructure
- Exposure type: regulated concessions and contracted infrastructure assets
- Valuation basis: quarterly appraiser inputs
- Main monitoring indicators: DSCR, LTV, valuation sensitivity, inflation linkage, concession duration, cash-flow stress, concentration, and selected sustainability indicators

## Performance Metrics

Infrastructure return metrics follow private-market convention. MOIC, DPI, RVPI, and TVPI are computed from fund cash flows and current residual value. IRR is calculated using XIRR on actual capital call and distribution dates.

### Benchmark

The benchmark for this simulated core infrastructure strategy is CPI + 400 bps net of fees. At 2.0% CPI, this implies a 6.0% net IRR target.

This reflects the simulated fund profile: long-duration assets, inflation linkage, contracted or regulated cash flows, and lower target returns than higher-risk private equity strategies.

Core infrastructure IRRs generally sit below PE buyout return targets because the strategy uses lower leverage and relies more on regulated revenues, availability-based payments, and long-duration cash flows. The trade-off is a more predictable income profile with lower expected return.

### Metric definitions

**MOIC** means Multiple on Invested Capital. It measures total value divided by total invested capital. A MOIC of 2.0x means every EUR 1 invested is worth EUR 2, including realised and unrealised value.

**DPI** means Distributed to Paid-In. It measures cash returned to investors divided by capital called. DPI is the realised cash-return metric.

**RVPI** means Residual Value to Paid-In. It measures current unrealised portfolio value divided by capital called.

**TVPI** means Total Value to Paid-In. It measures distributed value plus residual value divided by paid-in capital. In simple cases, TVPI equals DPI plus RVPI.

For a core infrastructure fund still within its investment period, high RVPI and low DPI can be expected because assets are long-duration and capital is not usually returned early. DPI builds through distributions, refinancing, or exits.


## Leverage and Covenant Monitoring

Infrastructure assets are often financed with project-level debt, commonly with limited or no recourse to the fund. Lenders monitor financial maintenance covenants, usually tested quarterly.

DSCR measures operating cash flow relative to debt service.

```text
DSCR = annual EBITDA / (annual principal + annual interest)
```

An LTV ratio measures debt relative to appraised enterprise value.

```text
LTV = net debt / appraised enterprise value
```

A DSCR breach can indicate that operating cash flows are not sufficient to service debt. An LTV breach can indicate that asset value has deteriorated relative to leverage.

Common drivers of covenant pressure include construction overruns, traffic underperformance, lower availability payments, higher debt costs, and discount-rate increases.

Possible lender responses include waivers, cash sweeps, sponsor capital injections, equity cures, or enforcement action in more severe cases.

The notebook uses a 10% DSCR headroom flag. Any asset where current DSCR is within 10% of its covenant floor is flagged for enhanced monitoring.


## Concentration Risk

Infrastructure funds face concentration risk mainly across sector, country, and asset sub-type.

For this simulated fund, the internal risk policy sets a 40% NAV sector concentration limit. A single sector above 40% of NAV may indicate reliance on one regulatory regime, demand driver, or project type.

Asset sub-type is a qualitative risk dimension:

* **Regulated:** revenues or allowed returns are set by a sector regulator. These assets tend to have more predictable cash flows, but remain exposed to regulatory reset risk.
* **Contracted:** revenues are based on fixed-price, offtake, or availability-payment arrangements. Counterparty credit quality is a key risk driver.
* **Concession:** revenues may depend on traffic, usage volumes, or economic activity. These assets can be more cyclical and more correlated with macro conditions.

AIFMD does not prescribe a fixed sector concentration limit for closed-ended infrastructure AIFs. The 40% threshold is treated here as the fund’s own internal policy limit.

## Inflation and Duration

Inflation linkage and long duration are core characteristics of infrastructure assets. They affect valuation sensitivity and long-term cash-flow predictability.

Inflation linkage measures the share of an asset’s revenues that adjusts with CPI, PPI, RPI, or another index. Regulated assets may have tariffs reset by the sector regulator with explicit indexation. Availability-based PPPs often link payments to inflation indices. Toll roads and airports may have partial linkage through tariff escalation clauses while retaining volume risk. Merchant assets may have limited or no automatic linkage.

The notebook calculates weighted inflation linkage as:

```text
Weighted linkage = sum(asset NAV weight × inflation linkage coefficient)
```

where the inflation linkage coefficient ranges from 0 to 1.

Duration in this notebook refers to remaining concession or contract life. For concession assets, expiry can represent a terminal event unless the asset is extended, refinanced, retendered, or replaced.

Assets approaching expiry within 3 years are flagged for review because they may require an exit, extension, or retendering strategy.

## Cashflow and Liquidity

For this closed-ended infrastructure fund, liquidity monitoring focuses on capital calls, fund expenses, asset-level debt service, and the timing of distributions. The fund does not model investor redemptions.

The shape of the J-curve depends on strategy. Core infrastructure funds investing in operational assets may generate cash flow from the start and distribute earlier, so the J-curve can be shallow. Core-plus, value-add, greenfield, and project-finance strategies may have a deeper J-curve because capital is used for construction, capex, or repositioning before operating cash flow builds.

Greenfield and project-finance funds can resemble the PE J-curve pattern. Assets consume capital during construction and distributions begin only after commercial operation, which may take several years.

Cash-flow coverage measures whether quarterly distributions from assets are sufficient to cover fund-level operating costs without requiring additional LP capital calls.

```text
Cash-flow coverage = quarterly asset distributions / fund expenses
```

Unfunded commitments are LP capital that has been committed but not yet drawn. For a closed-ended fund, they represent the remaining capital-call capacity and the investor-side funding obligation.

AIFMD liquidity monitoring should be consistent with the fund’s redemption policy. For this simulated closed-ended fund, liquidity is assessed against capital-call mechanics and expense coverage rather than investor redemption requests.

## Stress Testing

Infrastructure stress testing in this notebook is valuation input stress rather than liquid-market price stress.

The model stresses the assumptions that affect appraised equity value:

* discount rate used by the appraiser
* EBITDA
* inflation linkage coefficient
* net debt

The stressed enterprise value is calculated as:

```text
Stressed EV = EBITDA × (1 + inflation linkage × inflation shock) / (discount rate + discount-rate shock)
```

The stressed equity value is calculated as:

```text
Stressed equity = max(0, stressed EV - net debt)
```

The three scenarios are:

| Scenario       | Discount-rate shock | Inflation shock | Rationale                                                           |
| -------------- | ------------------: | --------------: | ------------------------------------------------------------------- |
| Rate shock     |            +100 bps |              0% | Higher discount rate reduces appraised enterprise value.            |
| Inflation loss |               0 bps |             -2% | Lower indexation or weaker inflation-linked revenue reduces EBITDA. |
| Combined       |            +100 bps |             -2% | Higher discount rate combined with weaker inflation-linked revenue. |

The scenarios are designed to test NAV sensitivity to valuation model inputs, not daily market risk.

## Annex IV Reporting Context

For this simulated infrastructure AIF, Annex IV reporting inputs are linked to the fund’s structure, leverage profile, liquidity profile, concentration, valuation approach, and main risk measures.

The infrastructure-specific indicators used in the notebook include DSCR, LTV, concession duration, inflation linkage, valuation sensitivity, cash-flow coverage, and concentration flags.

Project-level debt and fund-level leverage should be distinguished when interpreting the reporting output. The notebook treats DSCR and LTV as project-level monitoring indicators, while Annex IV-style leverage reporting remains fund-level.

Valuation inputs are treated as external inputs to the risk workflow. Risk monitoring tracks movements, flags material changes, and supports escalation where needed.

## ESG Risk Indicators

Infrastructure ESG profiles vary by sector and asset type.

Offshore wind and social infrastructure may show stronger environmental or social profiles, while airports and toll roads may carry higher carbon-intensity exposure. These indicators are treated as ESG and sustainability-risk inputs in the notebook.

The ESG output is built with `build_private_esg_df` using `asset_type='infra'`. The appraiser field from `infra_valuation_report` is used as `esg_reporter`.

Assets with controversy flags, such as `INFRA_003` and `INFRA_007`, can be reviewed alongside the DSCR and LTV covenant events identified in the covenant-monitoring section.





