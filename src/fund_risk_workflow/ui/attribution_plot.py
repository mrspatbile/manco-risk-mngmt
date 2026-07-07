"""
P&L attribution plotting utilities.
Visualizes daily factor decomposition (equity, rates, FX, residual).
"""

import matplotlib.pyplot as plt
from fund_risk_workflow.ui.plot_style import C, ACCENT, ACCENT2, ACCENT3, FONT
from fund_risk_workflow.ui.nb_utils import save_fig


def plot_attribution_cumsum(attr_cumsum, fund_id, valuation_date: str | None = None, export_id: str | None = None):
    """
    Plot cumulative P&L attribution by risk factor.

    Parameters
    ----------
    attr_cumsum : pd.DataFrame
        Cumulative attribution with columns:
        pnl_equity, pnl_rates, pnl_fx, pnl_residual (in EUR MM)
    fund_id : str
        Fund identifier for plot title
    valuation_date : str, optional
        Valuation date for subtitle

    Returns
    -------
    fig, ax
        Matplotlib figure and axes
    """

    fig, ax = plt.subplots(figsize=(11, 5))

    ax.plot(
        attr_cumsum.index,
        attr_cumsum['pnl_equity'],
        color=ACCENT,
        linewidth=1.5,
        label='Equity',
    )
    ax.plot(
        attr_cumsum.index,
        attr_cumsum['pnl_rates'],
        color=ACCENT2,
        linewidth=1.5,
        label='Rates',
    )
    ax.plot(
        attr_cumsum.index,
        attr_cumsum['pnl_fx'],
        color=ACCENT3,
        linewidth=1.5,
        label='FX',
    )
    ax.plot(
        attr_cumsum.index,
        attr_cumsum['pnl_residual'],
        color=C['red'],
        linewidth=1.0,
        linestyle='--',
        label='Residual',
    )

    ax.axhline(0, color='white', linewidth=0.5, linestyle='--')
    ax.set_ylabel('Cumulative P&L (EUR MM)')

    # Main title as figure suptitle
    fig.suptitle(
        f'Cumulative P&L Attribution by Risk Factor — {fund_id}',
        fontsize=14,
        fontweight='bold',
        color=C['cyan'],
        ha='left',
        x=0.03,
    )

    # Valuation date as figure text (below suptitle)
    if valuation_date:
        fig.text(
            0.03, 0.93,
            f'Computation Date {valuation_date}',
            fontsize=11,
            color=C['muted'],
            va='top',
        )

    ax.legend(fontsize=9)
    plt.tight_layout(rect=[0, 0, 1, 0.97])

    if export_id is not None:
        from pathlib import Path
        from fund_risk_workflow.ui.nb_utils import _slugify, _get_project_root
        title_slug = _slugify('P&L attribution')
        filename = f'{export_id}_{title_slug}'
        out_dir = _get_project_root() / 'fig' / fund_id
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f'{filename}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    else:
        save_fig(fig, fund_id, "05. PnL attribution")

    plt.show()

    return fig, ax
