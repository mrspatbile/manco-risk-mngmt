"""
tests/test_pe_utils.py
======================
Unit tests for pe_utils.py
Run with: python3 -m pytest tests/test_pe_utils.py -v
"""
import pytest
import numpy as np
import pandas as pd
from fund_risk_workflow.risk.pe_utils import (
    xirr, fund_irr, pe_multiples,
    pe_multiples_by_company, pe_multiples_timeseries, pe_value_bridge,
    pme_long_nickels,
)
from fund_risk_workflow.data.database import get_engine

ENGINE   = get_engine()
FUND_ID  = 'AIFM_PE_Buyout'
DATE     = '2026-03-31'


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


class TestPeValueBridge:

    def test_returns_expected_keys(self):
        result = pe_value_bridge(ENGINE, FUND_ID)
        assert 'rows' in result
        assert 'fund_totals' in result

    def test_rows_not_empty(self):
        result = pe_value_bridge(ENGINE, FUND_ID)
        assert len(result['rows']) > 0

    def test_required_row_keys(self):
        result = pe_value_bridge(ENGINE, FUND_ID)
        required = [
            'company_id', 'company_name', 'is_realised', 'cost_basis',
            'ebitda_growth', 'multiple_expansion', 'leverage_effect',
            'distributions', 'total_attributed', 'actual_value_created',
            'reconciliation_gap', 'reconciliation_gap_pct',
        ]
        for row in result['rows']:
            for key in required:
                assert key in row, f"Missing key '{key}' in row"

    def test_total_attributed_equals_sum_of_components(self):
        result = pe_value_bridge(ENGINE, FUND_ID)
        for row in result['rows']:
            expected = (
                row['ebitda_growth']
                + row['multiple_expansion']
                + row['leverage_effect']
                + row['distributions']
            )
            assert abs(row['total_attributed'] - expected) < 1e-2

    def test_reconciliation_gap_near_zero_for_exited(self):
        result = pe_value_bridge(ENGINE, FUND_ID)
        for row in result['rows']:
            if row['is_realised']:
                assert abs(row['reconciliation_gap_pct']) < 0.10, (
                    f"{row['company_name']}: gap {row['reconciliation_gap_pct']:.1%} "
                    f"exceeds 10% for exited company"
                )

    def test_fund_totals_keys_present(self):
        ft = pe_value_bridge(ENGINE, FUND_ID)['fund_totals']
        for col in ['ebitda_growth', 'multiple_expansion', 'leverage_effect',
                    'distributions', 'total_attributed', 'actual_value_created']:
            assert f'{col}_eur' in ft
            assert f'{col}_pct' in ft

    def test_single_company_returns_one_row(self):
        result_all = pe_value_bridge(ENGINE, FUND_ID)
        if not result_all['rows']:
            pytest.skip("No rows returned for fund")
        first_cid = result_all['rows'][0]['company_id']
        result_one = pe_value_bridge(ENGINE, FUND_ID, company_id=first_cid)
        assert len(result_one['rows']) == 1
        assert result_one['rows'][0]['company_id'] == first_cid


# ================================================================
# pme_long_nickels — no DB required, synthetic fixtures only
# ================================================================

def _make_index(
    start: float,
    annual_return: float,
    start_date: str = '2017-01-01',
    end_date: str   = '2024-01-01',
) -> pd.Series:
    """Synthetic monthly index price series growing at annual_return."""
    dates  = pd.date_range(start_date, end_date, freq='MS')
    prices = [start * (1 + annual_return) ** (i / 12) for i in range(len(dates))]
    return pd.Series(prices, index=dates)


class TestPmeLongNickels:

    def test_returns_dict(self):
        idx    = _make_index(100, 0.10)
        result = pme_long_nickels(
            [-100_000], ['2018-01-01'], idx,
            terminal_nav=200_000, valuation_date='2023-01-01'
        )
        assert isinstance(result, dict)

    def test_required_keys(self):
        idx    = _make_index(100, 0.10)
        result = pme_long_nickels(
            [-100_000], ['2018-01-01'], idx,
            terminal_nav=200_000, valuation_date='2023-01-01'
        )
        for key in ['pme_multiple', 'pme_irr', 'pe_irr', 'alpha',
                    'pme_terminal_nav', 'units', 'simulated_nav']:
            assert key in result

    def test_pe_outperforms_positive_alpha(self):
        # PE 3x in 5 years (~24.6% IRR) vs index at 8% annually → positive alpha
        idx    = _make_index(100, 0.08)
        result = pme_long_nickels(
            [-100_000], ['2018-01-01'], idx,
            terminal_nav=300_000, valuation_date='2023-01-01'
        )
        assert result['alpha'] is not None
        assert result['alpha'] > 0

    def test_pe_underperforms_negative_alpha(self):
        # PE 1.2x in 5 years (~3.7% IRR) vs index at 20% annually → negative alpha
        idx    = _make_index(100, 0.20)
        result = pme_long_nickels(
            [-100_000], ['2018-01-01'], idx,
            terminal_nav=120_000, valuation_date='2023-01-01'
        )
        assert result['alpha'] is not None
        assert result['alpha'] < 0

    def test_flat_market_pme_irr_near_zero(self):
        # Flat index → PME buys at 100, sells at 100 → PME IRR ≈ 0%
        idx    = pd.Series(
            100.0, index=pd.date_range('2017-01-01', '2024-01-01', freq='MS')
        )
        result = pme_long_nickels(
            [-100_000], ['2018-01-01'], idx,
            terminal_nav=150_000, valuation_date='2023-01-01'
        )
        assert result['pme_irr'] is not None
        assert abs(result['pme_irr']) < 0.01

    def test_alpha_equals_pe_irr_minus_pme_irr(self):
        idx    = _make_index(100, 0.10)
        result = pme_long_nickels(
            [-100_000], ['2018-01-01'], idx,
            terminal_nav=200_000, valuation_date='2023-01-01'
        )
        assert result['alpha'] == pytest.approx(
            result['pe_irr'] - result['pme_irr'], rel=1e-6
        )

    def test_pme_multiple_is_float(self):
        idx    = _make_index(100, 0.10)
        result = pme_long_nickels(
            [-100_000], ['2018-01-01'], idx,
            terminal_nav=200_000, valuation_date='2023-01-01'
        )
        assert isinstance(result['pme_multiple'], float)

    def test_simulated_nav_is_series(self):
        idx    = _make_index(100, 0.10)
        cfs    = [-100_000, -50_000, 30_000]
        dates  = ['2018-01-01', '2019-01-01', '2021-01-01']
        result = pme_long_nickels(
            cfs, dates, idx,
            terminal_nav=200_000, valuation_date='2023-01-01'
        )
        assert isinstance(result['simulated_nav'], pd.Series)
        assert len(result['simulated_nav']) == len(cfs)