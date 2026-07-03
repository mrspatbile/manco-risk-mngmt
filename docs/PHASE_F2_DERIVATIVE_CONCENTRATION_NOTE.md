# Phase F2: Derivative Concentration Checks (Deferred)

**Status:** Design note for future implementation  
**Date:** 2026-06-22  
**Scope:** Post-Phase F1 concentration semantics fix  

## Summary

Phase F1 fixed issuer and sector concentration semantics by excluding derivatives from corporate issuer concentration checks and clarifying sector concentration as net exposure (not gross). This defers specialized derivative concentration checks to Phase F2.

## Recommended Phase F2 Scope

### 1. Index Derivative Exposure Check

**Purpose:** Monitor synthetic equity exposure via equity index derivatives separately from corporate issuer concentration.

**Derivatives Included:**
- Equity index futures (SPX, EUROSTOXX, FTSE, etc.)
- Equity index options (puts, calls on indices)
- Do NOT include single-name equity derivatives (which are corporate issuer exposure)

**Exclude:**
- FX derivatives
- Bond/rate derivatives
- Credit derivatives (use underlying issuer look-through)

**Proposed Metric:**
```
index_deriv_exp = SUM(|gross_notional_eur| for index derivatives) / Gross_Exposure * 100
```

**Proposed Limit:** 50% of Gross Exposure

**Rationale:**
- Index derivatives are synthetic exposures to portfolios (not corporate issuers)
- Notional basis appropriate (reflects hedge sizing intent)
- Monitor separately from single-name concentration
- Gross exposure denominator captures leverage context

**Implementation Notes:**
- Use `compute_derivative_exposures_portfolio()` helper to get gross_notional
- Filter derivatives by contract type ('future', 'option') and underlying_asset_class ('Equity')
- Create new function: `_ptc_index_deriv_exposure()`
- Add to `_check_aifm_hf()` as Check #5

---

### 2. FX Derivative Exposure Check

**Purpose:** Monitor FX hedge sizing relative to portfolio.

**Derivatives Included:**
- FX forwards (EUR/USD, GBP/USD, etc.)
- FX options (calls, puts on currency pairs)
- FX swaps

**Exclude:**
- Equity derivatives
- Bond/rate derivatives
- Non-FX derivatives

**Proposed Metric:**
```
fx_deriv_exp = SUM(|delta_adjusted_notional_eur| for FX derivatives) / NAV * 100
```

**Proposed Limit:** 50% of NAV

**Rationale:**
- FX derivatives are not issuer concentration (cross-asset instrument)
- Delta-adjusted notional appropriate (represents actual FX hedge exposure)
- NAV denominator suitable for position-relative sizing
- Limit reflects reasonable hedge sizing (50% = typical 2:1 hedge on half the portfolio)

**Implementation Notes:**
- Use `compute_derivative_exposures_portfolio()` to get delta_adjusted_notional
- Filter derivatives by underlying_asset_class ('FX')
- Create new function: `_ptc_fx_deriv_exposure()`
- Add to `_check_aifm_hf()` as Check #5 or #6

---

### 3. Sector Gross Exposure View (Optional)

**Purpose:** Provide optional gross sector exposure metric for risk reporting (not for compliance checks yet).

**Note:** Phase F1 clarified sector concentration as net signed exposure. A gross exposure view would show total long + short exposure per sector.

**Proposed Metric (for reporting only):**
```
sector_gross_exp = SUM(|market_value_eur| by sector) / Gross_Exposure * 100
```

**When to Implement:**
- Only if risk reports need gross sector leverage view
- Keep separate from net sector concentration check (don't mix semantics)
- Label clearly as "gross sector exposure" to avoid confusion

---

### 4. Look-Through for Index Derivatives (Future Enhancement)

**Future Consideration:** If index derivative exposure needs sectoral breakdown, implement look-through to constituent sectors.

**Example Use Case:**
- SPX future → decompose to sector weights (Tech 30%, Finance 20%, etc.)
- Route economic risk to corresponding sectors
- More granular sector concentration monitoring

**Note:** Not needed for Phase F1/F2. Deferred to Phase F3 if business need arises.

---

## Changes Not Required in Phase F2

- ✗ No changes to leverage calculations (already use notional correctly)
- ✗ No changes to attribution routing (already use economic buckets correctly)
- ✗ No changes to ESG routing (already use delta-adjusted notional correctly)
- ✗ No changes to sector concentration check semantics (Phase F1 clarified as net)
- ✗ No changes to issuer concentration check (Phase F1 fixed to exclude derivatives)

---

## Test Coverage Needed for Phase F2

### Index Derivative Exposure Check Tests
- `test_index_deriv_check_includes_spy_future()`
- `test_index_deriv_check_includes_eurostoxx_future()`
- `test_index_deriv_check_includes_index_options()`
- `test_index_deriv_check_excludes_single_stock_options()`
- `test_index_deriv_check_exceeds_50_percent_limit()` (if applicable)

### FX Derivative Exposure Check Tests
- `test_fx_deriv_check_includes_eurusd_forward()`
- `test_fx_deriv_check_includes_gbpusd_forward()`
- `test_fx_deriv_check_includes_fx_options()`
- `test_fx_deriv_check_excludes_equity_derivatives()`
- `test_fx_deriv_check_uses_notional_not_market_value()`

### Optional Gross Sector Exposure Tests (if implemented)
- `test_sector_gross_exposure_calculation()`
- `test_sector_gross_vs_net_semantics()`

---

## Regulatory Context

- **AIFMD Article 15:** Risk function must monitor position concentration and hedge effectiveness
- **EU231/2013:** Leverage calculation uses gross notional (derivatives); index derivative sizing fits within this framework
- **ESMA Guidelines:** Recommend separate monitoring of synthetic exposures from direct holdings
- **Fund RMP:** Current limits (25% issuer, 30% sector) apply to direct positions; index derivatives monitored separately

---

## Implementation Priority

**High Priority (Phase F2 MVP):**
1. Index Derivative Exposure Check (50% Gross Exposure limit)
2. FX Derivative Exposure Check (50% NAV limit)

**Medium Priority (Phase F2 Optional):**
3. Sector Gross Exposure view for reporting

**Low Priority (Phase F3+):**
4. Look-through methodology for index derivatives
5. Dynamic concentration limits based on asset class mix

---

## Decision Pending

**Before implementing Phase F2, confirm:**
- Should derivative concentration checks use RMP configuration limits, or are 50% fixed limits acceptable?
- Should index derivative check use Gross Exposure or Commitment Exposure as denominator?
- Should FX derivative check flag breaches in pre-trade checks, or only for reporting/monitoring?
- Should look-through methodology be explored in Phase F2 or deferred to F3?

---

End of Phase F2 planning note. No implementation in Phase F1.
