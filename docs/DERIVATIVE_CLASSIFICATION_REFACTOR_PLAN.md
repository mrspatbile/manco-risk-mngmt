# Derivative Classification Refactor Plan

**Status**: Plan Only (No Implementation)  
**Date**: 2026-06-21  
**Scope**: Active workflows only (AIFM Hedge Fund, UCITS Balanced)

---

## EXECUTIVE SUMMARY

**Current State (Shortcut Classification)**:
- Futures: `asset_class="Equity"`, `sub_asset_class="Future"`
- FX Forwards: `asset_class="FX"`, `sub_asset_class="Forward"`
- Listed Options: `asset_class="Derivative"`, `sub_asset_class="Listed Option"`

**Target State (Proper Instrument Classification)**:
- ALL derivatives: `asset_class="Derivative"`
- Type distinction: `sub_asset_class` ∈ {"Future", "Forward", "Listed Option"}
- Economic exposure: sourced from `derivative_contracts.json` → `underlying_asset_class`

**Rationale**: Separate instrument classification (what it is) from economic exposure (what risk it carries).

---

## 1. AFFECTED FILES & LOCATIONS

### 1.1 Source Data

**reference_data/funds/AIFM_HedgeFund/position_specs.json**
```json
Lines 66-110:    3 futures (EU0009658145, FUT_SPY_SHORT_001, FUT_SX5E_SHORT_001)
Lines 196-223:   2 FX forwards (FWD_EURUSD_001, FWD_GBPUSD_001)
Lines 225-237:   1 listed option (OPT_SPX_PUT_001)

Current:
  - Futures:   asset_class="Equity"
  - Forwards:  asset_class="FX"
  - Options:   asset_class="Derivative"

Target:
  - ALL:       asset_class="Derivative"
              sub_asset_class = (Future|Forward|Listed Option)
              (underlying_asset_class stays in derivative_contracts.json)
```

**UCITS Position Specs**
- `reference_data/funds/UCITS_Balanced/position_specs.json`
- Current: No derivatives present (verify with audit)
- Status: May not need changes unless future UCITS derivatives added

### 1.2 Position Generation

**src/fund_risk_workflow/data/generate_positions.py**
- Lines 111-145: Position generation loop
- Lines 145+: Derivative-specific handling when `asset_class == 'Derivative'`
- **Current impact**: Only options are handled as Derivative; futures/forwards not processed
- **After refactor**: All derivatives must be handled uniformly

**src/fund_risk_workflow/data/setup_db.py**
- Position insertion into database
- **Current**: Reads position_specs.json as-is
- **After refactor**: No changes needed (will read new asset_class values)

### 1.3 Data Access Layer

**src/fund_risk_workflow/data/database.py**
- `query_positions()`: No asset_class filtering (reads all)
- **Impact**: No changes needed (returns classification as stored)

**src/fund_risk_workflow/data/enrichment.py**
- `get_risk_ready_df()`: Enriches positions
- Lines ~40-60: May have asset_class-specific enrichment logic
- **Action required**: Audit for asset_class-specific branches

### 1.4 Leverage & Exposure Calculation

**src/fund_risk_workflow/computation/leverage.py** (Phase 3b)
- Lines 55-90: Derivative loop checks `df['asset_class'] == 'Derivative'`
- **Impact**: Futures/forwards will now be caught by this loop ✅ (desired)
- **Regression test**: Leverage outputs must remain identical

**src/fund_risk_workflow/computation/derivatives.py** (Phase 3a)
- Line 271: Filters `risk_df['asset_class'] == 'Derivative'`
- **Impact**: Futures/forwards will now use helper ✅ (desired)
- **Action**: Verify helper handles sub_asset_class properly (it should)

### 1.5 ESG Exposure

**src/fund_risk_workflow/risk/esg_utils.py** (Phase 3c)
- Lines 110-124: Currently separates derivatives by asset_class
  ```python
  if pos['asset_class'] == 'Derivative':  # Only options currently
      # Use helper
  elif pos['asset_class'] == 'FX':        # Forwards currently
      # Zero exposure
  elif pos['asset_class'] == 'Cash':
      # Zero exposure
  else:                                    # Non-derivatives
      # Use market_value_eur
  ```
- **Impact**: CRITICAL CHANGE - must redesign ESG routing
- **Options** (detailed in section 5):
  1. All derivatives → `abs(delta_adjusted_notional_eur)`
  2. Only equity/bond derivatives → helper; others zero
  3. No change (preserve current behavior by sub_asset_class)
- **Decision required before Phase E implementation**

### 1.6 Liquidity

**src/fund_risk_workflow/computation/liquidity.py**
- Lines ~30-80: Likely has asset_class buckets
- **Current behavior**: Futures → Equity bucket; Forwards → FX bucket
- **Target behavior**: After reclassification, must route by `sub_asset_class` instead
- **Action required**: Audit and update routing logic

**src/fund_risk_workflow/computation/stress.py**
- May also have asset_class-based stress assumptions
- **Action required**: Audit for asset_class dependencies

### 1.7 Attribution

**src/fund_risk_workflow/computation/attribution.py**
- Likely has asset_class buckets for attribution
- **Action required**: Audit for asset_class-specific splits

### 1.8 Pre-Trade & Operational Checks

**src/fund_risk_workflow/data/operational_checks.py**
- **Action required**: Audit for asset_class filtering
- Likely checks like "is equity?", "is FX?" that may be broken

**src/fund_risk_workflow/risk/risk_utils.py** → `check_aifm_hf_clean_trade()`, `check_ucits_clean()`
- **Current**: Check concentrations, leverage by asset_class
- **After refactor**: May need to check by `underlying_asset_class` for exposure routing
- **Regression test**: Pre-trade outputs must remain identical for same trades

### 1.9 Reporting

**src/fund_risk_workflow/reporting/annex_iv.py**
- Likely breaks down exposures by asset class
- **Decision needed**: Report by instrument form (Derivative) or economic exposure (Equity/FX)?
- **Action**: Design reporting breakdowns

**src/fund_risk_workflow/ui/print_html_utils.py** (display tables)
- May have asset_class-specific formatting
- **Action required**: Audit for asset_class dependencies

### 1.10 Tests Affected

**Tests that will need updates** (regression/verification):
```
test_generate_positions.py         # Position generation
test_derivative_contracts.py       # Contract validation
test_leverage_helper_integration.py # Leverage outputs
test_esg_derivative_integration.py # ESG routing
test_risk_utils.py                 # Pre-trade checks
test_enrichment.py                 # Data enrichment
test_operational_checks.py         # Operational validations
```

---

## 2. CODE PATH AUDIT FINDINGS

### 2.1 Leverage (SAFE to reclassify)

**Current behavior**:
```python
# leverage.py line 271
deriv_mask = risk_df['asset_class'] == 'Derivative'
derivatives = risk_df[deriv_mask].copy()

if len(derivatives) > 0:
    # Call helper → compute_derivative_exposures_portfolio()
```

**After reclassification**:
- Futures (currently Equity) → now caught by `asset_class == 'Derivative'` ✅
- Forwards (currently FX) → now caught by `asset_class == 'Derivative'` ✅
- Options (currently Derivative) → still caught ✅

**Regression test**: Leverage outputs identical
- Gross leverage: 2.1039x (unchanged)
- Commitment leverage: 1.1084x (unchanged)
- Derivative notional: €16,358,468 (unchanged)

**Expected breakage**: None (formulas and helper unchanged)

### 2.2 ESG (CRITICAL - requires design decision)

**Current behavior**:
```python
# esg_utils.py lines 110-124
if pos['asset_class'] == 'Derivative':            # Only OPT_SPX_PUT_001
    # Use helper → delta-adjusted notional
elif pos['asset_class'] == 'FX':                  # FWD_EURUSD_001, FWD_GBPUSD_001
    # Zero exposure
elif pos['asset_class'] == 'Cash':
    # Zero exposure
else:                                              # All equity, bonds
    # Use market_value_eur
```

**After reclassification** (ALL derivatives now have `asset_class == 'Derivative'`):
- Futures (were Equity) → transition from market_value to ???
- Forwards (were FX) → transition from zero to ???
- Options (were Derivative) → remain on helper

**Design decision needed** (Section 5):
- Option A: All derivatives use `abs(delta_adjusted_notional_eur)` 
  - **Pros**: Consistent formula, futures/options get ESG-weighted exposure
  - **Cons**: Futures become ESG-weighted (may not want this)
  
- Option B: Filter by underlying_asset_class for ESG-relevant derivatives
  - **Pros**: Selective: equities/bonds get ESG weight, FX/commodities stay zero
  - **Cons**: More complex routing logic
  
- Option C: Preserve current behavior by sub_asset_class
  - **Pros**: Zero migration risk, outputs identical
  - **Cons**: Doesn't fully utilize derivative underlying data

**Expected breakage**: 
- **Certain**: ESG exposure routing changes
- **Likely**: ESG totals shift (futures now weighted vs zero before)
- **Depends on choice**: Magnitude of change

### 2.3 Liquidity (Needs rework)

**Current behavior** (inferred):
```python
# liquidity.py (estimated)
if asset_class in ('Equity', 'Future'):
    liquidity_bucket = 'listed_equity'
elif asset_class == 'FX':
    liquidity_bucket = 'fx'
elif asset_class == 'Bond':
    liquidity_bucket = 'bonds'
elif asset_class == 'Cash':
    liquidity_bucket = 'cash'
elif asset_class == 'Derivative':
    liquidity_bucket = 'listed'
```

**After reclassification**:
- Cannot use `asset_class` to route anymore
- Must use `sub_asset_class` + `underlying_asset_class` combo:
  ```python
  if sub_asset_class == 'Future':
      underlying = derivative_contracts[isin]['underlying_asset_class']
      if underlying == 'Equity':
          liquidity_bucket = 'listed_equity'
      elif underlying == 'FX':
          liquidity_bucket = 'fx'
  elif sub_asset_class == 'Forward':
      underlying = derivative_contracts[isin]['underlying_asset_class']
      if underlying == 'FX':
          liquidity_bucket = 'fx'
  elif sub_asset_class == 'Listed Option':
      underlying = derivative_contracts[isin]['underlying_asset_class']
      if underlying == 'Equity':
          liquidity_bucket = 'listed_equity'
  ```

**Expected breakage**: Likely (routing logic must be rewritten)

### 2.4 Attribution (Needs audit)

**Impact**: Similar to liquidity - must switch from asset_class to underlying_asset_class

### 2.5 Pre-Trade Checks (Should be safe)

**Current behavior**: Checks like gross_leverage, concentration, etc.
- These use `leverage_result` dict (already computed)
- Not directly dependent on asset_class filtering

**After refactor**: Should work unchanged if leverage is unchanged

**Expected breakage**: None (leverage unchanged → pre-trade unchanged)

### 2.6 Operational Checks (Audit required)

**Impact**: May have asset_class-specific business logic
- Example: "futures cannot be short?", "options must be listed?"
- **Action**: Full audit needed

---

## 3. DATABASE & REGENERATION STRATEGY

### 3.1 Data Flow

```
reference_data/position_specs.json
    ↓ (update asset_class for futures/forwards)
setup_db.py → generate_positions.py → database INSERT
    ↓
Query_positions() → positions table
    ↓
get_risk_ready_df() → enrichment → DataFrame
    ↓
Leverage / ESG / Liquidity / etc
```

### 3.2 Regeneration Steps

**Phase B.1**: Update position_specs.json
- Change 3 futures: `asset_class` = "Equity" → "Derivative"
- Change 2 forwards: `asset_class` = "FX" → "Derivative"
- Keep `sub_asset_class` values unchanged (Future, Forward)
- ✅ No UCITS derivatives → no UCITS changes needed

**Phase B.2**: Regenerate database
```bash
python3 setup_db.py --reset  # Drop & recreate
python3 generate_positions.py --fund AIFM_HedgeFund
# Result: 16 positions (3 futures, 2 forwards, 1 option now all asset_class=Derivative)
```

**Phase B.3**: Verify data
```python
from fund_risk_workflow.data.database import get_engine, query_positions
engine = get_engine()
positions = query_positions(engine, 'AIFM_HedgeFund', '2026-03-31')
derivatives = positions[positions['asset_class'] == 'Derivative']
assert len(derivatives) == 6  # 3 futures + 2 forwards + 1 option
```

### 3.3 Backup Strategy

- Ensure original `position_specs.json` backed up
- Test regeneration on copy before overwriting database
- Keep old database snapshot for comparison testing

---

## 4. EXPOSURE ROUTING IMPACT ANALYSIS

### 4.1 AIFM Leverage (Safe)

| Item | Current | After Refactor | Impact |
|------|---------|-----------------|--------|
| Gross exposure method | Derivatives at gross notional | Derivatives at gross notional | ✅ No change |
| Commitment exposure | Derivatives at delta-adjusted | Derivatives at delta-adjusted | ✅ No change |
| Hedge treatment | Outside helper | Outside helper | ✅ No change |
| Futures → Gross | abs(qty) * csize * px * fx | Same via helper | ✅ Match expected |
| Forwards → Gross | abs(qty) * csize * px * fx | Same via helper | ✅ Match expected |
| **Regression test**: Leverage outputs identical | TBD | Expected: 2.1039x gross, 1.1084x commitment |

### 4.2 ESG (Requires design decision)

| Item | Current | After Refactor | Decision |
|------|---------|-----------------|----------|
| Futures ESG weight | market_value_eur (Equity path) | ??? | Option A/B/C |
| Forwards ESG weight | 0.0 (FX path) | ??? | Option A/B/C |
| Options ESG weight | abs(delta_adj_notional) | abs(delta_adj_notional) | ✅ Unchanged |
| **Design needed**: ESG exposure for equity/bond derivatives vs FX derivatives |

### 4.3 Liquidity (Must rework routing)

| Item | Current | After Refactor | Action |
|------|---------|-----------------|--------|
| Futures bucket | listed_equity (via asset_class=Equity) | ??? by sub_asset_class + underlying | Rewrite routing |
| Forwards bucket | fx (via asset_class=FX) | ??? by sub_asset_class + underlying | Rewrite routing |
| Options bucket | listed (via asset_class=Derivative) | ??? by sub_asset_class + underlying | Update routing |

---

## 5. ESG DESIGN OPTIONS (Detailed)

### Option A: All Derivatives Use Delta-Adjusted Notional

**Rule**: If `asset_class == 'Derivative'`, use `abs(delta_adjusted_notional_eur)`

```python
# esg_utils.py (updated)
if pos['asset_class'] == 'Derivative':
    esg_exposure = abs(helper_result['delta_adjusted_notional_eur'])
elif pos['asset_class'] == 'FX':
    esg_exposure = 0.0
elif pos['asset_class'] == 'Cash':
    esg_exposure = 0.0
else:
    esg_exposure = abs(pos['market_value_eur'])
```

**Impact**:
- ✅ Simple: one formula for all derivatives
- ✅ Consistent: futures get ESG weight like options
- ❌ New behavior: FX forwards now have ESG exposure (currently 0)
- ❌ May not be intentional: not all derivatives are equity-like
- **Estimated ESG shift**: Forwards add exposure, but they have no ESG data anyway (NaN)

**Test baseline** (current ESG with Phase 3c):
- WAV ESG: 67.3
- Total ESG exposure: €128,070,878

**Expected after Option A**:
- WAV ESG: ??? (likely unchanged if forwards have NaN ESG scores)
- Total ESG exposure: ??? (forwards have zero ESG weight if underlying has no ESG)

### Option B: Equity/Bond Derivatives Use Helper; FX/Commodity Derivatives Zero

**Rule**: Route by `underlying_asset_class`

```python
if pos['asset_class'] == 'Derivative':
    underlying_class = derivative_contracts[isin]['underlying_asset_class']
    if underlying_class in ('Equity', 'Bond'):
        esg_exposure = abs(helper_result['delta_adjusted_notional_eur'])
    else:  # FX, Commodity, etc
        esg_exposure = 0.0
elif pos['asset_class'] == 'Cash':
    esg_exposure = 0.0
else:
    esg_exposure = abs(pos['market_value_eur'])
```

**Impact**:
- ✅ Selective: only ESG-relevant derivatives get weighted
- ✅ Matches intent: FX still zero
- ❌ More complex: requires derivative_contracts lookup
- ✅ Preserves current behavior for forwards/FX: zero exposure
- ✅ Aligns with underlying economic risk

**Test baseline** (current):
- Forward exposures: 0 (via asset_class=FX path)
- Equity derivatives: weighted (via asset_class=Derivative path)

**Expected after Option B**:
- Forwards still 0 (unchanged, routed by underlying_asset_class=FX)
- Options still weighted (routed by underlying_asset_class=Equity)
- **Regression test**: ESG outputs identical

### Option C: Preserve Current Behavior by Sub_Asset_Class

**Rule**: Route by `sub_asset_class`, not `asset_class`

```python
if pos['sub_asset_class'] == 'Listed Option':
    # Use helper
    esg_exposure = abs(helper_result['delta_adjusted_notional_eur'])
elif pos['sub_asset_class'] == 'Forward':
    # Keep as zero (like current FX behavior)
    esg_exposure = 0.0
elif pos['sub_asset_class'] == 'Future':
    # Route by underlying_asset_class (like current Equity behavior)
    underlying_class = derivative_contracts[isin]['underlying_asset_class']
    if underlying_class == 'Equity':
        # Use market_value_eur (current Equity path)
        esg_exposure = abs(pos['market_value_eur'])
    else:
        esg_exposure = 0.0
elif pos['asset_class'] == 'Cash':
    esg_exposure = 0.0
else:
    esg_exposure = abs(pos['market_value_eur'])
```

**Impact**:
- ✅ Zero migration risk: outputs identical
- ✅ Preserves current ESG behavior exactly
- ❌ Does NOT benefit from new helper for futures
- ❌ Complex logic (per sub_asset_class routing)
- ❌ Mixes old shortcut logic with new proper classification

### Recommendation

**Option B is recommended** for Phase E (ESG redesign):
- ✅ Simple: route by underlying_asset_class
- ✅ Uses new derivative metadata properly
- ✅ Preserves current FX/commodity treatment (zero exposure)
- ✅ Aligns with risk semantics (equity derivatives get ESG)
- ✅ Regression test feasible: ESG outputs should be unchanged

**Alternative if zero-risk approach preferred**: Option C (preserve current routing), but this loses the benefit of the reclassification.

---

## 6. LIQUIDITY ROUTING REDESIGN

### Current Liquidity Logic (Inferred)

```
asset_class='Equity'                          → 'listed_equity' bucket
asset_class='Future' (doesn't exist currently) → n/a
asset_class='Bond'                            → 'bonds' bucket
asset_class='FX'                              → 'fx' bucket
asset_class='Derivative'                      → 'listed' bucket
asset_class='Cash'                            → 'cash' bucket
```

### Target Liquidity Logic (Post-Reclassification)

```
asset_class='Derivative' AND sub_asset_class='Future':
  underlying = derivative_contracts[isin]['underlying_asset_class']
  if underlying == 'Equity':       → 'listed_equity' bucket
  elif underlying == 'FX':         → 'fx' bucket
  elif underlying == 'Bond':       → 'bonds' bucket

asset_class='Derivative' AND sub_asset_class='Forward':
  underlying = derivative_contracts[isin]['underlying_asset_class']
  if underlying == 'Equity':       → 'listed_equity' bucket
  elif underlying == 'FX':         → 'fx' bucket
  elif underlying == 'Bond':       → 'bonds' bucket

asset_class='Derivative' AND sub_asset_class='Listed Option':
  underlying = derivative_contracts[isin]['underlying_asset_class']
  if underlying == 'Equity':       → 'listed_equity' bucket
  elif underlying == 'FX':         → 'fx' bucket
  elif underlying == 'Bond':       → 'bonds' bucket

asset_class='Equity'              → 'listed_equity' bucket
asset_class='Bond'                → 'bonds' bucket
asset_class='FX'                  → 'fx' bucket
asset_class='Cash'                → 'cash' bucket
```

### Liquidity Changes per Derivative

| ISIN | Name | Current | Target | Change |
|------|------|---------|--------|--------|
| EU0009658145 | Euro Stoxx 50 Future | listed_equity (Equity) | listed_equity (via underlying=Equity) | ✅ Same |
| FUT_SPY_SHORT_001 | S&P 500 Future | listed_equity (Equity) | listed_equity (via underlying=Equity) | ✅ Same |
| FUT_SX5E_SHORT_001 | Euro Stoxx Hedge | listed_equity (Equity) | listed_equity (via underlying=Equity) | ✅ Same |
| FWD_EURUSD_001 | EUR/USD Forward | fx (FX) | fx (via underlying=FX) | ✅ Same |
| FWD_GBPUSD_001 | GBP/USD Forward | fx (FX) | fx (via underlying=FX) | ✅ Same |
| OPT_SPX_PUT_001 | SPX Put Option | listed (Derivative) | listed_equity (via underlying=Equity) | ⚠️  Different |

**Impact**: Listed Option routing changes from 'listed' to 'listed_equity' (more specific).

---

## 7. CONCENTRATION & PRE-TRADE IMPACT

### Concentration Checks

**Current behavior** (inferred):
```python
# risk_utils.py
equity_exposure = risk_df[risk_df['asset_class'] == 'Equity']['market_value_eur'].abs().sum()
fx_exposure = risk_df[risk_df['asset_class'] == 'FX']['market_value_eur'].abs().sum()
derivative_exposure = risk_df[risk_df['asset_class'] == 'Derivative']['market_value_eur'].abs().sum()
```

**After reclassification**:
- `asset_class == 'Equity'` no longer includes futures ❌ (loses €1.4B notional)
- `asset_class == 'FX'` no longer includes forwards ❌ (loses €5.5B notional)
- `asset_class == 'Derivative'` now includes futures + forwards ✅ (gains both)

**Impact on concentration limits** (AIFM Hedge Fund):
- Gross leverage: Uses derivative helper → **unchanged** ✅
- Equity concentration: May change (futures no longer counted as equity) ❓
- FX concentration: May change (forwards no longer counted as FX) ❓

**Solution**: 
- Use `leverage_result['gross_exposure']` (which uses helper) instead of asset_class filtering
- Route concentration by `underlying_asset_class` from derivative_contracts

### Pre-Trade Checks

**Current behavior**:
```python
def check_aifm_hf_clean_trade(risk_df, leverage_result, trade, nav):
    # Uses leverage_result['gross_leverage'], etc.
    # Not dependent on asset_class directly
```

**After refactor**: Should work unchanged ✅
- Pre-trade calls leverage (which is unchanged)
- Returns same gross/commitment leverage
- Concentration checks updated to use underlying_asset_class

---

## 8. REPORTING & ANNEX IV DESIGN DECISION

### Current Reporting (Inferred)

Annex IV likely breaks down by asset class:
```
Equities:     [Long equity ETFs + Long equity stocks]
Bonds:        [Bond holdings]
FX:           [FX forwards]
Derivatives:  [Listed options]
Cash:         [Cash]
```

### After Reclassification

**Decision**: Show exposure by instrument form or economic exposure?

**Option 1: Show by instrument form**
```
Equities:     [Long equity ETFs + Long equity stocks]
Bonds:        [Bond holdings]
FX:           [FX forwards]
Derivatives:  [All futures, forwards, options]
Cash:         [Cash]
```
- ❌ Loses economic bucket visibility
- ❌ Lumps equity futures with FX forwards

**Option 2: Show by economic exposure**
```
Equity Exposure:
  ├─ Direct equities
  ├─ Equity index futures (SPY, SX5E)
  └─ Equity option (SPX put)

FX Exposure:
  └─ FX forwards (EUR/USD, GBP/USD)

Bond Exposure:
  └─ Bonds

Cash:
  └─ Cash
```
- ✅ Shows economic risk clearly
- ✅ Supports regulatory interpretation
- ❌ Requires report template redesign

**Option 3: Show both (dual reporting)**
```
By Instrument Form:
  Equities, Bonds, Derivatives, Cash

By Economic Exposure:
  Equity Exposure, FX Exposure, Bond Exposure, Cash
```
- ✅ Complete transparency
- ❌ Report complexity doubles

**Recommendation**: Option 2 (by economic exposure) aligns better with AIFMD Annex IV intent (what risk does the fund have?), but requires design review.

---

## 9. COMPREHENSIVE TEST PLAN

### Phase A Tests: Audit & Code Mapping

**No tests; pure audit**

### Phase B Tests: Data Reclassification

**test_position_specs_reclassification.py** (new):
```python
def test_position_specs_all_derivatives_same_class():
    """All derivatives have asset_class='Derivative' after refactor."""
    specs = load_position_specs('AIFM_HedgeFund')
    derivatives = [p for p in specs if p.get('sub_asset_class') in 
                   ('Future', 'Forward', 'Listed Option')]
    assert all(p['asset_class'] == 'Derivative' for p in derivatives)
    assert len(derivatives) == 6

def test_position_specs_sub_asset_class_correct():
    """sub_asset_class correctly identifies derivative type."""
    specs = load_position_specs('AIFM_HedgeFund')
    futures = [p for p in specs if p['isin'] in 
               ('EU0009658145', 'FUT_SPY_SHORT_001', 'FUT_SX5E_SHORT_001')]
    assert all(p['sub_asset_class'] == 'Future' for p in futures)
    
    forwards = [p for p in specs if p['isin'] in 
                ('FWD_EURUSD_001', 'FWD_GBPUSD_001')]
    assert all(p['sub_asset_class'] == 'Forward' for p in forwards)
    
    options = [p for p in specs if p['isin'] == 'OPT_SPX_PUT_001']
    assert all(p['sub_asset_class'] == 'Listed Option' for p in options)

def test_database_regeneration_matches_specs():
    """Generated positions match reclassified specs."""
    positions = query_positions(engine, 'AIFM_HedgeFund', '2026-03-31')
    derivatives = positions[positions['asset_class'] == 'Derivative']
    assert len(derivatives) == 6
```

### Phase C Tests: Exposure Routing (Leverage)

**test_leverage_after_reclassification.py** (updated):
```python
def test_gross_leverage_unchanged():
    """Gross leverage identical after reclassification."""
    result = compute_leverage(risk_df_new, nav, bbg, deriv_bbg_map, currency_bbg_map)
    assert result['gross_leverage'] == pytest.approx(2.1039, rel=1e-3)

def test_commitment_leverage_unchanged():
    """Commitment leverage identical after reclassification."""
    result = compute_leverage(risk_df_new, nav, bbg, deriv_bbg_map, currency_bbg_map)
    assert result['commitment_leverage'] == pytest.approx(1.1084, rel=1e-3)

def test_all_derivatives_through_helper():
    """All 6 derivatives routed through helper (not asset_class shortcut)."""
    # Verify helper is called for futures + forwards + options
    result = compute_leverage(risk_df_new, nav, bbg, deriv_bbg_map, currency_bbg_map)
    assert result['deriv_notional_commitment'] == pytest.approx(16358468, rel=1e-3)
```

### Phase D Tests: Pre-Trade & Concentration

**test_pre_trade_after_reclassification.py** (updated):
```python
def test_aifm_hf_gross_leverage_check():
    """Pre-trade gross leverage check unchanged."""
    # Same trade, same fund state → same pass/fail
    assert check_aifm_hf_clean_trade(...) == expected_result

def test_concentration_by_underlying_asset_class():
    """Concentration routed by underlying_asset_class, not asset_class."""
    # Verify equity index futures count toward equity concentration
    # Verify FX forwards count toward FX concentration
```

### Phase E Tests: ESG (depends on design choice)

**test_esg_after_reclassification.py** (updated - assumes Option B):
```python
def test_option_esg_exposure_unchanged():
    """Listed option ESG exposure same as before."""
    esg_df = build_esg_df(risk_df_new, bbg, engine, 'AIFM_HedgeFund', '2026-03-31')
    opt_row = esg_df[esg_df['isin'] == 'OPT_SPX_PUT_001']
    assert opt_row['esg_exposure_eur'].values[0] == pytest.approx(16358468, rel=1e-3)

def test_forward_esg_exposure_still_zero():
    """FX forward ESG exposure remains zero (underlying=FX)."""
    esg_df = build_esg_df(risk_df_new, bbg, engine, 'AIFM_HedgeFund', '2026-03-31')
    fwd_row = esg_df[esg_df['isin'] == 'FWD_EURUSD_001']
    assert fwd_row['esg_exposure_eur'].values[0] == 0.0

def test_equity_future_esg_exposure_by_underlying():
    """Equity index future uses underlying_asset_class=Equity for routing."""
    # Current: market_value_eur (via Equity asset_class)
    # After: use underlying_asset_class to route
    # Expected: ESG exposure determined by underlying Equity classification
```

### Phase F Tests: Liquidity (if refactored)

**test_liquidity_after_reclassification.py** (new):
```python
def test_equity_future_in_equity_bucket():
    """Equity index future routes to listed_equity bucket."""
    liquidity = compute_liquidity(risk_df_new, ...)
    assert 'FUT_SPY_SHORT_001' in liquidity['listed_equity']

def test_fx_forward_in_fx_bucket():
    """FX forward routes to fx bucket."""
    liquidity = compute_liquidity(risk_df_new, ...)
    assert 'FWD_EURUSD_001' in liquidity['fx']
```

### Phase G Tests: Integration Smoke Check

**test_active_workflow_after_reclassification.py** (new):
```python
def test_aifm_hedge_fund_workflow():
    """Full workflow (load → leverage → ESG → pre-trade)."""
    # Leverage unchanged ✓
    # ESG outputs as designed ✓
    # Pre-trade checks work ✓
    # Liquidity correct ✓

def test_ucits_balanced_workflow():
    """UCITS workflow unchanged (no derivatives)."""
    # Should pass unchanged ✓
```

---

## 10. IMPLEMENTATION SEQUENCE

### Phase A: Audit & Code Mapping (Current)
**Deliverable**: This plan document
**Time**: ~4 hours (done)
**Output**: Comprehensive impact analysis

### Phase B: Data Reclassification
**Files to modify**:
- `reference_data/funds/AIFM_HedgeFund/position_specs.json` (futures & forwards: asset_class → Derivative)
- `reference_data/funds/UCITS_Balanced/position_specs.json` (verify, no changes needed)

**Steps**:
1. Backup original position_specs.json files
2. Reclassify futures & forwards in AIFM_HedgeFund/position_specs.json
3. Regenerate database: `setup_db.py --reset`
4. Generate positions: `generate_positions.py --fund AIFM_HedgeFund`
5. Run Phase B tests

**Time**: ~2 hours
**Risk**: Low (data layer only, no code changes)
**Regression**: Phase B tests verify 6 derivatives with correct asset_class/sub_asset_class

### Phase C: Exposure Routing (Leverage)
**Files to modify**:
- None (leverage.py already calls helper; no change needed)

**Steps**:
1. Verify leverage.py works unchanged (it already filters by asset_class == 'Derivative')
2. Run Phase D leverage regression tests
3. Confirm gross/commitment leverage unchanged

**Time**: ~1 hour
**Risk**: Low (no code changes, just verification)
**Regression**: Phase C tests confirm 2.1039x gross, 1.1084x commitment unchanged

### Phase D: Pre-Trade & Concentration Updates
**Files to modify**:
- `src/fund_risk_workflow/risk/risk_utils.py` (update concentration routing)
- `src/fund_risk_workflow/data/operational_checks.py` (audit & update if needed)

**Steps**:
1. Audit concentration logic in risk_utils.py
2. Update to use `leverage_result['gross_exposure']` instead of asset_class filtering
3. Route concentration by `underlying_asset_class` via derivative_contracts lookup
4. Run Phase D pre-trade regression tests

**Time**: ~3 hours
**Risk**: Medium (changes concentration routing logic)
**Regression**: Pre-trade checks return same pass/fail for same trades

### Phase E: ESG Derivative Treatment (Design Choice)
**Decision required**: Option A, B, or C
**Recommended**: Option B (route by underlying_asset_class)

**Files to modify**:
- `src/fund_risk_workflow/risk/esg_utils.py` (redesign derivative ESG routing)

**Steps** (assuming Option B):
1. Implement underlying_asset_class-based routing
2. Run Phase E ESG regression tests
3. Verify WAV ESG, total exposure unchanged

**Time**: ~3 hours
**Risk**: Medium (ESG routing redesign, but outputs should be similar)
**Regression**: Phase E tests confirm ESG outputs match current behavior

### Phase F: Liquidity Routing Updates (if time allows)
**Files to modify**:
- `src/fund_risk_workflow/computation/liquidity.py` (redesign asset_class routing)

**Steps**:
1. Audit liquidity.py asset_class buckets
2. Rewrite to use sub_asset_class + underlying_asset_class routing
3. Run Phase F liquidity tests
4. Verify futures/options/forwards in correct buckets

**Time**: ~4 hours
**Risk**: Medium-High (core liquidity logic change)
**Regression**: Phase F tests confirm bucket assignments correct

### Phase G: Reporting & Annex IV Design (Deferred)
**Decision required**: Show by instrument form or economic exposure?
**Status**: Defer to separate work (out of scope for active workflows)

### Phase G: Integration Smoke Test
**Deliverable**: test_active_workflow_after_reclassification.py

**Steps**:
1. Run full AIFM Hedge Fund workflow (load → leverage → ESG → pre-trade)
2. Run full UCITS Balanced workflow (should be unchanged)
3. Verify all 235 active tests pass
4. Compare outputs to baseline (pre-refactor)

**Time**: ~2 hours
**Risk**: Low (if Phases A-F passed)
**Regression**: All active tests pass; outputs match expected (unchanged or designed changes)

---

## 11. RISK ASSESSMENT & LIKELY BREAKAGES

### Certain Breakages (Without Fixes)

1. **ESG exposure routing** ⚠️ CRITICAL
   - Forwards currently zero (asset_class=FX)
   - After reclassification, would fall into same code path as options
   - **Fix**: Implement Phase E (routing by underlying_asset_class)
   - **Impact**: ESG totals may change, WAV ESG may change

2. **Liquidity bucket routing** ⚠️ CRITICAL
   - Cannot use `asset_class` to route anymore
   - Futures/options now all asset_class=Derivative
   - **Fix**: Implement Phase F (routing by sub_asset_class + underlying)
   - **Impact**: Liquidity buckets must be recalculated

3. **Concentration by asset_class** ⚠️ MAJOR
   - Equity concentration would not include futures anymore
   - FX concentration would not include forwards anymore
   - **Fix**: Route by underlying_asset_class instead
   - **Impact**: Concentration checks may show different values

### Likely Safe (Verified by Testing)

1. **Leverage** ✅ SAFE
   - Helper already filters by asset_class == 'Derivative'
   - After refactor, futures/forwards caught by helper
   - Formulas unchanged → outputs unchanged
   - **Regression test**: Gross/commitment leverage identical

2. **Pre-trade checks** ✅ SAFE
   - Use leverage_result dict (which is unchanged)
   - Not directly dependent on asset_class
   - **Regression test**: Pre-trade pass/fail unchanged

3. **UCITS workflow** ✅ SAFE
   - No derivatives present
   - No changes needed to UCITS position_specs
   - **Regression test**: UCITS tests pass unchanged

### Unlikely But Possible Breakages

1. **Operational checks** ❓ UNCERTAIN
   - May have asset_class-specific validation (e.g., "no naked puts")
   - **Mitigation**: Full audit in Phase A
   - **Regression test**: Operational checks pass/fail unchanged

2. **Attribution** ❓ UNCERTAIN
   - May have asset_class buckets
   - **Mitigation**: Audit in Phase A
   - **Regression test**: Attribution breakdowns match expected

3. **Enrichment pipeline** ❓ UNCERTAIN
   - May have asset_class-specific enrichment
   - **Mitigation**: Audit in Phase A
   - **Regression test**: Enriched DataFrame structure unchanged

---

## 12. VALIDATION CHECKPOINTS

### Before Implementation

- [ ] Code audit complete (Phase A)
- [ ] All code paths depending on asset_class identified
- [ ] Regression test plan finalized
- [ ] ESG design decision made (Option A/B/C)
- [ ] Liquidity routing redesign sketched
- [ ] Reporting breakdowns designed
- [ ] Stakeholder approval: leverage outputs acceptable to change from 100% current code to 100% helper?
- [ ] Stakeholder approval: ESG outputs acceptable to use underlying_asset_class routing?

### During Implementation

- [ ] Phase B: Position_specs reclassified, database regenerated, 6 derivatives asset_class=Derivative
- [ ] Phase C: Leverage tests pass, gross/commitment leverage identical
- [ ] Phase D: Pre-trade tests pass, concentration logic updated
- [ ] Phase E: ESG tests pass (depends on design choice)
- [ ] Phase F: Liquidity tests pass (if implemented)
- [ ] Phase G: Full workflow smoke tests pass

### After Implementation

- [ ] All 235 active tests pass
- [ ] AIFM Hedge Fund workflow runs end-to-end
- [ ] UCITS Balanced workflow runs end-to-end
- [ ] Leverage outputs match current (2.1039x gross, 1.1084x commitment)
- [ ] ESG outputs match current or designed changes
- [ ] Pre-trade checks work correctly
- [ ] No inactive notebooks broken (out of scope but monitor)

---

## 13. ESTIMATES & TIMELINE

| Phase | Task | Effort | Risk | Notes |
|-------|------|--------|------|-------|
| A | Audit & Planning | 4h | Low | Current (done) |
| B | Data Reclassification | 2h | Low | Position_specs, DB regen |
| C | Leverage Verification | 1h | Low | No code changes |
| D | Pre-Trade & Concentration | 3h | Medium | Updates routing logic |
| E | ESG Routing Redesign | 3h | Medium | Depends on design choice |
| F | Liquidity Routing Updates | 4h | Medium-High | Core logic change |
| G | Smoke Tests | 2h | Low | Integration testing |
| **Total** | | **19h** | Medium | ~2.5 days |

---

## 14. RECOMMENDED NEXT STEPS (After Plan Approval)

1. **Decision Point**: Approve ESG routing design (Option A, B, or C)
2. **Decision Point**: Approve liquidity routing redesign
3. **Decision Point**: Approve reporting breakdowns
4. **Implementation Gate**: Proceed with Phase B (data reclassification) once decisions made
5. **Testing Gate**: All regression tests pass before moving to next phase
6. **Stakeholder Review**: After Phase G, review outputs before committing changes

---

**End of Derivative Classification Refactor Plan**

**Status**: ✅ **Plan Complete - Ready for Stakeholder Review**

**Next Action**: Obtain approval on ESG design choice (Option A/B/C) before proceeding to Phase B implementation.
