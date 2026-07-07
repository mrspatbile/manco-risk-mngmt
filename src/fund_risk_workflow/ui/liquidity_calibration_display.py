"""Display helpers for liquidity calibration and LMT analysis.

Renders investor base summaries, redemption scenarios, and LMT trigger analysis.
"""

from IPython.display import display, HTML
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from fund_risk_workflow.ui.plot_style import C, ACCENT, ACCENT2, ACCENT3, apply_ax_style, section_title
from fund_risk_workflow.ui.print_html_utils import display_dark_table


def display_fund_liquidity_overview(
    fund_id: str,
    engine,
    export_id: str | None = None,
):
    """Display fund overview combined with liquidity monitoring parameters.

    Single table showing fund identity + liquidity monitoring thresholds.

    Parameters
    ----------
    fund_id : str
        Fund identifier
    engine : sqlalchemy.engine
        Database engine
    export_id : str, optional
        If provided, save rendered output as PNG.
    """
    from fund_risk_workflow.data.reference_data import load_fund_profile, load_rmp, load_liquidity_calibration_inputs

    # Load fund profile and risk policy
    fund_profile = load_fund_profile(fund_id)
    rmp = load_rmp(fund_id)

    rows = []
    highlight_indices = []

    # Section 1: Fund Overview
    highlight_indices.append(len(rows))
    rows.append({"Property": "Fund Overview", "Value": ""})

    fund_info = {
        "Fund Name": fund_profile.get("fund_name", fund_id),
        "Type": fund_profile.get("fund_type", "—"),
        "Strategy": fund_profile.get("strategy", "—"),
        "Currency": fund_profile.get("currency", "EUR"),
        "Domicile": fund_profile.get("domicile", "—"),
        "Regulator": fund_profile.get("regulator", "—"),
    }
    for key, value in fund_info.items():
        rows.append({"Property": key, "Value": value})

    # Section 2: Liquidity Monitoring
    highlight_indices.append(len(rows))
    rows.append({"Property": "Liquidity Monitoring", "Value": ""})

    # Combine from risk_policy and liquidity_calibration_inputs
    liq_monitoring = rmp.get("liquidity_monitoring", {})
    contractual = {}
    try:
        calib = load_liquidity_calibration_inputs(fund_id)
        contractual = calib.get("contractual_terms", {})
    except Exception:
        pass

    liq_info = {
        "Redemption Frequency": contractual.get("redemption_terms", "—"),
        "Notice Period": f"{contractual.get('notice_period_days', '—')} days",
        "Liquidity Profile": contractual.get("liquidity_profile", "—"),
        "Stress Window": f"{liq_monitoring.get('stress_window_days', '—')} days",
        "Pct ADV": f"{liq_monitoring.get('pct_adv', '—')*100:.0f}%" if isinstance(liq_monitoring.get('pct_adv'), (int, float)) else "—",
    }
    for key, value in liq_info.items():
        rows.append({"Property": key, "Value": value})

    df = pd.DataFrame(rows)

    html = display_dark_table(
        df,
        caption=f"Fund Liquidity Overview | {fund_profile.get('fund_name', fund_id)}",
        col_align_override={"Property": "left", "Value": "left"},
        col_widths={"Property": "240px", "Value": "250px"},
        highlight_rows=highlight_indices,
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Fund Liquidity Overview')
        filename = f'{export_id}_{title_slug}'
        save_html_as_png(html, fund_id, filename, folder_suffix='_liquidity')


def display_top_investors(
    investor_base: dict,
    fund_id: str,
    valuation_date: str,
    top_n: int = 5,
    export_id: str | None = None,
):
    """Display top N investors by AUM.

    Parameters
    ----------
    investor_base : dict
        Investor register from investors.json with 'investors' list.
    fund_id : str
        Fund identifier.
    valuation_date : str
        Valuation date (e.g., '2026-03-31').
    top_n : int, default 5
        Number of top investors to display.
    export_id : str, optional
        If provided, save rendered output as PNG.
    """
    from fund_risk_workflow.computation.liquidity_calibration import summarize_investor_base_by_type
    import pandas as pd

    nav = investor_base.get('target_nav_eur', 1.0)
    investors = investor_base.get('investors', [])

    if not investors:
        display(HTML("<div style='color: #999; font-size: 12px;'>No investor data available.</div>"))
        return

    # Convert to dataframe and filter out "Remaining" aggregates
    df_investors = pd.DataFrame(investors)
    df_investors = df_investors[
        ~(df_investors['investor_id'].str.contains('REM', na=False, case=False) |
          df_investors['investor_name'].str.lower().str.contains('remaining', na=False))
    ]

    # Sort by nav_pct and get top N
    df_top = df_investors.nlargest(top_n, 'nav_pct')[['investor_name', 'investor_type', 'nav_pct']].copy()

    # Format for display
    df_top['aum_eur'] = df_top['nav_pct'] * nav
    df_top['nav_pct_display'] = df_top['nav_pct'].apply(lambda x: f'{x*100:.1f}%')
    df_top['aum_display'] = df_top['aum_eur'].apply(lambda x: f'€{x/1e6:.1f}m')

    display_df = df_top[['investor_name', 'investor_type', 'nav_pct_display', 'aum_display']].copy()
    display_df.columns = ['Investor', 'Type', '% NAV', 'AUM (EUR)']


    # Build metadata with valuation date (like display_redemption_stress)
    metadata_str = f'{valuation_date}' if valuation_date else ''

    # Display table
    html = display_dark_table(
        display_df,
        caption=f'Top {top_n} Investors | {fund_id}',
        date_str=metadata_str,
        col_align_override={'Investor': 'left', 'Type': 'left', '% NAV': 'right', 'AUM (EUR)': 'right'},
        col_widths={'Investor': '150px', 'Type': '100px', '% NAV': '100px', 'AUM (EUR)': '100px'},
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify(f'Top {top_n} Investors')
        filename = f'{export_id}_{title_slug}'
        save_html_as_png(html, fund_id, filename, folder_suffix='_liquidity')


def display_investor_base(
    investor_base: dict,
    fund_id: str,
    valuation_date: str,
    export_id: str | None = None,
    folder_suffix: str | None = None,
):
    """Display investor base summary table.

    Parameters
    ----------
    investor_base : dict
        Investor register from investors.json with 'investors' list.

    fund_id : str
        Fund identifier.

    valuation_date : str
        Valuation date (e.g., '2026-03-31').

    export_id : str, optional
        If provided, save rendered output as PNG.
    """
    from fund_risk_workflow.computation.liquidity_calibration import summarize_investor_base_by_type

    summary_df = summarize_investor_base_by_type(investor_base)

    if summary_df.empty:
        display(HTML("<div style='color: #999; font-size: 12px;'>No investor data available.</div>"))
        return

    # Sort by AUM descending
    summary_df = summary_df.sort_values('aum_eur', ascending=False).reset_index(drop=True)

    # Format display
    display_df = summary_df.copy()
    display_df['count'] = display_df['count'].astype(int)
    display_df['aum_pct'] = display_df['aum_pct'].apply(lambda x: f'{x*100:.1f}%')
    display_df['aum_eur'] = display_df['aum_eur'].apply(lambda x: f'€{x/1e6:.1f}m')

    metadata_str = f'{valuation_date}' if valuation_date else ''
    
    html = display_dark_table(
        display_df,
        caption=f'Investor Base Summary | {fund_id}',
        date_str=metadata_str,
        col_align_override={'count': 'right', 'aum_pct': 'right', 'aum_eur': 'right'},
        col_widths={'investor_type': '100px', 'count': '100px', 'aum_pct': '100px', 'aum_eur': '100px'},
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify(f'Investor Type Breakdown')
        filename = f'{export_id}_{title_slug}'
        save_html_as_png(html, fund_id, filename, folder_suffix=folder_suffix)



def display_redemption_scenarios(
    scenarios_data: dict,
    fund_id: str,
    valuation_date: str,
    export_id: str | None = None,
):
    """Display calibrated redemption scenarios.

    Parameters
    ----------
    scenarios_data : dict
        Output from compute_redemption_scenarios() with keys:
        - 'redemption_scenarios': list of scenario dicts
        - 'largest_investor_name', 'largest_investor_pct'
        - 'weighted_normal_rate', 'weighted_stress_rate'

    fund_id : str
        Fund identifier.

    valuation_date : str
        Valuation date.

    export_id : str, optional
        If provided, save rendered output as PNG.
    """
    from fund_risk_workflow.computation.liquidity_calibration import format_scenario_for_display

    scenarios = scenarios_data.get('redemption_scenarios', [])
    largest_investor = scenarios_data.get('largest_investor_name', '—')
    largest_investor_pct = scenarios_data.get('largest_investor_pct', 0)

    rows = []
    for scenario in scenarios:
        name = scenario.get('name', '')
        pct = scenario.get('redemption_pct')

        if name == 'Largest investor':
            # Special formatting for largest investor
            if isinstance(pct, (int, float)):
                display_pct = f'{pct*100:.1f}% ({largest_investor})'
            else:
                display_pct = '—'
        else:
            if isinstance(pct, (int, float)):
                display_pct = f'{pct*100:.1f}%'
            else:
                display_pct = '—'

        rows.append({
            'Scenario': name,
            'Redemption': display_pct,
        })

    df = pd.DataFrame(rows)

    html = display_dark_table(
        df,
        caption=f'Redemption Scenarios | {fund_id}',
        col_align_override={'Redemption': 'right'},
        col_widths={'Scenario': '180px', 'Redemption': '200px'},
        return_html=True,
    )

    display(HTML(html))


def display_lmt_parameters(
    calibration_inputs: dict,
    fund_id: str,
    export_id: str | None = None,
):
    """Display LMT parameters as styled HTML table from liquidity calibration inputs.

    Parameters
    ----------
    calibration_inputs : dict
        Raw calibration data from load_investor_and_calibration_data().
    fund_id : str
        Fund identifier.
    export_id : str, optional
        If provided, save rendered output as PNG.
    """
    rows = []
    highlight_indices = []

    # Section: Contractual Terms
    highlight_indices.append(len(rows))
    rows.append({'Parameter': 'CONTRACTUAL TERMS', 'Value': ''})
    for key, val in calibration_inputs.get('contractual_terms', {}).items():
        rows.append({
            'Parameter': key.replace('_', ' ').title(),
            'Value': str(val)
        })

    # Section: Stress Assumptions
    highlight_indices.append(len(rows))
    rows.append({'Parameter': 'STRESS ASSUMPTIONS', 'Value': ''})
    for key, val in calibration_inputs.get('stress_assumptions', {}).items():
        rows.append({
            'Parameter': key.replace('_', ' ').title(),
            'Value': str(val)
        })

    # Section: LMT Calibration
    highlight_indices.append(len(rows))
    rows.append({'Parameter': 'LMT CALIBRATION', 'Value': ''})
    for key, val in calibration_inputs.get('lmt_calibration', {}).items():
        rows.append({
            'Parameter': key.replace('_', ' ').title(),
            'Value': str(val)
        })

    df = pd.DataFrame(rows)

    display_dark_table(
        df,
        caption=f'LMT Parameters | {fund_id}',
        date_str='',
        highlight_rows=highlight_indices,
    )

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        # Build HTML for export
        html_to_export = display_dark_table(
            df,
            caption=f'LMT Parameters | {fund_id}',
            date_str='',
            highlight_rows=highlight_indices,
            return_html=True,
        )
        title_slug = _slugify('LMT Parameters')
        filename = f'{export_id}_{title_slug}'
        save_html_as_png(html_to_export, fund_id, filename, folder_suffix='_liquidity')


def display_lmt_calibration_assumptions(
    calibration_inputs: dict,
    fund_id: str,
    export_id: str | None = None,
):
    """Display liquidity calibration assumptions as formatted table with sections.

    Parameters
    ----------
    calibration_inputs : dict
        Raw calibration data from load_investor_and_calibration_data().
    fund_id : str
        Fund identifier.
    export_id : str, optional
        If provided, save rendered output as PNG.
    """
    rows = []
    highlight_indices = []

    # Section 1: Contractual Terms
    highlight_indices.append(len(rows))
    rows.append({"Parameter": "Contractual Terms", "Value": ""})

    contractual = calibration_inputs.get('contractual_terms', {})
    for key, value in contractual.items():
        param_name = key.replace('_', ' ').title()
        rows.append({"Parameter": param_name, "Value": str(value)})

    # Section 2: Stress Assumptions
    highlight_indices.append(len(rows))
    rows.append({"Parameter": "Stress Assumptions", "Value": ""})

    stress = calibration_inputs.get('stress_assumptions', {})
    for key, value in stress.items():
        param_name = key.replace('_', ' ').title()
        if isinstance(value, float) and key == 'pct_adv':
            value_display = f'{value*100:.1f}%'
        else:
            value_display = str(value)
        rows.append({"Parameter": param_name, "Value": value_display})

    # Section 3: LMT Calibration
    highlight_indices.append(len(rows))
    rows.append({"Parameter": "LMT Calibration", "Value": ""})

    lmt_calib = calibration_inputs.get('lmt_calibration', {})
    for key, value in lmt_calib.items():
        param_name = key.replace('_', ' ').title()
        if isinstance(value, float) and '_pct' in key:
            value_display = f'{value*100:.1f}%'
        else:
            value_display = str(value)
        rows.append({"Parameter": param_name, "Value": value_display})

    df = pd.DataFrame(rows)

    html = display_dark_table(
        df,
        caption=f"Liquidity Calibration Assumptions | {fund_id}",
        col_align_override={"Parameter": "left", "Value": "left"},
        col_widths={"Parameter": "280px", "Value": "180px"},
        highlight_rows=highlight_indices,
        return_html=True,
    )

    display(HTML(html))


def display_lmt_summary(
    df_result: pd.DataFrame,
    fund_id: str,
    valuation_date: str,
    export_id: str | None = None,
):
    """Display LMT trigger summary table.

    Parameters
    ----------
    df_result : pd.DataFrame
        Result from lmt_trigger_analysis() with columns:
        month, gate_active, swing_active, suspension_active, paid_eur, deferred_eur, backlog_eur, etc.

    fund_id : str
        Fund identifier.

    valuation_date : str
        Valuation date.

    export_id : str, optional
        If provided, save rendered output as PNG.
    """
    if df_result.empty:
        display(HTML("<div style='color: #999; font-size: 12px;'>No LMT analysis available.</div>"))
        return

    # Extract key metrics
    gate_months = df_result[df_result['gate_active']]['month'].tolist()
    swing_months = df_result[df_result['swing_active']]['month'].tolist()
    suspension_months = df_result[df_result['suspension_active']]['month'].tolist()

    summary_rows = [
        ('Gate first fires (month)', gate_months[0] if gate_months else '—'),
        ('Swing first fires (month)', swing_months[0] if swing_months else '—'),
        ('Suspension triggers (month)', suspension_months[0] if suspension_months else '—'),
        ('Peak backlog (€m)', f"{df_result['backlog_eur'].max() / 1e6:.1f}"),
        ('Total paid over period (€m)', f"{df_result['paid_eur'].sum() / 1e6:.1f}"),
        ('Terminal liquid NAV (€m)', f"{df_result['liquid_nav_eur'].iloc[-1] / 1e6:.1f}"),
    ]

    df_display = pd.DataFrame(summary_rows, columns=['Metric', 'Value'])

    html = display_dark_table(
        df_display,
        caption=f'LMT Trigger Summary | {fund_id}',
        col_align_override={'Value': 'right'},
        col_widths={'Metric': '240px', 'Value': '150px'},
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('LMT Summary')
        filename = f'{export_id}_{title_slug}'
        save_html_as_png(html, fund_id, filename, folder_suffix='_liquidity')


def plot_redemption(
    df_result: pd.DataFrame,
    fund_id: str,
    valuation_date: str,
    export_id: str | None = None,
    scenario_label: str | None = None,
    gate_threshold: float | None = None,
    swing_threshold: float | None = None,
    consecutive_gate_for_suspension: int | None = None,
    redemption_model_note: str | None = None,
):
    """Plot redemptions: paid, deferred, and backlog over time.

    Parameters
    ----------
    df_result : pd.DataFrame
        Result from lmt_trigger_analysis().
    fund_id : str
        Fund identifier.
    valuation_date : str
        Valuation date.
    export_id : str, optional
        If provided, save rendered output as PNG.
    scenario_label : str, optional
        Descriptive label for the scenario (e.g., "Without LMT Effects", "With LMT Effects").
        If provided, appended to the chart title. Default None (no scenario label).
    gate_threshold : float, optional
        Gate threshold for LMT parameters display. If provided with other LMT params, shows inset.
    swing_threshold : float, optional
        Swing threshold for LMT parameters display.
    consecutive_gate_for_suspension : int, optional
        Consecutive gate threshold for LMT parameters display.
    redemption_model_note : str, optional
        Note about redemption model assumptions to display in inset. If None, uses default.
    """
    from pandas.tseries.offsets import DateOffset

    months = df_result['month'].values
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.subplots_adjust(top=0.88)

    # Generate month labels (e.g., "Jun/26", "Jul/26", ...)
    computation_date = pd.Timestamp(valuation_date)
    month_labels = [
        (computation_date + DateOffset(months=i)).strftime("%b/%y")
        for i in range(1, 13)
    ]

    # Paid redemptions: blue (on bottom)
    ax.bar(months, df_result['paid_eur'] / 1e6, color='#2563EB', label='Paid', width=0.5)

    # Deferred redemptions: blue (transparent), with hatch (on top)
    ax.bar(
        months,
        df_result['deferred_eur'] / 1e6,
        color='#2563EB',
        alpha=0.4,
        hatch='//',
        label='Deferred',
        bottom=df_result['paid_eur'] / 1e6,
        width=0.5,
        edgecolor='#2563EB',
        linewidth=0.5,
    )

    # Backlog: muted orange (outstanding balance)
    ax.plot(
        months,
        df_result['backlog_eur'] / 1e6,
        color='#D97706',
        marker='o',
        linewidth=2.5,
        label='Backlog',
    )

    ax.set_xticks(months)
    ax.set_xticklabels(month_labels, fontsize=9)
    ax.set_ylabel('EUR m', fontsize=9)
    legend = ax.legend(loc='upper right', fontsize=8, title='Redemptions', title_fontsize=8)
    legend.get_title().set_color('#9CA3AF')

    # Grid on Y-axis only
    ax.grid(True, axis='y', alpha=0.3, linestyle='-', linewidth=0.5)

    # Main title as figure suptitle
    title = 'Redemptions'
    if scenario_label:
        title = f'{title} | {scenario_label}'
    fig.suptitle(
        title,
        fontsize=14,
        fontweight='bold',
        color=C['cyan'],
        ha='left',
        x=0.03,
        y=0.98,
    )

    # Valuation date as figure text
    if valuation_date:
        fig.text(
            0.03, 0.9,
            f'Computation date {valuation_date}',
            fontsize=9.5,
            color=C['muted'],
            va='top',
        )

    # Add compact LMT inset if LMTs are active
    if gate_threshold is not None or swing_threshold is not None or consecutive_gate_for_suspension is not None:
        # Extract LMT trigger months from df_result
        gate_months = df_result[df_result['gate_active']]['month'].tolist()
        swing_months = df_result[df_result['swing_active']]['month'].tolist()
        suspension_months = df_result[df_result['suspension_active']]['month'].tolist()

        # Build compact vertical column inset with table-style alignment
        inset_lines = []

        # Section 1: LMT parameters
        inset_lines.append("LMT")
        inset_lines.append("─" * 19)
        if gate_threshold is not None:
            inset_lines.append(f"     Gate: {gate_threshold*100:.0f}%")
        if swing_threshold is not None:
            inset_lines.append(f"    Swing: {swing_threshold*100:.0f}%")
        if consecutive_gate_for_suspension is not None:
            inset_lines.append(f"     Susp: {consecutive_gate_for_suspension}m")
        inset_lines.append("")

        # Section 2: Triggered months
        inset_lines.append("Triggered")
        inset_lines.append("─" * 19)
        if gate_months:
            inset_lines.append(f"     Gate: {','.join(map(str, gate_months))}")
        else:
            inset_lines.append("     Gate: none")
        if swing_months:
            inset_lines.append(f"    Swing: {','.join(map(str, swing_months))}")
        else:
            inset_lines.append("    Swing: none")
        if suspension_months:
            inset_lines.append(f"     Susp: {','.join(map(str, suspension_months))}")
        else:
            inset_lines.append("     Susp: none")
        inset_lines.append("")

        # Section 3: Feedback
        inset_lines.append("Post-gate contagion")

        inset_text = '\n'.join(inset_lines)

        ax.text(
            0.02, 0.96, inset_text,
            transform=ax.transAxes,
            fontsize=6.0,
            ha="left",
            va="top",
            color="#9CA3AF",
            family='Helvetica Neue',
            bbox=dict(
                boxstyle="round,pad=0.70",
                facecolor="#E5E7EB",
                alpha=0.05,
                edgecolor="none",
            ),
        )

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    if export_id is not None:
        from pathlib import Path
        from fund_risk_workflow.ui.nb_utils import _slugify, _get_project_root
        title_slug = _slugify('LMT Paid Deferred Backlog')
        filename = f'{export_id}_{title_slug}'
        out_dir = _get_project_root() / 'fig' / f'{fund_id}_liquidity'
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f'{filename}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())

    plt.show()


def plot_lmt_nav_evolution(
    df_result: pd.DataFrame,
    fund_id: str,
    valuation_date: str,
    export_id: str | None = None,
    scenario_label: str | None = None,
):
    """Plot NAV evolution: liquid vs illiquid assets.

    Parameters
    ----------
    df_result : pd.DataFrame
        Result from lmt_trigger_analysis().
    fund_id : str
        Fund identifier.
    valuation_date : str
        Valuation date.
    export_id : str, optional
        If provided, save rendered output as PNG.
    scenario_label : str, optional
        Descriptive label for the scenario (e.g., "Without LMT Effects", "With LMT Effects").
        If provided, appended to the chart title. Default None (no scenario label).
    """
    from pandas.tseries.offsets import DateOffset

    months = df_result['month'].values
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.subplots_adjust(top=0.88)

    # Generate month labels (e.g., "Jun/26", "Jul/26", ...)
    computation_date = pd.Timestamp(valuation_date)
    month_labels = [
        (computation_date + DateOffset(months=i)).strftime("%b/%y")
        for i in range(1, 13)
    ]

    # NAV evolution: liquid (bright blue) and illiquid (dark blue)
    ax.stackplot(
        months,
        df_result['illiquid_nav_eur'] / 1e6,
        df_result['liquid_nav_eur'] / 1e6,
        labels=['Illiquid NAV', 'Liquid NAV'],
        colors=['#0c4a6e', '#2563EB'],  # dark blue, bright blue
        alpha=0.8,
    )
    ax.set_xticks(months)
    ax.set_xticklabels(month_labels, fontsize=9)
    ax.set_ylabel('EUR m', fontsize=9)
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc='upper right', fontsize=8)

    # Main title as figure suptitle
    title = 'NAV Evolution'
    if scenario_label:
        title = f'{title} | {scenario_label}'
    fig.suptitle(
        title,
        fontsize=14,
        fontweight='bold',
        color=C['cyan'],
        ha='left',
        x=0.03,
        y=0.98,
    )

    # Valuation date as figure text
    if valuation_date:
        fig.text(
            0.03, 0.9,
            f'Computation date {valuation_date}',
            fontsize=9.5,
            color=C['muted'],
            va='top',
        )

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    if export_id is not None:
        from pathlib import Path
        from fund_risk_workflow.ui.nb_utils import _slugify, _get_project_root
        title_slug = _slugify('LMT NAV Evolution')
        filename = f'{export_id}_{title_slug}'
        out_dir = _get_project_root() / 'fig' / f'{fund_id}_liquidity'
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f'{filename}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())

    plt.show()


def plot_lmt_flags(
    df_result: pd.DataFrame,
    fund_id: str,
    valuation_date: str,
    export_id: str | None = None,
):
    """Plot LMT trigger status matrix: Gate, Swing, Suspension by month.

    Binary status grid showing which months each LMT tool is triggered.
    Filled circles = triggered, X markers = not triggered.

    Parameters
    ----------
    df_result : pd.DataFrame
        Result from lmt_trigger_analysis().
    fund_id : str
        Fund identifier.
    valuation_date : str
        Valuation date.
    export_id : str, optional
        If provided, save rendered output as PNG.
    """
    from pandas.tseries.offsets import DateOffset

    months = df_result['month'].values
    trigger_color = '#D68632'  # Dimmed orange for triggered status
    inactive_color = '#AAB0BD'  # Muted grey for inactive

    # Tool order and positions with vertical spacing
    # Order from top to bottom: Gate, Swing, Suspension
    tool_order = ['Gate', 'Swing', 'Suspension']
    trigger_cols = ['gate_active', 'swing_active', 'suspension_active']
    y_positions = {
        'Gate': 2.8,
        'Swing': 1.4,
        'Suspension': 0.0,
    }

    # Generate month labels (e.g., "Jun/26", "Jul/26", ...)
    computation_date = pd.Timestamp(valuation_date)
    month_labels = [
        (computation_date + DateOffset(months=i)).strftime("%b/%y")
        for i in range(1, 13)
    ]

    fig, ax = plt.subplots(figsize=(8, 2))
    fig.subplots_adjust(top=0.88)

    # Faint row bands behind each tool (row bands provide all separation)
    for tool in tool_order:
        y = y_positions[tool]
        ax.axhspan(y - 0.45, y + 0.45, color='white', alpha=0.035, zorder=0)

    # Plot status markers for each tool
    for tool, col_name in zip(tool_order, trigger_cols):
        y = y_positions[tool]
        trigger_status = df_result[col_name].astype(int).values

        for month, is_active in zip(months, trigger_status):
            if is_active:
                # Filled circle for triggered
                ax.scatter(
                    month, y,
                    marker='o', s=90,
                    color=trigger_color,
                    edgecolor='white', linewidth=0.4,
                    zorder=3,
                )
            else:
                # X marker for not triggered
                ax.scatter(
                    month, y,
                    marker='x', s=35,
                    color=inactive_color,
                    alpha=0.75, linewidth=1.2,
                    zorder=2,
                )

    # Set up axes
    ax.set_yticks([y_positions[tool] for tool in tool_order])
    ax.set_yticklabels(tool_order, fontsize=12)
    ax.set_xticks(months)
    ax.set_xticklabels(month_labels, fontsize=9)
    ax.set_xlim(0.5, 12.5)
    ax.set_ylim(-0.7, 3.5)

    # Clean design: remove all spines and plot background
    ax.grid(False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.patch.set_alpha(0)  # Transparent plot background
    ax.set_axisbelow(True)

    # Main title
    fig.suptitle(
        'LMT Trigger Status Matrix',
        fontsize=14,
        fontweight='bold',
        color=C['cyan'],
        ha='left',
        x=0.03,
        y=0.98,
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    if export_id is not None:
        from pathlib import Path
        from fund_risk_workflow.ui.nb_utils import _slugify, _get_project_root
        title_slug = _slugify('LMT Trigger Status')
        filename = f'{export_id}_{title_slug}'
        out_dir = _get_project_root() / 'fig' / f'{fund_id}_liquidity'
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f'{filename}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())

    plt.show()


def plot_liquidity_profile_chart(
    funds_data: dict,
    valuation_date: str,
    bucket_order: list | None = None,
    export_id: str | None = None,
):
    """Plot liquidity bucket distribution for multiple funds.

    Parameters
    ----------
    funds_data : dict
        Dict mapping fund_id to DataFrames with liquidity buckets.
        E.g., {'UCITS_Balanced': df_with_liquidity_bucket_col}

    valuation_date : str
        Valuation date for display.

    bucket_order : list, optional
        Order of liquidity buckets. Default: ['1 day', '2-7 days', '8-30 days', '31-90 days', '91-365 days', '> 1 year']

    export_id : str, optional
        If provided, save figure to figs/.
    """
    from fund_risk_workflow.ui.nb_utils import save_fig

    if bucket_order is None:
        bucket_order = ['1 day', '2-7 days', '8-30 days', '31-90 days', '91-365 days', '> 1 year']

    fig, axes = plt.subplots(1, len(funds_data), figsize=(6 * len(funds_data), 5))
    if len(funds_data) == 1:
        axes = [axes]

    for ax, (fund_id, df) in zip(axes, funds_data.items()):
        nav = df['market_value_eur'].sum()
        bkt = (df.groupby('liquidity_bucket', observed=True)['market_value_eur']
                  .sum().reindex(bucket_order, fill_value=0.0))
        pcts = (bkt / nav * 100).values

        bars = ax.bar(range(len(bucket_order)), pcts, color=C['cyan'], width=0.6)
        ax.set_xticks(range(len(bucket_order)))
        ax.set_xticklabels(['1d', '2-7d', '8-30d', '31-90d', '91-365d', '>1yr'], fontsize=8)
        ax.set_ylabel('% of NAV', fontsize=8)
        section_title(ax, fund_id)
        ax.set_ylim(0, 115)
        for bar, pct in zip(bars, pcts):
            if pct > 2:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                        f'{pct:.0f}%', ha='center', va='bottom', fontsize=7)

    fig.suptitle('ESMA Liquidity Bucket Distribution', fontsize=12, fontweight='bold')
    plt.tight_layout()

    if export_id:
        save_fig(fig, '', export_id)

    plt.show()


def display_redemption_stress_table(
    stress_results: dict,
    valuation_date: str,
    export_id: str | None = None,
):
    """Display single-period redemption stress table.

    Parameters
    ----------
    stress_results : dict
        Dict with fund results, each containing NAV, redemption amount, liquid assets, etc.

    valuation_date : str
        Valuation date.

    export_id : str, optional
        If provided, save rendered output as PNG.
    """
    stress_rows = []
    for fund_name, result in stress_results.items():
        stress_rows.append({
            'Fund': fund_name,
            'NAV (€m)': f"{result['nav'] / 1e6:.1f}",
            'Redemption (€m)': f"{result['redemption_amount_eur'] / 1e6:.1f}",
            'Liquid Assets (€m)': f"{result['liquid_assets_eur'] / 1e6:.1f}",
            'Coverage Ratio': f"{result['coverage_ratio']:.2f}x",
            'Can Meet': '✓' if result.get('can_meet_redemption', True) else '✗',
        })

    df = pd.DataFrame(stress_rows)

    html = display_dark_table(
        df,
        caption='Redemption Stress | Single-Period Snapshot (25% NAV, 5-day notice)',
        col_align_override={'Coverage Ratio': 'right'},
        col_widths={'Fund': '150px', 'NAV (€m)': '120px', 'Coverage Ratio': '120px'},
        return_html=True,
    )

    display(HTML(html))


def display_lmt_cross_fund_summary(
    lmt_results: dict,
    valuation_date: str,
    export_id: str | None = None,
):
    """Display cross-fund LMT trigger summary.

    Parameters
    ----------
    lmt_results : dict
        Dict mapping fund_name to LMT result DataFrames.

    valuation_date : str
        Valuation date.

    export_id : str, optional
        If provided, save rendered output as PNG.
    """
    summary_rows = []
    for fname, df in lmt_results.items():
        gate_m = df[df['gate_active']]['month'].tolist()
        swing_m = df[df['swing_active']]['month'].tolist()
        susp_m = df[df['suspension_active']]['month'].tolist()
        summary_rows.append({
            'Fund': fname,
            'Gate first (month)': gate_m[0] if gate_m else '—',
            'Swing first (month)': swing_m[0] if swing_m else '—',
            'Suspension (month)': susp_m[0] if susp_m else '—',
            'Peak backlog (€m)': f"{df['backlog_eur'].max() / 1e6:.1f}",
            'Total paid (€m)': f"{df['paid_eur'].sum() / 1e6:.1f}",
        })

    df_summary = pd.DataFrame(summary_rows)

    html = display_dark_table(
        df_summary,
        caption='LMT Trigger Summary | Cross-Fund Analysis',
        col_align_override={col: 'right' for col in df_summary.columns},
        return_html=True,
    )

    display(HTML(html))


def plot_lmt_analysis(
    lmt_result: dict,
    fund_id: str,
    valuation_date: str,
    export_id: str | None = None,
    scenario_label: str | None = None,
    show_inset: bool = False,
):
    """Combined plot: Redemption Path, NAV Evolution, LMT Trigger Matrix (shared X-axis).

    Compact 3-panel view with shared month axis. Displays LMT parameters and triggered months
    in an inset box (top-left). Useful for comparing before/after LMT scenarios.

    Parameters
    ----------
    lmt_result : dict
        Result dict from lmt_trigger_analysis() containing:
        - 'df': DataFrame with columns: paid_eur, deferred_eur, backlog_eur,
          liquid_nav_eur, illiquid_nav_eur, total_nav_eur, gate_active, swing_active, suspension_active
        - 'gate_threshold': float or None
        - 'swing_threshold': float or None
        - 'consecutive_gate_for_suspension': int or None
    fund_id : str
        Fund identifier.
    valuation_date : str
        Valuation date (e.g., '2026-03-31').
    export_id : str, optional
        If provided, save rendered output as PNG to fig/{fund_id}_liquidity/.
    scenario_label : str, optional
        Scenario label for suptitle (e.g., "After LMT").
    show_inset : bool, default False
        If True, display LMT parameters and triggered months in inset box (top-left).
    """
    from pandas.tseries.offsets import DateOffset

    df_result = lmt_result['df']
    gate_threshold = lmt_result.get('gate_threshold')
    swing_threshold = lmt_result.get('swing_threshold')
    consecutive_gate_for_suspension = lmt_result.get('consecutive_gate_for_suspension')

    months = df_result['month'].values

    # Generate month labels
    computation_date = pd.Timestamp(valuation_date)
    month_labels = [
        (computation_date + DateOffset(months=i)).strftime("%b/%y")
        for i in range(1, 13)
    ]

    # Determine if LMT parameters are present
    has_lmt_params = (gate_threshold is not None or swing_threshold is not None or consecutive_gate_for_suspension is not None)

    # Create figure: 2-panel if no LMT, 3-panel if LMT present
    if has_lmt_params:
        fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True, gridspec_kw={'height_ratios': [2, 2, 1]})
        fig.subplots_adjust(hspace=0.15, top=0.93)
    else:
        fig, axes = plt.subplots(2, 1, figsize=(10, 5.6), sharex=True, gridspec_kw={'height_ratios': [2, 2]})
        fig.subplots_adjust(hspace=0.15, top=0.93)

    # Panel 1: Redemption Path
    ax = axes[0]
    ax.bar(months, df_result['paid_eur'] / 1e6, color='#2563EB', label='Paid', width=0.5)
    ax.bar(
        months,
        df_result['deferred_eur'] / 1e6,
        color='#2563EB',
        alpha=0.4,
        hatch='//',
        label='Deferred',
        bottom=df_result['paid_eur'] / 1e6,
        width=0.5,
        edgecolor='#2563EB',
        linewidth=0.5,
    )
    ax.plot(months, df_result['backlog_eur'] / 1e6, color='#D97706', marker='o', linewidth=2.5, label='Backlog')
    ax.set_ylabel('EUR m', fontsize=9)
    handles, labels = ax.get_legend_handles_labels()
    legend = ax.legend(handles, labels, loc='upper right', fontsize=8, title='Redemptions', title_fontsize=8)
    legend.get_title().set_color('#9CA3AF')
    ax.grid(True, axis='y', alpha=0.3, linestyle='-', linewidth=0.5)
    # ax.set_title('Redemption Path', fontsize=10, fontweight='normal', loc='left', color='#9CA3AF')

    # Panel 2: NAV Evolution (area plot, no lines, illiquid at bottom)
    ax = axes[1]
    ax.fill_between(months, 0, df_result['illiquid_nav_eur'] / 1e6, color='#0c4a6e', alpha=0.5, label='Illiquid NAV')
    ax.fill_between(months, df_result['illiquid_nav_eur'] / 1e6, df_result['total_nav_eur'] / 1e6, color='#2563EB', alpha=0.5, label='Liquid NAV')
    ax.set_ylabel('EUR m', fontsize=9)
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc='upper right', fontsize=8)
    ax.grid(True, axis='y', alpha=0.3, linestyle='-', linewidth=0.5)
    # ax.set_title('NAV Evolution', fontsize=10, fontweight='normal', loc='left', color='#9CA3AF')

    # Panel 3: LMT Trigger Matrix (compact, half height) — only if LMT parameters present
    if has_lmt_params:
        ax = axes[2]
        tool_order = ['Gate', 'Swing', 'Suspension']
        trigger_cols = ['gate_active', 'swing_active', 'suspension_active']
        y_positions = {'Gate': 2.8, 'Swing': 1.4, 'Suspension': 0.0}
        trigger_color = '#D68632'
        inactive_color = '#AAB0BD'

        for tool in tool_order:
            y = y_positions[tool]
            ax.axhspan(y - 0.45, y + 0.45, color='white', alpha=0.035, zorder=0)

        for tool, col_name in zip(tool_order, trigger_cols):
            y = y_positions[tool]
            trigger_status = df_result[col_name].astype(int).values
            for month, is_active in zip(months, trigger_status):
                color = trigger_color if is_active else inactive_color
                marker = 'o' if is_active else 'x'
                ax.plot(month, y, marker=marker, markersize=7, color=color, markeredgewidth=1.2)
            ax.text(0.05, y, tool, ha='right', va='center', fontsize=6, fontweight='normal', family='sans-serif', color='#9CA3AF')

        ax.set_ylim(-1, 3.5)
        ax.set_yticks([])
        ax.set_ylabel('')
        ax.grid(True, axis='x', alpha=0.2, linestyle='--', linewidth=0.5)

    # Main title (cyan, left-aligned, not bold)
    title = 'Redemption Path and NAV Evolution'
    if scenario_label:
        title = f'{title} | {scenario_label}'
    fig.suptitle(title, fontsize=12, fontweight='normal', color='#0891b2', ha='left', x=0.12, y=0.995)

    # Computation date
    if valuation_date:
        fig.text(
            0.12, 0.96,
            f'Computation date {valuation_date}',
            fontsize=9.5,
            color=C['muted'],
            va='top',
        )

    # Set x-axis labels only on bottom panel
    if has_lmt_params:
        axes[2].set_xticks(months)
        axes[2].set_xticklabels(month_labels, fontsize=9)
    else:
        axes[1].set_xticks(months)
        axes[1].set_xticklabels(month_labels, fontsize=9)

    # Add compact LMT inset if requested and LMT parameters provided
    if show_inset and has_lmt_params:
        # Extract LMT trigger months from df_result
        gate_months = df_result[df_result['gate_active']]['month'].tolist()
        swing_months = df_result[df_result['swing_active']]['month'].tolist()
        suspension_months = df_result[df_result['suspension_active']]['month'].tolist()

        # Build compact vertical column inset with table-style alignment (right-align label, left-align value)
        inset_lines = []

        # Section 1: LMT parameters
        inset_lines.append("LMT")
        inset_lines.append("─" * 16)
        if gate_threshold is not None:
            inset_lines.append(f"{'Gate':>9} {gate_threshold*100:.0f}%")
        if swing_threshold is not None:
            inset_lines.append(f"{'Swing':>9} {swing_threshold*100:.0f}%")
        if consecutive_gate_for_suspension is not None:
            inset_lines.append(f"{'Susp':>9} {consecutive_gate_for_suspension}m")
        inset_lines.append("")

        # Section 2: Triggered months
        inset_lines.append("Triggered")
        inset_lines.append("─" * 16)
        gate_val = ','.join(map(str, gate_months)) if gate_months else "none"
        swing_val = ','.join(map(str, swing_months)) if swing_months else "none"
        susp_val = ','.join(map(str, suspension_months)) if suspension_months else "none"
        inset_lines.append(f"{'Gate':>9} {gate_val}")
        inset_lines.append(f"{'Swing':>9} {swing_val}")
        inset_lines.append(f"{'Susp':>9} {susp_val}")
        inset_lines.append("")

        # Section 3: Feedback
        inset_lines.append("Post-gate feedback")

        inset_text = '\n'.join(inset_lines)

        axes[0].text(
            0.02, 0.96, inset_text,
            transform=axes[0].transAxes,
            fontsize=6.0,
            family='sans-serif',
            ha="left",
            va="top",
            color="#9CA3AF",
            bbox=dict(
                boxstyle="round,pad=0.50",
                facecolor="#3c425753",
                alpha=0.1,
                edgecolor="none",
            ),
        )

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify
        from pathlib import Path
        fig.canvas.draw()
        if scenario_label:
            title_slug = _slugify(scenario_label)
        else:
            title_slug = _slugify('LMT Analysis')
        filename = f'{export_id}_redemption_path_{title_slug}.png'
        export_dir = Path(__file__).parent.parent.parent.parent / 'fig' / f'{fund_id}_liquidity'
        export_dir.mkdir(parents=True, exist_ok=True)
        filepath = export_dir / filename
        print(f"Saving plot to: {filepath}")
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        print(f"✓ Plot saved successfully")

    plt.show()


def display_investor_redemption_inputs(
    investors_enriched: list,
    fund_id: str,
    valuation_date: str | None = None,
    export_id: str | None = None,
):
    """Display investor behavioural redemption inputs with computed weights and calibration rates.

    Parameters
    ----------
    investors_enriched : list
        List of investor dicts with type, weight, base_redemption_rate, stress_redemption_rate.
    fund_id : str
        Fund identifier.
    valuation_date : str, optional
        Valuation date for metadata (e.g., '2026-03-31').
    export_id : str, optional
        If provided, save rendered output as PNG.
    """
    from fund_risk_workflow.computation.liquidity_calibration import prepare_investor_assumptions_calibration

    display_df = prepare_investor_assumptions_calibration(investors_enriched)

    # Rename columns to multi-line headers
    display_df.columns = [
        'Calibration\nCategory',
        'NAV\nWeight',
        'Base\nRedemption Rate',
        'Stress\nRedemption Rate'
    ]

    # Build metadata with valuation date (like display_redemption_stress)
    metadata_str = f'As of {valuation_date}' if valuation_date else ''

    # Display table
    html = display_dark_table(
        display_df,
        caption='Investor Behavioural\nRedemption Inputs',
        col_align_override={'NAV\nWeight': 'right', 'Base\nRedemption Rate': 'right', 'Stress\nRedemption Rate': 'right'},
        col_widths={'Calibration\nCategory': '120px', 'NAV\nWeight': '120px', 'Base\nRedemption Rate': '120px', 'Stress\nRedemption Rate': '120px'},
        date_str=metadata_str,
        date_label='',
        return_html=True,
    )

    display(HTML(html))

    # Display total weight
    total_weight = sum(inv['weight'] for inv in investors_enriched)
    display(HTML(f"<p style='color: #666; font-size: 12px;'>Total weight: {total_weight:.1%}</p>"))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Investor Redemption Inputs')
        filename = f'{export_id}_{title_slug}'
        save_html_as_png(html, fund_id, filename, folder_suffix='_liquidity')
