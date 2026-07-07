"""
Liquidity profile plotting utilities.
Visualizes liquidity bucket breakdown and concentration.
"""

import matplotlib.pyplot as plt
from fund_risk_workflow.ui.plot_style import C, ACCENT, FONT
from fund_risk_workflow.ui.nb_utils import save_fig


def plot_liquidity_profile(bucket_df, fund_id, metric='pct_nav_abs', valuation_date: str | None = None, export_id: str | None = None):
    """
    Plot liquidity profile — exposure by bucket with value labels.

    Parameters
    ----------
    bucket_df : pd.DataFrame
        Liquidity bucket breakdown with columns:
        - liquidity_bucket : str
        - pct_nav_abs : float (absolute exposure % NAV)
        - pct_nav_signed : float (signed exposure % NAV)
    fund_id : str
        Fund identifier for file naming
    metric : str, optional
        Column to plot ('pct_nav_abs' or 'pct_nav_signed'). Default 'pct_nav_abs'
    valuation_date : str, optional
        Valuation date for subtitle

    Returns
    -------
    fig, ax
        Matplotlib figure and axes
    """

    fig, ax = plt.subplots(figsize=(7, 3))
    fig.subplots_adjust(top=0.88)

    bars = ax.bar(
        bucket_df['liquidity_bucket'],
        bucket_df[metric],
        color=ACCENT,
        alpha=0.85,
        width=0.5,
    )

    ax.axhline(0, color=C['dim'], lw=0.8)
    ax.set_ylabel('Absolute Exposure (% NAV)', fontsize=9)

    # Main title as figure suptitle
    fig.suptitle(
        'Liquidity Profile — Absolute Exposure by Bucket',
        fontsize=14,
        fontweight='bold',
        color=C['cyan'],
        ha='left',
        x=0.03,
        y=0.98,
    )

    # Valuation date as figure text (below suptitle)
    if valuation_date:
        fig.text(
            0.03, 0.9,
            f'As of {valuation_date}',
            fontsize=9.5,
            color=C['muted'],
            va='top',
        )

    # Label bars with values > 2%
    for bar, val in zip(bars, bucket_df[metric]):
        if val > 2:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                val / 2,
                f'{val:.1f}%',
                ha='center',
                va='center',
                fontsize=8,
                color='white',
                fontweight='bold',
            )

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    if export_id is not None:
        from pathlib import Path
        from fund_risk_workflow.ui.nb_utils import _slugify, _get_project_root
        title_slug = _slugify('Liquidity profile')
        filename = f'{export_id}_{title_slug}'
        out_dir = _get_project_root() / 'fig' / f'{fund_id}_liquidity'
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f'{filename}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    else:
        save_fig(fig, fund_id, "04. Liquidity buckets")

    plt.show()

    return fig, ax
