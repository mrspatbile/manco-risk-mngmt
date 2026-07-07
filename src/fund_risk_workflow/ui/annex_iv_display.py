"""
Annex IV report display and formatting utilities.

Provides reusable functions for rendering Annex IV transparency report sections
as styled HTML tables in Jupyter notebooks, with configurable column widths,
number formatting, and section header highlighting.

Regulatory context:
    AIFMD Art. 110 — Annex IV transparency report
    EU 231/2013 Articles 110–121 — regulatory reporting requirements
    ESMA technical guidance v1.7 (July 2024) — Annex IV field definitions
"""

import pandas as pd
from fund_risk_workflow.ui import print_html_utils as phtml

# Section header configuration: maps section name to (column_name, list of header texts)
SECTIONS_DICT = {
    'identification': (
        'field',
        ['FUND IDENTITY', 'AIFM', 'COUNTERPARTIES', 'REPORTING',
         'REDEMPTION TERMS', 'LEVERAGE LIMITS (RMP)'],
    ),
    'breakdown': (
        'Category',
        ['Asset Class', 'Geography', 'Currency', 'Top 5 positions'],
    ),
    'risk_measures': (
        'field',
        ['VaR & ES (99%, historical, 250 days)', 'LEVERAGE', 'LIQUIDITY HEADLINE'],
    ),
    'leverage_detail': (
        'item',
        ['GROSS METHOD — by source (EU231/2013 Art. 7)',
         'COMMITMENT METHOD (EU231/2013 Art. 8)'],
    ),
    'liquidity_buckets': None,
    'liquidity_terms': (
        'field',
        ['INVESTOR CONCENTRATION (ESMA thresholds)'],
    ),
    # PE report sections (explicit section list, MRS-198)
    'sector_exposure': None,
    'country_exposure': None,
    'stage_exposure': None,
    'top5_positions': None,
    'performance': (
        'field',
        ['CAPITAL', 'RETURN METRICS', 'INFRASTRUCTURE CHARACTERISTICS'],
    ),
    'aifmd_ii_disclosure': (
        'field',
        ['AIFMD II — EXPANDED DISCLOSURES (Directive 2024/927/EU)',
         'LIQUIDITY MANAGEMENT TOOLS (LMTs)', 'DELEGATION ARRANGEMENTS',
         'PRINCIPAL MARKETS', 'UNFUNDED COMMITMENTS'],
    ),
    # Infrastructure report sections (explicit section list, MRS-198)
    'asset_breakdown': None,
    'sector_breakdown': None,
    'country_breakdown': None,
}

# Default column widths (CSS) for each section
COL_WIDTHS_MAP = {
    'identification': {
        'Field': '260px',
        'Value': '280px',
    },
    'breakdown': {
        'Category': '280px',
        'NAV (EUR)': '160px',
        '% NAV': '80px',
    },
    'risk_measures': {
        'field': '300px',
        'value': '240px',
    },
    'leverage_detail': {
        'item': '300px',
        'gross_eur': '120px',
        'pct_nav': '100px',
    },
    'liquidity_buckets': {
        'bucket': '100px',
        'nav_eur': '200px',
        'nav_pct': '100px',
        'cumulative_pct': '100px',
    },
    'liquidity_terms': {
        'field': '300px',
        'value': '250px',
    },
    # PE / infrastructure sections (explicit section lists, MRS-198)
    'sector_exposure': {'sector': '260px', 'nav_eur': '160px',
                        'cost_pct': '90px'},
    'country_exposure': {'country': '260px', 'nav_eur': '160px',
                         'cost_pct': '90px'},
    'stage_exposure': {'stage': '260px', 'nav_eur': '160px',
                       'cost_pct': '90px'},
    'top5_positions': {'rank': '50px', 'name': '220px', 'nav_eur': '140px',
                       'nav_pct': '90px'},
    'performance': {'field': '300px', 'value': '280px'},
    'aifmd_ii_disclosure': {'field': '320px', 'value': '380px'},
    'asset_breakdown': {'asset_name': '240px', 'nav_eur': '140px',
                        'nav_pct': '90px'},
    'sector_breakdown': {'sector': '240px', 'nav_eur': '140px',
                         'nav_pct': '90px'},
    'country_breakdown': {'country': '240px', 'nav_eur': '140px',
                          'nav_pct': '90px'},
}

# Default number formatting (Python format strings) for each section
FMT_MAP = {
    'liquidity_buckets': {
        'nav_eur': '{:,.2f}',
        'nav_pct': '{:.2f}%',
        'cumulative_pct': '{:.0f}%',
    },
    'liquidity_terms': {
        'nav_eur': '{:,.2f}',
        'nav_pct': '{:.2f}%',
    },
    # PE / infrastructure sections (nav_eur arrives pre-formatted as text)
    'sector_exposure': {'cost_pct': '{:.2f}%'},
    'country_exposure': {'cost_pct': '{:.2f}%'},
    'stage_exposure': {'cost_pct': '{:.2f}%'},
    'top5_positions': {'nav_pct': '{:.2f}%'},
    'asset_breakdown': {'nav_pct': '{:.2f}%', 'moic': '{:.2f}x'},
    'sector_breakdown': {'nav_pct': '{:.2f}%'},
    'country_breakdown': {'nav_pct': '{:.2f}%'},
}


def _get_row_index(df: pd.DataFrame, sections: list[str],
                   colname: str) -> list[int]:
    """
    Find row indices in df where colname matches any of the section header texts.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to search
    sections : list[str]
        List of section header text values to match (case-insensitive)
    colname : str
        Column name to search in

    Returns
    -------
    list[int]
        Row indices where df[colname] (uppercased) matches any section (uppercased)
    """
    mask = df[colname].str.upper().isin([s.upper() for s in sections])
    section_rows = df[mask].index.tolist()
    return section_rows


def annex_iv_section(annex_iv: dict, section: str,
                     col_widths: dict | None = None,
                     fmt: dict | None = None,
                     spacer_width: str | int | None = None,
                     fund_id: str | None = None,
                     export_id: str | None = None) -> None:
    """
    Display a formatted HTML table for a single Annex IV report section.

    Takes a section DataFrame from the Annex IV report (built via build_annex_iv)
    and renders it as a styled HTML table with configurable column widths,
    number formatting, and row highlighting for section headers.

    Parameters
    ----------
    annex_iv : dict[str, pd.DataFrame]
        Annex IV report dict returned by build_annex_iv(), containing keyed
        DataFrames: 'identification', 'breakdown', 'risk_measures', 'leverage_detail',
        'liquidity_buckets', 'liquidity_terms', etc.
    section : str
        Name of the section to display. Must be a key in annex_iv.
        Example: 'breakdown', 'risk_measures', 'liquidity_buckets'.
    col_widths : dict[str, str], optional
        Column name → CSS width mapping (e.g., {'Category': '280px', '% NAV': '80px'}).
        If None, defaults are retrieved from COL_WIDTHS_MAP keyed by section name.
    fmt : dict[str, str], optional
        Column name → Python format string mapping (e.g., {'nav_pct': '{:.2f}%'}).
        Applied at display time; does not modify the DataFrame.
        If None, defaults are retrieved from FMT_MAP keyed by section name.
    spacer_width : int or str, optional
        Width of an optional spacer column (CSS width value).
        Used to pad the table or separate column groups. Defaults to None.

    Returns
    -------
    None
        Renders HTML directly to Jupyter cell output via phtml.display_dark_table().

    Notes
    -----
    Column name normalization occurs before display:
    - 'PCT' is replaced with '%'
    - 'NAV %' is replaced with '% NAV'

    Section header rows are automatically highlighted based on entries in the
    module-level SECTIONS_DICT. Headers are identified by matching the first
    column against configured section names (e.g., 'Asset Class', 'LEVERAGE',
    'INVESTOR CONCENTRATION').

    All columns are right-aligned for readability.

    Examples
    --------
    >>> from fund_risk_workflow.reporting.annex_iv import build_annex_iv
    >>> from fund_risk_workflow.ui.annex_iv_display import annex_iv_section
    >>> rpt = build_annex_iv(engine, 'AIFM_HedgeFund', '2026-03-31')
    >>> annex_iv_section(rpt, 'breakdown')
    # Displays breakdown section (Asset Class, Geography, Currency, Top 5)

    >>> annex_iv_section(rpt, 'leverage_detail',
    ...                  col_widths={'item': '350px', 'gross_eur': '150px'})
    # Displays with custom column widths

    Regulatory context
    ------------------
    AIFMD Article 110 — Annex IV transparency report.
    EU 231/2013 Articles 110–121 — regulatory reporting requirements.
    ESMA technical guidance v1.7 (July 2024) — Annex IV field definitions.
    """
    if col_widths is None:
        col_widths = COL_WIDTHS_MAP.get(section)
    if fmt is None:
        fmt = FMT_MAP.get(section)

    df = annex_iv[section].copy()
    df.columns = df.columns.str.replace('PCT', '%')
    df.columns = df.columns.str.replace('NAV %', '% NAV')
    col_align_override = {col: 'right' for col in df.columns}

    section_rows = None
    if SECTIONS_DICT.get(section):
        colname, sub_sections = SECTIONS_DICT[section]
        section_rows = _get_row_index(df, sub_sections, colname)

    html = phtml.display_dark_table(
        df,
        caption=section.upper().replace('_', ' '),
        fmt=fmt,
        col_align_override=col_align_override,
        highlight_rows=section_rows,
        col_widths=col_widths,
        spacer_width=spacer_width,
        return_html=True,
    )

    from IPython.display import display, HTML
    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        section_slug = _slugify(section)
        filename = f'{export_id}_annex_iv_{section_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)
