# AIFM Private Debt Fund Notes

This note collects supporting fund context, methodology notes, and interpretation guidance for the `AIFM_PrivateDebt` notebook.

## Fund Information

`AIFM_PrivateDebt` is a simulated private debt AIF invested in senior secured loans, high-yield bonds, and CLO exposures.

The fund is modelled as a credit-focused AIF with monitoring centred on borrower quality, covenant headroom, maturity profile, leverage, liquidity, stress testing, and selected sustainability indicators.

The monitoring workflow focuses on credit and portfolio risk indicators rather than applying a generic VaR framework.

Key fund characteristics used in the notebook:

* Fund ID: `AIFM_PrivateDebt`
* Strategy: private debt
* Asset types: senior secured loans, high-yield bonds, CLO exposures
* Structure: AIF
* Base workflow: position-based credit and liquidity monitoring
* Valuation basis: SQLite position, fund, reference, and market-data inputs enriched through the simulated Bloomberg workflow
* Main monitoring indicators: credit quality, covenant headroom, maturity profile, leverage, liquidity profile, redemption stress, investor concentration, counterparty stress, combined stress, and ESG indicators

## Simulated Data and RMP Context

Fund characteristics, risk limits, methodologies, and reporting parameters are simulated. They are used to show how a fund-level risk workflow can be represented in a structured notebook.

Risk Management Policy parameters are loaded as `rmp` and passed to the relevant risk functions. This keeps fund-specific parameters outside the calculation code and allows the notebook to show how policy settings drive measurement, monitoring, and limit checks.

The analysis is performed as of a fixed valuation date, consistent with the point-in-time design used across the fund workflows.

Portfolio positions, fund characteristics, counterparty records, reference data, and market data are retrieved from the SQLite data layer. Market data is enriched through the simulated Bloomberg workflow before being passed to the risk analytics modules.

## Leverage Monitoring

AIFMD leverage reporting uses gross and commitment-style measures.

The gross method sums absolute exposures relative to NAV. The commitment method recognises hedging and netting arrangements where applicable.

For a private debt fund, gross and commitment leverage can be close because loan exposures are not usually netted in the same way as offsetting derivative positions.

The notebook uses the leverage output to monitor declared leverage against fund-level limits and to distinguish financial borrowing, synthetic leverage, and exposure created through portfolio instruments.

## Stress Testing

Stress testing for this private debt fund focuses on rate and credit spread shocks.

The stress P&L is calculated using first-order sensitivities:

```text
Stress P&L = sensitivity × shock × market value
```

The scenarios used in the notebook include:

* rate shock: parallel rate increase affecting bond and CLO valuations
* credit widening: spread widening across loans, high-yield bonds, and CLOs
* combined shock: simultaneous rate and credit stress
* historical stress: selected market stress periods used as scenario labels

In this project, stress P&L uses first-order sensitivity measures such as modified duration for rates and credit. Loans and CLOs may be mark-to-model, so stressed valuations should be interpreted as sensitivity outputs rather than executable secondary-market prices.

## Liquidity Profile

The liquidity profile groups assets by estimated time to liquidation.

The notebook calculates days to liquidate using market value, average daily volume, and the fund's internal participation-rate assumption.

```text
Days to liquidate = absolute market value / (average daily volume × participation rate)
```

The internal `pct_adv` parameter represents the maximum share of average daily volume assumed to be tradeable per day without creating significant market impact.

Cash and money market instruments are treated as 1-day liquidity. Instruments with no usable trading volume are treated as illiquid.

The liquidity output supports redemption coverage, liquidity-bucket reporting, and stress testing.

## Redemption Stress

Redemption stress compares liquid assets available within the contractual notice period against redemption amounts.

The notebook uses four redemption scenarios:

| Scenario         |    Redemption | Notice | Rationale               |
| ---------------- | ------------: | -----: | ----------------------- |
| Normal           |       10% NAV | 5 days | Routine investor exit   |
| Large            |       25% NAV | 5 days | Large single redemption |
| Stress           |       50% NAV | 5 days | Coordinated stress exit |
| Largest investor | Fund-specific | 5 days | Concentration stress    |

Assets liquidatable within the notice period are compared with the redemption amount. A shortfall is treated as a liquidity pressure flag for review.

## Investor Concentration

Investor concentration increases redemption risk because one large investor exit can create liquidity pressure for the whole fund.

The notebook monitors single-investor and top-investor concentration and uses the investor register to derive the largest-investor redemption stress scenario.

The largest-investor scenario connects investor concentration with redemption stress by translating ownership concentration into a liquidity demand.

## Counterparty Stress

For a private debt fund, borrower default is a main counterparty risk.

The notebook models the largest single borrower defaulting on its outstanding principal. Recovery depends on collateral quality, instrument seniority, and the assumed recovery rate.

Senior secured loans can have higher recovery than mezzanine or second-lien positions, but recovery remains scenario-dependent.

The notebook uses a 40% recovery assumption, equivalent to 60% loss given default, for the largest-borrower default stress.

## Combined Stress

The combined stress joins market and liquidity pressure.

For this private debt workflow, the market shock is a credit spread widening, which reduces mark-to-market values of fixed-income loans, high-yield bonds, and CLO exposures.

The liquidity shock is a redemption demand. Because the private debt book is less liquid, stressed liquid assets are limited mainly to cash and near-cash instruments.

The combined scenario is used to show how valuation losses and redemption pressure interact.

## ESG Risk Indicators

The notebook monitors ESG indicators at portfolio level using NAV-weighted averages.

Metrics monitored include:

* weighted average ESG score
* weighted average environmental score
* weighted average social score
* weighted average governance score
* percentage of NAV in instruments below the internal ESG score threshold
* percentage of NAV with active controversy flags
* weighted average carbon intensity

ESG scores in this workflow use a 0-100 scale where higher is better. The internal low-score threshold is defined in the Risk Management Policy.

ESG data can come from simulated Bloomberg enrichment for liquid instruments or embedded fund administrator data for instruments without a Bloomberg ticker.

ESG scores should be treated as sustainability-risk inputs unless they are explicitly mapped to SFDR concepts such as Article 6, Article 8, Article 9, PAIs, pre-contractual disclosures, website disclosures, or periodic disclosures.

Derivatives have indirect ESG exposure through their underlying. Where relevant, exposure weighting should use economic exposure rather than market value alone.

## Annex IV Reporting Context

For this simulated private debt AIF, Annex IV reporting inputs are linked to fund structure, leverage profile, liquidity profile, investor concentration, principal exposures, and main risk measures.

The private-debt-specific indicators used in the notebook include leverage, liquidity buckets, redemption stress, investor concentration, borrower default stress, credit spread stress, and ESG indicators.

Private debt leverage interpretation should distinguish fund-level borrowing, portfolio instrument exposure, and synthetic leverage where derivatives are present.

The notebook treats Annex IV-style outputs as reporting inputs generated from the monitoring workflow.
