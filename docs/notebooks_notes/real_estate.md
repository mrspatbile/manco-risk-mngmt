Use this for:

```text
docs/notebooks_notes/real_estate.md
```

# AIFM Real Estate Fund Notes

This note collects supporting fund context, methodology notes, and interpretation guidance for the `AIFM_RealEstate` notebook.

## Fund Information

`AIFM_RealEstate` is a simulated real estate AIF invested in direct property assets, listed REITs, cash, and FX-hedged exposures.

The fund is modelled as a closed-ended mixed real estate strategy with direct-property exposure across office, logistics, retail, and residential assets, complemented by listed REITs and cash for liquid sleeve monitoring.

The monitoring workflow focuses on property and sleeve-level indicators rather than treating the whole fund as a daily liquid position-based portfolio.

Key fund characteristics used in the notebook:

* Fund ID: `AIFM_RealEstate`
* Strategy: mixed real estate
* Asset types: direct properties, listed REITs, cash, FX hedges
* Structure: closed-ended AIF
* Main property types: office, logistics, retail, residential
* Exposure type: direct property investments and listed real estate securities
* Valuation basis: quarterly appraiser inputs for direct properties and daily market prices for listed REITs
* Main monitoring indicators: LTV, rental yield, vacancy, effective yield, property value stress, rental stress, tenant concentration, liquidity profile by sleeve, leverage, and ESG indicators

## Real Estate Exposure Model

The notebook distinguishes between direct properties and listed REITs.

Direct properties are appraisal-based assets. They do not have Bloomberg tickers and should not be treated as daily traded securities. Their risk profile is monitored through property valuation, LTV, rental income, vacancy, tenant exposure, and stress testing.

Listed REITs are daily priced securities. They may use market-data enrichment and position-style analytics where relevant, including listed-market risk and liquidity measures.

Cash is monitored as a liquidity buffer.

FX hedges are monitored separately where relevant because they create hedge and counterparty exposure rather than direct property exposure.

## VaR and Expected Shortfall

Direct-property VaR is not the main risk lens for this closed-ended real estate AIF.

Direct properties are valued through quarterly appraisal inputs, so daily historical simulation VaR is not a natural fit for the direct-property sleeve. Where a parametric direct-property VaR approximation is shown, it should be treated as a modelling approximation rather than the main real estate risk measure.

Listed REIT VaR may remain relevant for the listed real estate sleeve because those positions are daily priced and market observable.

The preferred real estate risk interpretation should focus on:

* property value sensitivity
* LTV and debt headroom
* rental income stress
* vacancy and occupancy
* tenant concentration
* refinancing pressure
* liquidity by sleeve

## Direct Property Analysis

Direct property positions are monitored using property-level risk indicators.

The main metrics are:

* LTV: debt relative to property value
* rental yield: annual rent divided by property value
* vacancy rate: lettable space not generating income
* effective yield: rental yield adjusted for vacancy

These indicators are more relevant for direct real estate than daily market-price metrics.

## Leverage Monitoring

Real estate leverage should distinguish property-level debt from fund-level leverage.

Property-level debt is monitored through LTV and covenant headroom. Fund-level leverage is monitored relative to NAV and used as an input to reporting.

For this notebook, leverage interpretation should focus on:

* property-level LTV
* debt relative to appraised property values
* fund-level leverage relative to NAV
* distinction between financial borrowing and portfolio exposure
* Annex IV-style leverage reporting inputs where relevant

## Stress Testing

The real estate stress framework is based on property and sleeve-level risk drivers.

The main stress scenarios are:

* property value decline
* rental stress
* vacancy increase
* LTV covenant breach
* rate shock
* listed REIT market stress
* historical scenario labels where used by the notebook

For listed REITs and liquid exposures, stress P&L may use first-order sensitivities. For direct properties, stress testing should rely on direct property revaluation, rental income assumptions, or LTV-based scenarios.

A rate shock can affect listed REITs through market sensitivity and direct properties through valuation yields or cap-rate expansion. If the current function only applies duration sensitivity to bonds or REITs, direct-property rate transmission should be treated as only partly captured.

## Liquidity Profile

The liquidity profile should be interpreted by sleeve.

Direct properties are illiquid assets. They should not be treated as ADV-driven liquid positions. Their liquidity depends on property sale processes, market depth, valuation conditions, legal transfer process, debt arrangements, and asset-specific factors.

Listed REITs may use position-style liquidity measures where daily market data and trading volume are available.

Cash is treated as the liquidity buffer.

FX hedges should be monitored separately where relevant because they may create collateral, counterparty, or settlement liquidity needs.

## Redemption Stress and Closed-Ended Treatment

The fund is intended to be treated as closed-ended.

Open-ended redemption stress does not fully fit this structure. If the notebook includes redemption-style scenarios, they should be treated as legacy or review sections until replaced or complemented by real estate-specific liquidity analysis.

For a closed-ended real estate AIF, liquidity stress should focus more on:

* fund expenses
* debt service
* refinancing needs
* capex requirements
* tenant income shortfall
* cash-reserve adequacy
* asset sale timing
* liquidity support from listed REITs and cash

## Investor Concentration

Investor concentration can still matter in a closed-ended real estate fund, but the interpretation is different from an open-ended redemption workflow.

For a closed-ended fund, investor concentration may affect:

* capital-call reliability
* governance influence
* side-letter complexity
* transfer activity
* funding concentration
* LPAC or investor reporting focus

It should not be interpreted only as short-notice redemption pressure.

## Tenant Default and Concentration Stress

Tenant exposure is a central real estate risk driver.

A major tenant default or vacancy can reduce rental income and impair property value. The notebook models the largest single tenant defaulting on its lease, resulting in rental income loss under the selected stress assumptions.

Tenant register data is simulated in this project. In a fuller workflow, tenant exposure would be based on executed lease data, rent schedules, lease maturity, break clauses, rent indexation, security deposits, and vacancy assumptions.

## Combined Stress

The current combined stress includes a property value shock and a redemption demand.

For a closed-ended real estate fund, the redemption demand component should be reviewed. A better future combined stress would focus on real estate-specific pressure, such as:

* property value decline
* tenant default
* vacancy increase
* refinancing stress
* debt service pressure
* cash-flow shortfall
* capex needs
* limited liquidity from direct property sales

This should be handled in a later real estate-specific refactor.

## ESG Risk Indicators

The notebook monitors ESG indicators at portfolio level using NAV-weighted averages.

For real estate, ESG indicators may include energy efficiency, carbon intensity, building quality, tenant-related indicators, controversy flags, and sustainability-risk scores where available.

ESG data can come from Bloomberg for listed REITs and fund administrator or property-level data for direct property assets.

ESG scores should be treated as sustainability-risk inputs unless they are explicitly mapped to SFDR concepts such as Article 6, Article 8, Article 9, PAIs, pre-contractual disclosures, website disclosures, or periodic disclosures.

## Annex IV Reporting Context

For this simulated real estate AIF, Annex IV-style reporting inputs are linked to fund structure, leverage profile, liquidity profile, investor concentration, principal exposures, and main risk measures.

The real-estate-specific indicators used in the notebook include:

* fund-level leverage
* property-level LTV
* direct-property exposure
* listed REIT exposure
* liquidity profile by sleeve
* investor concentration
* tenant concentration
* property value stress
* rental stress
* ESG indicators

Direct properties, listed REITs, cash, and FX hedges should be distinguished when interpreting reporting output. The direct-property sleeve is appraisal-based and illiquid, while listed REITs and cash may support liquid-sleeve monitoring.

The notebook treats Annex IV-style outputs as reporting inputs generated from the monitoring workflow.
