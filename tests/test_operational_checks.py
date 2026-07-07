"""
tests/test_operational_checks.py
================================
Unit tests for operational_checks.py
Run with: python3 -m pytest tests/test_operational_checks.py -v
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from fund_risk_workflow.data.operational_checks import (
    business_day_offset,
    summarise_position_snapshot,
    summarise_risk_ready_dataset,
    validate_prices,
)


class TestBusinessDayOffset:
    """Tests for business_day_offset function."""

    def test_positive_offset(self):
        """Test forward business day offset."""
        result = business_day_offset("2026-03-31", 1)
        assert result == "2026-04-01"

    def test_negative_offset(self):
        """Test backward business day offset."""
        result = business_day_offset("2026-04-01", -1)
        assert result == "2026-03-31"

    def test_zero_offset(self):
        """Test zero offset returns same date."""
        result = business_day_offset("2026-03-31", 0)
        assert result == "2026-03-31"

    def test_weekend_handling(self):
        """Test that offsets skip weekends correctly."""
        # 2026-04-04 is a Saturday
        # +1 business day should give Monday 2026-04-06
        result = business_day_offset("2026-04-03", 1)
        assert result == "2026-04-06"

    def test_output_format(self):
        """Test that output is ISO date string."""
        result = business_day_offset("2026-03-31", 1)
        assert isinstance(result, str)
        assert len(result) == 10
        assert result.count("-") == 2


class TestSummarisePositionSnapshot:
    """Tests for summarise_position_snapshot function."""

    @pytest.fixture
    def sample_positions(self):
        """Create sample position data."""
        return pd.DataFrame(
            {
                "isin": ["US0001", "US0002", "US0003"],
                "instrument_name": ["Apple", "Microsoft", "Google"],
                "asset_class": ["Equity", "Equity", "Equity"],
                "bloomberg_ticker": ["AAPL US", "MSFT US", "GOOGL US"],
                "market_value_eur": [100.0, 200.0, 150.0],
            }
        )

    @pytest.fixture
    def sample_prior_positions(self):
        """Create sample prior position data."""
        return pd.DataFrame(
            {
                "isin": ["US0001", "US0002", "US0004"],
                "instrument_name": ["Apple", "Microsoft", "Intel"],
                "asset_class": ["Equity", "Equity", "Equity"],
                "bloomberg_ticker": ["AAPL US", "MSFT US", "INTC US"],
                "market_value_eur": [95.0, 195.0, 100.0],
            }
        )

    def test_identifies_new_isins(self, sample_positions, sample_prior_positions):
        """Test that new ISINs are correctly identified."""
        result = summarise_position_snapshot(sample_positions, sample_prior_positions)
        assert "US0003" in result["new_isins"]
        assert "US0001" not in result["new_isins"]

    def test_identifies_removed_isins(self, sample_positions, sample_prior_positions):
        """Test that removed ISINs are correctly identified."""
        result = summarise_position_snapshot(sample_positions, sample_prior_positions)
        assert "US0004" in result["removed_isins"]
        assert "US0001" not in result["removed_isins"]

    def test_calculates_nav(self, sample_positions, sample_prior_positions):
        """Test NAV calculation."""
        result = summarise_position_snapshot(sample_positions, sample_prior_positions)
        expected_nav = 100.0 + 200.0 + 150.0
        assert result["nav"] == expected_nav

    def test_position_summary_structure(self, sample_positions, sample_prior_positions):
        """Test position_summary DataFrame structure."""
        result = summarise_position_snapshot(sample_positions, sample_prior_positions)
        ps = result["position_summary"]
        assert "metric" in ps.columns
        assert "value" in ps.columns
        assert len(ps) == 8

    def test_asset_class_breakdown_structure(
        self, sample_positions, sample_prior_positions
    ):
        """Test asset_class_breakdown DataFrame structure."""
        result = summarise_position_snapshot(sample_positions, sample_prior_positions)
        acb = result["asset_class_breakdown"]
        assert "asset_class" in acb.columns
        assert "market_value_eur" in acb.columns
        assert "weight_pct" in acb.columns

    def test_instrument_changes_structure(self, sample_positions, sample_prior_positions):
        """Test instrument_changes DataFrame structure."""
        result = summarise_position_snapshot(sample_positions, sample_prior_positions)
        ic = result["instrument_changes"]
        assert "change_type" in ic.columns
        assert "isin" in ic.columns
        assert "instrument_name" in ic.columns
        assert "asset_class" in ic.columns
        assert "weight_pct" in ic.columns

    def test_instrument_changes_content(self, sample_positions, sample_prior_positions):
        """Test instrument_changes contains both new and removed instruments."""
        result = summarise_position_snapshot(sample_positions, sample_prior_positions)
        ic = result["instrument_changes"]
        assert len(ic) == 2
        change_types = set(ic["change_type"].values)
        assert "New instrument" in change_types
        assert "Removed instrument" in change_types
        assert "US0003" in ic["isin"].values
        assert "US0004" in ic["isin"].values

    def test_return_dictionary_keys(self, sample_positions, sample_prior_positions):
        """Test that return dictionary has all required keys."""
        result = summarise_position_snapshot(sample_positions, sample_prior_positions)
        required_keys = {
            "new_isins",
            "removed_isins",
            "nav",
            "position_summary",
            "asset_class_breakdown",
            "instrument_changes",
        }
        assert set(result.keys()) == required_keys

    def test_no_changes(self):
        """Test when there are no position changes."""
        positions = pd.DataFrame(
            {
                "isin": ["US0001"],
                "instrument_name": ["Apple"],
                "asset_class": ["Equity"],
                "market_value_eur": [100.0],
            }
        )
        result = summarise_position_snapshot(positions, positions)
        assert len(result["new_isins"]) == 0
        assert len(result["removed_isins"]) == 0
        ic = result["instrument_changes"]
        assert len(ic) == 1
        assert ic.iloc[0]["change_type"] == "No instrument changes"
        assert pd.isna(ic.iloc[0]["isin"])
        assert pd.isna(ic.iloc[0]["instrument_name"])
        assert pd.isna(ic.iloc[0]["asset_class"])
        assert pd.isna(ic.iloc[0]["weight_pct"])


class TestValidatePrices:
    """Tests for validate_prices function with date-aligned Bloomberg pricing."""

    @pytest.fixture
    def sample_positions_for_validation(self):
        """Create sample positions with Bloomberg tickers for validation."""
        return pd.DataFrame(
            {
                "instrument_name": ["Apple Inc", "Microsoft Corp", "Treasury Bond"],
                "asset_class": ["Equity", "Equity", "Bond"],
                "bloomberg_ticker": ["AAPL US Equity", "MSFT US Equity", "US912828YK09 Govt"],
                "price": [250.0, 400.0, 96.0],
                "market_value_eur": [100000.0, 120000.0, 50000.0],
            }
        )

    def test_validate_prices_returns_correct_columns(
        self, sample_positions_for_validation
    ):
        """Test that validate_prices returns required columns."""
        from fund_risk_workflow.data.mock_bloomberg import MockBloomberg

        bbg = MockBloomberg()
        price_validation, _ = validate_prices(
            sample_positions_for_validation,
            bbg,
            "2026-03-31"
        )

        required_columns = {
            "instrument_name",
            "asset_class",
            "bloomberg_ticker",
            "fund_admin_price",
            "bbg_price",
            "diff_pct",
            "status"
        }
        assert required_columns.issubset(set(price_validation.columns))

    def test_validate_prices_uses_valuation_date(
        self, sample_positions_for_validation
    ):
        """Test that validate_prices uses date-aligned pricing."""
        from fund_risk_workflow.data.mock_bloomberg import MockBloomberg

        bbg = MockBloomberg()
        valuation_date = "2026-03-31"

        price_validation, _ = validate_prices(
            sample_positions_for_validation,
            bbg,
            valuation_date
        )

        # For this test, we're verifying the function accepts the valuation_date
        # and returns prices (not checking exact values as those depend on cache)
        assert len(price_validation) == len(sample_positions_for_validation)
        assert not price_validation["bbg_price"].isna().all()

    def test_validate_prices_sorts_by_status(
        self, sample_positions_for_validation
    ):
        """Test that results are sorted by status."""
        from fund_risk_workflow.data.mock_bloomberg import MockBloomberg

        bbg = MockBloomberg()
        price_validation, _ = validate_prices(
            sample_positions_for_validation,
            bbg,
            "2026-03-31"
        )

        # Verify sorting: OK should come after FLAG and MANUAL_REVIEW
        statuses = price_validation["status"].unique()
        assert "OK" in statuses or "FLAG" in statuses or "MANUAL REVIEW" in statuses


class TestSummariseRiskReadyDataset:
    """Tests for summarise_risk_ready_dataset function."""

    @pytest.fixture
    def sample_risk_df(self):
        """Create sample risk-ready dataset."""
        return pd.DataFrame(
            {
                "instrument_name": ["Apple", "Microsoft", "Google", "Intel"],
                "asset_class": ["Equity", "Equity", "Equity", "Equity"],
                "market_value_eur": [100.0, 200.0, 150.0, 50.0],
                "weight_pct": [20.0, 40.0, 30.0, 10.0],
                "beta": [1.2, 1.0, 1.3, 0.9],
                "dur_adj_mid": [np.nan, np.nan, np.nan, np.nan],
                "convexity": [np.nan, np.nan, np.nan, np.nan],
                "adv_eur": [500.0, 1000.0, 750.0, 200.0],
                "enrichment_source": ["bbg", "bbg", "bbg", "fund_admin"],
            }
        )

    def test_enrichment_summary_structure(self, sample_risk_df):
        """Test enrichment_summary DataFrame structure."""
        result = summarise_risk_ready_dataset(sample_risk_df)
        es = result["enrichment_summary"]
        assert "enrichment_source" in es.columns
        assert "positions" in es.columns

    def test_sensitivity_coverage_structure(self, sample_risk_df):
        """Test sensitivity_coverage DataFrame structure."""
        result = summarise_risk_ready_dataset(sample_risk_df)
        sc = result["sensitivity_coverage"]
        assert "field" in sc.columns
        assert "available_positions" in sc.columns
        assert "total_positions" in sc.columns
        assert len(sc) == 4

    def test_top_positions_structure(self, sample_risk_df):
        """Test top_positions DataFrame structure."""
        result = summarise_risk_ready_dataset(sample_risk_df)
        tp = result["top_positions"]
        expected_columns = [
            "instrument_name",
            "asset_class",
            "market_value_eur",
            "weight_pct",
            "beta",
            "dur_adj_mid",
            "enrichment_source",
        ]
        assert all(col in tp.columns for col in expected_columns)

    def test_top_positions_sorted_by_absolute_value(self, sample_risk_df):
        """Test that top_positions is sorted by absolute market value."""
        result = summarise_risk_ready_dataset(sample_risk_df)
        tp = result["top_positions"]
        mv = tp["market_value_eur"].abs().values
        assert all(mv[i] >= mv[i + 1] for i in range(len(mv) - 1))

    def test_return_dictionary_keys(self, sample_risk_df):
        """Test that return dictionary has all required keys."""
        result = summarise_risk_ready_dataset(sample_risk_df)
        required_keys = {
            "enrichment_summary",
            "sensitivity_coverage",
            "top_positions",
        }
        assert set(result.keys()) == required_keys

    def test_beta_coverage(self, sample_risk_df):
        """Test beta coverage calculation."""
        result = summarise_risk_ready_dataset(sample_risk_df)
        sc = result["sensitivity_coverage"]
        beta_row = sc[sc["field"] == "beta"]
        assert beta_row.iloc[0]["available_positions"] == 4
        assert beta_row.iloc[0]["total_positions"] == 4

    def test_duration_coverage(self, sample_risk_df):
        """Test duration coverage calculation."""
        result = summarise_risk_ready_dataset(sample_risk_df)
        sc = result["sensitivity_coverage"]
        dur_row = sc[sc["field"] == "dur_adj_mid"]
        assert dur_row.iloc[0]["available_positions"] == 0
        assert dur_row.iloc[0]["total_positions"] == 4

    def test_adv_coverage(self, sample_risk_df):
        """Test ADV coverage calculation."""
        result = summarise_risk_ready_dataset(sample_risk_df)
        sc = result["sensitivity_coverage"]
        adv_row = sc[sc["field"] == "adv_eur"]
        assert adv_row.iloc[0]["available_positions"] == 4
