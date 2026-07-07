"""
PE buyout display helpers.

Renders PE workflow results as dark HTML tables and shared-style plots.
Display-only reshaping and formatting; no business calculation belongs
here.
"""

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from IPython.display import HTML, display

from fund_risk_workflow.ui.plot_style import (
    ACCENT,
    ACCENT2,
    C,
    FONT,
    apply_ax_style,
    section_title,
    sup_title,
)
from fund_risk_workflow.ui.print_html_utils import display_dark_table


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


# ── tables ──────────────────────────────────────────────────────────────────

def display_portfolio_overview(overview_df: pd.DataFrame,
                               valuation_date: str | None = None,
                               fund_id: str | None = None,
                               export_id: str | None = None) -> None:
    """Portfolio company overview from the PE tables."""
    _show(
        overview_df,
        'Portfolio Company Overview',
        fmt={'cost_basis_eur': '{:,.0f}', 'ownership_pct': '{:.1f}%',
             'entry_ev_ebitda': '{:.1f}x', 'entry_ev_sales': '{:.1f}x',
             'exit_multiple': '{:.2f}x'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
    )


def display_valuation_monitor(monitor_df: pd.DataFrame,
                              headroom_warning_pct: float = 20.0,
                              valuation_date: str | None = None,
                              fund_id: str | None = None,
                              export_id: str | None = None) -> None:
    """Latest appraisals with leverage covenants and headroom."""
    df = monitor_df.drop(columns=['key_risks'], errors='ignore')
    _show(
        df,
        'Valuation and Covenant Monitoring (independent appraisals)',
        fmt={'appraised_nav_eur': '{:,.0f}', 'ebitda_ltm_eur': '{:,.0f}',
             'ev_ebitda': '{:.1f}x', 'leverage_ratio': '{:.2f}x',
             'leverage_covenant': '{:.1f}x', 'headroom_pct': '{:.1f}%'},
        col_styles={'headroom_pct': lambda v: C['red']
                    if isinstance(v, float) and v < headroom_warning_pct
                    else None},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Valuation and Covenant Monitoring',
    )


def display_performance_summary(performance: dict,
                                valuation_date: str | None = None,
                                fund_id: str | None = None,
                                export_id: str | None = None) -> None:
    """Fund-level IRR and DPI / RVPI / TVPI multiples."""
    irr = performance['irr']
    mult = performance['multiples']
    df = pd.DataFrame([
        {'metric': 'Gross IRR (XIRR)', 'value': f"{irr['gross_irr']:.2%}"},
        {'metric': 'Net IRR (after fees and carry)',
         'value': f"{irr['net_irr']:.2%}"},
        {'metric': 'DPI', 'value': f"{mult['dpi']:.2f}x"},
        {'metric': 'RVPI', 'value': f"{mult['rvpi']:.2f}x"},
        {'metric': 'TVPI', 'value': f"{mult['tvpi']:.2f}x"},
        {'metric': 'Paid-in capital', 'value': f"EUR {mult['paid_in']:,.0f}"},
        {'metric': 'Distributions',
         'value': f"EUR {mult['distributions']:,.0f}"},
        {'metric': 'Current NAV', 'value': f"EUR {mult['nav']:,.0f}"},
    ])
    _show(df, 'Fund Performance Summary',
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id)


def display_multiples_by_company(by_company_df: pd.DataFrame,
                                 valuation_date: str | None = None,
                                 fund_id: str | None = None,
                                 export_id: str | None = None) -> None:
    """DPI / RVPI / TVPI per portfolio company."""
    _show(
        by_company_df,
        'Multiples by Company',
        fmt={'paid_in': '{:,.0f}', 'distributions': '{:,.0f}',
             'nav': '{:,.0f}', 'dpi': '{:.2f}x', 'rvpi': '{:.2f}x',
             'tvpi': '{:.2f}x'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
    )


def display_commitment_liquidity(cl: dict,
                                 valuation_date: str | None = None,
                                 fund_id: str | None = None,
                                 export_id: str | None = None) -> None:
    """Closed-ended funding-liquidity profile with coverage and stress."""
    coverage_flag = '✓ PASS' if cl['coverage_ratio'] >= 1.0 else '⚠ FAIL'
    stress_flag = ('✓ PASS' if cl['stress_shortfall_eur'] == 0.0
                   else '⚠ FAIL')
    df = pd.DataFrame([
        {'metric': 'Committed capital',
         'value': f"EUR {cl['committed_eur'] / 1e6:,.1f}M", 'note': ''},
        {'metric': 'Drawn capital',
         'value': f"EUR {cl['drawn_eur'] / 1e6:,.1f}M",
         'note': f"{cl['drawn_eur'] / cl['committed_eur']:.1%} of committed"},
        {'metric': 'Unfunded commitments',
         'value': f"EUR {cl['unfunded_eur'] / 1e6:,.1f}M",
         'note': f"{cl['unfunded_eur'] / cl['committed_eur']:.1%} of committed"},
        {'metric': 'Cash balance',
         'value': f"EUR {cl['cash_eur'] / 1e6:,.1f}M", 'note': ''},
        {'metric': 'Sub-line drawn / limit',
         'value': (f"EUR {cl['sub_line_drawn_eur'] / 1e6:,.1f}M / "
                   f"{cl['sub_line_limit_eur'] / 1e6:,.1f}M"),
         'note': f"headroom EUR {cl['sub_line_headroom_eur'] / 1e6:,.1f}M"},
        {'metric': 'Distributions (trailing 12m)',
         'value': f"EUR {cl['distributions_12m_eur'] / 1e6:,.1f}M", 'note': ''},
        {'metric': 'Capital calls (trailing 12m)',
         'value': f"EUR {cl['capital_calls_12m_eur'] / 1e6:,.1f}M",
         'note': 'Investment period ended'},
        {'metric': 'Management fees (trailing 12m)',
         'value': f"EUR {cl['fees_12m_eur'] / 1e6:,.1f}M", 'note': ''},
        {'metric': 'Coverage ratio',
         'value': f"{cl['coverage_ratio']:.2f}x", 'note': coverage_flag},
        {'metric': f"Stress call ({cl['stress_call_pct']:.0%} of unfunded)",
         'value': f"EUR {cl['stress_call_eur'] / 1e6:,.1f}M", 'note': ''},
        {'metric': 'Stress shortfall',
         'value': f"EUR {cl['stress_shortfall_eur'] / 1e6:,.1f}M",
         'note': stress_flag},
    ])
    _show(df, 'Commitments and Funding Liquidity',
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id)


def display_liquidity_buckets(cl: dict,
                              valuation_date: str | None = None,
                              fund_id: str | None = None,
                              export_id: str | None = None) -> None:
    """Closed-ended ESMA liquidity bucket table (assets side)."""
    buckets = cl['liquidity_buckets']
    over_1y = buckets.loc[
        buckets['liquidity_bucket'] == '> 1 year', 'pct_nav_abs'].iloc[0]
    flag = '✓ PASS' if over_1y >= 90 else 'REVIEW'
    _show(
        buckets,
        f'Closed-Ended Liquidity Buckets  |  > 1 year: {over_1y:.1f}% ({flag})',
        fmt={'abs_exposure': '{:,.0f}', 'pct_nav_abs': '{:.1f}%'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Closed-Ended Liquidity Buckets',
    )


def display_pme_summary(pme: dict,
                        valuation_date: str | None = None,
                        fund_id: str | None = None,
                        export_id: str | None = None) -> None:
    """Long-Nickels PME versus the cached public benchmark."""
    flag = ('✓ PE outperforms' if pme['alpha'] and pme['alpha'] > 0
            else '⚠ Public markets outperform')
    df = pd.DataFrame([
        {'metric': 'PE IRR (net, XIRR)', 'value': f"{pme['pe_irr']:.2%}",
         'note': ''},
        {'metric': f"PME IRR ({pme['benchmark']})",
         'value': f"{pme['pme_irr']:.2%}", 'note': ''},
        {'metric': 'Alpha (PE - PME)', 'value': f"{pme['alpha']:+.2%}",
         'note': flag},
        {'metric': 'PME multiple', 'value': f"{pme['pme_multiple']:.2f}x",
         'note': ''},
        {'metric': 'PME terminal NAV',
         'value': f"EUR {pme['pme_terminal_nav'] / 1e6:,.1f}M",
         'note': 'Replicated index portfolio'},
        {'metric': 'Actual PE NAV',
         'value': f"EUR {pme['terminal_nav'] / 1e6:,.1f}M",
         'note': 'At valuation date'},
    ])
    _show(df, f"PME — Long-Nickels ({pme['benchmark']})",
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
          export_name='PME Long Nickels')


def display_stress_by_company(stress: dict,
                              valuation_date: str | None = None,
                              fund_id: str | None = None,
                              export_id: str | None = None) -> None:
    """Scenario NAV impact per active company."""
    _show(
        stress['by_company'],
        'Stress NAV Impact by Company (active portfolio)',
        fmt={c: '{:,.0f}' for c in stress['by_company'].columns
             if c.endswith(('_eur', '_markdown', '_compression', '_stress',
                            '_concentration', '_proxy'))},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Stress NAV Impact by Company',
    )


def display_stress_summary(stress: dict,
                           valuation_date: str | None = None,
                           fund_id: str | None = None,
                           export_id: str | None = None) -> None:
    """Fund-level scenario summary against active NAV."""
    worst = stress['summary']['pct_nav'].min()
    _show(
        stress['summary'],
        f"Fund-Level Stress Summary  |  Base NAV (active): "
        f"EUR {stress['base_nav_eur'] / 1e6:,.1f}M",
        fmt={'delta_nav_eur': '{:,.0f}', 'pct_nav': '{:.1f}%'},
        col_styles={'pct_nav': lambda v: C['red']
                    if isinstance(v, float) and v <= worst else None},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Fund-Level Stress Summary',
    )


def display_bridge_gaps(value_bridge: dict,
                        valuation_date: str | None = None,
                        fund_id: str | None = None,
                        export_id: str | None = None) -> None:
    """Reconciliation gap per company for the value bridge."""
    rows = [{
        'company': r['company_name'],
        'status': 'Realised' if r['is_realised'] else 'Unrealised',
        'gap_eur': r['reconciliation_gap'],
        'gap_pct': (r['reconciliation_gap_pct'] * 100
                    if not np.isnan(r['reconciliation_gap_pct']) else None),
        'material': 'yes' if r['gap_is_material'] else '',
    } for r in value_bridge['rows']]
    _show(
        pd.DataFrame(rows),
        'Value Bridge — Reconciliation Gap by Company',
        fmt={'gap_eur': '{:,.0f}', 'gap_pct': '{:+.1f}%'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Value Bridge Reconciliation Gaps',
    )


# ── plots ───────────────────────────────────────────────────────────────────

def plot_j_curve(j_curve: pd.DataFrame, fund_id: str,
                 valuation_date: str | None = None,
                 export_id: str | None = None):
    """Two-panel J-curve: quarterly flows/CNCF and DPI/RVPI/TVPI."""
    cf = j_curve
    dates = cf.index
    trough_idx = cf['cncf'].idxmin()
    trough_val = cf.loc[trough_idx, 'cncf']

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 9),
        gridspec_kw={'height_ratios': [2, 1]}, sharex=True)

    ax1.plot(dates, cf['nav'], color=ACCENT2, linewidth=1.4,
             linestyle=':', label='NAV (unrealised)')
    ax1.bar(dates, -cf['capital_called'], width=60, color=C['red'],
            alpha=0.75, label='Capital called')
    ax1.bar(dates, -cf['mgmt_fees'], width=60, color=C['amber'], alpha=0.65,
            bottom=-cf['capital_called'], label='Management fees')
    ax1.bar(dates, cf['distributions'], width=60, color=C['green'],
            alpha=0.75, label='Distributions')
    ax1.plot(dates, cf['cncf'], color='white', linewidth=2.2, marker='o',
             markersize=3.5, label='Cumulative NCF')
    ax1.axhline(0, color=C['dim'], linewidth=0.8, linestyle='--')
    ax1.annotate(
        f'Trough\n{trough_idx.strftime("%b %Y")}\n{trough_val / 1e6:.1f}M',
        xy=(trough_idx, trough_val), xytext=(trough_idx, trough_val * 0.6),
        arrowprops=dict(arrowstyle='->', color=C['red']),
        fontsize=FONT['small'], color=C['red'], ha='center')
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x / 1e6:.0f}M'))
    ax1.set_ylabel('EUR')
    section_title(ax1, 'J-Curve — Quarterly Cash Flows and Cumulative NCF')
    ax1.legend(loc='upper left', fontsize=FONT['small'])

    ax2.plot(dates, cf['tvpi'], color='white', linewidth=2, label='TVPI')
    ax2.plot(dates, cf['dpi'], color=C['green'], linewidth=1.6,
             linestyle='--', label='DPI')
    ax2.plot(dates, cf['rvpi'], color=ACCENT, linewidth=1.6,
             linestyle=':', label='RVPI')
    ax2.axhline(1.0, color=C['dim'], linewidth=0.8, linestyle='--')
    ax2.set_ylabel('Multiple (x)')
    ax2.legend(loc='upper left', fontsize=FONT['small'])
    apply_ax_style(ax2)
    ax2.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.1f}x'))

    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'PE J curve')
    plt.show()



def plot_exit_waterfalls(exit_waterfalls: list, fund_id: str,
                         valuation_date: str | None = None,
                         export_id: str | None = None):
    """European waterfall allocation per realised exit."""
    import matplotlib.patches as mpatches

    lp_color, gp_color = C['blue2'], C['green']
    fig, axes = plt.subplots(1, len(exit_waterfalls), figsize=(16, 8))
    if len(exit_waterfalls) == 1:
        axes = [axes]

    for ax, wf in zip(axes, exit_waterfalls):
        bottom = 0.0
        for i, step in enumerate(wf['steps']):
            color = lp_color if step['party'] == 'LP' else gp_color
            ax.bar(i, step['amount_eur'], bottom=bottom, color=color,
                   alpha=0.85, width=0.6)
            ax.text(i, bottom + step['amount_eur'] / 2,
                    f"{step['amount_eur'] / 1e6:.1f}M", ha='center',
                    va='center', fontsize=FONT['small'], color='white',
                    fontweight='bold')
            bottom += step['amount_eur']
        gross = wf['gross_exit_value_eur']
        ax.axhline(gross, color='white', linewidth=1.2, linestyle='--',
                   alpha=0.6)
        ax.text(len(wf['steps']) - 0.4, gross,
                f'Gross\n{gross / 1e6:.1f}M', fontsize=FONT['small'],
                va='bottom', color='white')
        ax.set_xticks(range(len(wf['steps'])))
        ax.set_xticklabels(
            [s['label'].replace(' ', '\n', 1) for s in wf['steps']],
            fontsize=FONT['small'])
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda v, _: f'{v / 1e6:.0f}M'))
        section_title(ax, f"{wf['company_name']} | {wf['exit_date']}")

    fig.legend(handles=[
        mpatches.Patch(color=lp_color, alpha=0.85, label='LP'),
        mpatches.Patch(color=gp_color, alpha=0.85, label='GP'),
    ], loc='upper right', fontsize=FONT['body'])
    sup_title(fig, 'European Waterfall — Exit Proceeds Distribution')
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'European waterfall')
    plt.show()



def plot_cash_management(cash_summary: pd.DataFrame, fund_id: str,
                         valuation_date: str | None = None,
                         export_id: str | None = None):
    """Cash reserve, subscription line, net cash, and interest series."""
    df = cash_summary
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 11), sharex=True)

    ax1.bar(df['date'], df['cash_balance_eur'] / 1e6, width=60, color=ACCENT,
            alpha=0.7, label='Cash reserve')
    ax1.plot(df['date'], df['sub_line_drawn'] / 1e6, color=C['amber'],
             linewidth=2, marker='o', markersize=4, label='Sub line drawn')
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.0f}M'))
    ax1.set_ylabel('EUR M')
    section_title(ax1, 'Fund Cash Management')
    ax1.legend(fontsize=FONT['small'])

    colors = [C['green'] if v >= 0 else C['red']
              for v in df['net_cash_position']]
    ax2.bar(df['date'], df['net_cash_position'] / 1e6, width=60,
            color=colors, alpha=0.8)
    ax2.axhline(0, color=C['dim'], linewidth=0.8, linestyle='--')
    ax2.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.0f}M'))
    ax2.set_ylabel('EUR M')
    section_title(ax2, 'Net Cash Position (Cash reserve - Sub line)')

    ax3.plot(df['date'], df['cumulative_interest_earned'] / 1e6,
             color=C['green'], linewidth=2, label='Cumulative interest earned')
    ax3.plot(df['date'], df['cumulative_interest_paid'] / 1e6,
             color=C['red'], linewidth=2, linestyle='--',
             label='Cumulative interest paid')
    ax3.fill_between(df['date'],
                     df['cumulative_interest_earned'] / 1e6,
                     df['cumulative_interest_paid'] / 1e6,
                     alpha=0.15, color=C['green'], label='Net benefit')
    ax3.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.1f}M'))
    ax3.set_ylabel('EUR M')
    ax3.set_xlabel('Quarter')
    section_title(ax3, 'Cumulative Interest: Earned vs Paid')
    ax3.legend(fontsize=FONT['small'])

    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'Fund cash management')
    plt.show()



_GAP_THRESHOLD = 0.05


def _bridge_waterfall_chart(row: dict, ax: plt.Axes) -> None:
    """Single value-bridge waterfall (display-only reshaping)."""
    components = [
        ('Entry equity', row['entry_equity_value'], C['cyan']),
        ('EBITDA growth', row['ebitda_growth'], C['blue2']),
        ('Multiple expansion', row['multiple_expansion'], C['blue2']),
        ('Leverage effect', row['leverage_effect'], C['blue2']),
        ('Distributions', row['distributions'], C['blue2']),
    ]
    gap_pct = row['reconciliation_gap_pct']
    gap_material = not np.isnan(gap_pct) and abs(gap_pct) > _GAP_THRESHOLD
    components.append(('Recon. gap', row['reconciliation_gap'],
                       C['red'] if gap_material else C['border']))

    labels, heights, bottoms, colors = [], [], [], []
    running = 0.0
    for i, (label, value, color) in enumerate(components):
        bottoms.append(0.0 if i == 0 else running)
        running = value if i == 0 else running + value
        labels.append(label.replace(' ', '\n', 1))
        heights.append(value)
        colors.append(color)
    labels.append('Exit\nequity' if row['is_realised'] else 'Current\nNAV')
    heights.append(running)
    bottoms.append(0.0)
    colors.append(C['cyan'])

    x = np.arange(len(labels))
    for i in range(len(labels)):
        h, b = heights[i], bottoms[i]
        ax.bar(x[i], abs(h) / 1e6,
               bottom=b / 1e6 if h >= 0 else (b + h) / 1e6,
               color=colors[i], width=0.6, linewidth=0)
        ax.text(x[i], (b + h / 2) / 1e6, f'{h / 1e6:+.1f}M',
                ha='center', va='center', fontsize=7, color='white',
                fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel('EUR (MM)')
    ax.axhline(0, color='white', linewidth=0.5, linestyle='--')
    suffix = ' [REALISED]' if row['is_realised'] else ' [UNREALISED]'
    section_title(ax, f"{row['company_name']}{suffix}", fontsize=10)


def plot_value_bridge_by_company(value_bridge: dict, fund_id: str,
                                 valuation_date: str | None = None,
                                 export_id: str | None = None):
    """Grid of per-company value-bridge waterfalls."""
    rows = value_bridge['rows']
    n = len(rows)
    ncols = 2
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(10, 3.4 * nrows))
    axes = np.array(axes).flatten()
    for i, row in enumerate(rows):
        _bridge_waterfall_chart(row, axes[i])
    for j in range(n, len(axes)):
        axes[j].set_visible(False)
    sup_title(fig, 'Return Attribution — Value Bridge by Company')
    plt.tight_layout()
    plt.subplots_adjust(hspace=0.45, top=0.93)
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'Value bridge by company')
    plt.show()



def plot_value_bridge_fund(value_bridge: dict, fund_id: str,
                           valuation_date: str | None = None,
                           export_id: str | None = None):
    """Fund-level value-bridge waterfall."""
    rows = value_bridge['rows']
    ft = value_bridge['fund_totals']
    av = ft['actual_value_created_eur']
    gap_pct = ft['reconciliation_gap_eur'] / av if av else float('nan')
    fig, ax = plt.subplots(figsize=(10, 5))
    _bridge_waterfall_chart({
        'company_name': 'Fund Total',
        'is_realised': all(r['is_realised'] for r in rows),
        'entry_equity_value': ft['total_cost_basis'],
        'ebitda_growth': ft['ebitda_growth_eur'],
        'multiple_expansion': ft['multiple_expansion_eur'],
        'leverage_effect': ft['leverage_effect_eur'],
        'distributions': ft['distributions_eur'],
        'reconciliation_gap': ft['reconciliation_gap_eur'],
        'reconciliation_gap_pct': gap_pct,
    }, ax)
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'Fund level value bridge')
    plt.show()



def plot_pme(pme: dict, fund_id: str,
             valuation_date: str | None = None,
             export_id: str | None = None):
    """PE IRR vs PME IRR vs alpha bar view."""
    fig, ax = plt.subplots(figsize=(5.5, 2.6))
    labels = ['PE IRR\n(net)', f"PME IRR\n({pme['benchmark'].split()[0]})",
              'Alpha\n(PE - PME)']
    values = [pme['pe_irr'] * 100, pme['pme_irr'] * 100, pme['alpha'] * 100]
    colors = [ACCENT, ACCENT2,
              C['green'] if pme['alpha'] > 0 else C['red']]
    bars = ax.bar(labels, values, color=colors, alpha=0.85, width=0.45)
    ax.axhline(0, color='white', linewidth=0.8, linestyle='--')
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() / 2 + (0.3 if val >= 0 else -0.6),
                f'{val:+.2f}%', ha='center', fontsize=FONT['small'],
                fontweight='bold', color='white')
    ax.set_ylabel('Annual return (%)')
    section_title(ax, 'PE vs Public Market Equivalent — Long-Nickels')
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'PME comparison')
    plt.show()



def plot_stress_summary(stress: dict, fund_id: str,
                        valuation_date: str | None = None,
                        export_id: str | None = None):
    """Fund-level stress scenario bar view."""
    summary = stress['summary']
    base_m = stress['base_nav_eur'] / 1e6
    labels = [s.split(' — ', 1)[-1].replace(' ', '\n', 1)
              for s in summary['scenario']]
    deltas_m = summary['delta_nav_eur'] / 1e6
    pcts = summary['pct_nav']

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.bar(labels, deltas_m, color=C['red'], alpha=0.85, width=0.5)
    ax.axhline(0, color=C['dim'], lw=0.8)
    ax.set_ylabel('ΔNAV (EUR M)')
    for bar, val, pct in zip(bars, deltas_m, pcts):
        cx = bar.get_x() + bar.get_width() / 2
        ax.text(cx, val / 2, f'{pct:.1f}%', ha='center', va='center',
                fontsize=FONT['body'], color='white', fontweight='bold')
        ax.text(cx, val - 8, f'{val:,.1f}M', ha='center', va='top',
                fontsize=FONT['small'], color='white')
    sup_title(fig,
              f'PE Stress Testing — Base NAV (active): EUR {base_m:,.1f}M')
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'PE stress summary')
    plt.show()
    
