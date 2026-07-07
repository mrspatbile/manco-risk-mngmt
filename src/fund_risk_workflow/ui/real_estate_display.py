"""
Real estate display helpers.

Renders real-estate workflow results as dark HTML tables and
shared-style plots. Display-only reshaping and formatting; no business
calculation belongs here.
"""

import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import HTML, display

from fund_risk_workflow.ui.plot_style import (
    ACCENT,
    ACCENT2,
    C,
    FONT,
    apply_ax_style,
    sup_title,
)
from fund_risk_workflow.ui.print_html_utils import display_dark_table

# Reused closed-ended investor view (identical presentation contract)
from fund_risk_workflow.ui.private_debt_display import (  # noqa: F401
    display_investor_concentration_closed_ended,
)


def _show(df: pd.DataFrame, caption: str,
          fmt: dict | None = None,
          valuation_date: str | None = None,
          fund_id: str | None = None,
          export_id: str | None = None,
          export_name: str | None = None,
          **kwargs) -> None:
    """Render a dark table and optionally export it as a PNG."""
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


def _export_fig(fig, fund_id: str, export_id: str, slug: str) -> None:
    from fund_risk_workflow.ui.nb_utils import _get_project_root, _slugify
    out_dir = _get_project_root() / 'fig' / fund_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'{export_id}_{_slugify(slug)}.png'
    fig.savefig(path, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())


def display_sleeve_summary(sleeve_df: pd.DataFrame,
                           valuation_date: str | None = None,
                           fund_id: str | None = None,
                           export_id: str | None = None) -> None:
    """Sleeve breakdown: direct property, listed REIT, FX hedge, cash."""
    _show(sleeve_df, 'Sleeve Overview',
          fmt={'market_value_eur': '{:,.0f}', 'pct_nav': '{:.1f}%',
               'n_positions': '{:.0f}'},
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id)


def display_direct_property_profile(property_profile: dict,
                                    valuation_date: str | None = None,
                                    fund_id: str | None = None,
                                    export_id: str | None = None) -> None:
    """Per-property monitoring table with a weighted-average row."""
    props = property_profile['properties'].drop(columns=['isin'])
    wav = property_profile['weighted_avg']
    wav_row = pd.DataFrame([{
        'instrument_name': 'Weighted average',
        'property_type': '', 'country': '',
        'market_value_eur': wav['market_value_eur'],
        'pct_nav': float('nan'),
        'ltv_pct': wav['ltv_pct'],
        'rental_yield_pct': wav['rental_yield_pct'],
        'vacancy_rate_pct': wav['vacancy_rate_pct'],
        'effective_yield_pct': wav['effective_yield_pct'],
    }])
    df = pd.concat([props, wav_row], ignore_index=True)
    _show(
        df,
        'Direct Property Monitoring',
        fmt={'market_value_eur': '{:,.0f}', 'pct_nav': '{:.1f}%',
             'ltv_pct': '{:.1f}%', 'rental_yield_pct': '{:.1f}%',
             'vacancy_rate_pct': '{:.1f}%', 'effective_yield_pct': '{:.1f}%'},
        highlight_rows=[len(df) - 1],
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
    )


def plot_direct_property_metrics(property_profile: dict,
                                 fund_id: str,
                                 ltv_warning_pct: float | None = None,
                                 valuation_date: str | None = None,
                                 export_id: str | None = None):
    """Three-panel bar view of LTV, rental yield, and vacancy by property."""
    props = property_profile['properties']
    names = [n.replace(' ', '\n', 1) if len(n) > 22 else n
             for n in props['instrument_name']]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    sup_title(fig, 'Direct Property Key Metrics')

    panels = [
        ('ltv_pct', 'LTV (%)', ltv_warning_pct),
        ('rental_yield_pct', 'Rental Yield (%)', None),
        ('vacancy_rate_pct', 'Vacancy Rate (%)', None),
    ]
    for ax, (col, title, limit) in zip(axes, panels):
        colors = [ACCENT2 if (limit and v > limit) else ACCENT
                  for v in props[col]]
        bars = ax.barh(names, props[col], color=colors, height=0.5, alpha=0.9)
        if limit:
            ax.axvline(limit, color=ACCENT2, lw=1.2, linestyle='--',
                       label=f'Warning {limit:.0f}%')
            ax.legend(fontsize=FONT['small'])
        ax.set_title(title, fontsize=FONT['section'], color=C['cyan'])
        apply_ax_style(ax, grid_axis='x')
        for bar, val in zip(bars, props[col]):
            ax.text(bar.get_width() + 0.3,
                    bar.get_y() + bar.get_height() / 2,
                    f'{val:.1f}%', va='center', fontsize=FONT['small'],
                    color=C['muted'])

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'Direct property key metrics')
    plt.show()
    return fig



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
    """Scenario P&L table with the worst scenario in red."""
    worst_pct = results_df['pct_nav'].min()
    _show(
        results_df,
        'Stress Scenario Results',
        fmt={'stressed_pnl_eur': '{:,.0f}', 'pct_nav': '{:.2f}%'},
        col_styles={'pct_nav': lambda v: C['red']
                    if isinstance(v, float) and v <= worst_pct else None},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
    )


def display_ltv_stress(ltv_stress: dict,
                       valuation_date: str | None = None,
                       fund_id: str | None = None,
                       export_id: str | None = None) -> None:
    """Stressed LTV per property versus the covenant stress threshold."""
    df = ltv_stress['by_position'].copy()
    df['stressed_ltv'] = df['stressed_ltv'] * 100
    threshold_pct = ltv_stress['threshold'] * 100
    status = (f'⚠ {ltv_stress["n_breaches"]} breach(es)'
              if ltv_stress['n_breaches'] else '✓ no breaches')
    _show(
        df,
        f'LTV Covenant Stress  |  Property value {ltv_stress["shock"]:.0%}  |  '
        f'Threshold: {threshold_pct:.0f}%  |  {status}',
        fmt={'ltv_pct': '{:.1f}%', 'stressed_ltv': '{:.1f}%'},
        col_styles={'stressed_ltv': lambda v: C['red']
                    if isinstance(v, float) and v > threshold_pct else None},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='LTV Covenant Stress',
    )


def display_tenant_concentration(tenant_concentration: dict,
                                 as_of_date: str | None = None,
                                 fund_id: str | None = None,
                                 export_id: str | None = None) -> None:
    """Tenant and property rental concentration from the lease register."""
    _show(
        tenant_concentration['by_tenant'],
        'Tenant Rental Concentration (simulated lease register)',
        fmt={'annual_rent_eur': '{:,.0f}', 'pct_total_rent': '{:.1f}%',
             'n_leases': '{:.0f}'},
        valuation_date=as_of_date, fund_id=fund_id, export_id=export_id,
        export_name='Tenant Rental Concentration',
    )
    _show(
        tenant_concentration['by_property'],
        'Property Rental Concentration (simulated lease register)',
        fmt={'annual_rent_eur': '{:,.0f}', 'pct_total_rent': '{:.1f}%',
             'n_leases': '{:.0f}'},
        valuation_date=as_of_date, fund_id=fund_id, export_id=export_id,
        export_name='Property Rental Concentration',
    )


def display_tenant_default_stress(tenant_default: dict,
                                  fund_id: str | None = None,
                                  export_id: str | None = None) -> None:
    """Largest-tenant default stress, labelled simulated."""
    worst = tenant_default['worst']
    caption = (
        f'Tenant Default Stress (simulated)  |  Worst case: '
        f'{worst["tenant_name"]}  |  1y income loss: '
        f'EUR {worst["income_loss_eur"]:,.0f} ({worst["loss_pct_nav"]:.2f}% NAV)'
        f'  |  Implied NAV impact @ {tenant_default["capitalisation_yield"]:.0%}'
        f' cap yield: {worst["implied_nav_impact_pct"]:.1f}% NAV'
    )
    _show(
        tenant_default['by_tenant'],
        caption,
        fmt={'annual_rent_eur': '{:,.0f}', 'income_loss_eur': '{:,.0f}',
             'loss_pct_nav': '{:.2f}%', 'implied_nav_impact_eur': '{:,.0f}',
             'implied_nav_impact_pct': '{:.1f}%'},
        valuation_date=tenant_default.get('as_of_date'),
        fund_id=fund_id, export_id=export_id,
        export_name='Tenant Default Stress',
    )
