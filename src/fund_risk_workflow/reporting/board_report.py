"""
src/board_report.py
===================
Monthly Board Risk Report — AIFM internal governance document.

Produces a multi-page PDF suitable for distribution to the Board and
Risk Committee under AIFMD Art. 15. This is NOT the Annex IV
regulatory submission to the CSSF; it is the internal governance record
that demonstrates the Board is actively receiving and reviewing risk
information (the document CSSF inspects).

Usage
-----
    from fund_risk_workflow.reporting.board_report import generate_board_report
    from fund_risk_workflow.data.database import get_engine
    path = generate_board_report(get_engine(), valuation_date='2026-03-31')

    # or standalone:
    python -m src.board_report
"""


import os
import warnings
from datetime import datetime
from typing import Dict, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

from fund_risk_workflow.data.database import get_engine, query_nav_history
from fund_risk_workflow.data.enrichment import get_risk_ready_df
from fund_risk_workflow.risk.risk_utils import (
    HISTORICAL_SCENARIOS,
    var_historical, var_scale, es_historical, es_scale,
    stress_equity, stress_rates, stress_credit,
    stress_combined, stress_historical, stress_property, stress_rental,
    compute_liquidity_profile,
)

warnings.filterwarnings('ignore')

from fund_risk_workflow.config import LIQUIDITY_BUCKET_ORDER
from fund_risk_workflow.ui.plot_style import C,  FUND_COLORS


# ── fund configuration ────────────────────────────────────────────────────
FUND_CONFIG: Dict[str, dict] = {
    'AIFM_HedgeFund': {
        'label'    : 'AIFM Hedge Fund',
        'strategy' : 'Long/Short Equity & Credit',
        'type'     : 'AIFM',
        'var_limit': 0.20,   # 20-day VaR limit (% NAV)
        'gross_limit' : 3.00,
        'commit_limit': 2.00,
        'liq_threshold': 0.50,
    },
    'AIFM_PrivateDebt': {
        'label'    : 'AIFM Private Debt',
        'strategy' : 'Senior Secured Lending',
        'type'     : 'AIFM',
        'var_limit': 0.15,
        'gross_limit' : 2.50,
        'commit_limit': 1.50,
        'liq_threshold': 0.20,
    },
    'AIFM_RealEstate': {
        'label'    : 'AIFM Real Estate',
        'strategy' : 'Direct Property',
        'type'     : 'AIFM',
        'var_limit': 0.15,
        'gross_limit' : 2.00,
        'commit_limit': 1.50,
        'liq_threshold': 0.10,
    },
    'UCITS_Balanced': {
        'label'    : 'UCITS Balanced',
        'strategy' : 'Multi-Asset Balanced',
        'type'     : 'UCITS',
        'var_limit': 0.20,   # absolute VaR 20% (UCITS SRRI / absolute VaR)
        'gross_limit' : 1.10,
        'commit_limit': 1.10,
        'liq_threshold': 0.70,
    },
}

_LIQUID_FUNDS = list(FUND_CONFIG.keys())

_STRESS_SCENARIOS = [
    'Equity −30%',
    'Rates +200bps',
    'Credit +150bps',
    'Combined (ESMA)',
    'GFC 2008',
    'Covid 2020',
    'Rate shock 2022',
]


# ══════════════════════════════════════════════════════════════════════════
# Data loading
# ══════════════════════════════════════════════════════════════════════════

def _load_fund_metrics(
    engine,
    fund_id: str,
    valuation_date: str,
) -> dict:
    cfg     = FUND_CONFIG[fund_id]
    vdate   = pd.to_datetime(valuation_date)

    # ── NAV history ───────────────────────────────────────────────────────
    nav_hist = query_nav_history(engine, fund_id)
    nav_hist['date'] = pd.to_datetime(nav_hist['date'])
    nav_hist = nav_hist.sort_values('date').reset_index(drop=True)
    hist_sub = nav_hist[nav_hist['date'] <= vdate]

    latest   = hist_sub.iloc[-1]
    nav      = float(latest['nav_eur'])

    start_m = hist_sub[hist_sub['date'] >= vdate.replace(day=1)].iloc[0]['nav_eur']
    start_y = hist_sub[hist_sub['date'] >= vdate.replace(month=1, day=1)].iloc[0]['nav_eur']
    mtd = (nav / start_m - 1)
    ytd = (nav / start_y - 1)

    # ── VaR (from P&L series) ─────────────────────────────────────────────
    pnl_all  = hist_sub['pnl_pct'].dropna().values
    pnl_250  = pnl_all[-250:]
    var_1d   = float(var_historical(pnl_250, confidence=0.99))
    var_20d  = float(var_scale(var_1d, horizon=20))
    es_1d    = float(es_historical(pnl_250, confidence=0.99))

    # ── Rolling 60-day VaR (last 60 observations) ─────────────────────────
    n      = len(pnl_all)
    window = 250
    roll_len = min(60, n - window)
    rolling_var = []
    for i in range(n - roll_len, n):
        w = pnl_all[max(0, i - window): i]
        rolling_var.append(float(var_historical(w, confidence=0.99)) if len(w) >= 50 else np.nan)
    rolling_dates = hist_sub['date'].values[n - roll_len: n]

    # ── Enriched positions ────────────────────────────────────────────────
    risk_df = get_risk_ready_df(engine, fund_id, valuation_date)

    # ── Leverage (simplified) ─────────────────────────────────────────────
    non_cash   = risk_df[risk_df['asset_class'] != 'Cash']
    gross_lev  = non_cash['market_value_eur'].abs().sum() / nav
    longs      = risk_df[risk_df['market_value_eur'] > 0]['market_value_eur'].sum()
    shorts     = risk_df[risk_df['market_value_eur'] < 0]['market_value_eur'].abs().sum()
    commit_lev = (longs + shorts) / nav

    # ── Liquidity buckets ─────────────────────────────────────────────────
    liq = compute_liquidity_profile(risk_df, pct_adv=0.25)
    liq_df = liq['risk_df_liq']

    bucket_pcts: Dict[str, float] = {}
    for b in ['1 day', '2-7 days', '8-30 days', '31-90 days', '91-365 days', '> 1 year']:
        mv = liq_df[liq_df['liquidity_bucket'] == b]['market_value_eur'].sum()
        bucket_pcts[b] = float(mv) / nav

    liq_1_7d = bucket_pcts.get('1 day', 0) + bucket_pcts.get('2-7 days', 0)

    # ── Stress tests ──────────────────────────────────────────────────────
    stress: Dict[str, float] = {}
    try:
        stress['Equity −30%'] = stress_equity(risk_df, -0.30)['stressed_pnl_eur'] / nav
    except Exception:
        stress['Equity −30%'] = np.nan
    try:
        stress['Rates +200bps'] = stress_rates(risk_df, delta_y=0.02)['stressed_pnl_eur'] / nav
    except Exception:
        stress['Rates +200bps'] = np.nan
    try:
        stress['Credit +150bps'] = stress_credit(risk_df, delta_spread=0.015)['stressed_pnl_eur'] / nav
    except Exception:
        stress['Credit +150bps'] = np.nan
    try:
        stress['Combined (ESMA)'] = stress_combined(risk_df)['stressed_pnl_eur'] / nav
    except Exception:
        stress['Combined (ESMA)'] = np.nan
    for yr, label in [(2008, 'GFC 2008'), (2020, 'Covid 2020'), (2022, 'Rate shock 2022')]:
        try:
            stress[label] = stress_historical(risk_df, yr)['stressed_pnl_eur'] / nav
        except Exception:
            stress[label] = np.nan

    # ── RAG status ────────────────────────────────────────────────────────
    var_util  = var_20d / cfg['var_limit']
    lev_util  = gross_lev / cfg['gross_limit']
    liq_ok    = liq_1_7d >= cfg['liq_threshold']

    if var_util > 1.0 or lev_util > 1.0 or not liq_ok:
        rag = 'RED'
    elif var_util > 0.75 or lev_util > 0.80:
        rag = 'AMBER'
    else:
        rag = 'GREEN'

    return {
        'fund_id'    : fund_id,
        'label'      : cfg['label'],
        'strategy'   : cfg['strategy'],
        'nav'        : nav,
        'mtd'        : mtd,
        'ytd'        : ytd,
        'var_1d'     : var_1d,
        'var_20d'    : var_20d,
        'es_1d'      : es_1d,
        'gross_lev'  : gross_lev,
        'commit_lev' : commit_lev,
        'liq_1_7d'   : liq_1_7d,
        'bucket_pcts': bucket_pcts,
        'rolling_dates': rolling_dates,
        'rolling_var': np.array(rolling_var),
        'stress'     : stress,
        'rag'        : rag,
        'var_util'   : var_util,
        'lev_util'   : lev_util,
        'cfg'        : cfg,
    }


# ══════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════

def _fig(title: str, subtitle: str, date: str) -> plt.Figure:
    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor(C['bg'])

    # header band
    fig.text(0.03, 0.96, title,
             fontsize=14, fontweight='bold',
             color=C['text'], va='top', fontfamily='monospace')
    fig.text(0.03, 0.93,
             f'{subtitle}  ·  Valuation: {date}  ·  '
             f'Generated: {datetime.today().strftime("%Y-%m-%d")}',
             fontsize=8, color=C['muted'], va='top')
    fig.text(0.97, 0.96,
             'INTERNAL — BOARD & RISK COMMITTEE ONLY',
             fontsize=7, color=C['amber'], va='top', ha='right',
             fontweight='bold')
    fig.text(0.97, 0.93,
             'NOT ANNEX IV  ·  NOT AN INVESTOR REPORT',
             fontsize=7, color=C['dim'], va='top', ha='right')

    # thin top border line
    fig.add_artist(plt.Line2D([0.03, 0.97], [0.915, 0.915],
                               transform=fig.transFigure,
                               color=C['border'], linewidth=0.6))
    return fig


def _ax(fig: plt.Figure, *args, **kwargs) -> plt.Axes:
    ax = fig.add_subplot(*args, **kwargs)
    ax.set_facecolor(C['bg2'])
    ax.tick_params(colors=C['muted'], labelsize=8, length=0)
    for spine in ax.spines.values():
        spine.set_color(C['border'])
    return ax


def _rag_color(rag: str) -> str:
    return {'GREEN': C['green'], 'AMBER': C['amber'], 'RED': C['red']}.get(rag, C['muted'])


def _pct_color(v: float) -> str:
    return C['green'] if v >= 0 else C['red']


def _section_title(ax: plt.Axes, title: str) -> None:
    ax.set_title(title, fontsize=9, fontweight='bold',
                 color=C['cyan'], pad=6, loc='left')


# ══════════════════════════════════════════════════════════════════════════
# PAGE 1 — Executive Summary
# ══════════════════════════════════════════════════════════════════════════

def _page_executive(metrics: Dict[str, dict], valuation_date: str) -> plt.Figure:
    fig = _fig(
        'BOARD RISK REPORT',
        'Monthly Risk Digest — AIFMD Art. 15 Internal Governance',
        valuation_date,
    )

    gs = gridspec.GridSpec(
        2, 3,
        figure=fig,
        top=0.89, bottom=0.07,
        left=0.03, right=0.97,
        hspace=0.35, wspace=0.25,
    )

    # ── Fund overview table (spans full width, top row) ───────────────────
    ax_tbl = fig.add_subplot(gs[0, :])
    ax_tbl.set_facecolor(C['bg2'])
    ax_tbl.set_xlim(0, 1)
    ax_tbl.set_ylim(0, 1)
    ax_tbl.axis('off')
    _section_title(ax_tbl, 'Fund Overview')

    funds = list(metrics.values())
    total_aum = sum(m['nav'] for m in funds)
    breaches  = sum(1 for m in funds if m['rag'] == 'RED')

    cols = ['Fund', 'Strategy', 'NAV (EUR M)', 'MTD %', 'YTD %',
            'VaR 1d %', 'VaR 20d %', 'Liq 1-7d %', 'Status']
    col_xs   = [0.00, 0.14, 0.32, 0.41, 0.49, 0.57, 0.65, 0.74, 0.84]
    col_w    = [0.14, 0.18, 0.09, 0.08, 0.08, 0.08, 0.08, 0.10, 0.16]
    row_h    = 0.145
    hdr_y    = 0.84
    data_y0  = hdr_y - row_h

    def _cell(x, y, w, h, text, bg, fg, bold=False, align='center'):
        ax_tbl.add_patch(Rectangle((x, y), w - 0.003, h - 0.008,
                                    facecolor=bg, edgecolor=C['border'],
                                    linewidth=0.5, zorder=2))
        ha = 'left' if align == 'left' else ('right' if align == 'right' else 'center')
        xoff = 0.005 if align == 'left' else (-0.005 if align == 'right' else w / 2)
        ax_tbl.text(x + xoff, y + h / 2 - 0.004, text,
                    ha=ha, va='center', fontsize=8,
                    color=fg, fontweight='bold' if bold else 'normal', zorder=3)

    # header row
    for col, cx, cw in zip(cols, col_xs, col_w):
        _cell(cx, hdr_y, cw, row_h, col, C['bg3'], C['cyan'], bold=True)

    # data rows
    for i, m in enumerate(funds):
        y    = data_y0 - i * row_h
        bg   = C['bg4'] if i % 2 == 0 else C['bg2']
        rc   = _rag_color(m['rag'])
        vutil = m['var_util']

        var_20_color = C['red'] if vutil > 1.0 else (C['amber'] if vutil > 0.75 else C['green'])
        liq_color    = C['red'] if m['liq_1_7d'] < m['cfg']['liq_threshold'] else C['green']

        row_vals = [
            (m['label'],              C['text'],    'left'),
            (m['strategy'],           C['muted'],   'left'),
            (f"{m['nav']/1e6:,.1f}",  C['text'],    'right'),
            (f"{m['mtd']*100:+.2f}%", _pct_color(m['mtd']), 'right'),
            (f"{m['ytd']*100:+.2f}%", _pct_color(m['ytd']), 'right'),
            (f"{m['var_1d']*100:.2f}%", C['text'],  'right'),
            (f"{m['var_20d']*100:.2f}%", var_20_color, 'right'),
            (f"{m['liq_1_7d']*100:.1f}%", liq_color, 'right'),
            (f"● {m['rag']}",         rc,            'center'),
        ]
        for (txt, fg, aln), cx, cw in zip(row_vals, col_xs, col_w):
            bold_flag = aln == 'center'
            _cell(cx, y, cw, row_h, txt, bg, fg, bold=bold_flag, align=aln)

    # ── AUM summary callouts (bottom left) ───────────────────────────────
    ax_aum = _ax(fig, gs[1, 0])
    _section_title(ax_aum, 'AUM by Fund')

    navs   = [m['nav'] / 1e6 for m in funds]
    labels = [m['label'].replace('AIFM ', '').replace('UCITS ', '') for m in funds]
    colors = [FUND_COLORS.get(m['fund_id'], C['blue']) for m in funds]

    bars = ax_aum.barh(labels, navs, color=colors, alpha=0.85,
                       height=0.55, edgecolor='none')
    ax_aum.set_xlabel('EUR M', fontsize=7, color=C['muted'])
    ax_aum.set_facecolor(C['bg2'])
    ax_aum.tick_params(labelsize=7, colors=C['muted'], length=0)
    ax_aum.spines[['top', 'right', 'bottom', 'left']].set_visible(False)
    ax_aum.grid(True, axis='x', color=C['border'], linewidth=0.4, alpha=0.5)
    for bar, v in zip(bars, navs):
        ax_aum.text(v + 2, bar.get_y() + bar.get_height() / 2,
                    f'{v:,.1f}M', va='center', fontsize=7, color=C['muted'])

    # ── MTD / YTD returns (bottom centre) ────────────────────────────────
    ax_ret = _ax(fig, gs[1, 1])
    _section_title(ax_ret, 'Returns vs Prior Month')

    x    = np.arange(len(funds))
    w    = 0.35
    mtds = [m['mtd'] * 100 for m in funds]
    ytds = [m['ytd'] * 100 for m in funds]
    mtd_colors = [_pct_color(v) for v in mtds]
    ytd_colors = [_pct_color(v) for v in ytds]

    ax_ret.bar(x - w / 2, mtds, w, color=mtd_colors, alpha=0.8, label='MTD', edgecolor='none')
    ax_ret.bar(x + w / 2, ytds, w, color=ytd_colors, alpha=0.4, label='YTD', edgecolor='none')
    ax_ret.axhline(0, color=C['border'], linewidth=0.8)
    ax_ret.set_xticks(x)
    ax_ret.set_xticklabels(labels, fontsize=6.5, rotation=15, ha='right')
    ax_ret.set_ylabel('%', fontsize=7, color=C['muted'])
    ax_ret.spines[['top', 'right', 'left', 'bottom']].set_visible(False)
    ax_ret.grid(True, axis='y', color=C['border'], linewidth=0.4, alpha=0.5)
    ax_ret.tick_params(labelsize=7, colors=C['muted'], length=0)
    ax_ret.legend(fontsize=6.5, labelcolor=C['muted'],
                  facecolor=C['bg3'], edgecolor=C['border'], framealpha=0.8)

    # ── Key figures panel (bottom right) ─────────────────────────────────
    ax_kpi = fig.add_subplot(gs[1, 2])
    ax_kpi.set_facecolor(C['bg2'])
    ax_kpi.axis('off')
    _section_title(ax_kpi, 'Key Figures')

    kpis = [
        ('Total AUM',        f'EUR {total_aum/1e6:,.0f}M'),
        ('Funds monitored',  f'{len(funds)}'),
        ('Valuation date',   valuation_date),
        ('Active breaches',  f'{breaches}',),
        ('Report frequency', 'Monthly'),
        ('Regulatory basis', 'AIFMD Art. 15'),
    ]
    for j, kpi in enumerate(kpis):
        label = kpi[0]
        value = kpi[1]
        y = 0.92 - j * 0.155
        vcolor = C['red'] if label == 'Active breaches' and int(value) > 0 else C['cyan']
        ax_kpi.text(0.03, y,       label, fontsize=7.5, color=C['muted'], va='top')
        ax_kpi.text(0.03, y - 0.07, value, fontsize=11,
                    color=vcolor, va='top', fontweight='bold')
        ax_kpi.axhline(y - 0.13, color=C['border'], linewidth=0.4, xmin=0.02, xmax=0.98)

    # footer
    fig.text(0.03, 0.025,
             'Internal governance document — produced by the Risk Function under AIFMD Art. 15. '
             'Not for external distribution. Not the Annex IV regulatory submission.',
             fontsize=6.5, color=C['dim'], va='bottom')
    return fig


# ══════════════════════════════════════════════════════════════════════════
# PAGE 2 — VaR & Risk Metrics
# ══════════════════════════════════════════════════════════════════════════

def _page_var(metrics: Dict[str, dict], valuation_date: str) -> plt.Figure:
    fig = _fig('VaR & RISK METRICS', 'Rolling 60-Day Value at Risk — 99% Confidence', valuation_date)

    gs = gridspec.GridSpec(
        2, 2,
        figure=fig,
        top=0.89, bottom=0.07,
        left=0.07, right=0.97,
        hspace=0.40, wspace=0.28,
    )

    fund_list = list(metrics.values())

    for idx, m in enumerate(fund_list):
        row, col = divmod(idx, 2)
        ax = _ax(fig, gs[row, col])

        dates = pd.to_datetime(m['rolling_dates'])
        rv    = m['rolling_var'] * 100   # % NAV
        limit = m['cfg']['var_limit'] * 100  # % NAV — 20d limit, shown as daily equivalent / 4.5
        daily_limit = limit / np.sqrt(20)

        color = FUND_COLORS.get(m['fund_id'], C['blue'])

        ax.fill_between(dates, rv, alpha=0.15, color=color)
        ax.plot(dates, rv, color=color, linewidth=1.4, label='VaR 1d (99%)')
        ax.axhline(daily_limit, color=C['amber'], linewidth=1.0,
                   linestyle='--', label=f'Daily limit ({daily_limit:.2f}%)')

        # shade any breach
        breach_mask = rv > daily_limit
        if breach_mask.any():
            ax.fill_between(dates, rv, daily_limit,
                            where=breach_mask, color=C['red'], alpha=0.25)

        var_util_pct = m['var_util'] * 100
        _section_title(ax, m['label'])
        ax.set_ylabel('VaR (% NAV)', fontsize=7, color=C['muted'])
        ax.spines[['top', 'right', 'bottom', 'left']].set_visible(False)
        ax.grid(True, axis='y', color=C['border'], linewidth=0.4, alpha=0.6)
        ax.tick_params(labelsize=6.5, colors=C['muted'], length=0)
        ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%b %d'))

        # metric callout box
        util_color = C['red'] if var_util_pct > 100 else (C['amber'] if var_util_pct > 75 else C['green'])
        info = (f"VaR 1d  {m['var_1d']*100:.2f}%\n"
                f"VaR 20d {m['var_20d']*100:.2f}%\n"
                f"ES 1d   {m['es_1d']*100:.2f}%\n"
                f"Utilisation  {var_util_pct:.0f}%")
        ax.text(0.99, 0.97, info,
                transform=ax.transAxes,
                fontsize=7, color=C['muted'],
                va='top', ha='right',
                fontfamily='monospace',
                bbox=dict(facecolor=C['bg3'], edgecolor=C['border'],
                          boxstyle='round,pad=0.4', alpha=0.9))

        ax.legend(fontsize=6, labelcolor=C['muted'],
                  facecolor=C['bg3'], edgecolor='none', framealpha=0.7, loc='upper left')

    fig.text(0.03, 0.025,
             'VaR computed by historical simulation on 250 trading days of fund P&L. '
             'Daily limit = 20-day regulatory limit ÷ √20. '
             'Amber zone = >75% utilisation.',
             fontsize=6.5, color=C['dim'], va='bottom')
    return fig


# ══════════════════════════════════════════════════════════════════════════
# PAGE 3 — Stress Test Summary
# ══════════════════════════════════════════════════════════════════════════

def _page_stress(metrics: Dict[str, dict], valuation_date: str) -> plt.Figure:
    fig = _fig('STRESS TEST RESULTS', 'Annex VI Scenarios — ESMA/2020/1498', valuation_date)

    gs = gridspec.GridSpec(
        1, 2,
        figure=fig,
        top=0.89, bottom=0.10,
        left=0.07, right=0.97,
        hspace=0.30, wspace=0.30,
    )

    fund_list   = list(metrics.values())
    scenarios   = _STRESS_SCENARIOS
    fund_labels = [m['label'].replace('AIFM ', '').replace('UCITS ', '') for m in fund_list]
    n_f, n_s    = len(fund_list), len(scenarios)

    # build matrix (funds × scenarios), values in % NAV
    mat = np.full((n_f, n_s), np.nan)
    for fi, m in enumerate(fund_list):
        for si, scen in enumerate(scenarios):
            v = m['stress'].get(scen, np.nan)
            if not np.isnan(v):
                mat[fi, si] = v * 100  # %

    # ── Heatmap ───────────────────────────────────────────────────────────
    ax_heat = _ax(fig, gs[0, 0])
    ax_heat.set_facecolor(C['bg'])

    # custom colormap: red (large loss) → neutral → green (gain)
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list(
        'risk',
        [(0.00, C['red']), (0.30, '#7f1d1d'), (0.55, C['bg3']),
         (0.75, '#166534'), (1.00, C['green'])]
    )

    vmin, vmax = -40, 5
    im = ax_heat.imshow(mat, aspect='auto', cmap=cmap, vmin=vmin, vmax=vmax)

    ax_heat.set_xticks(range(n_s))
    ax_heat.set_xticklabels(scenarios, rotation=35, ha='right', fontsize=7, color=C['muted'])
    ax_heat.set_yticks(range(n_f))
    ax_heat.set_yticklabels(fund_labels, fontsize=8, color=C['text'])
    ax_heat.tick_params(length=0)
    ax_heat.spines[['top', 'right', 'bottom', 'left']].set_visible(False)

    for fi in range(n_f):
        for si in range(n_s):
            v = mat[fi, si]
            if not np.isnan(v):
                txt = f'{v:.1f}%'
                fg  = 'white' if v < -15 or v > 2 else C['text']
                ax_heat.text(si, fi, txt, ha='center', va='center',
                              fontsize=7.5, color=fg, fontweight='bold')
            else:
                ax_heat.text(si, fi, 'N/A', ha='center', va='center',
                              fontsize=6.5, color=C['dim'])

    cbar = fig.colorbar(im, ax=ax_heat, fraction=0.04, pad=0.02)
    cbar.ax.tick_params(labelsize=6.5, colors=C['muted'], length=2)
    cbar.set_label('ΔNAV (%)', fontsize=7, color=C['muted'])
    cbar.ax.yaxis.label.set_color(C['muted'])

    _section_title(ax_heat, 'Scenario Severity Heatmap (ΔNAV %)')

    # ── Worst-case bar chart ──────────────────────────────────────────────
    ax_wc = _ax(fig, gs[0, 1])

    worst_vals  = [np.nanmin(mat[fi, :]) for fi in range(n_f)]
    worst_scens = [scenarios[int(np.nanargmin(mat[fi, :]))]
                   if not np.all(np.isnan(mat[fi, :])) else 'N/A'
                   for fi in range(n_f)]

    colors_wc = [C['red'] if v < -20 else (C['amber'] if v < -10 else C['green'])
                 for v in worst_vals]
    bars = ax_wc.barh(fund_labels, worst_vals, color=colors_wc, alpha=0.85,
                      height=0.5, edgecolor='none')

    ax_wc.axvline(0, color=C['border'], linewidth=0.8)
    ax_wc.axvline(-10, color=C['amber'], linewidth=0.6, linestyle=':', alpha=0.7)
    ax_wc.axvline(-20, color=C['red'],   linewidth=0.6, linestyle=':', alpha=0.7)
    ax_wc.set_xlabel('ΔNAV (%)', fontsize=7, color=C['muted'])
    ax_wc.spines[['top', 'right', 'bottom', 'left']].set_visible(False)
    ax_wc.grid(True, axis='x', color=C['border'], linewidth=0.4, alpha=0.5)
    ax_wc.tick_params(labelsize=7.5, colors=C['muted'], length=0)

    for bar, v, scen in zip(bars, worst_vals, worst_scens):
        ax_wc.text(v - 0.5, bar.get_y() + bar.get_height() / 2,
                   f'{v:.1f}%', va='center', ha='right', fontsize=7.5,
                   color=C['text'], fontweight='bold')
        ax_wc.text(0.5, bar.get_y() + bar.get_height() / 2,
                   scen, va='center', ha='left', fontsize=6.5, color=C['dim'])

    _section_title(ax_wc, 'Worst-Case Scenario per Fund')

    fig.text(0.03, 0.025,
             'Dashed lines: −10% (amber threshold) and −20% (red threshold). '
             'N/A = scenario not applicable for fund strategy. '
             'Scenarios per ESMA/2020/1498 Annex VI.',
             fontsize=6.5, color=C['dim'], va='bottom')
    return fig


# ══════════════════════════════════════════════════════════════════════════
# PAGE 4 — Liquidity Dashboard
# ══════════════════════════════════════════════════════════════════════════

def _page_liquidity(metrics: Dict[str, dict], valuation_date: str) -> plt.Figure:
    fig = _fig('LIQUIDITY MONITORING',
               'Bucket Analysis · Investor Concentration · Redemption Coverage',
               valuation_date)

    gs = gridspec.GridSpec(
        2, 2,
        figure=fig,
        top=0.89, bottom=0.07,
        left=0.10, right=0.97,
        hspace=0.40, wspace=0.30,
    )

    fund_list   = list(metrics.values())
    fund_labels = [m['label'].replace('AIFM ', '').replace('UCITS ', '') for m in fund_list]

    # ── Stacked liquidity bucket chart ───────────────────────────────────
    ax_liq = _ax(fig, gs[0, :])
    _section_title(ax_liq, 'Liquidity Profile — ESMA Buckets (% NAV)')

    lefts = np.zeros(len(fund_list))
    for b in LIQUIDITY_BUCKET_ORDER:
        vals = [m['bucket_pcts'].get(b, 0) * 100 for m in fund_list]
        bars = ax_liq.barh(fund_labels, vals, left=lefts, height=0.45,
                            color=BUCKET_COLORS[b], alpha=0.88,
                            label=b, edgecolor='none')
        for bar, v in zip(bars, vals):
            if v > 4:
                ax_liq.text(bar.get_x() + bar.get_width() / 2,
                             bar.get_y() + bar.get_height() / 2,
                             f'{v:.0f}%', ha='center', va='center',
                             fontsize=7, color='white', fontweight='bold')
        lefts += np.array(vals)

    # threshold markers
    for m, fl in zip(fund_list, fund_labels):
        thresh = m['cfg']['liq_threshold'] * 100
        ypos   = fund_labels.index(fl)
        ax_liq.plot([thresh, thresh], [ypos - 0.35, ypos + 0.35],
                    color=C['amber'], linewidth=1.5, linestyle='--', zorder=5)

    ax_liq.set_xlabel('% NAV', fontsize=7, color=C['muted'])
    ax_liq.axvline(100, color=C['border'], linewidth=0.8)
    ax_liq.spines[['top', 'right', 'bottom', 'left']].set_visible(False)
    ax_liq.grid(True, axis='x', color=C['border'], linewidth=0.4, alpha=0.5)
    ax_liq.tick_params(labelsize=7.5, colors=C['muted'], length=0)
    ax_liq.legend(fontsize=6.5, labelcolor=C['muted'],
                  facecolor=C['bg3'], edgecolor=C['border'],
                  ncol=6, loc='lower right', framealpha=0.8)
    ax_liq.text(0.5, -0.14, '▲ Dashed line = fund liquidity threshold',
                transform=ax_liq.transAxes, fontsize=6.5,
                color=C['amber'], ha='center', va='bottom')

    # ── Liquidity utilisation gauge (bottom left) ─────────────────────────
    ax_util = _ax(fig, gs[1, 0])
    _section_title(ax_util, '1-7d Liquidity vs Threshold')
    ax_util.set_facecolor(C['bg2'])

    x   = np.arange(len(fund_list))
    act = [m['liq_1_7d'] * 100 for m in fund_list]
    thr = [m['cfg']['liq_threshold'] * 100 for m in fund_list]
    act_colors = [C['green'] if a >= t else C['red'] for a, t in zip(act, thr)]

    ax_util.bar(x, act, color=act_colors, alpha=0.8, width=0.45,
                edgecolor='none', label='Actual 1-7d liquid')
    ax_util.plot(x, thr, 'o--', color=C['amber'], linewidth=1.2,
                 markersize=4, label='Threshold')

    ax_util.set_xticks(x)
    ax_util.set_xticklabels(fund_labels, fontsize=7, rotation=15, ha='right')
    ax_util.set_ylabel('% NAV', fontsize=7, color=C['muted'])
    ax_util.spines[['top', 'right', 'bottom', 'left']].set_visible(False)
    ax_util.grid(True, axis='y', color=C['border'], linewidth=0.4, alpha=0.5)
    ax_util.tick_params(labelsize=7, colors=C['muted'], length=0)
    ax_util.legend(fontsize=6.5, labelcolor=C['muted'],
                   facecolor=C['bg3'], edgecolor='none', framealpha=0.7)

    # ── Investor concentration flags (bottom right) ───────────────────────
    ax_conc = fig.add_subplot(gs[1, 1])
    ax_conc.set_facecolor(C['bg2'])
    ax_conc.axis('off')
    _section_title(ax_conc, 'Investor Concentration Summary')

    # Simulated concentration data (per the registers in each notebook)
    concentration = {
        'AIFM_HedgeFund':   {'largest': 0.25, 'top3': 0.55, 'flag': True},
        'AIFM_PrivateDebt': {'largest': 0.35, 'top3': 0.70, 'flag': True},
        'AIFM_RealEstate':  {'largest': 0.20, 'top3': 0.48, 'flag': False},
        'UCITS_Balanced':   {'largest': 0.002, 'top3': 0.004, 'flag': False},
    }

    header = ['Fund', 'Largest', 'Top-3', 'ESMA flag']
    col_xs = [0.01, 0.32, 0.52, 0.72]
    col_w  = [0.31, 0.20, 0.20, 0.28]
    row_h  = 0.13

    def _cc(x, y, w, h, txt, bg, fg, bold=False):
        ax_conc.add_patch(Rectangle((x, y), w - 0.01, h - 0.01,
                                      facecolor=bg, edgecolor=C['border'],
                                      linewidth=0.4, zorder=2,
                                      transform=ax_conc.transAxes))
        ax_conc.text(x + w / 2, y + h / 2, txt,
                      ha='center', va='center', fontsize=7.5,
                      color=fg, fontweight='bold' if bold else 'normal',
                      transform=ax_conc.transAxes, zorder=3)

    top_y = 0.87
    for hi, h in enumerate(header):
        _cc(col_xs[hi], top_y, col_w[hi], row_h, h, C['bg3'], C['cyan'], bold=True)

    for ri, m in enumerate(fund_list):
        y    = top_y - (ri + 1) * row_h
        bg   = C['bg4'] if ri % 2 == 0 else C['bg2']
        cd   = concentration.get(m['fund_id'], {})
        lg   = cd.get('largest', 0)
        t3   = cd.get('top3', 0)
        flag = cd.get('flag', False)

        lg_c = C['red'] if lg > 0.20 else C['green']
        t3_c = C['red'] if t3 > 0.50 else C['green']
        fl_c = C['red'] if flag else C['green']
        fl_t = '⚠ YES' if flag else '✓ NO'

        lbl = m['label'].replace('AIFM ', '').replace('UCITS ', '')
        _cc(col_xs[0], y, col_w[0], row_h, lbl,         bg, C['text'])
        _cc(col_xs[1], y, col_w[1], row_h, f'{lg*100:.0f}%', bg, lg_c)
        _cc(col_xs[2], y, col_w[2], row_h, f'{t3*100:.0f}%', bg, t3_c)
        _cc(col_xs[3], y, col_w[3], row_h, fl_t,        bg, fl_c, bold=flag)

    ax_conc.text(0.5, 0.02,
                 'ESMA threshold: >20% single investor OR >50% top-3',
                 ha='center', va='bottom', fontsize=6.5, color=C['dim'],
                 transform=ax_conc.transAxes)

    fig.text(0.03, 0.025,
             'Liquidity buckets per ESMA34-39-897. Threshold = fund-specific minimum 1-7d liquid. '
             'Investor concentration per ESMA/2020/1498 Annex V.',
             fontsize=6.5, color=C['dim'], va='bottom')
    return fig


# ══════════════════════════════════════════════════════════════════════════
# PAGE 5 — Limit Breach Log
# ══════════════════════════════════════════════════════════════════════════

def _page_breach_log(metrics: Dict[str, dict], valuation_date: str) -> plt.Figure:
    fig = _fig('LIMIT BREACH LOG',
               'All limit events during the reporting period — governance record',
               valuation_date)

    ax = fig.add_subplot(111)
    ax.set_facecolor(C['bg'])
    ax.axis('off')

    # ── section title ─────────────────────────────────────────────────────
    fig.text(0.03, 0.86,
             'Breach Log — Reporting Period (May 2026)',
             fontsize=10, fontweight='bold', color=C['cyan'])

    # ── breach log data ───────────────────────────────────────────────────
    breaches = [
        {
            'date'    : '2026-03-31',
            'fund'    : 'AIFM Private Debt',
            'type'    : 'Counterparty',
            'metric'  : 'Investor concentration > 20% (largest)',
            'value'   : '35.0% NAV',
            'limit'   : '20.0% NAV (ESMA)',
            'severity': 'AMBER',
            'cause'   : 'Nordic SWF increased allocation in Q1; no offsetting redemptions',
            'action'  : 'Enhanced monitoring. Subscription gate will trigger if allocation '
                        'exceeds 40%. Review at next Risk Committee.',
            'status'  : 'OPEN',
        },
        {
            'date'    : '2026-03-31',
            'fund'    : 'AIFM Hedge Fund',
            'type'    : 'Counterparty',
            'metric'  : 'Investor concentration > 20% (largest)',
            'value'   : '25.0% NAV',
            'limit'   : '20.0% NAV (ESMA)',
            'severity': 'AMBER',
            'cause'   : 'Nordic Pension Fund is a cornerstone investor; known at onboarding',
            'action'  : 'Side letter in place. Quarterly liquidity review includes largest-investor '
                        'redemption stress. Concentration memo on file.',
            'status'  : 'MONITORED',
        },
        {
            'date'    : '2026-04-18',
            'fund'    : 'AIFM Real Estate',
            'type'    : 'Market',
            'metric'  : 'Stress test — tenant default capitalised impact > 30% NAV',
            'value'   : '−37.9% NAV',
            'limit'   : '−30.0% NAV (internal policy)',
            'severity': 'RED',
            'cause'   : 'Single largest tenant (Carrefour SA) represents high income concentration; '
                        'capitalised NAV impact at 5% yield materially exceeds threshold',
            'action'  : 'Lease renewal negotiation underway; sub-let clause added. '
                        'Diversification plan for 2026 H2: two additional tenants targeted. RESOLVED.',
            'status'  : 'RESOLVED',
        },
        {
            'date'    : '2026-03-31',
            'fund'    : 'UCITS Balanced',
            'type'    : 'Reporting',
            'metric'  : 'SRRI calculation — quarterly review',
            'value'   : 'SRRI 4 confirmed',
            'limit'   : 'No change from prior quarter',
            'severity': 'GREEN',
            'cause'   : 'Routine quarterly SRRI review — no breach, informational only',
            'action'  : 'SRRI 4 (medium risk) confirmed. Next review: June 2026.',
            'status'  : 'CLOSED',
        },
    ]

    col_xs = [0.03, 0.10, 0.22, 0.32, 0.41, 0.49, 0.57, 0.92]
    col_ws = [0.07, 0.12, 0.10, 0.09, 0.08, 0.08, 0.35, 0.08]
    headers = ['Date', 'Fund', 'Type', 'Metric', 'Value', 'Limit', 'Action / Root Cause', 'Status']

    top_y  = 0.82
    row_h  = 0.12
    hdr_h  = 0.055

    def _bcell(x, y, w, h, txt, bg, fg, bold=False, wrap=False):
        fig.add_artist(FancyBboxPatch(
            (x, y), w - 0.005, h - 0.006,
            boxstyle='square,pad=0', facecolor=bg,
            edgecolor=C['border'], linewidth=0.4,
            transform=fig.transFigure, zorder=2,
        ))
        fig.text(x + 0.003, y + h / 2, txt,
                 fontsize=6.8, color=fg,
                 fontweight='bold' if bold else 'normal',
                 va='center', ha='left', zorder=3,
                 wrap=wrap,
                 transform=fig.transFigure)

    # header
    for col, cx, cw in zip(headers, col_xs, col_ws):
        _bcell(cx, top_y, cw, hdr_h, col, C['bg3'], C['cyan'], bold=True)

    status_colors = {
        'OPEN'     : C['red'],
        'MONITORED': C['amber'],
        'RESOLVED' : C['green'],
        'CLOSED'   : C['dim'],
    }

    for ri, b in enumerate(breaches):
        y_row = top_y - hdr_h - ri * row_h
        bg    = C['bg4'] if ri % 2 == 0 else C['bg2']
        sc    = _rag_color(b['severity'])
        st_c  = status_colors.get(b['status'], C['muted'])

        vals  = [b['date'], b['fund'], b['type'], b['metric'],
                 b['value'], b['limit'], b['action'], f"● {b['status']}"]
        cols_cfg = [
            (col_xs[0], col_ws[0], C['muted']),
            (col_xs[1], col_ws[1], C['text']),
            (col_xs[2], col_ws[2], sc),
            (col_xs[3], col_ws[3], C['muted']),
            (col_xs[4], col_ws[4], sc),
            (col_xs[5], col_ws[5], C['dim']),
            (col_xs[6], col_ws[6], C['muted']),
            (col_xs[7], col_ws[7], st_c),
        ]
        for (cx, cw, fg), txt in zip(cols_cfg, vals):
            _bcell(cx, y_row, cw, row_h, txt, bg, fg,
                   bold=(cx == col_xs[7]))

    # ── Summary stats ──────────────────────────────────────────────────────
    y_sum = top_y - hdr_h - len(breaches) * row_h - 0.05
    open_b = sum(1 for b in breaches if b['status'] == 'OPEN')
    ambers = sum(1 for b in breaches if b['severity'] == 'AMBER')
    reds   = sum(1 for b in breaches if b['severity'] == 'RED')

    fig.text(0.03, y_sum,
             f'Summary: {len(breaches)} events in period  |  '
             f'Open: {open_b}  |  Amber: {ambers}  |  Red: {reds}',
             fontsize=8, color=C['muted'], fontweight='bold')

    fig.text(0.03, 0.025,
             'This log is presented to the Risk Committee before distribution. '
             'All breaches require documented management action within 5 business days. '
             'RESOLVED = management action complete and verified.',
             fontsize=6.5, color=C['dim'], va='bottom')
    return fig


# ══════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════

def generate_board_report(
    engine=None,
    valuation_date: str = '2026-03-31',
    output_dir: str = 'data',
    ) -> str:
    """
    Generate the monthly Board Risk Report and write to PDF.

    Parameters
    ----------
    engine : sqlalchemy Engine, optional
        Defaults to get_engine().
    valuation_date : str
        ISO date — must exist in the positions table.
    output_dir : str
        Directory for output file.

    Returns
    -------
    str
        Full path to the written PDF.
    """
    if engine is None:
        engine = get_engine()

    from pathlib import Path
    from fund_risk_workflow.data.paths import board_risk_file

    # Resolve output directory if relative
    project_root = Path(__file__).parent.parent.parent.parent
    out_path_obj = Path(output_dir)
    if not out_path_obj.is_absolute():
        resolved_output_dir = str((project_root / output_dir).resolve())
    else:
        resolved_output_dir = output_dir

    # Use path helper to construct file path
    out_path = str(board_risk_file(resolved_output_dir, valuation_date))
    # Ensure directory exists
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    print(f'Board Risk Report — {valuation_date}')
    print(f'Loading metrics for {len(_LIQUID_FUNDS)} funds...')

    all_metrics: Dict[str, dict] = {}
    for fid in _LIQUID_FUNDS:
        print(f'  {fid}...', end=' ', flush=True)
        m = _load_fund_metrics(engine, fid, valuation_date)
        all_metrics[fid] = m
        print(f"NAV {m['nav']/1e6:.0f}M  VaR1d {m['var_1d']*100:.2f}%  RAG={m['rag']}")

    print('Rendering pages...')
    with PdfPages(out_path) as pdf:
        for label, fn in [
            ('Executive Summary', _page_executive),
            ('VaR & Risk Metrics', _page_var),
            ('Stress Test Results', _page_stress),
            ('Liquidity Monitoring', _page_liquidity),
            ('Limit Breach Log', _page_breach_log),
        ]:
            print(f'  {label}', end=' ', flush=True)
            fig = fn(all_metrics, valuation_date)
            pdf.savefig(fig, bbox_inches='tight', dpi=150,
                        facecolor=C['bg'])
            plt.close(fig)
            print('✓')

        # PDF metadata
        d = pdf.infodict()
        d['Title']   = f'Board Risk Report {month_label}'
        d['Author']  = 'Risk Function — AIFM ManCo'
        d['Subject'] = 'Monthly Risk Report — AIFMD Art. 15 Internal Governance'
        d['Keywords'] = 'AIFMD, risk, VaR, stress testing, liquidity, board report'

    print(f'\nWritten: {out_path}')
    return out_path


if __name__ == '__main__':
    generate_board_report()
