"""
tests/test_derivative_contracts.py
==================================
Unit tests for derivative contract reference data and loaders.
Run with: python3 -m pytest tests/test_derivative_contracts.py -v
"""

import pytest
from pathlib import Path
from fund_risk_workflow.data.reference_data import (
    load_derivative_contracts,
    load_derivative_contract,
    _validate_derivative_contract,
)
from fund_risk_workflow.data.database import get_engine, query_positions
from fund_risk_workflow.config import VALUATION_DATE


class TestDerivativeContractsLoad:
    """Test derivative contracts loading."""

    def test_load_all_derivative_contracts(self):
        """Test loading all derivative contracts."""
        contracts = load_derivative_contracts()
        assert isinstance(contracts, dict)
        assert len(contracts) > 0

    def test_load_all_contracts_have_required_fields(self):
        """Test that all loaded contracts have required common fields."""
        contracts = load_derivative_contracts()
        required_common = {
            'instrument_name', 'contract_type', 'underlying_ticker',
            'underlying_asset_class', 'contract_multiplier',
            'settlement_currency', 'listed_or_otc', 'exposure_method_hint'
        }
        for isin, contract in contracts.items():
            for field in required_common:
                assert field in contract, \
                    f"Contract {isin} missing field: {field}"

    def test_load_single_contract_option(self):
        """Test loading a single option contract."""
        contract = load_derivative_contract('OPT_SPX_PUT_001')
        assert contract['contract_type'] == 'option'
        assert contract['option_type'] == 'put'
        assert contract['strike'] == 5500
        assert contract['expiry_date'] == '2026-06-19'
        assert contract['contract_multiplier'] == 100
        assert contract['underlying_ticker'] == 'SPX Index'
        assert contract['exposure_method_hint'] == 'delta_adjusted_underlying_notional'

    def test_load_single_contract_future(self):
        """Test loading a future contract."""
        contract = load_derivative_contract('FUT_SPY_SHORT_001')
        assert contract['contract_type'] == 'future'
        assert contract['contract_multiplier'] == 100
        assert contract['underlying_ticker'] == 'SPY US Equity'
        assert contract['exposure_method_hint'] == 'underlying_notional'
        assert contract['option_type'] is None
        assert contract['strike'] is None

    def test_load_single_contract_forward(self):
        """Test loading a forward contract."""
        contract = load_derivative_contract('FWD_EURUSD_001')
        assert contract['contract_type'] == 'forward'
        assert contract['contract_multiplier'] == 1
        assert contract['underlying_ticker'] == 'EURUSD Curncy'
        assert contract['exposure_method_hint'] == 'fx_notional'
        assert contract['listed_or_otc'] == 'OTC'

    def test_load_single_contract_not_found(self):
        """Test loading non-existent contract raises KeyError."""
        with pytest.raises(KeyError):
            load_derivative_contract('NONEXISTENT_DERIV_001')

    def test_active_derivatives_coverage(self):
        """Test that all active derivatives have contract entries.

        Checks AIFM_HedgeFund positions and ensures each derivative
        has a corresponding contract in derivative_contracts.json.
        """
        contracts = load_derivative_contracts()
        contract_isins = set(contracts.keys())

        # Query active positions from database
        engine = get_engine()
        positions = query_positions(
            engine, 'AIFM_HedgeFund', position_date=VALUATION_DATE
        )

        # Filter to derivatives only
        derivatives = positions[positions['asset_class'] == 'Derivative']

        if len(derivatives) > 0:
            for _, deriv in derivatives.iterrows():
                isin = deriv['isin']
                assert isin in contract_isins, \
                    f"Derivative {isin} ({deriv['instrument_name']}) not found in derivative_contracts.json"

    def test_all_contracts_have_valid_contract_type(self):
        """Test that all contracts have valid contract_type."""
        contracts = load_derivative_contracts()
        valid_types = {'future', 'option', 'forward'}
        for isin, contract in contracts.items():
            assert contract['contract_type'] in valid_types, \
                f"Contract {isin} has invalid contract_type: {contract['contract_type']}"

    def test_all_contracts_have_valid_listed_otc(self):
        """Test that all contracts have valid listed_or_otc."""
        contracts = load_derivative_contracts()
        valid_listed_otc = {'Listed', 'OTC'}
        for isin, contract in contracts.items():
            assert contract['listed_or_otc'] in valid_listed_otc, \
                f"Contract {isin} has invalid listed_or_otc: {contract['listed_or_otc']}"

    def test_all_contracts_have_valid_exposure_method_hint(self):
        """Test that all contracts have valid exposure_method_hint."""
        contracts = load_derivative_contracts()
        valid_hints = {
            'underlying_notional', 'delta_adjusted_underlying_notional',
            'fx_notional', 'premium_value'
        }
        for isin, contract in contracts.items():
            assert contract['exposure_method_hint'] in valid_hints, \
                f"Contract {isin} has invalid exposure_method_hint: {contract['exposure_method_hint']}"


class TestDerivativeContractValidation:
    """Test derivative contract validation."""

    def test_option_requires_strike(self):
        """Test that option validation requires strike."""
        invalid_option = {
            'instrument_name': 'Test Option',
            'contract_type': 'option',
            'option_type': 'call',
            'strike': None,  # Missing
            'expiry_date': '2026-06-19',
            'underlying_ticker': 'SPX Index',
            'underlying_asset_class': 'Equity',
            'contract_multiplier': 100,
            'settlement_currency': 'USD',
            'listed_or_otc': 'Listed',
            'exposure_method_hint': 'delta_adjusted_underlying_notional',
        }
        with pytest.raises(ValueError, match="strike"):
            _validate_derivative_contract(invalid_option, 'TEST_OPT_001')

    def test_option_requires_expiry_date(self):
        """Test that option validation requires expiry_date."""
        invalid_option = {
            'instrument_name': 'Test Option',
            'contract_type': 'option',
            'option_type': 'call',
            'strike': 100,
            'expiry_date': None,  # Missing
            'underlying_ticker': 'SPX Index',
            'underlying_asset_class': 'Equity',
            'contract_multiplier': 100,
            'settlement_currency': 'USD',
            'listed_or_otc': 'Listed',
            'exposure_method_hint': 'delta_adjusted_underlying_notional',
        }
        with pytest.raises(ValueError, match="expiry_date"):
            _validate_derivative_contract(invalid_option, 'TEST_OPT_001')

    def test_option_requires_option_type(self):
        """Test that option validation requires option_type."""
        invalid_option = {
            'instrument_name': 'Test Option',
            'contract_type': 'option',
            'option_type': None,  # Missing
            'strike': 100,
            'expiry_date': '2026-06-19',
            'underlying_ticker': 'SPX Index',
            'underlying_asset_class': 'Equity',
            'contract_multiplier': 100,
            'settlement_currency': 'USD',
            'listed_or_otc': 'Listed',
            'exposure_method_hint': 'delta_adjusted_underlying_notional',
        }
        with pytest.raises(ValueError, match="option_type"):
            _validate_derivative_contract(invalid_option, 'TEST_OPT_001')

    def test_option_type_must_be_call_or_put(self):
        """Test that option_type must be 'call' or 'put'."""
        invalid_option = {
            'instrument_name': 'Test Option',
            'contract_type': 'option',
            'option_type': 'straddle',  # Invalid
            'strike': 100,
            'expiry_date': '2026-06-19',
            'underlying_ticker': 'SPX Index',
            'underlying_asset_class': 'Equity',
            'contract_multiplier': 100,
            'settlement_currency': 'USD',
            'listed_or_otc': 'Listed',
            'exposure_method_hint': 'delta_adjusted_underlying_notional',
        }
        with pytest.raises(ValueError, match="option_type must be"):
            _validate_derivative_contract(invalid_option, 'TEST_OPT_001')

    def test_future_requires_underlying_ticker(self):
        """Test that future validation requires underlying_ticker."""
        invalid_future = {
            'instrument_name': 'Test Future',
            'contract_type': 'future',
            'underlying_ticker': None,  # Missing
            'underlying_asset_class': 'Equity',
            'contract_multiplier': 100,
            'settlement_currency': 'USD',
            'listed_or_otc': 'Listed',
            'exposure_method_hint': 'underlying_notional',
        }
        with pytest.raises(ValueError, match="underlying_ticker"):
            _validate_derivative_contract(invalid_future, 'TEST_FUT_001')

    def test_future_requires_contract_multiplier(self):
        """Test that future validation requires contract_multiplier."""
        invalid_future = {
            'instrument_name': 'Test Future',
            'contract_type': 'future',
            'underlying_ticker': 'SPX Index',
            'underlying_asset_class': 'Equity',
            'contract_multiplier': None,  # Missing
            'settlement_currency': 'USD',
            'listed_or_otc': 'Listed',
            'exposure_method_hint': 'underlying_notional',
        }
        with pytest.raises(ValueError, match="contract_multiplier"):
            _validate_derivative_contract(invalid_future, 'TEST_FUT_001')

    def test_forward_requires_underlying_ticker(self):
        """Test that forward validation requires underlying_ticker."""
        invalid_forward = {
            'instrument_name': 'Test Forward',
            'contract_type': 'forward',
            'underlying_ticker': None,  # Missing
            'underlying_asset_class': 'FX',
            'contract_multiplier': 1,
            'settlement_currency': 'USD',
            'listed_or_otc': 'OTC',
            'exposure_method_hint': 'fx_notional',
        }
        with pytest.raises(ValueError, match="underlying_ticker"):
            _validate_derivative_contract(invalid_forward, 'TEST_FWD_001')

    def test_forward_requires_settlement_currency(self):
        """Test that forward validation requires settlement_currency."""
        invalid_forward = {
            'instrument_name': 'Test Forward',
            'contract_type': 'forward',
            'underlying_ticker': 'EURUSD Curncy',
            'underlying_asset_class': 'FX',
            'contract_multiplier': 1,
            'settlement_currency': None,  # Missing
            'listed_or_otc': 'OTC',
            'exposure_method_hint': 'fx_notional',
        }
        with pytest.raises(ValueError, match="settlement_currency"):
            _validate_derivative_contract(invalid_forward, 'TEST_FWD_001')

    def test_invalid_contract_type(self):
        """Test that invalid contract_type is rejected."""
        invalid_contract = {
            'instrument_name': 'Test Instrument',
            'contract_type': 'swap',  # Invalid
            'underlying_ticker': 'SPX Index',
            'underlying_asset_class': 'Equity',
            'contract_multiplier': 100,
            'settlement_currency': 'USD',
            'listed_or_otc': 'Listed',
            'exposure_method_hint': 'underlying_notional',
        }
        with pytest.raises(ValueError, match="contract_type must be one of"):
            _validate_derivative_contract(invalid_contract, 'TEST_INV_001')

    def test_invalid_listed_otc(self):
        """Test that invalid listed_or_otc is rejected."""
        invalid_contract = {
            'instrument_name': 'Test Instrument',
            'contract_type': 'future',
            'underlying_ticker': 'SPX Index',
            'underlying_asset_class': 'Equity',
            'contract_multiplier': 100,
            'settlement_currency': 'USD',
            'listed_or_otc': 'Hybrid',  # Invalid
            'exposure_method_hint': 'underlying_notional',
        }
        with pytest.raises(ValueError, match="listed_or_otc must be one of"):
            _validate_derivative_contract(invalid_contract, 'TEST_INV_001')

    def test_invalid_exposure_method_hint(self):
        """Test that invalid exposure_method_hint is rejected."""
        invalid_contract = {
            'instrument_name': 'Test Instrument',
            'contract_type': 'future',
            'underlying_ticker': 'SPX Index',
            'underlying_asset_class': 'Equity',
            'contract_multiplier': 100,
            'settlement_currency': 'USD',
            'listed_or_otc': 'Listed',
            'exposure_method_hint': 'bad_method',  # Invalid
        }
        with pytest.raises(ValueError, match="exposure_method_hint must be one of"):
            _validate_derivative_contract(invalid_contract, 'TEST_INV_001')


class TestDerivativeContractsStructure:
    """Test derivative contracts JSON structure."""

    def test_derivative_contracts_json_exists(self):
        """Test that derivative_contracts.json file exists."""
        ref_data_root = Path(__file__).parent.parent / 'reference_data'
        deriv_file = ref_data_root / 'derivatives' / 'derivative_contracts.json'
        assert deriv_file.exists(), f"derivative_contracts.json not found at {deriv_file}"

    def test_expected_active_derivatives_present(self):
        """Test that all expected active derivatives are in the file."""
        contracts = load_derivative_contracts()
        expected_isins = {
            'FUT_SPY_SHORT_001',
            'FUT_SX5E_SHORT_001',
            'EU0009658145',
            'FWD_EURUSD_001',
            'FWD_GBPUSD_001',
            'OPT_SPX_PUT_001',
        }
        actual_isins = set(contracts.keys())
        assert expected_isins.issubset(actual_isins), \
            f"Missing expected derivatives: {expected_isins - actual_isins}"

    def test_futures_have_null_strike_option_type(self):
        """Test that futures have null strike and option_type."""
        contracts = load_derivative_contracts()
        futures = [c for c in contracts.values() if c['contract_type'] == 'future']
        for fut in futures:
            assert fut['strike'] is None, f"Future {fut['instrument_name']} should have null strike"
            assert fut['option_type'] is None, f"Future {fut['instrument_name']} should have null option_type"

    def test_forwards_have_null_strike_option_type_expiry(self):
        """Test that forwards have null strike, option_type, and expiry_date."""
        contracts = load_derivative_contracts()
        forwards = [c for c in contracts.values() if c['contract_type'] == 'forward']
        for fwd in forwards:
            assert fwd['strike'] is None, f"Forward {fwd['instrument_name']} should have null strike"
            assert fwd['option_type'] is None, f"Forward {fwd['instrument_name']} should have null option_type"
            assert fwd['expiry_date'] is None, f"Forward {fwd['instrument_name']} should have null expiry_date"

    def test_options_have_required_strike_expiry(self):
        """Test that options have strike and expiry_date."""
        contracts = load_derivative_contracts()
        options = [c for c in contracts.values() if c['contract_type'] == 'option']
        for opt in options:
            assert opt['strike'] is not None, f"Option {opt['instrument_name']} should have strike"
            assert opt['expiry_date'] is not None, f"Option {opt['instrument_name']} should have expiry_date"

    def test_option_expiry_date_format(self):
        """Test that option expiry dates are in YYYY-MM-DD format."""
        contracts = load_derivative_contracts()
        options = [c for c in contracts.values() if c['contract_type'] == 'option']
        for opt in options:
            assert isinstance(opt['expiry_date'], str), \
                f"Option {opt['instrument_name']} expiry_date should be string"
            assert len(opt['expiry_date']) == 10, \
                f"Option {opt['instrument_name']} expiry_date should be YYYY-MM-DD format"
            assert opt['expiry_date'][4] == '-' and opt['expiry_date'][7] == '-', \
                f"Option {opt['instrument_name']} expiry_date should be YYYY-MM-DD format"

    def test_contract_multiplier_is_numeric(self):
        """Test that all contract multipliers are numeric."""
        contracts = load_derivative_contracts()
        for isin, contract in contracts.items():
            assert isinstance(contract['contract_multiplier'], (int, float)), \
                f"Contract {isin} multiplier should be numeric, got {type(contract['contract_multiplier'])}"
            assert contract['contract_multiplier'] > 0, \
                f"Contract {isin} multiplier should be positive"
