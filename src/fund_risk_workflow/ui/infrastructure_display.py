"""
Infrastructure display helpers.

Renders infrastructure workflow results as dark HTML tables and
shared-style plots, including the covenant monitor with inline
sparklines. Display-only reshaping and formatting; no business
calculation belongs here.
"""

import base64
import io

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
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

SECTOR_COLORS = {'Utilities': C['blue2'], 'Transport': C['cyan'],
                 'Energy': C['green'], 'Social': C['purple']}


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


def _sparkline(values: list, breaches: list | None = None) -> str:
    """Small inline trend image as an HTML <img> data URI."""
    fig, ax = plt.subplots(figsize=(1.8, 0.4))
    x = range(len(values))
    ax.plot(x, values, color=ACCENT, lw=1.2)
    ax.scatter(x, values, color=ACCENT, s=12, zorder=5)
    if breaches is not None:
        for i, is_breach in enumerate(breaches):
            if is_breach:
                ax.scatter(i, values[i], color=C['red'], s=20, zorder=6)
    ax.axis('off')
    fig.patch.set_alpha(0)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=80, bbox_inches='tight',
                facecolor='none', transparent=True)
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode()
    return (f'<img src="data:image/png;base64,{encoded}" '
            f'style="height:30px;vertical-align:middle;">')


# ── tables ──────────────────────────────────────────────────────────────────

def display_fund_metadata(portfolio_overview: dict,
                          valuation_date: str | None = None,
                          fund_id: str | None = None,
                          export_id: str | None = None) -> None:
    """Fund structure metadata."""
    _show(portfolio_overview['fund_metadata'], 'Fund Structure',
          valuation_date=valuation_date, fund_id=fund_id,
          export_id=export_id)


def display_asset_portfolio(portfolio_overview: dict,
                            valuation_date: str | None = None,
                            fund_id: str | None = None,
                            export_id: str | None = None) -> None:
    """Asset-level portfolio table with appraised equity and NAV weight."""
    _show(
        portfolio_overview['assets'],
        'Asset Portfolio (independent appraisals)',
        fmt={'ownership_pct': '{:.1f}%', 'drawn_equity_eur': '{:,.0f}',
             'appraised_equity_eur': '{:,.0f}', 'nav_pct': '{:.1f}%'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Asset Portfolio',
    )


def display_discount_rate_movement(dr_df: pd.DataFrame,
                                   fund_id: str | None = None,
                                   export_id: str | None = None) -> None:
    """Quarter-on-quarter appraiser discount-rate movement."""
    threshold = dr_df.attrs.get('flag_threshold_bps', 50)
    n_flagged = int(dr_df['flagged'].sum())
    status = (f'⚠ {n_flagged} asset(s) flagged'
              if n_flagged else '✓ no movements beyond threshold')
    df = dr_df.copy()
    df['flagged'] = df['flagged'].map(lambda x: '⚠ YES' if x else '—')
    _show(
        df,
        f'Appraiser Discount Rate Movement (QoQ)  |  '
        f'Flag threshold: {threshold:.0f}bps  |  {status}',
        fmt={'dr_prev': '{:.2%}', 'dr_curr': '{:.2%}',
             'dr_chg_bps': '{:+.0f}', 'inflation_assumption': '{:.2%}'},
        valuation_date=dr_df.attrs.get('quarter'),
        fund_id=fund_id, export_id=export_id,
        export_name='Discount Rate Movement',
    )


def display_performance(performance: dict,
                        valuation_date: str | None = None,
                        fund_id: str | None = None,
                        export_id: str | None = None) -> None:
    """Fund multiples and IRR versus the policy benchmark."""
    mult = performance['multiples']
    flag = ('✓ above target' if performance['irr_vs_target'] >= 0
            else '⚠ below target')
    df = pd.DataFrame([
        {'metric': 'Drawn capital',
         'value': f"EUR {mult['drawn_capital'] / 1e6:,.1f}M", 'note': ''},
        {'metric': 'Distributions',
         'value': f"EUR {mult['distributions'] / 1e6:,.1f}M", 'note': ''},
        {'metric': 'Current NAV',
         'value': f"EUR {mult['nav'] / 1e6:,.1f}M", 'note': ''},
        {'metric': 'DPI', 'value': f"{mult['dpi']:.2f}x",
         'note': 'Realised return'},
        {'metric': 'RVPI', 'value': f"{mult['rvpi']:.2f}x",
         'note': 'Unrealised return'},
        {'metric': 'MOIC', 'value': f"{mult['moic']:.2f}x",
         'note': 'DPI + RVPI'},
        {'metric': 'Fund IRR (net, XIRR)',
         'value': f"{performance['irr']:.2%}", 'note': ''},
        {'metric': (f"Benchmark (CPI {performance['cpi_assumption']:.1%} + "
                    f"{performance['benchmark_spread_bps']:.0f}bps)"),
         'value': f"{performance['target_irr']:.2%}", 'note': ''},
        {'metric': 'IRR vs benchmark',
         'value': f"{performance['irr_vs_target']:+.2%}", 'note': flag},
    ])
    _show(df, 'Performance Metrics',
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id)


def display_covenant_monitor(monitor_df: pd.DataFrame, metric_label: str,
                             valuation_date: str | None = None,
                             fund_id: str | None = None,
                             export_id: str | None = None) -> None:
    """Per-asset covenant monitor with inline trend sparklines."""
    df = monitor_df.copy()
    df['last_quarters'] = [
        _sparkline(h, b) for h, b in zip(df['history'], df['breach_history'])]
    df = df.drop(columns=['history', 'breach_history'])
    df['trend'] = df['trend'].map(
        {'improving': '↑', 'deteriorating': '↓', 'stable': '→'}).fillna('·')
    df['waiver'] = df['waiver'].map(lambda x: '⚠' if x else '—')
    df['status'] = df['status'].map(
        {'Breach': '🔴 Breach', 'Watch': '🟡 Watch', 'OK': '🟢 OK'})
    df['breach_count'] = df['breach_count'].map(
        lambda x: str(x) if x else '—')
    df = df[['asset_name', 'actual', 'covenant', 'last_quarters',
             'headroom', 'headroom_pct', 'breach_count', 'trend',
             'waiver', 'status']]
    _show(
        df,
        f'{metric_label} Covenant Monitor',
        fmt={'actual': '{:.2f}x', 'covenant': '{:.2f}x',
             'headroom': '{:+.2f}', 'headroom_pct': '{:+.1f}%'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name=f'{metric_label} Covenant Monitor',
    )


def display_sector_concentration(concentration: dict,
                                 valuation_date: str | None = None,
                                 fund_id: str | None = None,
                                 export_id: str | None = None) -> None:
    """Sector concentration versus the internal 40% NAV threshold."""
    sector = concentration['sector'].copy()
    n_breaches = int(sector['concentrated'].sum())
    status = (f'⚠ {n_breaches} sector(s) above limit'
              if n_breaches else '✓ within limit')
    sector['concentrated'] = sector['concentrated'].map(
        lambda x: '⚠ BREACH' if x else '—')
    _show(
        sector,
        f'Sector Concentration  |  Limit: 40% NAV  |  {status}',
        fmt={'nav_eur': '{:,.0f}', 'nav_pct': '{:.1f}%'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Sector Concentration',
    )


def display_inflation_summary(inflation: dict,
                              valuation_date: str | None = None,
                              fund_id: str | None = None,
                              export_id: str | None = None) -> None:
    """Portfolio inflation-linkage summary."""
    df = pd.DataFrame([
        {'metric': 'Weighted avg. inflation linkage',
         'value': f"{inflation['weighted_avg_linkage']:.1%}",
         'description': 'NAV-weighted average across assets'},
        {'metric': '% fully CPI-linked',
         'value': f"{inflation['pct_fully_linked']:.1f}%",
         'description': 'Regulated tariffs or full CPI pass-through'},
        {'metric': '% partially linked',
         'value': f"{inflation['pct_partially_linked']:.1f}%",
         'description': 'Partial indexation or price review mechanism'},
        {'metric': '% unlinked',
         'value': f"{inflation['pct_unlinked']:.1f}%",
         'description': 'Fixed-fee or merchant exposure'},
    ])
    _show(df, 'Inflation Sensitivity Summary',
          valuation_date=valuation_date, fund_id=fund_id, export_id=export_id)


def display_duration_profile(duration_df: pd.DataFrame,
                             valuation_date: str | None = None,
                             fund_id: str | None = None,
                             export_id: str | None = None) -> None:
    """Concession duration profile with near-expiry flags."""
    wav = duration_df.attrs.get('weighted_avg_remaining_years')
    df = duration_df[['asset_name', 'concession_end', 'remaining_years',
                      'nav_weight', 'near_expiry']].copy()
    df['nav_weight'] = df['nav_weight'] * 100
    df['near_expiry'] = df['near_expiry'].map(lambda x: '⚠ YES' if x else '—')
    _show(
        df,
        f'Concession Duration Profile  |  Weighted avg: {wav:.1f} years',
        fmt={'remaining_years': '{:.1f}', 'nav_weight': '{:.1f}%'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Concession Duration Profile',
    )


def display_stress_summary(stress: dict,
                           valuation_date: str | None = None,
                           fund_id: str | None = None,
                           export_id: str | None = None) -> None:
    """NAV stress scenario summary table."""
    worst = stress['summary']['nav_change_pct'].min()
    _show(
        stress['summary'],
        'NAV Stress Scenarios (valuation-input stress)',
        fmt={'base_nav_eur': '{:,.0f}', 'stressed_nav_eur': '{:,.0f}',
             'nav_change_eur': '{:,.0f}', 'nav_change_pct': '{:+.2f}%'},
        col_styles={'nav_change_pct': lambda v: C['red']
                    if isinstance(v, float) and v <= worst else None},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='NAV Stress Scenarios',
    )


def display_asset_stress_detail(stress: dict, scenario_name: str,
                                valuation_date: str | None = None,
                                fund_id: str | None = None,
                                export_id: str | None = None) -> None:
    """Asset-level impact for one stress scenario."""
    res = stress['results'][scenario_name]
    detail = res['asset_detail'].copy()
    detail['nav_change_pct'] = detail['nav_change'] / detail['base_nav'] * 100
    detail = detail.drop(columns=['asset_id']).sort_values('nav_change')
    _show(
        detail,
        f'Asset-Level Stress Impact  |  {scenario_name}',
        fmt={'base_nav': '{:,.0f}', 'stressed_nav': '{:,.0f}',
             'nav_change': '{:+,.0f}', 'nav_change_pct': '{:+.1f}%'},
        valuation_date=valuation_date, fund_id=fund_id, export_id=export_id,
        export_name='Asset-Level Stress Impact',
    )


# ── plots ───────────────────────────────────────────────────────────────────

def plot_nav_timeseries(nav_ts: pd.DataFrame, fund_id: str,
                        valuation_date: str | None = None,
                        export_id: str | None = None):
    """Fund NAV quarterly time series."""
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(nav_ts['date'], nav_ts['nav_eur'] / 1e6, color=ACCENT,
            linewidth=2, marker='o', markersize=4)
    ax.fill_between(nav_ts['date'], nav_ts['nav_eur'] / 1e6, alpha=0.12,
                    color=ACCENT)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:,.0f}M'))
    ax.set_ylabel('EUR')
    section_title(ax, 'Fund NAV — Quarterly Timeseries')
    apply_ax_style(ax)
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'NAV timeseries')
    plt.show()


def plot_nav_by_asset(asset_breakdown: pd.DataFrame, fund_id: str,
                      valuation_date: str | None = None,
                      export_id: str | None = None):
    """NAV contribution by asset, coloured by sector."""
    colors = [SECTOR_COLORS.get(s, C['dim'])
              for s in asset_breakdown['sector']]
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.barh(asset_breakdown['asset_name'],
                   asset_breakdown['nav_eur'] / 1e6,
                   color=colors, alpha=0.85, height=0.6)
    for bar, pct in zip(bars, asset_breakdown['nav_pct']):
        ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2,
                f'{pct:.1f}%', va='center', fontsize=FONT['small'],
                color=C['muted'])
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:,.0f}M'))
    section_title(ax, 'NAV by Asset')
    apply_ax_style(ax, grid_axis='x')
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c, label=s)
                       for s, c in SECTOR_COLORS.items()],
              fontsize=FONT['small'], loc='upper right')
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'NAV by asset')
    plt.show()


def plot_moic_decomposition(performance: dict, fund_id: str,
                            valuation_date: str | None = None,
                            export_id: str | None = None):
    """DPI vs RVPI decomposition of MOIC."""
    mult = performance['multiples']
    fig, ax = plt.subplots(figsize=(4.2, 2.6))
    components = {'DPI\n(realised)': mult['dpi'],
                  'RVPI\n(unrealised)': mult['rvpi']}
    bars = ax.bar(components.keys(), components.values(),
                  color=ACCENT, alpha=0.85, width=0.4)
    ax.axhline(1.0, color='white', linewidth=1, linestyle='--', alpha=0.6,
               label='Cost (1.0x)')
    for bar, val in zip(bars, components.values()):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.08,
                f'{val:.2f}x', ha='center', fontsize=FONT['small'],
                color='white', fontweight='bold')
    ax.set_ylabel('Multiple (x)')
    ax.set_ylim(0, max(mult['moic'] * 1.15, 1.3))
    section_title(ax, 'MOIC Decomposition')
    apply_ax_style(ax)
    ax.legend(fontsize=FONT['small'])
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'MOIC decomposition')
    plt.show()


def plot_concentration(concentration: dict, fund_id: str,
                       valuation_date: str | None = None,
                       export_id: str | None = None):
    """Country, sub-type, and sector concentration panels."""
    country = concentration['country']
    subtype = concentration['sub_type']
    sector = concentration['sector']

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 4))

    bars1 = ax1.bar(country['country'], country['nav_pct'], color=ACCENT,
                    alpha=0.85, width=0.5)
    for bar, pct in zip(bars1, country['nav_pct']):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 f'{pct:.1f}%', ha='center', fontsize=FONT['small'],
                 color=C['muted'])
    ax1.set_ylabel('% NAV')
    section_title(ax1, 'Country Concentration')
    apply_ax_style(ax1)

    bars2 = ax2.barh(subtype['sub_type'], subtype['nav_pct'], color=ACCENT,
                     alpha=0.85, height=0.5)
    for bar, pct in zip(bars2, subtype['nav_pct']):
        ax2.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                 f'{pct:.1f}%', va='center', fontsize=FONT['small'],
                 color=C['muted'])
    ax2.set_xlabel('% NAV')
    section_title(ax2, 'Sub-type Mix')
    apply_ax_style(ax2, grid_axis='x')

    bar_colors = [C['red'] if c else ACCENT for c in sector['concentrated']]
    bars3 = ax3.barh(sector['sector'], sector['nav_pct'], color=bar_colors,
                     alpha=0.85, height=0.5)
    ax3.axvline(40.0, color=C['red'], linewidth=1, linestyle='--')
    ax3.text(40.5, 0.98, '40% limit', color=C['red'], fontsize=FONT['small'],
             va='top', transform=ax3.get_xaxis_transform())
    for bar, pct in zip(bars3, sector['nav_pct']):
        ax3.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                 f'{pct:.1f}%', va='center', fontsize=FONT['small'],
                 color=C['muted'])
    ax3.set_xlabel('% NAV')
    ax3.set_xlim(0, max(sector['nav_pct'].max() * 1.2, 50))
    section_title(ax3, 'Sector Concentration')
    apply_ax_style(ax3, grid_axis='x')

    sup_title(fig, 'Concentration — Country, Sub-type and Sector')
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id,
                    'Concentration country subtype sector')
    plt.show()


def plot_inflation_linkage(inflation: dict, fund_id: str,
                           valuation_date: str | None = None,
                           export_id: str | None = None):
    """Per-asset inflation linkage and linkage mix."""
    ad = pd.DataFrame(inflation['asset_detail']).sort_values(
        'inflation_linkage', ascending=False)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4))

    bar_colors = [ACCENT if v >= 0.75 else ACCENT2 if v >= 0.40 else C['red']
                  for v in ad['inflation_linkage']]
    bars = ax1.barh(ad['asset_name'], ad['inflation_linkage'] * 100,
                    color=bar_colors, alpha=0.85, height=0.55)
    ax1.axvline(75, color=ACCENT, linewidth=1, linestyle='--', alpha=0.6,
                label='Fully linked (75%)')
    ax1.axvline(40, color=ACCENT2, linewidth=1, linestyle='--', alpha=0.6,
                label='Partial threshold (40%)')
    for bar, v in zip(bars, ad['inflation_linkage']):
        ax1.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                 f'{v:.0%}', va='center', fontsize=FONT['small'],
                 color=C['muted'])
    ax1.set_xlabel('Inflation linkage (%)')
    ax1.set_xlim(0, 115)
    section_title(ax1, 'Inflation Linkage by Asset')
    apply_ax_style(ax1, grid_axis='x')
    ax1.legend(fontsize=FONT['small'])

    sizes = [inflation['pct_fully_linked'],
             inflation['pct_partially_linked'], inflation['pct_unlinked']]
    labels = ['Fully linked', 'Partially linked', 'Unlinked']
    clrs = [ACCENT, ACCENT2, C['muted']]
    non_zero = [(s, l, c) for s, l, c in zip(sizes, labels, clrs) if s > 0]
    if non_zero:
        s, l, c = zip(*non_zero)
        _, _, autotexts = ax2.pie(
            s, labels=l, colors=c, autopct='%1.1f%%', startangle=90,
            pctdistance=0.7, wedgeprops=dict(width=0.7),
            textprops={'color': C['muted'], 'fontsize': FONT['body']})
        for t in autotexts:
            t.set_fontsize(FONT['small'])
            t.set_color('white')
    section_title(ax2, 'Linkage Mix (% NAV)')

    sup_title(fig,
              f'Inflation Sensitivity  |  Weighted avg. linkage: '
              f'{inflation["weighted_avg_linkage"]:.1%}')
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'Inflation sensitivity')
    plt.show()


def plot_duration_profile(duration_df: pd.DataFrame, fund_id: str,
                          valuation_date: str | None = None,
                          export_id: str | None = None):
    """Remaining concession life per asset."""
    wav = duration_df.attrs.get('weighted_avg_remaining_years')
    dur_sorted = duration_df.sort_values('remaining_years')
    bar_colors = [C['red'] if x else ACCENT
                  for x in dur_sorted['near_expiry']]
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(dur_sorted['asset_name'], dur_sorted['remaining_years'],
                   color=bar_colors, alpha=0.85, height=0.55)
    ax.axvline(3, color=C['red'], linewidth=1.5, linestyle='--', alpha=0.7,
               label='3-year expiry flag')
    ax.axvline(wav, color='white', linewidth=1.5, linestyle=':', alpha=0.7,
               label=f'Weighted avg ({wav:.1f} yrs)')
    for bar, yrs in zip(bars, dur_sorted['remaining_years']):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f'{yrs:.1f} yrs', va='center', fontsize=FONT['small'],
                color=C['muted'])
    ax.set_xlabel('Remaining concession life (years)')
    section_title(ax, 'Concession Duration Profile')
    apply_ax_style(ax, grid_axis='x')
    ax.legend(fontsize=FONT['small'])
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'Concession duration profile')
    plt.show()


def plot_infra_j_curve(cashflow_profile: pd.DataFrame, fund_id: str,
                       valuation_date: str | None = None,
                       export_id: str | None = None):
    """Quarterly capital calls, fees, distributions, CNCF, and DPI."""
    cf = cashflow_profile
    trough_idx = cf['cncf'].idxmin()
    trough_val = cf.loc[trough_idx, 'cncf']

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6),
                                   gridspec_kw={'height_ratios': [2, 1]},
                                   sharex=True)
    ax1.bar(cf.index, -cf['calls'], width=60, color=C['red'], alpha=0.75,
            label='Capital calls')
    ax1.bar(cf.index, -cf['fees'], width=60, color=C['amber'], alpha=0.65,
            bottom=-cf['calls'], label='Management fees')
    ax1.bar(cf.index, cf['distributions'], width=60, color=C['green'],
            alpha=0.75, label='Distributions')
    ax1.plot(cf.index, cf['cncf'], color='white', linewidth=2.2, marker='o',
             markersize=3.5, label='Cumulative NCF')
    ax1.axhline(0, color=C['dim'], linewidth=0.8, linestyle='--')
    ax1.annotate(
        f'Trough\n{trough_idx.strftime("%b %Y")}\n{trough_val / 1e6:.0f}M',
        xy=(trough_idx, trough_val), xytext=(trough_idx, trough_val * 0.65),
        arrowprops=dict(arrowstyle='->', color=C['red']),
        fontsize=FONT['small'], color=C['red'], ha='center')
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x / 1e6:.0f}M'))
    ax1.set_ylabel('EUR')
    section_title(ax1, 'Infrastructure J-Curve')
    ax1.legend(fontsize=FONT['small'], loc='lower left')
    apply_ax_style(ax1)

    ax2.plot(cf.index, cf['dpi'], color=ACCENT, linewidth=2,
             label='DPI (distributions / called)')
    ax2.axhline(1.0, color=C['dim'], linewidth=0.8, linestyle='--')
    ax2.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.2f}x'))
    ax2.set_ylabel('DPI (x)')
    ax2.legend(fontsize=FONT['small'], loc='upper left')
    apply_ax_style(ax2)

    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'Infrastructure J curve')
    plt.show()


def plot_cashflow_coverage(coverage: pd.DataFrame, fund_id: str,
                           valuation_date: str | None = None,
                           export_id: str | None = None):
    """Distributions vs management fees with the coverage ratio."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax_right = ax.twinx()

    ax.bar(coverage['date'], coverage['distributions'] / 1e6, width=60,
           color=C['green'], alpha=0.7, label='Distributions')
    ax.bar(coverage['date'], coverage['management_fees'] / 1e6, width=60,
           color=C['amber'], alpha=0.85, label='Management fees',
           bottom=coverage['distributions'] / 1e6)

    cov_valid = coverage[coverage['coverage_ratio'] > 0]
    ax_right.plot(cov_valid['date'], cov_valid['coverage_ratio'],
                  color='white', linewidth=2, marker='o', markersize=3.5,
                  label='Coverage ratio (right)')
    ax_right.axhline(1.0, color=C['red'], linewidth=1.2, linestyle='--',
                     alpha=0.7)

    ax.set_ylabel('EUR M')
    ax_right.set_ylabel('Coverage ratio (x)')
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f'{x:.0f}M'))
    section_title(ax, 'Cashflow Coverage — Distributions vs Fees')
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax_right.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=FONT['small'],
              loc='upper left')
    apply_ax_style(ax)
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'Cashflow coverage')
    plt.show()


def plot_stress_impact(stress: dict, fund_id: str,
                       valuation_date: str | None = None,
                       export_id: str | None = None):
    """Fund-level NAV impact per stress scenario."""
    summary = stress['summary']
    impacts = summary['nav_change_pct']
    colors = [C['red'] if v < 0 else C['green'] for v in impacts]
    fig, ax = plt.subplots(figsize=(7, 2.6))
    bars = ax.barh(summary['scenario'], impacts, color=colors, alpha=0.85,
                   height=0.45)
    ax.axvline(0, color='white', linewidth=0.8)
    ax.set_xlim(min(impacts) * 1.15, 1)
    for bar, val in zip(bars, impacts):
        ax.text(bar.get_width() - 0.3, bar.get_y() + bar.get_height() / 2,
                f'{val:+.1f}%', va='center', ha='right',
                fontsize=FONT['small'], fontweight='bold', color='white')
    ax.set_xlabel('NAV change (%)')
    section_title(ax, 'Stress Impact on Fund NAV')
    apply_ax_style(ax, grid_axis='x')
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'Stress impact fund NAV')
    plt.show()


def plot_asset_stress_detail(stress: dict, scenario_name: str, fund_id: str,
                             valuation_date: str | None = None,
                             export_id: str | None = None):
    """Asset-level NAV impact for one scenario."""
    res = stress['results'][scenario_name]
    detail = res['asset_detail'].copy()
    detail['nav_change_pct'] = detail['nav_change'] / detail['base_nav'] * 100
    detail = detail.sort_values('nav_change')

    fig, ax = plt.subplots(figsize=(9, 5))
    pcts = detail['nav_change_pct']
    bars = ax.barh(detail['asset_name'], pcts, color=C['red'], alpha=0.80,
                   height=0.55)
    for bar, val in zip(bars, pcts):
        ax.text(bar.get_width() - 0.3, bar.get_y() + bar.get_height() / 2,
                f'{val:+.2f}%', va='center', ha='right',
                fontsize=FONT['small'], fontweight='bold', color='white')
    ax.axvline(0, color='white', linewidth=0.8)
    ax.set_xlabel('NAV change (%)')
    ax.set_xlim(min(pcts) * 1.1, 0)
    section_title(ax, f'Asset-Level Stress Impact  |  {scenario_name}')
    apply_ax_style(ax, grid_axis='x')
    plt.tight_layout()
    if export_id is not None:
        _export_fig(fig, fund_id, export_id, 'Asset level stress impact')
    plt.show()
