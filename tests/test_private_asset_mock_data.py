"""Validation for explicitly simulated private-asset reference registers."""

import json
from pathlib import Path

import pandas as pd
import pytest

from fund_risk_workflow.data.database import get_engine
from fund_risk_workflow.data.enrichment import get_risk_ready_df
from fund_risk_workflow.data.mock_bloomberg import MockBloomberg
from fund_risk_workflow.data.reference_data import (
    load_investor_base,
    load_investor_base_dict,
    load_tenant_register,
)
from fund_risk_workflow.risk.esg_utils import build_esg_df


ROOT = Path(__file__).parent.parent
DATE = '2026-03-31'
ENGINE = get_engine()
BBG = MockBloomberg()


@pytest.mark.parametrize(
    ('fund_id', 'expected_count'),
    [
        ('AIFM_PrivateDebt', 8),
        ('AIFM_RealEstate', 12),
    ],
)
def test_simulated_investor_register_is_complete(fund_id, expected_count):
    register = load_investor_base_dict(fund_id)
    investors = load_investor_base(fund_id, nav_eur=100_000_000)

    assert register['data_classification'] == 'simulated'
    assert len(investors) == expected_count
    assert investors['investor_id'].is_unique
    assert investors['nav_pct'].sum() == pytest.approx(1.0)
    assert investors['aum_eur'].sum() == pytest.approx(100_000_000)


def test_real_estate_tenant_register_links_to_direct_properties():
    tenants = load_tenant_register('AIFM_RealEstate')
    specs_path = (
        ROOT
        / 'reference_data/funds/AIFM_RealEstate/position_specs.json'
    )
    specs = json.loads(specs_path.read_text())['position_specs']
    properties = {
        row['isin']: row
        for row in specs
        if row.get('is_direct_property') is True
    }

    assert tenants.attrs['data_classification'] == 'simulated'
    assert len(tenants) == 8
    assert tenants['lease_id'].is_unique
    assert set(tenants['property_isin']) == set(properties)
    assert (tenants['annual_rent_eur'] > 0).all()
    assert (tenants['lease_end_date'] > pd.Timestamp(DATE)).all()


def test_tenant_rent_reconciles_to_property_inputs():
    tenants = load_tenant_register('AIFM_RealEstate')
    specs_path = (
        ROOT
        / 'reference_data/funds/AIFM_RealEstate/position_specs.json'
    )
    specs = json.loads(specs_path.read_text())['position_specs']

    rent_by_property = tenants.groupby('property_isin')['annual_rent_eur'].sum()
    for prop in specs:
        if prop.get('is_direct_property') is not True:
            continue
        expected_occupied_rent = (
            prop['price']
            * prop['rental_yield_pct'] / 100
            * (1 - prop['vacancy_rate_pct'] / 100)
        )
        assert rent_by_property[prop['isin']] == pytest.approx(
            expected_occupied_rent,
            rel=0.01,
        )


@pytest.mark.parametrize(
    ('fund_id', 'esg_relevant_classes', 'expected_scored'),
    [
        ('AIFM_PrivateDebt', {'Loan', 'Bond', 'CLO'}, 9),
        ('AIFM_RealEstate', {'Real Estate'}, 6),
    ],
)
def test_opt_in_reference_esg_scores_cover_private_assets(
    fund_id,
    esg_relevant_classes,
    expected_scored,
):
    risk_df = get_risk_ready_df(ENGINE, fund_id, DATE)
    esg_df = build_esg_df(
        risk_df,
        BBG,
        ENGINE,
        fund_id,
        DATE,
        use_reference_scores_for_unlisted=True,
    )
    relevant = esg_df[esg_df['asset_class'].isin(esg_relevant_classes)]

    assert len(relevant) == expected_scored
    assert relevant['esg_score'].notna().all()


def test_default_esg_behavior_remains_backward_compatible():
    risk_df = get_risk_ready_df(ENGINE, 'AIFM_HedgeFund', DATE)
    default = build_esg_df(
        risk_df, BBG, ENGINE, 'AIFM_HedgeFund', DATE
    )
    explicit_default = build_esg_df(
        risk_df,
        BBG,
        ENGINE,
        'AIFM_HedgeFund',
        DATE,
        use_reference_scores_for_unlisted=False,
    )

    pd.testing.assert_frame_equal(default, explicit_default)
