"""
tests/test_annex_iv.py
======================
Unit tests for src/annex_iv.py

Run with: python3 -m pytest tests/test_annex_iv.py -v

Required coverage (MRS-83):
    - liquidity_buckets section is populated (6 rows, correct columns)
    - cumulative_pct sums to ~100 for all liquid funds
    - All five fund types build without error
    - export_annex_iv_excel writes a non-empty file
"""

import os
import pytest
import pandas as pd
from fund_risk_workflow.data.database import get_engine
from fund_risk_workflow.reporting.annex_iv import build_annex_iv, export_annex_iv_excel

ENGINE  = get_engine()
QUARTER = '2026-03-31'

_LIQ_COLS     = ['bucket', 'nav_eur', 'nav_pct', 'cumulative_pct']
_BUCKET_COUNT = 6   # ESMA standard: 1d, 2-7d, 8-30d, 31-90d, 91-365d, >1yr


# ================================================================
# Hedge Fund — MRS-34
# ================================================================

class TestBuildAnnexIvHf:

    @pytest.fixture(scope='class')
    def rpt(self):
        return build_annex_iv(ENGINE, 'AIFM_HedgeFund', QUARTER)

    def test_returns_dict(self, rpt):
        assert isinstance(rpt, dict)

    def test_required_keys(self, rpt):
        for key in ['identification', 'asset_class_breakdown', 'geography_breakdown',
                    'currency_breakdown', 'top5_positions', 'risk_measures',
                    'leverage_detail', 'liquidity_buckets', 'liquidity_terms']:
            assert key in rpt, f'Missing key: {key}'

    def test_nav_positive(self, rpt):
        assert rpt['_nav'] > 0

    def test_identification_is_dataframe(self, rpt):
        assert isinstance(rpt['identification'], pd.DataFrame)

    def test_identification_has_fund_id(self, rpt):
        df = rpt['identification']
        fields = df['field'].tolist()
        assert 'Fund identifier' in fields
        row = df[df['field'] == 'Fund identifier']
        assert row['value'].iloc[0] == 'AIFM_HedgeFund'

    def test_asset_class_breakdown_columns(self, rpt):
        df = rpt['asset_class_breakdown']
        for col in ['asset_class', 'nav_eur', 'nav_pct']:
            assert col in df.columns

    def test_top5_has_five_rows(self, rpt):
        assert len(rpt['top5_positions']) == 5

    def test_risk_measures_is_dataframe(self, rpt):
        assert isinstance(rpt['risk_measures'], pd.DataFrame)

    # ── Liquidity (MRS-83 required) ──────────────────────────────

    def test_liquidity_buckets_is_dataframe(self, rpt):
        assert isinstance(rpt['liquidity_buckets'], pd.DataFrame)

    def test_liquidity_buckets_has_six_rows(self, rpt):
        """MRS-83: liquidity section must be populated with all 6 ESMA buckets."""
        assert len(rpt['liquidity_buckets']) == _BUCKET_COUNT

    def test_liquidity_buckets_required_columns(self, rpt):
        """MRS-83: bucket summary must have bucket, nav_eur, nav_pct, cumulative_pct."""
        df = rpt['liquidity_buckets']
        for col in _LIQ_COLS:
            assert col in df.columns, f'Missing liquidity column: {col}'

    def test_liquidity_nav_pct_sums_to_100(self, rpt):
        """MRS-83: nav_pct must sum to ~100 (all positions assigned to a bucket)."""
        total = rpt['liquidity_buckets']['nav_pct'].sum()
        assert abs(total - 100.0) < 0.5

    def test_liquidity_cumulative_ends_at_100(self, rpt):
        """MRS-83: cumulative_pct final row must equal ~100."""
        last = rpt['liquidity_buckets']['cumulative_pct'].iloc[-1]
        assert abs(last - 100.0) < 0.5

    def test_liquidity_nav_pct_cumulative_correct(self, rpt):
        """For hedge funds, nav_pct can be negative (short positions), but cumulative must equal 100%."""
        last = rpt['liquidity_buckets']['cumulative_pct'].iloc[-1]
        assert abs(last - 100.0) < 0.5

    def test_liquidity_bucket_labels(self, rpt):
        from fund_risk_workflow.config import LIQUIDITY_BUCKET_ORDER
        assert rpt['liquidity_buckets']['bucket'].tolist() == LIQUIDITY_BUCKET_ORDER

    def test_hf_highly_liquid(self, rpt):
        # HF holds liquid equities — expect >80% in ≤7 days
        df   = rpt['liquidity_buckets']
        fast = df[df['bucket'].isin(['1 day', '2-7 days'])]['nav_pct'].sum()
        assert fast > 80.0, f'HF expected >80% liquid in ≤7d, got {fast:.1f}%'

    def test_leverage_detail_columns(self, rpt):
        df = rpt['leverage_detail']
        assert 'item' in df.columns

    def test_liquidity_terms_is_dataframe(self, rpt):
        assert isinstance(rpt['liquidity_terms'], pd.DataFrame)


# ================================================================
# Private Debt — MRS-34
# ================================================================

class TestBuildAnnexIvPd:

    @pytest.fixture(scope='class')
    def rpt(self):
        return build_annex_iv(ENGINE, 'AIFM_PrivateDebt', QUARTER)

    def test_nav_positive(self, rpt):
        assert rpt['_nav'] > 0

    def test_identification_is_closed_ended(self, rpt):
        row = rpt['identification'].loc[
            rpt['identification']['field'] == 'Redemption frequency',
            'value',
        ]
        assert row.iloc[0] == 'Closed-ended — no periodic redemption'

    def test_liquidity_buckets_six_rows(self, rpt):
        """MRS-83: liquidity section must be populated."""
        assert len(rpt['liquidity_buckets']) == _BUCKET_COUNT

    def test_liquidity_required_columns(self, rpt):
        for col in _LIQ_COLS:
            assert col in rpt['liquidity_buckets'].columns

    def test_liquidity_nav_pct_sums_to_100(self, rpt):
        total = rpt['liquidity_buckets']['nav_pct'].sum()
        assert abs(total - 100.0) < 0.5

    def test_liquidity_cumulative_ends_at_100(self, rpt):
        last = rpt['liquidity_buckets']['cumulative_pct'].iloc[-1]
        assert abs(last - 100.0) < 0.5

    def test_pd_has_illiquid_bucket(self, rpt):
        # Private debt loans are illiquid — expect NAV in "> 1 year"
        df    = rpt['liquidity_buckets']
        illiq = df[df['bucket'] == '> 1 year']['nav_pct'].iloc[0]
        assert illiq > 0.0, 'PD fund should have illiquid positions in > 1 year bucket'

    def test_identification_fund_id(self, rpt):
        df  = rpt['identification']
        row = df[df['field'] == 'Fund identifier']
        assert row['value'].iloc[0] == 'AIFM_PrivateDebt'


# ================================================================
# Real Estate — MRS-34
# ================================================================

class TestBuildAnnexIvRe:

    @pytest.fixture(scope='class')
    def rpt(self):
        return build_annex_iv(ENGINE, 'AIFM_RealEstate', QUARTER)

    def test_nav_positive(self, rpt):
        assert rpt['_nav'] > 0

    def test_identification_is_closed_ended(self, rpt):
        row = rpt['identification'].loc[
            rpt['identification']['field'] == 'Redemption frequency',
            'value',
        ]
        assert row.iloc[0] == 'Closed-ended — no periodic redemption'

    def test_liquidity_buckets_six_rows(self, rpt):
        """MRS-83: liquidity section must be populated."""
        assert len(rpt['liquidity_buckets']) == _BUCKET_COUNT

    def test_liquidity_required_columns(self, rpt):
        for col in _LIQ_COLS:
            assert col in rpt['liquidity_buckets'].columns

    def test_liquidity_nav_pct_sums_to_100(self, rpt):
        total = rpt['liquidity_buckets']['nav_pct'].sum()
        assert abs(total - 100.0) < 0.5

    def test_liquidity_cumulative_ends_at_100(self, rpt):
        last = rpt['liquidity_buckets']['cumulative_pct'].iloc[-1]
        assert abs(last - 100.0) < 0.5

    def test_re_dominated_by_illiquid(self, rpt):
        # Direct property positions go into > 1 year bucket
        df    = rpt['liquidity_buckets']
        illiq = df[df['bucket'] == '> 1 year']['nav_pct'].iloc[0]
        assert illiq > 50.0, (
            f'RE fund should have >50% NAV in "> 1 year" bucket (direct property). '
            f'Got {illiq:.1f}%'
        )


# ================================================================
# PE Buyout — MRS-59
# ================================================================

class TestBuildAnnexIvPe:

    @pytest.fixture(scope='class')
    def rpt(self):
        return build_annex_iv(ENGINE, 'AIFM_PE_Buyout', QUARTER)

    def test_returns_dict(self, rpt):
        assert isinstance(rpt, dict)

    def test_required_keys(self, rpt):
        for key in ['identification', 'sector_exposure', 'country_exposure',
                    'stage_exposure', 'top5_positions', 'leverage_detail',
                    'performance', 'aifmd_ii_disclosure']:
            assert key in rpt, f'Missing key: {key}'

    def test_nav_positive(self, rpt):
        assert rpt['_nav'] > 0

    def test_identification_fund_id(self, rpt):
        df  = rpt['identification']
        row = df[df['field'] == 'Fund identifier']
        assert row['value'].iloc[0] == 'AIFM_PE_Buyout'

    def test_sector_exposure_has_cost_pct(self, rpt):
        df = rpt['sector_exposure']
        assert 'cost_pct' in df.columns

    def test_sector_pct_sums_to_100(self, rpt):
        total = rpt['sector_exposure']['cost_pct'].sum()
        assert abs(total - 100.0) < 0.5

    def test_top5_positions_not_empty(self, rpt):
        assert len(rpt['top5_positions']) > 0

    def test_performance_contains_irr(self, rpt):
        fields = rpt['performance']['field'].tolist()
        assert 'Net IRR' in fields

    def test_performance_contains_tvpi(self, rpt):
        fields = rpt['performance']['field'].tolist()
        assert 'TVPI' in fields

    def test_leverage_detail_mentions_project_debt(self, rpt):
        items = rpt['leverage_detail']['item'].str.cat(sep=' ')
        assert 'project' in items.lower() or 'PROJECT' in items

    def test_aifmd_ii_has_lmt_section(self, rpt):
        fields = rpt['aifmd_ii_disclosure']['field'].str.cat(sep=' ')
        assert 'LIQUIDITY MANAGEMENT' in fields

    def test_no_liquidity_buckets_for_pe(self, rpt):
        # PE is closed-ended — no ESMA bucket table
        assert 'liquidity_buckets' not in rpt


# ================================================================
# Infrastructure Core — MRS-78
# ================================================================

class TestBuildAnnexIvInfra:

    @pytest.fixture(scope='class')
    def rpt(self):
        return build_annex_iv(ENGINE, 'AIFM_Infra_Core', QUARTER)

    def test_returns_dict(self, rpt):
        assert isinstance(rpt, dict)

    def test_required_keys(self, rpt):
        for key in ['identification', 'asset_breakdown', 'sector_breakdown',
                    'country_breakdown', 'top5_positions', 'leverage_detail',
                    'performance']:
            assert key in rpt, f'Missing key: {key}'

    def test_nav_positive(self, rpt):
        assert rpt['_nav'] > 0

    def test_identification_fund_id(self, rpt):
        df  = rpt['identification']
        row = df[df['field'] == 'Fund identifier']
        assert row['value'].iloc[0] == 'AIFM_Infra_Core'

    def test_asset_breakdown_not_empty(self, rpt):
        assert len(rpt['asset_breakdown']) > 0

    def test_sector_breakdown_has_concentrated_col(self, rpt):
        # concentration_by_sector returns a 'concentrated' flag
        assert 'concentrated' in rpt['sector_breakdown'].columns

    def test_top5_has_up_to_five_rows(self, rpt):
        assert 1 <= len(rpt['top5_positions']) <= 5

    def test_leverage_detail_mentions_project_debt(self, rpt):
        items = rpt['leverage_detail']['item'].str.cat(sep=' ')
        assert 'project' in items.lower() or 'PROJECT' in items

    def test_performance_contains_irr(self, rpt):
        fields = rpt['performance']['field'].tolist()
        assert 'Net IRR' in fields

    def test_performance_contains_inflation_linkage(self, rpt):
        fields = rpt['performance']['field'].tolist()
        assert any('inflation' in f.lower() for f in fields)

    def test_no_liquidity_buckets_for_infra(self, rpt):
        # Infra is closed-ended — no ESMA bucket table
        assert 'liquidity_buckets' not in rpt


# ================================================================
# Scoped workflow display
# ================================================================

def test_workflow_displays_only_explicit_closed_end_sections(monkeypatch):
    from fund_risk_workflow.reporting import annex_iv_workflow

    report = {
        'identification': pd.DataFrame({'field': ['Fund'], 'value': ['PD']}),
        'breakdown': pd.DataFrame({'Category': ['Loan'], 'NAV (EUR)': [1]}),
        'leverage_detail': pd.DataFrame({'item': ['Gross'], 'value': ['1.0x']}),
        'liquidity_buckets': pd.DataFrame({'bucket': ['1 day']}),
    }
    displayed = []
    monkeypatch.setattr(
        annex_iv_workflow.annex_iv,
        'build_annex_iv',
        lambda *args, **kwargs: report,
    )
    monkeypatch.setattr(
        annex_iv_workflow.annex_display,
        'annex_iv_section',
        lambda _report, section, **kwargs: displayed.append(section),
    )
    monkeypatch.setattr(
        annex_iv_workflow.annex_iv,
        'export_annex_iv_excel',
        lambda *args, **kwargs: 'mock.xlsx',
    )

    sections = ('identification', 'breakdown', 'leverage_detail')
    result = annex_iv_workflow.run(
        engine=None,
        fund_id='AIFM_PrivateDebt',
        quarter=QUARTER,
        first_export_id='25',
        sections=sections,
    )

    assert displayed == list(sections)
    assert [name for name, _ in result['sections']] == list(sections)
    assert 'liquidity_buckets' not in displayed


# ================================================================
# Excel export
# ================================================================

class TestExportAnnexIvExcel:

    def test_returns_path_string(self):
        path = export_annex_iv_excel(ENGINE, quarter=QUARTER, output_dir='data')
        assert isinstance(path, str)

    def test_file_exists(self):
        path = export_annex_iv_excel(ENGINE, quarter=QUARTER, output_dir='data')
        assert os.path.exists(path)

    def test_file_is_xlsx(self):
        path = export_annex_iv_excel(ENGINE, quarter=QUARTER, output_dir='data')
        assert path.endswith('.xlsx')

    def test_file_non_empty(self):
        path = export_annex_iv_excel(ENGINE, quarter=QUARTER, output_dir='data')
        assert os.path.getsize(path) > 10_000

    def test_quarter_in_filename(self):
        path = export_annex_iv_excel(ENGINE, quarter=QUARTER, output_dir='data')
        # Quarter format (e.g., 2026Q1) now appears in directory path, not filename
        from datetime import datetime
        quarter_date = datetime.strptime(QUARTER, '%Y-%m-%d')
        quarter_num = (quarter_date.month - 1) // 3 + 1
        quarter_formatted = f'{quarter_date.year}Q{quarter_num}'
        # Check full path includes quarter in directory structure
        assert quarter_formatted in path
