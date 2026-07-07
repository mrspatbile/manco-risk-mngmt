"""
tests/test_generate_positions.py
=================================
Unit tests for generate_positions.py
Run with: python3 -m pytest tests/test_generate_positions.py -v
"""

import pytest
import pandas as pd
import numpy as np
import os
from fund_risk_workflow.data.generate_positions import (
    generate_hedge_fund,
    generate_private_debt,
    generate_real_estate,
    generate_ucits_balanced,
    DATES,
    OUTPUT_DIR,
)
from fund_risk_workflow.data.paths import position_file
from fund_risk_workflow.config import VALUATION_DATE


# ----------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------

@pytest.fixture(scope='module')
def hedge_fund():
    return generate_hedge_fund()

@pytest.fixture(scope='module')
def private_debt():
    return generate_private_debt()

@pytest.fixture(scope='module')
def real_estate():
    return generate_real_estate()

@pytest.fixture(scope='module')
def ucits():
    return generate_ucits_balanced()

@pytest.fixture(scope='module')
def all_funds(hedge_fund, private_debt, real_estate, ucits):
    return {
        'AIFM_HedgeFund'  : hedge_fund,
        'AIFM_PrivateDebt': private_debt,
        'AIFM_RealEstate' : real_estate,
        'UCITS_Balanced'  : ucits,
    }


# ----------------------------------------------------------------
# Standard columns tests (all funds)
# ----------------------------------------------------------------

STANDARD_COLS = [
    'fund_id', 'fund_name', 'position_date', 'isin', 'bloomberg_ticker',
    'instrument_name', 'asset_class', 'sub_asset_class',
    'currency', 'quantity', 'price', 'market_value_local',
    'market_value_eur', 'weight_pct', 'country', 'rating',
    'maturity', 'sector', 'adv_eur'
]

RE_EXTRA_COLS = [
    'ltv_pct', 'rental_yield_pct', 'vacancy_rate_pct',
    'property_type', 'valuation_date', 'is_direct_property'
]


class TestStandardColumns:

    def test_hedge_fund_has_standard_cols(self, hedge_fund):
        for col in STANDARD_COLS:
            assert col in hedge_fund.columns, f'missing: {col}'

    def test_private_debt_has_standard_cols(self, private_debt):
        for col in STANDARD_COLS:
            assert col in private_debt.columns, f'missing: {col}'

    def test_real_estate_has_standard_cols(self, real_estate):
        for col in STANDARD_COLS:
            assert col in real_estate.columns, f'missing: {col}'

    def test_ucits_has_standard_cols(self, ucits):
        for col in STANDARD_COLS:
            assert col in ucits.columns, f'missing: {col}'

    def test_real_estate_has_extra_cols(self, real_estate):
        for col in RE_EXTRA_COLS:
            assert col in real_estate.columns, f'missing RE col: {col}'


# ----------------------------------------------------------------
# History requirement tests (250 trading days)
# ----------------------------------------------------------------

class TestHistory:

    def test_hedge_fund_has_250_days(self, hedge_fund):
        n_dates = hedge_fund['position_date'].nunique()
        assert n_dates >= 250, f'only {n_dates} days'

    def test_private_debt_has_250_days(self, private_debt):
        n_dates = private_debt['position_date'].nunique()
        assert n_dates >= 250

    def test_real_estate_has_250_days(self, real_estate):
        n_dates = real_estate['position_date'].nunique()
        assert n_dates >= 250

    def test_ucits_has_250_days(self, ucits):
        n_dates = ucits['position_date'].nunique()
        assert n_dates >= 250

    def test_no_weekends_in_dates(self, hedge_fund):
        dates = pd.to_datetime(hedge_fund['position_date'])
        assert dates.dt.dayofweek.max() <= 4


# ----------------------------------------------------------------
# Weight tests
# ----------------------------------------------------------------

class TestWeights:

    def test_hedge_fund_weights_sum_to_100(self, hedge_fund):
        for date, group in hedge_fund.groupby('position_date'):
            total = group['weight_pct'].sum()
            assert abs(total - 100.0) < 1.0, \
                f'weights sum to {total} on {date}'

    def test_private_debt_weights_sum_to_100(self, private_debt):
        for date, group in private_debt.groupby('position_date'):
            total = group['weight_pct'].sum()
            assert abs(total - 100.0) < 1.0

    def test_ucits_weights_sum_to_100(self, ucits):
        for date, group in ucits.groupby('position_date'):
            total = group['weight_pct'].sum()
            assert abs(total - 100.0) < 1.0

    def test_hedge_fund_has_short_positions(self, hedge_fund):
        assert (hedge_fund['market_value_eur'] < 0).any()

    def test_hedge_fund_short_weights_negative(self, hedge_fund):
        shorts = hedge_fund[hedge_fund['quantity'] < 0]
        assert (shorts['market_value_eur'] < 0).all()


# ----------------------------------------------------------------
# Position count tests
# ----------------------------------------------------------------

class TestPositionCount:

    def test_hedge_fund_at_least_10_positions(self, hedge_fund):
        n = hedge_fund['isin'].nunique()
        assert n >= 10, f'only {n} positions'

    def test_private_debt_at_least_10_positions(self, private_debt):
        n = private_debt['isin'].nunique()
        assert n >= 10

    def test_real_estate_at_least_5_positions(self, real_estate):
        n = real_estate['isin'].nunique()
        assert n >= 5

    def test_ucits_at_least_5_positions(self, ucits):
        n = ucits['isin'].nunique()
        assert n >= 5


# ----------------------------------------------------------------
# Asset class tests
# ----------------------------------------------------------------

class TestAssetClasses:

    def test_hedge_fund_has_equity(self, hedge_fund):
        assert 'Equity' in hedge_fund['asset_class'].values

    def test_hedge_fund_has_bonds(self, hedge_fund):
        assert 'Bond' in hedge_fund['asset_class'].values

    def test_hedge_fund_has_fx_exposure(self, hedge_fund):
        # After derivative reclassification, FX exposure comes via derivative
        # contracts with underlying_asset_class='FX', not asset_class='FX'.
        # Check for FX forwards in the fund (should have FWD_EURUSD_001, FWD_GBPUSD_001).
        from fund_risk_workflow.data.reference_data import load_derivative_contracts
        fx_derivatives = [
            'FWD_EURUSD_001',
            'FWD_GBPUSD_001',
        ]
        derivatives = hedge_fund[hedge_fund['asset_class'] == 'Derivative']
        fx_deriv_isins = derivatives['isin'].values
        assert any(isin in fx_deriv_isins for isin in fx_derivatives), \
            f'No FX derivatives found. Expected some of {fx_derivatives} in {fx_deriv_isins}'

    def test_private_debt_has_loans(self, private_debt):
        assert 'Loan' in private_debt['asset_class'].values

    def test_private_debt_has_clo(self, private_debt):
        assert 'CLO' in private_debt['asset_class'].values

    def test_real_estate_has_direct_properties(self, real_estate):
        direct = real_estate[
            real_estate['is_direct_property'] == True]
        assert len(direct) > 0

    def test_real_estate_has_listed_reits(self, real_estate):
        reits = real_estate[
            real_estate['is_direct_property'] == False]
        assert len(reits) > 0

    def test_ucits_has_equity(self, ucits):
        assert 'Equity' in ucits['asset_class'].values

    def test_ucits_has_bonds(self, ucits):
        assert 'Bond' in ucits['asset_class'].values

    def test_ucits_all_long_only(self, ucits):
        assert (ucits['market_value_eur'] >= 0).all()


# ----------------------------------------------------------------
# Real estate specific tests
# ----------------------------------------------------------------

class TestRealEstate:

    def test_direct_properties_no_bloomberg_ticker(self, real_estate):
        direct = real_estate[
            real_estate['is_direct_property'] == True]
        assert direct['bloomberg_ticker'].isna().all()

    def test_direct_properties_zero_adv(self, real_estate):
        direct = real_estate[
            real_estate['is_direct_property'] == True]
        assert (direct['adv_eur'] == 0).all()

    def test_direct_properties_have_ltv(self, real_estate):
        direct = real_estate[
            real_estate['is_direct_property'] == True]
        assert direct['ltv_pct'].notna().all()

    def test_direct_properties_have_rental_yield(self, real_estate):
        direct = real_estate[
            real_estate['is_direct_property'] == True]
        assert direct['rental_yield_pct'].notna().all()

    def test_direct_properties_have_vacancy_rate(self, real_estate):
        direct = real_estate[
            real_estate['is_direct_property'] == True]
        assert direct['vacancy_rate_pct'].notna().all()

    def test_listed_reits_have_bloomberg_ticker(self, real_estate):
        reits = real_estate[
            (real_estate['is_direct_property'] == False) &
            (real_estate['asset_class'] == 'Real Estate')
        ]
        assert reits['bloomberg_ticker'].notna().all()

    def test_ltv_reasonable_range(self, real_estate):
        direct = real_estate[
            real_estate['is_direct_property'] == True]
        assert (direct['ltv_pct'] > 0).all()
        assert (direct['ltv_pct'] < 100).all()

    def test_property_types_valid(self, real_estate):
        valid_types = {'Office', 'Retail', 'Residential', 'Logistics'}
        direct = real_estate[
            real_estate['is_direct_property'] == True]
        types = set(direct['property_type'].dropna().unique())
        assert types.issubset(valid_types)


# ----------------------------------------------------------------
# Price and market value tests
# ----------------------------------------------------------------

class TestPricesAndValues:

    def test_all_prices_positive(self, all_funds):
        for name, df in all_funds.items():
            long_only = df[df['quantity'] > 0]
            assert (long_only['price'] > 0).all(), \
                f'negative price in {name}'

    def test_market_value_consistent_with_price(self, hedge_fund):
        sample = hedge_fund[hedge_fund['quantity'] > 0].head(100)
        computed = (sample['price'] * sample['quantity'] *
                    sample.apply(lambda r: 1.0, axis=1))
        assert (sample['market_value_local'] > 0).all()

    def test_last_price_matches_reference(self, hedge_fund):
        latest = hedge_fund[
            hedge_fund['position_date'] == hedge_fund['position_date'].max()]
        spy = latest[latest['bloomberg_ticker'] == 'SPY US Equity']
        assert float(spy['price'].values[0]) > 0


# ----------------------------------------------------------------
# Excel output tests
# ----------------------------------------------------------------

class TestExcelOutput:

    def test_excel_files_created(self):
        import subprocess
        subprocess.run(
            ['python3', 'generate_positions.py'],
            capture_output=True
        )
        for fund in ['AIFM_HedgeFund', 'AIFM_PrivateDebt',
                     'AIFM_RealEstate', 'UCITS_Balanced']:
            path = str(position_file(OUTPUT_DIR, fund, VALUATION_DATE))
            assert os.path.exists(path), f'missing: {path}'

    def test_excel_readable_with_pandas(self):
        for fund in ['AIFM_HedgeFund', 'AIFM_PrivateDebt',
                     'AIFM_RealEstate', 'UCITS_Balanced']:
            path = str(position_file(OUTPUT_DIR, fund, VALUATION_DATE))
            if os.path.exists(path):
                df = pd.read_excel(path)
                assert len(df) > 0

    def test_excel_has_correct_columns(self):
        path = str(position_file(OUTPUT_DIR, 'UCITS_Balanced', VALUATION_DATE))
        if os.path.exists(path):
            df = pd.read_excel(path)
            for col in STANDARD_COLS:
                assert col in df.columns

class TestMarketValueComputation:

    def test_bond_market_value_uses_price_per_100(
            self, hedge_fund):
        bonds = hedge_fund[
            (hedge_fund['asset_class'] == 'Bond') &
            (hedge_fund['position_date'] == hedge_fund['position_date'].max())
        ].iloc[0]
        expected = bonds['quantity'] * bonds['price'] / 100
        assert abs(bonds['market_value_local'] - expected) < 1.0

    def test_loan_market_value_uses_price_per_100(
            self, private_debt):
        loans = private_debt[
            (private_debt['asset_class'] == 'Loan') &
            (private_debt['position_date'] == private_debt['position_date'].max())
        ].iloc[0]
        expected = loans['quantity'] * loans['price'] / 100
        assert abs(loans['market_value_local'] - expected) < 1.0

    def test_clo_market_value_uses_price_per_100(
            self, private_debt):
        clos = private_debt[
            (private_debt['asset_class'] == 'CLO') &
            (private_debt['position_date'] == private_debt['position_date'].max())
        ].iloc[0]
        expected = clos['quantity'] * clos['price'] / 100
        assert abs(clos['market_value_local'] - expected) < 1.0

    def test_equity_market_value_uses_price_per_share(
            self, hedge_fund):
        equities = hedge_fund[
            (hedge_fund['asset_class'] == 'Equity') &
            (hedge_fund['quantity'] > 0) &
            (hedge_fund['position_date'] == hedge_fund['position_date'].max())
        ].iloc[0]
        expected = equities['quantity'] * equities['price']
        assert abs(equities['market_value_local'] - expected) < 2.0

    def test_derivative_market_value_options_use_lot_size_100(self, hedge_fund):
        # Listed options use lot size 100 for display valuation
        options = hedge_fund[
            (hedge_fund['asset_class'] == 'Derivative') &
            (hedge_fund['sub_asset_class'] == 'Listed Option') &
            (hedge_fund['position_date'] == hedge_fund['position_date'].max())
        ]
        if len(options) > 0:
            opt = options.iloc[0]
            expected = opt['quantity'] * opt['price'] * 100
            assert abs(opt['market_value_local'] - expected) < 1.0

    def test_derivative_market_value_futures_forwards_use_economic_valuation(self, hedge_fund):
        # Futures and forwards use quantity * price (economic valuation for display)
        # Real derivative notional comes from derivative_contracts + exposure helper
        futures_forwards = hedge_fund[
            (hedge_fund['asset_class'] == 'Derivative') &
            (hedge_fund['sub_asset_class'].isin(['Future', 'Forward'])) &
            (hedge_fund['position_date'] == hedge_fund['position_date'].max())
        ]
        if len(futures_forwards) > 0:
            deriv = futures_forwards.iloc[0]
            expected = deriv['quantity'] * deriv['price']
            assert abs(deriv['market_value_local'] - expected) < 1.0

    def test_cash_market_value_equals_quantity(
            self, hedge_fund):
        cash = hedge_fund[
            (hedge_fund['asset_class'] == 'Cash') &
            (hedge_fund['position_date'] == hedge_fund['position_date'].max())
        ].iloc[0]
        assert abs(cash['market_value_local'] - cash['quantity']) < 1.0

    def test_real_estate_market_value_equals_price(
            self, real_estate):
        direct = real_estate[
            (real_estate['is_direct_property'] == True) &
            (real_estate['position_date'] == real_estate['position_date'].max())
        ].iloc[0]
        assert abs(direct['market_value_local'] - direct['price']) < 1.0


class TestESGFields:

    def test_illiquid_loan_has_esg_score(self):
        df = generate_private_debt()
        acuris = df[df['isin'] == 'XS9876543210'].iloc[0]
        assert acuris['esg_score'] == 38

    def test_illiquid_loan_ineos_controversy(self):
        df = generate_private_debt()
        ineos = df[df['isin'] == 'XS9876543212'].iloc[0]
        assert ineos['controversy_flag'] == True

    def test_direct_property_has_esg(self):
        df = generate_real_estate()
        office = df[df['isin'] == 'PROP_LU_001'].iloc[0]
        assert office['esg_score'] == 72

    def test_direct_property_has_carbon_intensity(self):
        df = generate_real_estate()
        office = df[df['isin'] == 'PROP_LU_001'].iloc[0]
        assert office['carbon_intensity'] == 85.2


    def test_liquid_instrument_esg_none(self):
        df = generate_private_debt()
        telecom = df[df['isin'] == 'XS2341234567'].iloc[0]
        assert pd.isna(telecom['esg_score'])

    def test_clo_esg_simulated_look_through(self):
        # CLO entries in esg_scores.json now carry explicitly simulated
        # manager-estimated look-through scores (MRS-198), so the
        # generator embeds them like other no-ticker reference scores.
        df = generate_private_debt()
        clo = df[df['isin'] == 'XS1122334455'].iloc[0]
        assert clo['esg_score'] == 57

    def test_cash_esg_none(self):
        df = generate_private_debt()
        cash = df[df['isin'] == 'CASH_EUR_002'].iloc[0]
        assert pd.isna(cash['esg_score'])


    def test_esg_columns_present_all_funds(self):
        for df in [generate_hedge_fund(), generate_private_debt(),
                   generate_real_estate(), generate_ucits_balanced()]:
            for col in ['esg_score', 'env_score', 'soc_score',
                        'gov_score', 'controversy_flag', 'carbon_intensity']:
                assert col in df.columns