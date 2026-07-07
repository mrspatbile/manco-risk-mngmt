"""
src/reporting/annex_iv_workflow.py
==================================
Annex IV report orchestration workflow.

Encapsulates the full Annex IV reporting process:
- build the report
- display sections
- export to Excel
- return metadata

Usage
-----
    from fund_risk_workflow.reporting.annex_iv_workflow import run

    result = run(
        engine=engine,
        fund_id='AIFM_HedgeFund',
        quarter='2026-03-31',
        first_export_id='25',
    )

    print(result['workbook_path'])
"""


import fund_risk_workflow.reporting.annex_iv as annex_iv
import fund_risk_workflow.ui.annex_iv_display as annex_display


def run(
    engine,
    fund_id: str,
    quarter: str,
    first_export_id: str | int,
    output_dir: str = "data",
    sections: tuple[str, ...] | list[str] | None = None,
) -> dict:
    """
    Orchestrate full Annex IV reporting workflow.

    Builds the Annex IV report, displays all sections, exports to Excel,
    and returns a result dictionary.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        Database engine for Annex IV data queries.
    fund_id : str
        Fund identifier (e.g. 'AIFM_HedgeFund').
    quarter : str
        Reporting quarter in 'YYYY-MM-DD' format (e.g. '2026-03-31').
    first_export_id : str or int
        Starting export ID for the first section.
        Subsequent sections auto-increment (25, 26, 27, ...).
    output_dir : str, default '../../data'
        Output directory for Excel workbook (relative to project root).
    sections : tuple[str, ...] or list[str], optional
        Explicit report sections to display. When omitted, preserves the
        established liquid-AIF section order. Closed-ended notebook workflows
        can omit liquidity and redemption sections without changing the
        default hedge-fund behavior.

    Returns
    -------
    dict
        Result dictionary with keys:
        - 'report': Built Annex IV report object
        - 'workbook_path': Path to exported workbook (relative to project root)
        - 'sections': List of (section_name, export_id) tuples
    """
    # Sections to display in order
    section_names = list(sections) if sections is not None else [
        "identification",
        "breakdown",
        "risk_measures",
        "leverage_detail",
        "liquidity_buckets",
        "liquidity_terms",
    ]

    # Convert first_export_id to int and compute sequential export IDs
    first_id = int(first_export_id)
    sections = [
        (name, str(first_id + i))
        for i, name in enumerate(section_names)
    ]

    # 1. Build the Annex IV report
    annex_iv_report = annex_iv.build_annex_iv(engine, fund_id, quarter=quarter)

    missing_sections = [
        section_name
        for section_name in section_names
        if section_name not in annex_iv_report
    ]
    if missing_sections:
        raise ValueError(
            f"Annex IV sections unavailable for {fund_id}: {missing_sections}"
        )

    # 2. Display each section
    for section_name, export_id in sections:
        annex_display.annex_iv_section(
            annex_iv_report,
            section_name,
            fund_id=fund_id,
            export_id=export_id,
        )

    # 3. Export to Excel (for this fund only)
    workbook_path = annex_iv.export_annex_iv_excel(
        engine,
        quarter=quarter,
        fund_ids=[fund_id],
        output_dir=output_dir,
    )

    # 4. Return result dictionary
    return {
        "report": annex_iv_report,
        "workbook_path": workbook_path,
        "sections": sections,
    }
