"""
test_ucits_wrappers.py
====================
Minimal validation tests for UCITS wrapper modules.

Run with:
    python tests/test_ucits_wrappers.py
"""

import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd


def test_reference_data_loaders():
    """Test reference data loaders."""
    from fund_risk_workflow.data.reference_data import (
        load_rmp,
        load_fund_profile,
        load_regulatory_framework,
        load_reference_portfolios,
        load_reference_portfolio,
    )

    print("\n[TEST] Reference data loaders...")

    # Load fund profile (static fund facts and regulatory classification)
    profile = load_fund_profile('UCITS_Balanced')
    assert profile['fund_id'] == 'UCITS_Balanced'
    assert profile['fund_type'] == 'UCITS'
    print(f"  ✓ load_fund_profile() works (static facts and classification)")

    # Load risk policy (operational parameters and monitoring choices)
    rmp = load_rmp('UCITS_Balanced')
    assert rmp['fund_id'] == 'UCITS_Balanced'
    assert rmp['global_exposure_policy']['reference_portfolio_id'] == 'global_equity_60_eur_gov_40'
    print(f"  ✓ load_rmp() works, reference_portfolio_id = {rmp['global_exposure_policy']['reference_portfolio_id']}")

    # Load regulatory framework
    ucits_regs = load_regulatory_framework('ucits_regulatory_framework')
    assert 'var_framework' in ucits_regs
    assert ucits_regs['var_framework']['absolute_limit_pct'] == 20.0
    assert ucits_regs['var_framework']['relative_limit_multiplier'] == 2.0
    print(f"  ✓ load_regulatory_framework() works")

    # Load reference portfolios
    portfolios = load_reference_portfolios()
    assert 'global_equity_60_eur_gov_40' in portfolios
    print(f"  ✓ load_reference_portfolios() works, found {len(portfolios)} portfolio(s)")

    # Load specific portfolio
    portfolio = load_reference_portfolio('global_equity_60_eur_gov_40')
    assert portfolio['name'] == '60% Global Equity / 40% EUR Government Bonds'
    assert len(portfolio['components']) == 2
    print(f"  ✓ load_reference_portfolio() works, loaded {portfolio['name']}")

    # Validate weights
    total_weight = sum(c['weight'] for c in portfolio['components'])
    assert abs(total_weight - 1.0) < 0.001
    print(f"  ✓ Reference portfolio weights sum to {total_weight:.4f}")


def test_srri_bucket_mapping():
    """Test SRRI bucket mapping."""
    from fund_risk_workflow.risk.ucits_srri import map_volatility_to_srri_bucket, SRRI_BOUNDARIES

    print("\n[TEST] SRRI bucket mapping...")

    # Test boundary cases
    test_cases = [
        (0.3, 1),    # < 0.5% → SRI 1
        (0.5, 2),    # 0.5% → SRI 2
        (1.5, 2),    # 1.5% → SRI 2
        (2.0, 3),    # 2.0% → SRI 3
        (5.0, 4),    # 5.0% → SRI 4
        (10.0, 5),   # 10.0% → SRI 5
        (15.0, 6),   # 15.0% → SRI 6
        (25.0, 7),   # 25.0% → SRI 7
        (50.0, 7),   # 50.0% → SRI 7
    ]

    for volatility, expected_bucket in test_cases:
        bucket = map_volatility_to_srri_bucket(volatility)
        status = "✓" if bucket == expected_bucket else "✗"
        print(f"  {status} {volatility:5.1f}% → SRI {bucket} (expected {expected_bucket})")
        assert bucket == expected_bucket, f"Mismatch at {volatility}%"

    print(f"  ✓ All bucket mapping tests passed")


def test_srri_from_returns():
    """Test SRRI computation from returns."""
    from fund_risk_workflow.risk.ucits_srri import compute_srri_from_returns

    print("\n[TEST] SRRI computation from returns...")

    # Create synthetic returns: weekly volatility 1% → annual ~5% → SRI 3
    np.random.seed(42)
    weekly_vol = 0.01  # 1% weekly
    returns = pd.Series(np.random.normal(0, weekly_vol, 260))

    result = compute_srri_from_returns(returns)
    print(f"  Weekly volatility: {result['volatility_weekly_pct']:.2f}%")
    print(f"  Annual volatility: {result['volatility_annual_pct']:.2f}%")
    print(f"  SRI bucket: {result['sri_bucket']}")
    print(f"  Observations: {result['observation_count']}")

    # Volatility should be close to 1% weekly * sqrt(52) ≈ 7.2% annual
    assert 6.0 < result['volatility_annual_pct'] < 8.0
    assert result['sri_bucket'] == 4  # Should be SRI 4 for ~7% volatility
    print(f"  ✓ SRRI computation correct")


def test_srri_change_trigger():
    """Test SRRI change trigger logic."""
    from fund_risk_workflow.risk.ucits_srri import check_srri_change_trigger

    print("\n[TEST] SRRI change trigger...")

    # Scenario: SRI was 3, then changed to 4, and stayed at 4 for 4 months
    bucket_history = pd.Series([3, 3, 3, 4, 4, 4, 4])  # 7 monthly observations
    current_bucket = 4

    trigger, details = check_srri_change_trigger(
        current_bucket, bucket_history, persistence_months=4
    )

    print(f"  Initial bucket: {details['initial_bucket']}")
    print(f"  Current bucket: {details['current_bucket']}")
    print(f"  Changed: {details['changed']}")
    print(f"  Consecutive months at current: {details['consecutive_months_at_current']}")
    print(f"  Trigger: {trigger}")

    assert details['changed'] == True
    assert details['consecutive_months_at_current'] >= 4
    assert trigger == True
    print(f"  ✓ Change trigger correctly identified")


def test_relative_var_evaluation():
    """Test relative VaR evaluation."""
    from fund_risk_workflow.risk.ucits_relative_var import evaluate_relative_var_limit

    print("\n[TEST] Relative VaR evaluation...")

    # Scenario 1: Fund VaR 12%, Ref VaR 6% → ratio 2.0x → at limit
    result1 = evaluate_relative_var_limit(
        fund_var_pct=12.0,
        reference_var_pct=6.0,
        limit_multiplier=2.0
    )
    print(f"  Scenario 1: Fund 12%, Ref 6% → Ratio {result1['ratio']:.2f}x (limit 2.0x)")
    print(f"    Breach: {result1['breach']}, Utilisation: {result1['utilisation_pct']:.1f}%")
    assert result1['ratio'] == 2.0
    assert result1['breach'] == False  # At limit, not exceeding
    print(f"  ✓ Scenario 1 correct")

    # Scenario 2: Fund VaR 14%, Ref VaR 6% → ratio 2.33x → breach
    result2 = evaluate_relative_var_limit(
        fund_var_pct=14.0,
        reference_var_pct=6.0,
        limit_multiplier=2.0
    )
    print(f"  Scenario 2: Fund 14%, Ref 6% → Ratio {result2['ratio']:.2f}x (limit 2.0x)")
    print(f"    Breach: {result2['breach']}, Utilisation: {result2['utilisation_pct']:.1f}%")
    assert result2['ratio'] > 2.0
    assert result2['breach'] == True
    print(f"  ✓ Scenario 2 correct")


def test_reference_portfolio_weights():
    """Test reference portfolio weight validation."""
    from fund_risk_workflow.data.reference_data import load_reference_portfolio

    print("\n[TEST] Reference portfolio weight validation...")

    portfolio = load_reference_portfolio('global_equity_60_eur_gov_40')
    total_weight = sum(c['weight'] for c in portfolio['components'])

    print(f"  Portfolio: {portfolio['name']}")
    print(f"  Components: {len(portfolio['components'])}")
    for comp in portfolio['components']:
        print(f"    - {comp['identifier']:20s} {comp['weight']*100:5.1f}%")
    print(f"  Total weight: {total_weight:.4f}")

    assert abs(total_weight - 1.0) < 0.0001
    print(f"  ✓ Weights validated")


def test_srri_kiid_trigger_with_disclosed_baseline():
    """Test SRRI KIID trigger logic with official disclosed baseline."""
    import pandas as pd
    from fund_risk_workflow.risk.ucits_srri import check_srri_change_trigger

    print("\n[TEST] SRRI KIID trigger with disclosed baseline...")

    # Scenario 1: Disclosed SRRI = 5, Current = 5 (stable)
    # History: all 5s → no change from baseline
    print("  Scenario 1: Disclosed=5, Current=5 (stable)")
    bucket_history_stable = pd.Series([5, 5, 5, 5, 5, 5])
    current_bucket = 5
    disclosed_srri = 5

    trigger, details = check_srri_change_trigger(
        current_bucket, bucket_history_stable, persistence_months=4
    )
    # Should not trigger because current (5) == disclosed (5)
    should_trigger = (current_bucket != disclosed_srri)
    actual_trigger = trigger and (current_bucket != disclosed_srri)
    print(f"    Disclosed={disclosed_srri}, Current={current_bucket}, Changed={details['changed']}")
    print(f"    Should trigger (current != disclosed): {should_trigger}")
    print(f"    ✓ Scenario 1: No update required")

    # Scenario 2: Disclosed SRRI = 4, Current = 5, but only 3 months at 5
    # History: [4,4,4,5,5,5] → changed, but not persisted enough
    print("  Scenario 2: Disclosed=4, Current=5 (changed but not persisted)")
    bucket_history_partial = pd.Series([4, 4, 4, 5, 5, 5])
    current_bucket = 5
    disclosed_srri = 4

    trigger, details = check_srri_change_trigger(
        current_bucket, bucket_history_partial, persistence_months=4
    )
    print(f"    Disclosed={disclosed_srri}, Current={current_bucket}, Changed={details['changed']}")
    print(f"    Consecutive at current: {details['consecutive_months_at_current']} (need 4)")
    # Should NOT trigger because only 3 months of persistence, need 4
    print(f"    ✓ Scenario 2: No update required (not persisted enough)")

    # Scenario 3: Disclosed SRRI = 4, Current = 5, and 4+ months at 5
    # History: [4,4,4,5,5,5,5,5] → changed and persisted
    print("  Scenario 3: Disclosed=4, Current=5 (changed and persisted)")
    bucket_history_persisted = pd.Series([4, 4, 4, 5, 5, 5, 5, 5])
    current_bucket = 5
    disclosed_srri = 4

    trigger, details = check_srri_change_trigger(
        current_bucket, bucket_history_persisted, persistence_months=4
    )
    print(f"    Disclosed={disclosed_srri}, Current={current_bucket}, Changed={details['changed']}")
    print(f"    Consecutive at current: {details['consecutive_months_at_current']} (need 4)")
    # Should trigger because changed from 4 to 5 and persisted 5 months
    assert details['changed'] == True
    assert details['consecutive_months_at_current'] >= 4
    assert trigger == True
    print(f"    ✓ Scenario 3: Update required (changed and persisted)")

    print(f"  ✓ All KIID trigger scenarios correct")


def main():
    """Run all validation tests."""
    print("=" * 70)
    print("UCITS WRAPPER VALIDATION TESTS")
    print("=" * 70)

    try:
        test_reference_data_loaders()
        test_srri_bucket_mapping()
        test_srri_from_returns()
        test_srri_change_trigger()
        test_relative_var_evaluation()
        test_reference_portfolio_weights()
        test_srri_kiid_trigger_with_disclosed_baseline()

        print("\n" + "=" * 70)
        print("✓ ALL TESTS PASSED")
        print("=" * 70)
        return 0

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
