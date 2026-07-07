# Phase 3 Design Note: Canonical Derivative Exposure Helper

**Status**: Design Only — No Implementation Yet  
**Date**: 2026-06-21  
**Phase**: Phase 3 (to proceed after Phase 2 acceptance)

---

## 1. Proposed Module and Functions

### Module Location
```
src/fund_risk_workflow/computation/derivatives.py
```

### Proposed Function Signatures

#### 1.1 Market Input Fetcher
```python
def fetch_derivative_market_inputs(
    bloomberg_ticker: str,
    bbg,
    cache: dict | None = None
) -> dict:
    """
    Fetch DELTA, OPT_UNDL_PX, CONTRACT_SIZE from Bloomberg for a derivative.
    
    Supports optional per-run cache to avoid repeated fetches of the same
    ticker within a single portfolio calculation.
    
    Parameters
    ----------
    bloomberg_ticker : str
        Bloomberg ticker (e.g., 'SPXW 260619P05500 Index', 'SPY US Equity')
    bbg : MockBloomberg or BloombergAPI
        Bloomberg data provider
    cache : dict, optional
        Running cache {ticker: market_inputs_dict}. Modified in-place.
    
    Returns
    -------
    dict with keys:
        delta : float or None
            Hedge ratio (None if not available or not applicable)
        underlying_price : float
            OPT_UNDL_PX or equivalent spot/forward price
        contract_size : float
            CONTRACT_SIZE (multiplier). Defaults to 1 if not found.
        ccy : str
            Settlement currency from CRNCY
        _fetched_at : str
            Timestamp for cache validity
    
    Raises
    ------
    ValueError
        If bloomberg_ticker is None or empty
    
    Notes
    -----
    Cache is optional; if provided and ticker exists, returns cached value.
    Otherwise fetches from bbg and updates cache (if provided).
    """
    pass
```

#### 1.2 Single Position Exposure Compute
```python
def compute_derivative_exposure(
    quantity: float,
    delta: float | None,
    underlying_price: float | None,
    contract_multiplier: float,
    fx_rate: float,
    contract_type: str,
    is_hedge: bool = False
) -> dict:
    """
    Compute derivative exposure(s) for a single position.
    
    Returns both gross and delta-adjusted notional. Caller decides
    which basis to use (AIFMD gross, AIFMD commitment, UCITS global, etc).
    
    Parameters
    ----------
    quantity : float
        Quantity of derivative contracts
    delta : float or None
        Hedge ratio. None for futures (treated as delta=1) or if unavailable.
    underlying_price : float or None
        Spot or forward price of underlying. Required for notional calc.
    contract_multiplier : float
        Notional units per contract (e.g. 100 for equity options)
    fx_rate : float
        Conversion factor from derivative settlement currency to EUR.
        Default 1.0 (already in EUR or rate already applied).
    contract_type : str
        'future', 'option', or 'forward'. Controls delta logic.
    is_hedge : bool, default False
        Flag for regulatory netting (used by caller, not here).
    
    Returns
    -------
    dict with keys:
        market_value_eur : float
            As input (premium or cash position)
        gross_notional_eur : float
            abs(qty) × contract_multiplier × underlying_price × fx_rate
            (no delta adjustment; input to AIFMD gross exposure method)
        delta_adjusted_notional_eur : float
            delta × qty × contract_multiplier × underlying_price × fx_rate
            where delta = 1 for futures/forwards if None
            (input to AIFMD commitment exposure method; hedge netting is caller's responsibility)
        underlying_price : float
            For reference
        underlying_multiplier : float
            For reference
        delta : float or None
            For reference
        exposure_basis : str
            'underlying_notional' (futures, forwards)
            'delta_adjusted_underlying_notional' (options)
            (basis label only; no regulatory interpretation applied inside helper)
    
    Raises
    ------
    ValueError
        If underlying_price is None and exposure is notional (not premium)
    ValueError
        If contract_multiplier is None or ≤ 0
    """
    pass
```

#### 1.3 Portfolio Snapshot Compute
```python
def compute_derivative_exposures_portfolio(
    risk_df: pd.DataFrame,
    bbg,
    deriv_contracts: dict,
    currency_bbg_map: dict | None = None,
) -> dict:
    """
    Compute derivative exposures for all derivative positions in portfolio.
    
    Aggregates single-position exposures and returns gross, delta-adjusted,
    and commitment (hedge-aware) totals.
    
    Parameters
    ----------
    risk_df : pd.DataFrame
        Risk-ready positions. Requires columns:
        - isin, quantity, market_value_eur, bloomberg_ticker
        - asset_class, is_hedge, price, fx_rate
    bbg : MockBloomberg or BloombergAPI
        Bloomberg data provider
    deriv_contracts : dict
        Loaded from reference_data.load_derivative_contracts()
        {isin: contract_dict}
    currency_bbg_map : dict, optional
        {ccy: bbg_fx_ticker} for FX conversions (e.g., {'USD': 'EURUSD Curncy'})
    
    Returns
    -------
    dict with keys:
        by_position : pd.DataFrame
            One row per derivative with columns:
            - isin, quantity, market_value_eur
            - gross_notional_eur, delta_adjusted_notional_eur
            - delta, underlying_price, contract_multiplier
            - exposure_basis
        
        gross_total_eur : float
            Sum of gross_notional_eur for all derivatives
        
        delta_adjusted_total_eur : float
            Sum of delta_adjusted_notional_eur for all derivatives
            (input to AIFMD commitment exposure method; hedge netting is caller's responsibility)
        
        gross_by_contract_type : dict
            {'future': ..., 'option': ..., 'forward': ...}
        
        delta_adjusted_by_contract_type : dict
            {'future': ..., 'option': ..., 'forward': ...}
        
        bbg_cache : dict
            Running cache of {ticker: market_inputs} for reference
    
    Raises
    ------
    ValueError
        If any derivative is missing from deriv_contracts
    ValueError
        If required market inputs (underlying_price) are unavailable
        and cannot be omitted for notional calculation
    """
    pass
```

---

## 2. Inputs and Outputs

### Minimum Required Inputs

**From Positions DataFrame:**
- `isin` — instrument identifier
- `quantity` — contract count or notional quantity
- `price` — market price per unit (for market value, not notional)
- `market_value_eur` — current position value in EUR
- `bloomberg_ticker` — ticker for Bloomberg data fetch
- `asset_class` — "Derivative" filter
- `sub_asset_class` — "Listed Option", "Future", "Forward" (informational)
- `is_hedge` — boolean flag for regulatory netting (AIFMD Art. 8)
- `fx_rate` — rate to EUR (if settlement currency ≠ EUR)

**From derivative_contracts.json (via loader):**
- `contract_type` — "future", "option", or "forward"
- `contract_multiplier` — units per contract (e.g., 100)
- `underlying_ticker` — Bloomberg ticker for underlying
- `underlying_asset_class` — "Equity", "FX", etc.
- `settlement_currency` — "USD", "EUR", etc.
- `exposure_method_hint` — metadata only, not decision logic

**From MockBloomberg (fetched at runtime):**
- `DELTA` — hedge ratio (optional for futures; required for options)
- `OPT_UNDL_PX` — spot/forward price of underlying
- `CONTRACT_SIZE` — runtime multiplier (cross-check only; use ref data first)
- `CRNCY` — settlement currency (verify against ref data)

### Output Structure

Each exposure output is **explicit about basis**:

```python
{
    "market_value_eur": 45200,  # premium paid (for options), cash settlement
    
    "gross_notional_eur": 584231000,  # abs(qty) × multiplier × undl_px × fx
    # Used for AIFMD Art. 7 gross exposure (hedges included)
    
    "delta_adjusted_notional_eur": 163424680,  # delta × qty × multiplier × undl_px × fx
    # Used for AIFMD Art. 8 commitment (hedges excluded by caller)
    
    "commitment_exposure_eur": 163424680,  # delta_adjusted, or 0 if is_hedge
    # AIFMD commitment after hedge netting
    
    "underlying_ticker": "SPX Index",  # for traceability
    "underlying_asset_class": "Equity",
    "delta": -0.28,  # for reference
    "underlying_price": 5842.31,
    "contract_multiplier": 100,
    
    "exposure_basis": "delta_adjusted_underlying_notional",  # from ref data hint
    
    "warnings": []  # if any fallback or estimation occurred
}
```

---

## 3. Exposure Bases (Do Not Return One Ambiguous Number)

The helper must return **all three exposure bases** for each position:

| Basis | Formula | When Used |
|-------|---------|-----------|
| **Gross Notional** | `abs(qty) × csize × undl_px × fx` | AIFMD gross exposure method (includes all positions) |
| **Delta-Adjusted Notional** | `delta × qty × csize × undl_px × fx` | AIFMD commitment exposure method (raw delta-adjusted) & ESG (input) |

**Why two?**
- Caller decides regulatory treatment and hedge netting, not the helper.
- AIFMD gross exposure method includes all derivatives at full notional.
- AIFMD commitment exposure method uses delta-adjusted notional, then caller applies hedge netting.
- ESG may use delta-adjusted without hedge netting.
- UCITS pre-trade uses different calculation (not in this helper).

**Hedge Logic (Outside Helper):**
- Helper returns delta-adjusted notional regardless of `is_hedge` flag.
- Caller (leverage computation, ESG, reporting) applies hedge netting if needed.
- This keeps regulatory interpretation logic outside the pure computation module.

---

## 4. AIFMD vs UCITS Distinction

### For AIFM Hedge Fund (Current Primary Use)
**Current formulas must be reproduced exactly:**

```
AIFMD Gross Leverage (Article 7):
  gross_exposure = Σ abs(market_value_eur) for equities/bonds
                 + Σ [abs(qty) × csize × undl_px × fx] for derivatives
                 + borrowings

AIFMD Commitment Leverage (Article 8):
  commitment_exposure = net_equity + bonds + fx_exposure
                      + Σ [delta × qty × csize × undl_px × fx]  for non-hedge derivatives
                      + borrowings
```

**Phase 3 must prove equivalence** before wiring in.

### For UCITS Balanced (Future, Separate Step)
**Do not reuse AIFMD names or logic.**

Relevant UCITS concepts:
- **Global Exposure**: Commitment approach (currently documented) or VaR-based
- **Derivative Exposure**: Sum of notional or delta-adjusted notional (TBD)
- **Pre-Trade Exposure**: Current formula is `qty × price_eur`, not notional

**Current UCITS pre-trade issue:**
- Uses `qty × price_eur` (premium or simple market value)
- Ignores `contract_multiplier` and `delta`
- Different from monitoring if monitoring uses notional

**Design consequence:**
- Phase 3 creates helper for *both* bases (notional and premium)
- Phase 3 wires only AIFMD initially
- UCITS wiring deferred to Phase 4 (after separate review)

---

## 5. Formula Preservation

### Formulas to Reproduce Exactly (AIFM Hedge Fund)

#### Futures
```
Current (leverage.py, line 77):
  deriv_gross_map[idx] = abs(qty) * csize * undl_px * fx_rate
  deriv_commitment_map[idx] = delta * qty * csize * undl_px * fx_rate
  
Helper must return:
  gross_notional_eur = abs(quantity) × contract_multiplier × underlying_price × fx_rate
  delta_adjusted_notional_eur = delta × quantity × contract_multiplier × underlying_price × fx_rate
  (delta = 1.0 if None, as futures have delta=1)
```

#### Options
```
Current (same formulas, delta from Bloomberg):
  deriv_gross_map[idx] = abs(qty) * csize * undl_px * fx_rate
  deriv_commitment_map[idx] = delta * qty * csize * undl_px * fx_rate
  
Helper must return:
  gross_notional_eur = abs(quantity) × contract_multiplier × underlying_price × fx_rate
  delta_adjusted_notional_eur = delta × quantity × contract_multiplier × underlying_price × fx_rate
  (delta from Bloomberg OPT_UNDL_PX or bdp call)
```

#### FX Forwards
```
Current (treated like options, delta ≈ 1):
  deriv_gross_map[idx] = abs(qty) * 1 * undl_px * fx_rate
  deriv_commitment_map[idx] = 1 * qty * 1 * undl_px * fx_rate
  
Helper must return:
  gross_notional_eur = abs(quantity) × 1 × underlying_rate × fx_rate
  delta_adjusted_notional_eur = quantity × 1 × underlying_rate × fx_rate
  (delta = 1.0 implicitly)
```

#### Hedge Treatment (Outside Helper)
```
Current (leverage.py, line 80):
  deriv_commitment_map[idx] = (
      delta * qty * csize * undl_px * fx_rate
      if row.get('is_hedge', 0) != 1 else 0.0
  )
  
Helper RETURNS delta_adjusted_notional_eur regardless.
CALLER (leverage_computation.py) applies hedge netting if needed (zero out if is_hedge=1).
```

**Test requirement:**
- Helper returns correct raw values; caller applies hedge logic

---

## 6. Fallback Behaviour

### Current Bad Fallback
```python
# leverage.py lines 82-87 (fallback when Bloomberg not available)
else:
    deriv_gross_map[idx] = abs(row['market_value_eur'])
    deriv_commitment_map[idx] = (
        row['market_value_eur']
        if row.get('is_hedge', 0) != 1 else 0.0
    )
```

**Problem:** Uses market_value_eur for notional exposure (wrong when multiplier ≠ 1).

### Proposed Safer Rules

**Rule 1: Fail Loudly**
```python
def compute_derivative_exposure(...):
    if underlying_price is None and exposure_basis in ['notional', 'delta_adjusted']:
        raise ValueError(
            f"Derivative {isin}: underlying_price required for {exposure_basis} exposure, "
            f"but not available from Bloomberg. Check deriv_contracts and MockBloomberg setup."
        )
    
    if contract_multiplier is None or contract_multiplier <= 0:
        raise ValueError(
            f"Derivative {isin}: contract_multiplier must be positive, "
            f"got {contract_multiplier}. Check deriv_contracts.json."
        )
```

**Rule 2: Explicit Basis Selection**
```python
# Caller specifies what they want:
if exposure_basis == 'notional':
    # Must have underlying_price, multiplier; will error if missing
    result = compute_derivative_exposure(..., basis='gross')
elif exposure_basis == 'premium':
    # Use market_value_eur (for option premium, cash positions)
    result = compute_derivative_exposure(..., basis='premium')
```

**Rule 3: Cache State Visible**
```python
result = {
    "gross_notional_eur": ...,
    "delta_adjusted_notional_eur": ...,
    "warnings": [
        "DELTA not available from Bloomberg; using delta=0.5 (mid-point estimate)"
    ]  # caller can decide whether to accept or reject
}
```

**Rule 4: No Silent Premium/Notional Confusion**
- If notional exposure is requested but only premium is available → error
- If premium exposure is requested but market_value_eur is zero → return 0, not estimated notional

---

## 7. Caching Strategy

### Lightweight Per-Run Cache

**Scope:** Cache within a single `compute_derivative_exposures_portfolio()` call.

**Design:**
```python
def fetch_derivative_market_inputs(
    bloomberg_ticker: str,
    bbg,
    cache: dict | None = None
) -> dict:
    if cache and bloomberg_ticker in cache:
        return cache[bloomberg_ticker]
    
    # Fetch from Bloomberg
    market_inputs = {
        'delta': bbg.bdp(ticker, 'DELTA'),
        'underlying_price': bbg.bdp(ticker, 'OPT_UNDL_PX'),
        'contract_size': bbg.bdp(ticker, 'CONTRACT_SIZE'),
        'ccy': bbg.bdp(ticker, 'CRNCY'),
    }
    
    # Update cache if provided
    if cache is not None:
        cache[bloomberg_ticker] = market_inputs
    
    return market_inputs
```

**Usage in Portfolio Compute:**
```python
def compute_derivative_exposures_portfolio(...):
    bbg_cache = {}  # per-run cache
    
    for _, pos in risk_df[risk_df['asset_class']=='Derivative'].iterrows():
        market_inputs = fetch_derivative_market_inputs(
            pos['bloomberg_ticker'], bbg, cache=bbg_cache
        )
        # Bloomberg is called at most once per unique ticker per calculation
    
    return {..., 'bbg_cache': bbg_cache}
```

**Benefits:**
- Avoids repeated Bloomberg calls (e.g., if portfolio has 5 OPT_SPX_PUT_001 positions, DELTA fetched once)
- No heavy state machine; cache is local to function
- Caller can inspect cache for debugging (optional transparency)

**No persistence across runs** (cache is reset between snapshots).

---

## 8. Test Plan

### Test Categories

#### 8.1 Correctness: Reproduce Current Formulas

**Test: Futures Gross and Commitment**
```python
def test_compute_derivative_exposure_future_gross_and_commitment():
    """SPY future: qty=-30000, csize=100, undl_px=523.42, fx=0.89"""
    result = compute_derivative_exposure(
        quantity=-30000,
        delta=1.0,  # futures
        underlying_price=523.42,
        contract_multiplier=100,
        fx_rate=0.89,
        contract_type='future',
        is_hedge=True
    )
    
    expected_gross = 30000 * 100 * 523.42 * 0.89
    expected_delta_adj = 1.0 * (-30000) * 100 * 523.42 * 0.89
    
    assert result['gross_notional_eur'] == expected_gross
    assert result['delta_adjusted_notional_eur'] == expected_delta_adj
```

**Test: Option Delta-Adjusted**
```python
def test_compute_derivative_exposure_option_delta_adjusted():
    """SPX Put: qty=-100, delta=-0.28, csize=100, undl_px=5842.31, fx=0.89"""
    result = compute_derivative_exposure(
        quantity=-100,
        delta=-0.28,
        underlying_price=5842.31,
        contract_multiplier=100,
        fx_rate=0.89,
        contract_type='option'
    )
    
    expected_gross = 100 * 100 * 5842.31 * 0.89
    expected_delta_adj = -0.28 * (-100) * 100 * 5842.31 * 0.89
    
    assert result['gross_notional_eur'] == expected_gross
    assert result['delta_adjusted_notional_eur'] == expected_delta_adj
```

**Test: Forward Notional**
```python
def test_compute_derivative_exposure_forward_notional():
    """EUR/USD forward: qty=10M, csize=1, rate=1.1234, fx=0.89"""
    result = compute_derivative_exposure(
        quantity=10000000,
        delta=1.0,  # forwards
        underlying_price=1.1234,
        contract_multiplier=1,
        fx_rate=0.89,
        contract_type='forward'
    )
    
    expected = 10000000 * 1 * 1.1234 * 0.89
    assert result['delta_adjusted_notional_eur'] == pytest.approx(expected)
```

#### 8.2 Error Handling: Reject Bad Inputs

**Test: Missing Underlying Price for Notional**
```python
def test_compute_derivative_exposure_missing_underlying_price():
    """Notional exposure without underlying_price should raise ValueError."""
    with pytest.raises(ValueError, match="underlying_price required"):
        compute_derivative_exposure(
            quantity=100,
            delta=0.5,
            underlying_price=None,  # ← missing
            contract_multiplier=100,
            fx_rate=1.0,
            contract_type='option'
        )
```

**Test: Missing Contract Multiplier**
```python
def test_compute_derivative_exposure_missing_multiplier():
    """contract_multiplier=0 or None should raise ValueError."""
    with pytest.raises(ValueError, match="contract_multiplier.*positive"):
        compute_derivative_exposure(
            quantity=100,
            delta=0.5,
            underlying_price=100.0,
            contract_multiplier=None,  # ← missing
            fx_rate=1.0,
            contract_type='option'
        )
```

**Test: No Fallback to Market Value**
```python
def test_no_fallback_market_value_for_notional():
    """Missing underlying_price should NOT fall back to market_value_eur."""
    result = compute_derivative_exposure(
        quantity=100,
        delta=0.5,
        underlying_price=None,
        contract_multiplier=100,
        fx_rate=1.0,
        contract_type='option'
    )
    # Should raise, not return market_value_eur estimate
```

#### 8.3 Integration: Portfolio Snapshot

**Test: Portfolio Aggregate Matches Inline Sum**
```python
def test_compute_derivative_exposures_portfolio_matches_inline():
    """
    Construct a risk_df with 3 derivatives (future, option, forward).
    Compare portfolio result to inline formula.
    Verify gross_total_eur, delta_adjusted_total_eur match.
    """
    risk_df = pd.DataFrame({
        'isin': ['FUT_SPY_SHORT_001', 'OPT_SPX_PUT_001', 'FWD_EURUSD_001'],
        'quantity': [-30000, -100, 10000000],
        'price': [523.42, 45.2, 1.1234],
        'market_value_eur': [-1398226560, -4031.8, 10000000],  # example values
        'bloomberg_ticker': ['SPY US Equity', 'SPXW 260619P05500 Index', 'EURUSD Curncy'],
        'asset_class': ['Derivative', 'Derivative', 'Derivative'],
        'is_hedge': [True, False, True],
        'fx_rate': [0.89, 0.89, 0.89],
    })
    
    deriv_contracts = load_derivative_contracts()
    bbg = MockBloomberg()
    
    result = compute_derivative_exposures_portfolio(
        risk_df, bbg, deriv_contracts
    )
    
    # Compare to current inline calculation in leverage.py
    # Should match exactly
```

#### 8.4 Caching

**Test: Cache Reduces Bloomberg Calls**
```python
def test_fetch_derivative_market_inputs_caches():
    """Same ticker fetched twice; second call uses cache."""
    cache = {}
    
    # First call
    fetch_derivative_market_inputs('SPY US Equity', bbg, cache)
    assert 'SPY US Equity' in cache
    
    # Second call with same ticker
    # If we mock bbg.bdp to raise, second call should not raise (uses cache)
    fetch_derivative_market_inputs('SPY US Equity', bbg_mocked, cache)
    # Should succeed because cache is used
```

#### 8.5 Hedge Logic

**Test: Hedge Flag Does Not Affect Helper Output**
```python
def test_hedge_flag_not_used_in_helper():
    """
    Same position with is_hedge=True and is_hedge=False
    should produce same delta_adjusted output from helper.
    (Caller applies netting rule.)
    """
    result_hedge = compute_derivative_exposure(..., is_hedge=True)
    result_no_hedge = compute_derivative_exposure(..., is_hedge=False)
    
    # Delta-adjusted output should be identical
    assert result_hedge['delta_adjusted_notional_eur'] \
        == result_no_hedge['delta_adjusted_notional_eur']
    
    # (Commitment netting is caller's responsibility)
```

---

## 9. Implementation Sequence (Smallest Safe Steps)

### Phase 3a: Foundation (Weeks 1–2)

1. **Create module**
   - File: `src/fund_risk_workflow/computation/derivatives.py`
   - Lines: ~150–200
   - Scope: Three functions (fetcher, single position, portfolio)

2. **Add tests**
   - File: `tests/test_derivative_exposure_helper.py`
   - Tests: ~12 test cases (formula correctness, error handling, caching, hedge)
   - Verify: Current inline formulas reproduced exactly

3. **Run tests in isolation**
   - `pytest tests/test_derivative_exposure_helper.py -v`
   - No integration with leverage.py yet
   - 100% of new tests should pass

### Phase 3b: AIFM Integration (Weeks 2–3)

4. **Update leverage.py**
   - Replace inline deriv_gross_map and deriv_commitment_map logic
   - Call helper via `compute_derivative_exposures_portfolio()`
   - Changes: ~40 lines removed, replaced by helper call

5. **Regression tests**
   - Run existing tests: `pytest tests/test_risk_utils.py::TestCheckAifmHfClean -v`
   - Compare pre/post leverage results on live database
   - Assert: Results unchanged (within floating-point tolerance)

6. **Verify with real data**
   - Run AIFM_HedgeFund notebook
   - Check leverage outputs match current values
   - Board risk report should be identical

### Phase 3c: Optional ESG Integration (Weeks 3–4, if time)

7. **Wire into ESG (optional)**
   - If esg_utils.py uses same formulas
   - Replace inline delta-adjusted notional with helper call
   - Tests: Compare ESG exposure outputs before/after

### Phase 3d: UCITS Deferred (After Separate Review)

8. **Do NOT wire into UCITS pre-trade yet**
   - UCITS pre-trade currently uses `qty × price`, not notional
   - Separate Phase 4 ticket with explicit UCITS requirements
   - Helper ready; wiring decision deferred

---

## 10. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Helper reproduces current formulas wrong | Regression tests compare every AIFM leverage run pre/post; assert identical |
| Cache causes stale data across runs | Cache is local to function; reset each calculation snapshot |
| UCITS pre-trade accidentally wired | Phase 3 explicitly does NOT touch UCITS; Phase 4 separate ticket |
| Hedge logic pushed into helper | Helper ignores is_hedge; returns raw delta-adjusted; caller applies netting |
| Silent fallback to market value | All fallbacks raise ValueError; caller must handle explicitly |
| Bloomberg unavailable during run | Error message guides troubleshooting (check MockBloomberg, deriv_contracts, ticker mappings) |

---

## 11. Success Criteria

- ✅ Helper module created with 3 functions
- ✅ All 12+ tests pass (formulas, errors, caching, hedge)
- ✅ Current AIFM leverage results unchanged after wiring helper
- ✅ Inline derivative logic replaced; code duplication eliminated
- ✅ Clear output fields (gross, delta-adj, commitment, basis metadata)
- ✅ No silent fallbacks; errors are explicit
- ✅ UCITS pre-trade explicitly NOT modified
- ✅ ESG integration optional and deferred if not same formula

---

**Recommendation:**  
Proceed with Phase 3 implementation after design approval.  
Suggested timeline: 2–3 weeks including regression testing.

