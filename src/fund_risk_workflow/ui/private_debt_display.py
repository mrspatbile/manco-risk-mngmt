"""
Private debt display helpers.

Renders private-debt workflow results as dark HTML tables through the
shared display_dark_table renderer. Display-only reshaping and
formatting; no business calculation belongs here.
"""

import pandas as pd
from IPython.display import HTML, display

from fund_risk_workflow.ui.plot_style import C
from fund_risk_workflow.ui.print_html_utils import display_dark_table


def _show(df: pd.DataFrame, caption: str,
          fmt: dict | None = None,
          valuation_date: str | None = None,
          fund_id: str | None = None,
          export_id: str | None = None,
          export_name: str | None = None,
          **kwargs) -> None:
    """Render a dark table and optionally export it as a PNG.

    export_name overrides the caption for the export filename slug —
    use it when the caption embeds computed values.
    """
    html = display_dark_table(
        df,
        caption=caption,
        fmt=fmt,
        date_str=valuation_date,
        return_html=True,
        **kwargs,
    )
    display(HTML(html))
    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        filename = f'{export_id}_{_slugify(export_name or caption)}'
        save_html_as_png(html, fund_id or 'unknown', filename)


_PROFILE_FMT = {
    'market_value_eur': '{:,.0f}',
    'pct_nav': '{:.1f}%',
    'n_positions': '{:.0f}',
}


def display_rating_profile(rating_df: pd.DataFrame,
                           valuation_date: str | None = None,
                           fund_id: str | None = None,
                           export_id: str | None = None) -> None:
    """Credit-quality profile by rating."""
    _show(rating_df, 'Credit Quality by Rating', fmt=_PROFILE_FMT,
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id)


def display_seniority_profile(seniority_df: pd.DataFrame,
                              valuation_date: str | None = None,
                              fund_id: str | None = None,
                              export_id: str | None = None) -> None:
    """Exposure by seniority / sub-asset class."""
    _show(seniority_df, 'Seniority and Sub-Asset Class', fmt=_PROFILE_FMT,
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id)


def display_sector_profile(sector_df: pd.DataFrame,
                           valuation_date: str | None = None,
                           fund_id: str | None = None,
                           export_id: str | None = None) -> None:
    """Exposure by borrower sector."""
    _show(sector_df, 'Sector Concentration', fmt=_PROFILE_FMT,
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id)


def display_country_profile(country_df: pd.DataFrame,
                            valuation_date: str | None = None,
                            fund_id: str | None = None,
                            export_id: str | None = None) -> None:
    """Exposure by country of risk."""
    _show(country_df, 'Country Concentration', fmt=_PROFILE_FMT,
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id)


def display_borrower_concentration(borrower_df: pd.DataFrame,
                                   limit_pct: float = 20.0,
                                   valuation_date: str | None = None,
                                   fund_id: str | None = None,
                                   export_id: str | None = None) -> None:
    """Borrower exposure concentration versus the single-borrower limit."""
    _show(
        borrower_df,
        f'Borrower Concentration  |  Single-borrower limit: {limit_pct:.0f}% NAV',
        fmt={'exposure_eur': '{:,.0f}', 'pct_nav': '{:.1f}%'},
        col_styles={'pct_nav': lambda v: C['red']
                    if isinstance(v, float) and v > limit_pct else None},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Borrower Concentration',
    )


def display_maturity_ladder(maturity_df: pd.DataFrame,
                            valuation_date: str | None = None,
                            fund_id: str | None = None,
                            export_id: str | None = None) -> None:
    """Maturity ladder from stated position maturities."""
    _show(maturity_df, 'Maturity Ladder', fmt=_PROFILE_FMT,
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id)


def display_stress_assumptions(assumptions_df: pd.DataFrame,
                               valuation_date: str | None = None,
                               fund_id: str | None = None,
                               export_id: str | None = None) -> None:
    """Documented stress assumptions sourced from the risk policy."""
    df = assumptions_df.copy()
    df['value'] = df['value'].map('{:.2%}'.format)
    _show(df, 'Stress Assumptions (Risk Policy)',
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id)


def display_stress_results(results_df: pd.DataFrame,
                           valuation_date: str | None = None,
                           fund_id: str | None = None,
                           export_id: str | None = None) -> None:
    """Scenario P&L table with the worst scenario highlighted."""
    worst_pct = results_df['pct_nav'].min()
    _show(
        results_df,
        'Stress Scenario Results',
        fmt={'stressed_pnl_eur': '{:,.0f}', 'pct_nav': '{:.2f}%'},
        col_styles={'pct_nav': lambda v: C['red']
                    if isinstance(v, float) and v <= worst_pct else None},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
    )


def display_borrower_default(borrower_default: dict,
                             valuation_date: str | None = None,
                             fund_id: str | None = None,
                             export_id: str | None = None,
                             n_top: int = 5) -> None:
    """Borrower default stress with the documented recovery assumption."""
    recovery = borrower_default['recovery_rate']
    worst = borrower_default['worst']
    limit_pct = borrower_default['single_borrower_limit_pct']
    status = '⚠ BREACH' if worst['limit_breach'] else '✓ within limit'
    caption = (
        f'Borrower Default Stress  |  Recovery: {recovery:.0%} '
        f'(assumption)  |  Worst case: {worst["borrower"]} '
        f'({worst["loss_pct_nav"]:.1f}% NAV loss)  |  '
        f'Single-borrower limit {limit_pct:.0f}%: {status}'
    )
    _show(
        borrower_default['by_borrower'].head(n_top),
        caption,
        fmt={'exposure_eur': '{:,.0f}', 'pct_nav': '{:.1f}%',
             'loss_eur': '{:,.0f}', 'loss_pct_nav': '{:.1f}%'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Borrower Default Stress',
    )


def display_investor_concentration_closed_ended(
        investor_concentration: dict,
        valuation_date: str | None = None,
        fund_id: str | None = None,
        export_id: str | None = None) -> None:
    """Closed-ended ownership/governance concentration indicators.

    Shows single-investor and top-three concentration against ESMA
    thresholds, plus the investor-type breakdown. Intentionally renders
    no redemption stress — the fund has no periodic redemption.
    """
    summary = investor_concentration['summary']
    flag_single = '⚠ ESMA flag' if summary['concentration_flag'] else '✓ OK'
    flag_top3 = '⚠ High conc.' if summary['high_concentration'] else '✓ OK'

    by_inv = investor_concentration['by_investor'].copy()
    by_inv['pct_nav'] = by_inv['pct_nav'] * 100
    _show(
        by_inv,
        f'Investor Register (simulated)  |  '
        f'Largest: {summary["largest_investor_pct"]:.0%} ({flag_single})  |  '
        f'Top 3: {summary["top3_pct"]:.0%} ({flag_top3})',
        fmt={'aum_eur': '{:,.0f}', 'pct_nav': '{:.1f}%'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Investor Register',
    )

    by_type = investor_concentration['by_type']
    _show(
        by_type,
        'Investor Type Concentration (ownership/governance indicator)',
        fmt={'aum_eur': '{:,.0f}', 'pct_nav': '{:.1f}%',
             'n_investors': '{:.0f}'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
    )
