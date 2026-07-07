"""
VaR backtest plotting utility.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from fund_risk_workflow.ui.plot_style import C, ACCENT, ACCENT2, section_title, FONT
from fund_risk_workflow.ui.nb_utils import save_fig


def plot_var_backtest(dates, returns, var_hist, fund_id, title=None, zone=None,
                      kupiec_pvalue=None, christoffersen_pvalue=None, valuation_date: str | None = None,
                      confidence_level: str = "99%", lookback_days: int = 250, holding_period_days: int = 1,
                      export_id: str | None = None):
    """
    Plot VaR backtest — daily P&L vs VaR limit with breach highlighting.

    Parameters
    ----------
    dates : pd.Series or array-like
        Trading dates
    returns : pd.Series or array-like
        Daily P&L returns (decimal, e.g. 0.01 = 1%)
    var_hist : pd.Series or array-like
        VaR threshold (decimal, e.g. 0.02 = 2%)
    fund_id : str
        Fund identifier for filename
    title : str, optional
        Plot title. If None, uses 'VaR Backtest — {fund_id}'
    zone : str, optional
        ESMA zone ('Green', 'Amber', 'Red') to include in title
    kupiec_pvalue : float, optional
        Kupiec POF test p-value (0-1)
    christoffersen_pvalue : float, optional
        Christoffersen test p-value (0-1)
    valuation_date : str, optional
        Valuation date for subtitle metadata
    confidence_level : str, optional
        Confidence level (e.g. '99%'). Default: '99%'
    lookback_days : int, optional
        Historical lookback period in days. Default: 250
    holding_period_days : int, optional
        VaR holding period in days. Default: 1

    Returns
    -------
    fig, ax
        Matplotlib figure and axes
    """
    # Convert to numpy arrays
    returns_arr = np.asarray(pd.to_numeric(returns, errors='coerce'))
    var_arr = np.asarray(pd.to_numeric(var_hist, errors='coerce'))
    x_axis = np.arange(len(returns_arr))

    # Increase figure size for legend outside and stats below
    fig, ax = plt.subplots(figsize=(10, 5.5))

    ax.plot(x_axis, returns_arr * 100,
            color=C['muted'], lw=0.9,
            label='Daily P&L', alpha=0.7)
    ax.plot(x_axis, -var_arr * 100,
            color=ACCENT, lw=1.2,
            label='99% VaR (historical)')

    # Highlight breaches
    breaches = returns_arr < -var_arr
    n_breaches = breaches.sum()
    ax.scatter(x_axis[breaches], returns_arr[breaches] * 100,
               color=ACCENT2, s=10, zorder=5,
               label=f'Breaches ({n_breaches})')

    # Main title (suptitle) — only basic title, no metadata
    suptitle_text = f'VaR Backtest — {fund_id}'
    if zone:
        suptitle_text += f' — Zone: {zone}'

    fig.suptitle(
        suptitle_text,
        fontsize=14,
        fontweight='bold',
        color=C['cyan'],
        ha='left',
        x=0.03,
    )

    # Metadata as figure text (below suptitle)
    if valuation_date:
        fig.text(
            0.03, 0.935,
            f'Computation Date {valuation_date} | {confidence_level} confidence | {lookback_days} d lookback | {holding_period_days} day VaR',
            fontsize=11,
            color=C['muted'],
            va='top',
        )

    # Y-axis formatting: show percentages on tick labels
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: '{:.0f}%'.format(y)))
    ax.set_ylabel('Daily P&L / VaR', fontsize=9)
    ax.set_xlabel('Trading Days', fontsize=9)

    # Legend outside on right, top-aligned with transparent rounded box
    legend = ax.legend(fontsize=10, loc='upper left', bbox_to_anchor=(1.02, 1), frameon=True)
    legend_bg = legend.get_frame()
    legend_bg.set_facecolor('#f5f5f5')
    legend_bg.set_alpha(0.07)
    legend_bg.set_edgecolor('#cccccc')
    legend_bg.set_linewidth(0.8)
    legend_bg.set_boxstyle('round,pad=0.5')

    # Add test results in clean cards below legend (same size as legend box)
    if kupiec_pvalue is not None or christoffersen_pvalue is not None:
        from matplotlib.patches import FancyBboxPatch

        card_y = 0.65  # Start position for test cards
        box_width = 0.18  # Width to match legend box
        box_height = 0.18  # Height to encompass all elements

        # Kupiec test card
        if kupiec_pvalue is not None:
            kupiec_result = 'PASS' if kupiec_pvalue > 0.05 else 'FAIL'
            kupiec_color = '#3d7f1f' if kupiec_pvalue > 0.05 else '#8b0000'

            # Background box (same size as legend)
            box = FancyBboxPatch((1.05, card_y - box_height), box_width, box_height,
                                boxstyle='round,pad=0.02', transform=ax.transAxes,
                                facecolor='#f5f5f5', alpha=0.07, edgecolor='#cccccc', linewidth=0.8)
            ax.add_patch(box)

            # Text elements inside box
            ax.text(1.07, card_y - 0.01, 'Kupiec POF', transform=ax.transAxes,
                   fontsize=9, verticalalignment='top', family='sans-serif', color=C['muted'])
            ax.text(1.07, card_y - 0.07, f'p={kupiec_pvalue:.4f}', transform=ax.transAxes,
                   fontsize=8, verticalalignment='top', family='sans-serif', color=C['muted'])
            ax.text(1.07, card_y - 0.13, kupiec_result, transform=ax.transAxes,
                   fontsize=9, verticalalignment='top', family='sans-serif',
                   weight='semibold', color=kupiec_color)

            card_y -= 0.25

        # Christoffersen test card
        if christoffersen_pvalue is not None:
            chris_result = 'PASS' if christoffersen_pvalue > 0.05 else 'FAIL'
            chris_color = '#3d7f1f' if christoffersen_pvalue > 0.05 else '#8b0000'

            # Background box (same size as legend)
            box = FancyBboxPatch((1.05, card_y - box_height), box_width, box_height,
                                boxstyle='round,pad=0.02', transform=ax.transAxes,
                                facecolor='#f5f5f5', alpha=0.07, edgecolor='#cccccc', linewidth=0.8)
            ax.add_patch(box)

            # Text elements inside box
            ax.text(1.07, card_y - 0.01, 'Christoffersen', transform=ax.transAxes,
                   fontsize=9, verticalalignment='top', family='sans-serif', color=C['muted'])
            ax.text(1.07, card_y - 0.07, f'p={christoffersen_pvalue:.4f}', transform=ax.transAxes,
                   fontsize=8, verticalalignment='top', family='sans-serif', color=C['muted'])
            ax.text(1.07, card_y - 0.13, chris_result, transform=ax.transAxes,
                   fontsize=9, verticalalignment='top', family='sans-serif',
                   weight='semibold', color=chris_color)

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    if export_id is not None:
        from pathlib import Path
        from fund_risk_workflow.ui.nb_utils import _slugify, _get_project_root
        title_slug = _slugify('VaR backtest')
        filename = f'{export_id}_{title_slug}'
        out_dir = _get_project_root() / 'fig' / fund_id
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f'{filename}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    else:
        save_fig(fig, fund_id, "VaR backtest")

    plt.show()

    return fig, ax
