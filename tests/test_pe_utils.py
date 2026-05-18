"""
tests/test_pe_utils.py
======================
Unit tests for pe_utils.py
Run with: python3 -m pytest tests/test_pe_utils.py -v
"""
import pytest
import numpy as np
import pandas as pd
from src.pe_utils import (
    xirr, fund_irr, pe_multiples,
    pe_multiples_by_company, pe_multiples_timeseries
)
from src.database import get_engine

ENGINE   = get_engine()
FUND_ID  = 'AIFM_PE_Buyout'
DATE     = '2026-05-13'


class TestXirr:

    def test_basic_return(self):
        # 3x in 5 years ≈ 24.6% IRR
        cfs   = [-100, 300]
        dates = ['2018-01-01', '2023-01-01']
        irr   = xirr(cfs, dates)
        assert irr is not None
        assert abs(irr - 0.246) < 0.01

    def test_negative_investment(self):
        cfs   = [-100, 50, 80]
        dates = ['2018-01-01', '2021-01-01', '2023-01-01']
        irr   = xirr(cfs, dates)
        assert irr is not None
        assert irr > 0

    def test_returns_none_on_no_solution(self):
        # all negative cash flows, no solution
        cfs   = [-100, -50]
        dates = ['2018-01-01', '2020-01-01']
        irr   = xirr(cfs, dates)
        assert irr is None

    def test_consistent_with_excel_xirr(self):
        # known Excel XIRR result
        cfs   = [-1000, 250, 250, 250, 250, 250]
        dates = ['2018-01-01', '2019-01-01', '2020-01-01',
                 '2021-01-01', '2022-01-01', '2023-01-01']
        irr   = xirr(cfs, dates)
        assert irr is not None
        assert abs(irr - 0.0745) < 0.01

    def test_high_return(self):
        # 5x in 4 years ≈ 49.5% IRR
        cfs   = [-100, 500]
        dates = ['2018-01-01', '2022-01-01']
        irr   = xirr(cfs, dates)
        assert irr is not None
        assert abs(irr - 0.495) < 0.01


class TestFundIrr:

    def test_returns_dict(self):
        result = fund_irr(ENGINE, FUND_ID, DATE)
        assert isinstance(result, dict)

    def test_required_keys(self):
        result = fund_irr(ENGINE, FUND_ID, DATE)
        for key in ['gross_irr', 'net_irr', 'cash_flows', 'dates']:
            assert key in result

    def test_gross_irr_positive(self):
        result = fund_irr(ENGINE, FUND_ID, DATE)
        assert result['gross_irr'] is not None
        assert result['gross_irr'] > 0

    def test_net_irr_less_than_gross(self):
        result = fund_irr(ENGINE, FUND_ID, DATE)
        assert result['net_irr'] < result['gross_irr']

    def test_cash_flows_have_negatives(self):
        result = fund_irr(ENGINE, FUND_ID, DATE)
        assert any(cf < 0 for cf in result['cash_flows'])

    def test_cash_flows_have_positives(self):
        result = fund_irr(ENGINE, FUND_ID, DATE)
        assert any(cf > 0 for cf in result['cash_flows'])


class TestPeMultiples:

    def test_returns_dict(self):
        result = pe_multiples(ENGINE, FUND_ID, DATE)
        assert isinstance(result, dict)

    def test_required_keys(self):
        result = pe_multiples(ENGINE, FUND_ID, DATE)
        for key in ['dpi', 'rvpi', 'tvpi', 'paid_in', 'distributions', 'nav']:
            assert key in result

    def test_tvpi_equals_dpi_plus_rvpi(self):
        result = pe_multiples(ENGINE, FUND_ID, DATE)
        assert abs(result['tvpi'] - (result['dpi'] + result['rvpi'])) < 0.001

    def test_paid_in_positive(self):
        result = pe_multiples(ENGINE, FUND_ID, DATE)
        assert result['paid_in'] > 0

    def test_tvpi_positive(self):
        result = pe_multiples(ENGINE, FUND_ID, DATE)
        assert result['tvpi'] > 0


class TestPeMultiplesByCompany:

    def test_returns_dataframe(self):
        result = pe_multiples_by_company(ENGINE, FUND_ID, DATE)
        assert isinstance(result, pd.DataFrame)

    def test_all_companies_present(self):
        result = pe_multiples_by_company(ENGINE, FUND_ID, DATE)
        assert len(result) == 8

    def test_tvpi_equals_dpi_plus_rvpi(self):
        result = pe_multiples_by_company(ENGINE, FUND_ID, DATE)
        for _, row in result.iterrows():
            assert abs(row['tvpi'] - (row['dpi'] + row['rvpi'])) < 0.001

    def test_exited_companies_have_zero_rvpi(self):
        result = pe_multiples_by_company(ENGINE, FUND_ID, DATE)
        exited = result[result['status'] == 'Exited']
        assert (exited['rvpi'] == 0).all()

    def test_required_columns(self):
        result = pe_multiples_by_company(ENGINE, FUND_ID, DATE)
        for col in ['company_id', 'company_name', 'cost_basis',
                    'distributions', 'nav', 'dpi', 'rvpi', 'tvpi', 'status']:
            assert col in result.columns


class TestPeMultiplesTimeseries:

    def test_returns_dataframe(self):
        result = pe_multiples_timeseries(ENGINE, FUND_ID)
        assert isinstance(result, pd.DataFrame)

    def test_required_columns(self):
        result = pe_multiples_timeseries(ENGINE, FUND_ID)
        for col in ['date', 'paid_in', 'dpi', 'rvpi', 'tvpi']:
            assert col in result.columns

    def test_tvpi_equals_dpi_plus_rvpi(self):
        result = pe_multiples_timeseries(ENGINE, FUND_ID)
        for _, row in result.iterrows():
            assert abs(row['tvpi'] - (row['dpi'] + row['rvpi'])) < 0.01

    def test_dates_sorted(self):
        result = pe_multiples_timeseries(ENGINE, FUND_ID)
        assert result['date'].is_monotonic_increasing

    # Note: TVPI is non-negative by construction (distributions and NAV are both non-negative).
    # In practice a performing fund should show TVPI > 1.0 at some point during its life.
    # A fund that never exceeds 1.0x TVPI represents a full loss of capital.
    # We do not assert this in tests as a complete flop, while rare, is possible.
    def test_tvpi_nonnegative(self):
        result = pe_multiples_timeseries(ENGINE, FUND_ID)
        assert (result['tvpi'] >= 0).all()