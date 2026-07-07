"""
Reusable plotting utilities for fund analytics visualizations.
"""

import matplotlib.pyplot as plt
import pandas as pd
from fund_risk_workflow.ui.plot_style import C, FONT
from fund_risk_workflow.ui.nb_utils import save_fig

# Default colors and settings
DEFAULT_ACCENT_POS = C['blue']    # positive values
DEFAULT_ACCENT_NEG = C['red']     # negative values
DEFAULT_DPI = 150


def compute_breakdown(df: pd.DataFrame, group_by: str = 'asset_class') -> pd.DataFrame:
    """
    Compute asset class (or other grouping) breakdown with counts and weights.

    Parameters
    ----------
    df : pd.DataFrame
        Risk DataFrame with columns: group_by, market_value_eur, isin.
    group_by : str
        Column to group by. Default: 'asset_class'.

    Returns
    -------
    pd.DataFrame
        Breakdown with columns: market_value_eur, n_positions, weight_pct.
        Sorted by market_value_eur descending.
    """
    nav = float(df['market_value_eur'].sum())

    breakdown = df.groupby(group_by).agg(
        market_value_eur=('market_value_eur', 'sum'),
        n_positions=('isin', 'count'),
    ).sort_values('market_value_eur', ascending=False)

    breakdown['weight_pct'] = breakdown['market_value_eur'] / nav * 100

    return breakdown


def plot_breakdown_horizontal(df_or_breakdown: pd.Series | pd.DataFrame,
                               title: str,
                               figsize: tuple = (6, 2),
                               group_by: str = 'asset_class',
                               fund_id: str | None = None,
                               filename: str | None = None,
                               valuation_date: str | None = None) -> None:
    """
    Plot a horizontal bar chart for breakdown data (e.g., asset class, sector weights).

    Parameters
    ----------
    df_or_breakdown : pd.DataFrame or pd.Series
        Either a risk DataFrame (columns: asset_class, market_value_eur, etc.) to group and aggregate,
        or a pre-computed breakdown Series/DataFrame with 'weight_pct' column.
    title : str
        Chart title.
    figsize : tuple
        Figure size (width, height). Default: (6, 2).
    group_by : str
        Column to group by if df_or_breakdown is a risk DataFrame. Default: 'asset_class'.
    fund_id : str, optional
        Fund ID for saving figure. If provided with filename, figure is saved.
    filename : str, optional
        Filename for saving figure. If provided with fund_id, figure is saved.

    Returns
    -------
    None
        Displays plot via plt.show().
    """
    # Compute breakdown from risk_df
    if 'market_value_eur' in df_or_breakdown.columns:
        breakdown_df = compute_breakdown(df_or_breakdown, group_by=group_by)
        breakdown = breakdown_df['weight_pct']
    else:
        # Assume it's already a breakdown Series/DataFrame
        breakdown = df_or_breakdown
        if isinstance(breakdown, pd.DataFrame):
            # Extract weight_pct or first numeric column
            if 'weight_pct' in breakdown.columns:
                breakdown = breakdown['weight_pct']
            else:
                for col in breakdown.columns:
                    if pd.api.types.is_numeric_dtype(breakdown[col]):
                        breakdown = breakdown[col]
                        break

    fig, ax = plt.subplots(figsize=figsize)
    colors = [DEFAULT_ACCENT_NEG if v < 0 else DEFAULT_ACCENT_POS for v in breakdown]

    bars = ax.barh(breakdown.index, breakdown, color=colors, height=0.45, alpha=0.85)

    ax.set_xlabel('Weight (% NAV)', fontsize=9)
    ax.set_xlim(0, breakdown.max() * 1.1)

    # Main title as figure suptitle
    fig.suptitle(
        title,
        fontsize=11,
        fontweight='bold',
        color=C['cyan'],
        ha='left',
        x=0.03,
    )

    # Valuation date as axes title (below suptitle)
    if valuation_date:
        ax.set_title(
            f'As of {valuation_date}',
            fontsize=9.5,
            fontweight='normal',
            color=C['muted'],
            loc='left',
            pad=0,
        )

    # Add value labels on bars
    for bar, val in zip(bars, breakdown):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                f'{val:.1f}%', va='center', fontsize=7)

    ax.grid(False)
    plt.tight_layout(rect=[0, 0, 1, 1.05])

    # Save figure if both fund_id and filename provided
    if fund_id is not None and filename is not None:
        save_fig(fig, fund_id, filename, dpi=DEFAULT_DPI)

    plt.show()
