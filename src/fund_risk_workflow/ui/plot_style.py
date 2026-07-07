"""
plot_style.py
=============
Shared matplotlib dark theme, colour palette, typography, and helper
functions for all risk notebooks. Fully aligned with the board report
visual identity defined in board_report.py.

Usage
-----
    from fund_risk_workflow.ui.plot_style import C, FUND_COLORS, ACCENT, ACCENT2, ACCENT3
    from fund_risk_workflow.ui.plot_style import apply_ax_style, section_title, fig_header
    from fund_risk_workflow.ui.plot_style import pct_color, rag_color, callout_box
"""

from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates
import matplotlib.gridspec as gridspec
from matplotlib.patches import Rectangle, FancyBboxPatch


# ══════════════════════════════════════════════════════════════════════════
# Colour palette  (single source of truth — mirrors board_report.py _C)
# ══════════════════════════════════════════════════════════════════════════

C: dict[str, str] = {
    # backgrounds — darkest to lightest
    'bg'    : '#0a0f1e',
    'bg2'   : '#0f1729',
    'bg3'   : '#1a1f2e',
    'bg4'   : '#1d2235',
    'panel' : '#111827',
    # structure
    'border': '#374151',
    # text
    'text'  : '#f9fafb',
    'muted' : '#9ca3af',
    'dim'   : '#6b7280',
    # accents
    'cyan'  : '#1a9ed4',
    'cyan2' : '#38bdf8',
    'green' : '#22c55e',
    'amber' : "#c67236ff",
    'amber2': '#ea580c',
    'red'   : '#ef4444',
    'blue'  : '#3b82f6',
    'blue2' : '#2563eb',
    'purple': '#a855f7',
    'rose'  : '#f43f5e',
}

# semantic aliases for convenience
ACCENT  = C['blue2']
ACCENT2 = C['red']
ACCENT3 = C['green']
WARNING = C['amber']


# ══════════════════════════════════════════════════════════════════════════
# Domain colour maps
# ══════════════════════════════════════════════════════════════════════════

FUND_COLORS: dict[str, str] = {
    'AIFM_HedgeFund'  : C['cyan'],
    'AIFM_PrivateDebt': C['amber'],
    'AIFM_RealEstate' : C['green'],
    'AIFM_PE_Buyout'  : C['purple'],
    'AIFM_Infra_Core' : C['rose'],
    'UCITS_Balanced'  : C['blue'],
}

RAG_COLORS: dict[str, str] = {
    'GREEN': C['green'],
    'AMBER': C['amber'],
    'RED'  : C['red'],
}

STATUS_COLORS: dict[str, str] = {
    'OPEN'     : C['red'],
    'MONITORED': C['amber'],
    'RESOLVED' : C['green'],
    'CLOSED'   : C['dim'],
}


# ══════════════════════════════════════════════════════════════════════════
# Typography constants  (all sizes in points, matching board_report.py)
# ══════════════════════════════════════════════════════════════════════════
import matplotlib.font_manager as fm

def _resolve_font() -> str:
    available = {f.name for f in fm.fontManager.ttflist}
    candidates = [
        'Helvetica Neue',
        'SF Pro Display',
        'Gill Sans',
        'Trebuchet MS',
        'DejaVu Sans',   # always available in matplotlib
    ]
    for font in candidates:
        if font in available:
            return font
    return 'sans-serif'

FONT_FAMILY = _resolve_font()

FONT = {
    'family'      : FONT_FAMILY,
    # figure-level text
    'title'       : 14,       # main figure title
    'subtitle'    : 8,        # subtitle / metadata line
    'watermark'   : 7,        # INTERNAL — BOARD & RISK COMMITTEE ONLY
    'footer'      : 6.5,      # footer disclaimer
    # axes-level text
    'section'     : 9,        # section/axes title (cyan, bold, loc=left)
    'body'        : 8,        # general axis text, tick labels
    'small'       : 7,        # bar labels, legend, annotations
    'tiny'        : 6.5,      # secondary annotations
    'xsmall'      : 6,        # legend when very compact
    # table text
    'table_header': 8,        # table column headers
    'table_body'  : 8,        # table data cells
    'table_small' : 7.5,      # compact table cells
    # callout boxes
    'callout'     : 7,        # monospace info box in corner of axes
    # KPI panels
    'kpi_label'   : 7.5,
    'kpi_value'   : 11,
}


# ══════════════════════════════════════════════════════════════════════════
# Global rcParams  (applied at import time)
# ══════════════════════════════════════════════════════════════════════════

plt.rcParams.update({
    # backgrounds
    'figure.facecolor'      : C['bg'],
    'axes.facecolor'        : C['bg2'],
    # borders and spines
    'axes.edgecolor'        : C['border'],
    'axes.linewidth'        : 0.6,
    # labels and ticks
    'axes.labelcolor'       : C['muted'],
    'axes.labelsize'        : FONT['body'],
    'xtick.color'           : C['muted'],
    'ytick.color'           : C['muted'],
    'xtick.labelsize'       : FONT['body'],
    'ytick.labelsize'       : FONT['body'],
    'xtick.major.size'      : 0,          # no tick marks — clean look
    'ytick.major.size'      : 0,
    'xtick.minor.size'      : 0,
    'ytick.minor.size'      : 0,
    # text
    'text.color'            : C['text'],
    'font.family'           : FONT['family'],
    'font.size'             : FONT['body'],
    # grid
    'axes.grid'             : True,
    'axes.grid.axis'        : 'y',
    'grid.color'            : C['border'],
    'grid.linestyle'        : '-',
    'grid.linewidth'        : 0.4,
    'grid.alpha'            : 0.5,
    # spines — top and right off by default
    'axes.spines.top'       : False,
    'axes.spines.right'     : False,
    'axes.spines.left'      : False,
    'axes.spines.bottom'    : True,
    # legend
    'legend.facecolor'      : C['bg3'],
    'legend.edgecolor'      : C['border'],
    'legend.fontsize'       : FONT['small'],
    'legend.labelcolor'     : C['muted'],
    'legend.framealpha'     : 0.8,
    # figure
    'figure.dpi'            : 130,
    'figure.titlesize'      : FONT['title'],
    'figure.titleweight'    : 'bold',
    # lines
    'lines.linewidth'       : 1.4,
    'patch.edgecolor'       : 'none',
    # date formatting
    'date.autoformatter.day': '%b %d',
})


# ══════════════════════════════════════════════════════════════════════════
# Axes helpers
# ══════════════════════════════════════════════════════════════════════════

def apply_ax_style(ax: plt.Axes, grid_axis: str = 'y') -> plt.Axes:
    """
    Apply board-report-consistent dark styling to any axes object.
    Call after creating the axes, before plotting.
    """
    ax.set_facecolor(C['bg2'])
    ax.tick_params(colors=C['muted'], labelsize=FONT['body'], length=0)
    for spine in ax.spines.values():
        spine.set_color(C['border'])
        spine.set_linewidth(0.6)
    ax.grid(True, axis=grid_axis, color=C['border'], linewidth=0.4, alpha=0.5)
    return ax


def remove_spines(ax: plt.Axes, which: list[str] | None = None) -> None:
    """Hide spines. Default removes all four."""
    sides = which or ['top', 'right', 'left', 'bottom']
    for side in sides:
        ax.spines[side].set_visible(False)


def section_title(ax: plt.Axes, title: str, fontsize:int=FONT['section'], pad:int=6) -> None:
    """Cyan left-aligned bold section title — matches board_report._section_title."""
    ax.set_title(
        title,
        fontsize=fontsize,
        fontweight='bold',
        color=C['cyan'],
        pad=pad,
        loc='left',
    )


def section_title_with_date(ax: plt.Axes, title: str, valuation_date: str | None = None,
                             fontsize: int = FONT['section']) -> None:
    """Cyan left-aligned bold section title with optional gray date subtitle."""
    ax.set_title(
        title,
        fontsize=fontsize,
        fontweight='bold',
        color=C['cyan'],
        pad=10,
        loc='left',
    )
    if valuation_date:
        # Use figure-level subtitle for date (cleaner positioning)
        fig = ax.get_figure()
        fig.suptitle(
            f'As of {valuation_date}',
            fontsize=FONT['subtitle'],
            fontweight='normal',
            color=C['dim'],
            x=0.01,
            y=0.98,
            ha='left',
            va='top',
        )


def date_xaxis(ax: plt.Axes, fmt: str = '%b %d') -> None:
    """Apply a clean date formatter to the x-axis."""
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter(fmt))
    ax.tick_params(axis='x', colors=C['muted'], labelsize=FONT['tiny'])


# ══════════════════════════════════════════════════════════════════════════
# Figure-level helpers
# ══════════════════════════════════════════════════════════════════════════

def fig_header(
    fig: plt.Figure,
    title: str,
    subtitle: str = '',
    watermark: bool = True,
) -> None:
    """
    Add the board-report header band to a figure.
    Title top-left in bold monospace, subtitle below in muted,
    optional INTERNAL watermark top-right.
    Matches board_report._fig().
    """
    fig.patch.set_facecolor(C['bg'])

    fig.text(
        0.03, 0.96, title,
        fontsize=FONT['title'], fontweight='bold',
        color=C['text'], va='top', fontfamily='monospace',
    )

    if subtitle:
        ts = datetime.today().strftime('%Y-%m-%d')
        fig.text(
            0.03, 0.93,
            f'{subtitle}  ·  Generated: {ts}',
            fontsize=FONT['subtitle'], color=C['muted'], va='top',
        )

    if watermark:
        fig.text(
            0.97, 0.96,
            'INTERNAL — BOARD & RISK COMMITTEE ONLY',
            fontsize=FONT['watermark'], color=C['amber'],
            va='top', ha='right', fontweight='bold',
        )
        fig.text(
            0.97, 0.93,
            'NOT ANNEX IV  ·  NOT AN INVESTOR REPORT',
            fontsize=FONT['watermark'], color=C['dim'],
            va='top', ha='right',
        )

    # thin separator line
    fig.add_artist(plt.Line2D(
        [0.03, 0.97], [0.915, 0.915],
        transform=fig.transFigure,
        color=C['border'], linewidth=0.6,
    ))


def fig_footer(fig: plt.Figure, text: str) -> None:
    """Add a small footer disclaimer at the bottom of a figure."""
    fig.text(
        0.03, 0.025, text,
        fontsize=FONT['footer'], color=C['dim'], va='bottom',
    )

def sup_title(fig: plt.Figure, title: str, fontsize=FONT['section']) -> None:
    fig.suptitle(
        title,
        fontsize=fontsize,
        # The resolved sans-serif font provides no 900 (black) weight, so
        # matplotlib silently falls back to 700 and emits a findfont warning.
        # 'bold' (700) renders identically without the warning.
        fontweight='bold',
        color=C['cyan'],
        x=0.01,
        ha='left',
    )


# ══════════════════════════════════════════════════════════════════════════
# Annotation helpers
# ══════════════════════════════════════════════════════════════════════════

def callout_box(ax: plt.Axes, text: str, loc: str = 'upper right') -> None:
    """
    Monospace info box in the corner of an axes.
    Matches the metric callout boxes in board_report._page_var().
    loc: 'upper right' | 'upper left' | 'lower right' | 'lower left'
    """
    locs = {
        'upper right': (0.99, 0.97, 'right', 'top'),
        'upper left' : (0.01, 0.97, 'left',  'top'),
        'lower right': (0.99, 0.03, 'right', 'bottom'),
        'lower left' : (0.01, 0.03, 'left',  'bottom'),
    }
    x, y, ha, va = locs.get(loc, locs['upper right'])
    ax.text(
        x, y, text,
        transform=ax.transAxes,
        fontsize=FONT['callout'], color=C['muted'],
        va=va, ha=ha, fontfamily='monospace',
        bbox=dict(
            facecolor=C['bg3'], edgecolor=C['border'],
            boxstyle='round,pad=0.4', alpha=0.9,
        ),
    )


def threshold_vline(ax: plt.Axes, x, label: str = '') -> None:
    """Amber dashed vertical threshold line."""
    ax.axvline(x, color=C['amber'], linewidth=1.2, linestyle='--', alpha=0.85, zorder=5)
    if label:
        ax.text(x, ax.get_ylim()[1], f' {label}',
                fontsize=FONT['tiny'], color=C['amber'], va='top')


def threshold_hline(ax: plt.Axes, y, label: str = '') -> None:
    """Amber dashed horizontal threshold line."""
    ax.axhline(y, color=C['amber'], linewidth=1.2, linestyle='--', alpha=0.85, zorder=5)
    if label:
        ax.text(ax.get_xlim()[0], y, f' {label}',
                fontsize=FONT['tiny'], color=C['amber'], va='bottom')


def breach_fill(ax: plt.Axes, dates, values, limit) -> None:
    """
    Red shaded fill above a breach threshold.
    Matches board_report._page_var() breach shading.
    """
    import numpy as np
    breach_mask = values > limit
    if breach_mask.any():
        ax.fill_between(
            dates, values, limit,
            where=breach_mask,
            color=C['red'], alpha=0.25,
        )


# ══════════════════════════════════════════════════════════════════════════
# Colour utilities
# ══════════════════════════════════════════════════════════════════════════

def pct_color(v: float) -> str:
    """Green for positive or zero, red for negative."""
    return C['green'] if v >= 0 else C['red']


def rag_color(rag: str) -> str:
    """RAG string to colour. Returns muted grey for unknown values."""
    return RAG_COLORS.get(rag, C['muted'])


def util_color(utilisation: float) -> str:
    """
    Utilisation ratio (0–1+) to traffic-light colour.
    >1.0 = red, >0.75 = amber, else green.
    Matches board_report VaR utilisation colouring.
    """
    if utilisation > 1.0:
        return C['red']
    if utilisation > 0.75:
        return C['amber']
    return C['green']


def liq_color(actual: float, threshold: float) -> str:
    """Green if actual >= threshold, red otherwise."""
    return C['green'] if actual >= threshold else C['red']


# ══════════════════════════════════════════════════════════════════════════
# Table cell helper  (matches board_report._cell / _cc pattern)
# ══════════════════════════════════════════════════════════════════════════

def table_cell(
    ax: plt.Axes,
    x: float, y: float,
    w: float, h: float,
    text: str,
    bg: str,
    fg: str,
    bold: bool = False,
    align: str = 'center',
    fontsize: float | None = None,
) -> None:
    """
    Draw a single table cell (rectangle + text) on an axes.
    Coordinates are in axes data units (0–1 if ax has no data).
    Matches the _cell() pattern used in board_report.py.
    """
    fs = fontsize or FONT['table_body']
    ax.add_patch(Rectangle(
        (x, y), w - 0.003, h - 0.008,
        facecolor=bg, edgecolor=C['border'],
        linewidth=0.5, zorder=2,
    ))
    ha_map = {'left': 'left', 'right': 'right', 'center': 'center'}
    ha = ha_map.get(align, 'center')
    xoff = 0.005 if align == 'left' else (-0.005 if align == 'right' else w / 2)
    ax.text(
        x + xoff, y + h / 2 - 0.004, text,
        ha=ha, va='center',
        fontsize=fs, color=fg,
        fontweight='bold' if bold else 'normal',
        zorder=3,
    )