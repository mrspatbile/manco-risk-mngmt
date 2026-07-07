from IPython.display import display, HTML
import re
import pandas as pd
from datetime import datetime, timedelta
from fund_risk_workflow.ui.plot_style import C
from fund_risk_workflow.risk.risk_utils import redemption_stress
from fund_risk_workflow.config import VALUATION_DATE


def _xnav(prefix: str = '') -> str:
    """Column name that display_dark_table renders as PREFIX\n(×NAV).
    Use wherever a column represents an exposure as a multiple of NAV.
    The × (U+00D7) is unaffected by CSS text-transform: uppercase.
    """
    return f'{prefix}\n(×NAV)' if prefix else '\n(×NAV)'


def format_redemption_scenario(scenario: dict) -> str:
    """Format a redemption scenario dict for display as Name (X%) or Name (fund-specific).

    Parameters
    ----------
    scenario : dict
        Dict with 'name' and 'redemption_pct' keys.
        If 'redemption_pct' is numeric, formats as "Name (X%)".
        If 'redemption_pct' is 'largest_investor', formats as "Name (fund-specific)".

    Returns
    -------
    str
        Formatted scenario string, e.g. "Normal (10%)" or "Largest investor (fund-specific)".
    """
    name = scenario.get('name', '')
    pct = scenario.get('redemption_pct')

    if isinstance(pct, str) and pct == 'largest_investor':
        return f"{name} (fund-specific)"
    elif isinstance(pct, (int, float)):
        return f"{name} ({int(pct * 100)}%)"
    else:
        return name


def display_dark_table(
    df,
    caption                   : str        = '',
    fmt                       : dict | None = None,
    col_styles                : dict | None = None,
    col_align_override        : dict | None = None,
    highlight_rows            : list | None = None,
    col_header_align_override : dict | None = None,
    col_widths : dict | None = None,  # e.g. {'metric': '200px', 'value': '100px'}
    spacer_width              : str | None = None,  # e.g. '100px' | adds invisible spacer column
    date_str                  : str | None = None,  # e.g. '2026-03-31' | shown below caption
    date_label                : str        = 'As of',  # label for the date line
    hide_header               : bool       = False,  # hide column headers by matching text to background
    return_html               : bool       = False,  # if True, return HTML string instead of displaying
):
    """
    Render a DataFrame as a dark-themed styled HTML table in Jupyter.

    Consistent with the board report visual identity. Column names are
    auto-formatted: underscores replaced by spaces, EUR columns get a
    second line '(EUR)', all names title-cased.

    Parameters
    ----------
    df : pd.DataFrame
        Data to display. Original column names are used for fmt and
        col_styles keys | renaming happens internally for display only.

    caption : str
        Table title. Rendered in cyan, left-aligned, above the table.

    fmt : dict, optional
        Format strings keyed by original column name.
        e.g. {'market_value_eur': '{:,.0f}', 'weight_pct': '{:.2f}%'}
        Missing values rendered as '—'.

    col_styles : dict, optional
        Per-column color functions keyed by original column name.
        Each value is a callable: (cell_value) -> color_str or None.
        None means no color override (keeps default muted grey).
        e.g. {'esg_score': lambda v: C['green'] if v >= 70 else C['red']}

    col_align_override : dict, optional
        Override auto-detected alignment for specific columns (both
        header and cells). Keyed by original column name.
        Auto-detection: numeric/bool -> right, text -> center, first col -> left.
        e.g. {'esg_score': 'center'}

    highlight_rows : list, optional
        List of integer index values to render as section headers |
        uppercase, distinct background, letter-spacing.
        e.g. [0, 5] highlights the first and sixth rows.

    col_header_align_override : dict, optional
        Override alignment for column headers only, independently of
        cell alignment. Keyed by original column name.
        e.g. {'market_value_eur': 'center'} keeps cells right-aligned
        but centres the header.

    spacer_width : str, optional
        Width of invisible spacer column (last column). Useful for normalizing
        table widths across multiple tables with different content.
        e.g. '100px' adds an invisible 100px column at the end.
        Column is hidden (visibility: hidden) but takes up space.

    Notes
    -----
    - Index is always hidden.
    - Requires C (colour palette dict) from plot_style to be in scope.
    - ESG example: use ESG_COL_STYLES and ESG_FMT as col_styles and fmt.
    """
    
    _UPPER = {'Eur', 'Nav', 'Aum', 'Otc', 'Lcr', 'Rag', 'Dpi', 'Irr', 'Esg',
              'Env', 'Soc', 'Gov', 'Pai', 'Hhi', 'Pb', 'Id', 'Qtd', 'Tna'}

    def _fmt_col(col):
        # Spacer column header should be empty
        if col == '__spacer__':
            return ''
        col = col.replace('_', ' ').replace('pct', '%')
        # Normalize all NAV % variants to % NAV
        col = col.replace('NAV %', '% NAV')
        col = col.replace('nav %', '% NAV')
        # Standalone 'n' (count columns: n_obs, n_positions …) → qtd
        col = re.sub(r'\bn\b', 'qtd', col)
        if 'eur' in col.lower() and '(eur)' not in col.lower():
            # case-insensitive strip; if nothing is left (col was just 'EUR')
            # keep it as-is | no parentheses, no repetition
            col_stripped = col.lower().replace('eur', '').strip()
            if col_stripped:
                col = f'{col_stripped}\n(EUR)'
        titled = col.title()
        for abbrev in _UPPER:
            titled = titled.replace(abbrev, abbrev.upper())
        return titled

    df = df.replace(0, float('nan'))
    df_display          = df.rename(columns={c: _fmt_col(c) for c in df.columns})
    col_map             = dict(zip(df.columns, df_display.columns))

    # Add invisible spacer column if requested
    # spacer_width controls the visual width via repeated characters (e.g. '_' * 80)
    if spacer_width:
        spacer_col = '__spacer__'
        # Parse spacer_width as number of characters (e.g. '80' → 80 chars)
        try:
            n_chars = int(spacer_width.replace('px', '').strip())
            df_display[spacer_col] = '_' * n_chars
        except:
            df_display[spacer_col] = ''
    col_styles_remapped = {col_map[k]: v for k, v in col_styles.items() if k in col_map} if col_styles else None
    fmt_remapped        = {col_map.get(k, k): v for k, v in fmt.items()} if fmt else None

    def _style(df):
        styles = []
        for row_num, (i, row) in enumerate(df.iterrows()):
            is_highlight   = highlight_rows and i in highlight_rows
            bg             = "#36394F" if is_highlight else ('#1a1f2e' if row_num % 2 == 0 else '#141929')
            color          = '#587580' if is_highlight else C['muted']
            fw             = 'bold'   if is_highlight else 'normal'
            text_transform = 'uppercase' if is_highlight else 'none'
            letter_spacing = '0.05em'   if is_highlight else 'normal'
            font_size      = '10px'     if is_highlight else '11px'
            base = (f'background-color: {bg}; color: {color}; font-weight: {fw}; '
                    f'font-family: Arial, sans-serif; font-size: {font_size}; '
                    f'text-transform: {text_transform}; letter-spacing: {letter_spacing};')
            row_style = [base] * len(df.columns)
            if col_styles_remapped:
                for col, color_fn in col_styles_remapped.items():
                    if col in df.columns:
                        idx   = df.columns.get_loc(col)
                        color = color_fn(row[col])
                        if color:
                            row_style[idx] = (f'background-color: {bg}; color: {color}; '
                                              f'font-weight: bold; font-family: Arial, sans-serif; font-size: 11px;')
            styles.append(row_style)
        return pd.DataFrame(styles, index=df.index, columns=df.columns)

    def _col_align(df):
        aligns = {}
        for col in df.columns:
            try:
                if df[col].dtype in ('float64', 'int64', 'bool'):
                    aligns[col] = 'right'
                else:
                    aligns[col] = 'center'
            except Exception:
                aligns[col] = 'center'
        aligns[df.columns[0]] = 'left'
        return aligns

    # Build header styles | optionally hidden
    thead_props = [
        ('background-color', '#2F3245'),
        ('font-family',      'Arial, sans-serif'),
        ('font-size',        '1px' if hide_header else '10px'),
        ('font-weight',      'bold'),
        ('padding',          '0px' if hide_header else '6px 12px'),
        ('border-bottom',    '2px solid #0f1729'),
        ('color',            '#2F3245' if hide_header else '#a5cfdf'),  # match background if hidden
        ('letter-spacing',   '0.05em'),
        ('text-transform',   'uppercase'),
        ('white-space',      'pre-wrap'),
        ('line-height',      '1px' if hide_header else 'normal'),
    ]

    table_styles = [
        {'selector': 'caption', 'props': [
            ('color',            C['cyan']),
            ('font-size',        '14px'),
            ('font-weight',      'bold'),
            ('text-align',       'left'),
            ('font-family',      'Helvetica Neue, Helvetica, Arial, sans-serif'),
            ('padding-bottom',   '8px'),
            ('padding-left',     '10px'),
            ('background-color', '#1a2540'),
        ]},
        {'selector': 'thead th', 'props': thead_props},
        {'selector': 'td', 'props': [
            ('padding',       '5px 12px'),
            ('border-bottom', '1px solid #0f1729'),
            ('font-family',   'Arial, sans-serif'),
        ]},
        {'selector': 'table', 'props': [
            ('border-collapse', 'collapse'),
            ('width',           '100%'),
        ]},
    ]

    # Hide spacer column text but keep width (text color = background, so invisible)
    if spacer_width and '__spacer__' in df_display.columns:
        spacer_col_idx = df_display.columns.get_loc('__spacer__') + 1
        table_styles.append({
            'selector': f'thead th:nth-child({spacer_col_idx})',
            'props'   : [('color', '#2F3245')]  # Header bg color | text invisible
        })
        table_styles.append({
            'selector': f'td:nth-child({spacer_col_idx})',
            'props'   : [('color', '#1a1f2e')]  # Row bg color | text invisible, keeps width
        })

    aligns = _col_align(df_display)
    if col_align_override:
        for col, align in col_align_override.items():
            remapped = col_map.get(col, col)
            if remapped in aligns:
                aligns[remapped] = align

    for col, align in aligns.items():
        col_idx = df_display.columns.get_loc(col) + 1
        table_styles.append({
            'selector': f'td:nth-child({col_idx})',
            'props'   : [('text-align', f'{align} !important')]
        })
        table_styles.append({
            'selector': f'thead th:nth-child({col_idx})',
            'props'   : [('text-align', f'{align} !important')]
        })
    if col_widths:
        for col, width in col_widths.items():
            remapped = col_map.get(col, col)
            if remapped in df_display.columns:
                col_idx = df_display.columns.get_loc(remapped) + 1
                table_styles.append({
                    'selector': f'thead th:nth-child({col_idx})',
                    'props'   : [('width', width), ('min-width', width)]
                })

    # override header alignment only
    if col_header_align_override:
        for col, align in col_header_align_override.items():
            remapped = col_map.get(col, col)
            if remapped in df_display.columns:
                col_idx = df_display.columns.get_loc(remapped) + 1
                table_styles.append({
                    'selector': f'thead th:nth-child({col_idx})',
                    'props'   : [('text-align', f'{align} !important')]
                })

    styled = df_display.style.apply(_style, axis=None).set_table_styles(table_styles)

    if caption:
        if date_str:
            caption = f'{caption}<br><span style="font-size: 10px; font-weight: normal; color: #999; margin-top: 4px; display: block;">{date_label} {date_str}</span>'
        styled = styled.set_caption(caption)
    if fmt_remapped:
        styled = styled.format(fmt_remapped, na_rep='—')

    styled = styled.hide(axis='index')

    if return_html:
        return styled.to_html()
    else:
        display(styled)

#-------------------
# general info displays
#-------------------

def display_fund_rmp_parameters(fund_id: str, engine, export_id: str | None = None):
    """
    Display fund's Risk Management Policy parameters grouped by section.

    Reads fund's risk_policy.json and displays all parameters grouped by
    top-level sections (var_framework, leverage_limits, etc.).
    Adapts to any fund type (AIFM, UCITS, PE, private debt, real estate, etc).
    Internal notes (_note_*) shown at bottom.

    Parameters
    ----------
    fund_id : str
        Fund identifier
    engine : sqlalchemy.engine
        Database engine (passed for consistency with other display functions)
    export_id : str or None, default None
        If provided, save rendered HTML as PNG to reports/<fund_id>/<export_id>_*.png
    """
    from fund_risk_workflow.data.reference_data import load_rmp, load_scenario_file

    # Load risk policy
    rmp = load_rmp(fund_id)

    rows = []
    notes = []

    # Load scenario definitions for readable names
    def load_scenario_names(source_file):
        """Load scenario definitions and create ID-to-name mapping."""
        mapping = {}
        try:
            scenario_data = load_scenario_file(source_file)
            for scenario_id, scenario_def in scenario_data.get('scenarios', {}).items():
                scenario_name = scenario_def.get('scenario_name', scenario_id)
                mapping[scenario_id] = scenario_name
        except (FileNotFoundError, KeyError, TypeError):
            pass
        return mapping

    # Preload scenario mappings
    univariate_scenarios_map = load_scenario_names('ucits_univariate_stress_scenarios')
    historical_scenarios_map = load_scenario_names('scenario_library_2_historical')

    # Section title mappings (maps actual JSON keys to display titles)
    section_titles = {
        'var_framework': 'VaR Framework',
        'expected_shortfall': 'Expected Shortfall',
        'backtesting': 'VaR Backtesting',
        'var_backtesting': 'VaR Backtesting',
        'global_exposure_policy': 'Global Exposure Policy',
        'leverage_limits': 'Leverage Limits',
        'leverage_limits_internal': 'Leverage Limits',
        'concentration_limits': 'Concentration Limits',
        'concentration_limits_internal': 'Concentration Limits',
        'stress_testing': 'Stress Testing',
        'stress_scenarios': 'Stress Testing',
        'investor_concentration': 'Investor Concentration Monitoring',
        'investor_concentration_monitoring': 'Investor Concentration Monitoring',
        'liquidity_monitoring': 'Liquidity Monitoring',
        'redemption_terms': 'Redemption Terms',
        # Alternative asset and fund-specific sections
        'fund_structure': 'Fund Structure',
        'performance_metrics': 'Performance Metrics',
        'unfunded_commitments': 'Unfunded Commitments',
        'esg_framework': 'ESG Framework',
        'covenant_monitoring': 'Covenant Monitoring',
        'direct_property_monitoring': 'Direct Property Monitoring',
        'valuation_framework': 'Valuation Framework',
        'inflation_sensitivity': 'Inflation Sensitivity',
        'sector_concentration': 'Sector Concentration',
        'leverage': 'Leverage',
        'priips_kid': 'PRIIPs KID',
    }

    # Top-level field mappings (non-nested fields)
    top_level_fields = {
        'fund_id': 'Fund ID',
        'liquidity_profile': 'Liquidity Profile',
        'valuation_frequency': 'Valuation Frequency',
        'notice_period_days': 'Notice Period',
        'lockup_days': 'Lockup Period',
    }

    # Field name to readable label conversions
    field_labels = {
        'confidence_level': 'Confidence level',
        'holding_period_days': 'Holding period',
        'lookback_period_days': 'Lookback period',
        'models': 'Models',
        'distribution': 'Distribution',
        'observation_window': 'Observation window',
        'tests': 'Tests',
        'acceptable_breach_rate': 'Acceptable breach rate',
        'monitoring_threshold': 'Monitoring threshold',
        'gross_leverage': 'Gross leverage',
        'commitment_leverage': 'Commitment leverage',
        'notional_leverage': 'Notional leverage',
        'single_issuer': 'Single issuer',
        'single_sector': 'Single sector',
        'single_country': 'Single country',
        'enabled': 'Enabled',
        'scenario_types': 'Scenario types',
        'single_investor_threshold': 'Single investor threshold',
        'top_3_investors_threshold': 'Top 3 investors threshold',
        'top_5_investors_threshold': 'Top 5 investors threshold',
        'structure': 'Structure',
        'redemption_frequency': 'Redemption frequency',
        'redemption_notice_days': 'Redemption notice',
        'redemption_settlement_days': 'Settlement',
        'display': 'Display',
        'liquidity_profile': 'Liquidity profile',
        'valuation_frequency': 'Valuation frequency',
        'breach_rate_thresholds': 'Breach rate thresholds',
        'acceptable_pct': 'Acceptable',
        'monitor_pct': 'Monitor',
        'parametric_distribution': 'Distribution',
        'parametric_degrees_of_freedom': 'Degrees of freedom',
        'scaling_method': 'Scaling method',
        'use_var': 'Use VaR',
        'use_backtesting': 'Use backtesting',
        'use_stress_testing': 'Use stress testing',
        'method': 'Method',
        'method_routing': 'Method Routing',
        'commitment': 'Commitment Method',
        'absolute_var': 'Absolute VaR Method',
        'relative_var': 'Relative VaR Method',
        'commitment_exposure_pct_tna': 'Commitment Exposure',
        'absolute_var_pct_tna': 'Absolute VaR',
        'relative_var_pct': 'Relative VaR',
        'reference_portfolio_id': 'Reference Portfolio',
        'uses_commitment_disclosure': 'Uses Commitment Disclosure',
        'uses_derivative_notional_leverage_reporting': 'Derivative Notional Leverage Reporting',
        'notes': 'Notes',
        'gross_leverage_max': 'Gross leverage',
        'commitment_leverage_max': 'Commitment leverage',
        'single_issuer_max_pct': 'Single issuer',
        'single_investor_threshold_pct': 'Single investor threshold',
        'top_3_investors_threshold_pct': 'Top 3 investors threshold',
        'top_5_investors_threshold_pct': 'Top 5 investors threshold',
        'scenario_types': 'Scenario types',
        'univariate_scenarios': 'Univariate Scenarios',
        'most_relevant_historical_scenarios': 'Most Relevant Historical Scenarios',
        'pct_tna': '% TNA',
        'pnl_eur': 'P&L (EUR)',
        'source': 'Source',
        'basis': 'Basis',
        'prescribed_scenarios': 'Prescribed Scenarios',
        'selected_scenarios': 'Selected Scenarios',
        'requires_holding_period_days': 'Requires Holding Period Days',
        # Alternative asset and fund-specific fields
        'benchmark_pme': 'Benchmark PME',
        'committed_capital_eur': 'Committed capital',
        'costs_disclosure': 'Costs disclosure',
        'discount_rate_by_asset': 'Discount rate by asset',
        'drawn_capital_eur': 'Drawn capital',
        'dscr_threshold_by_asset': 'DSCR threshold by asset',
        'esg_data_source': 'ESG data source',
        'fund_level_limit': 'Fund level limit',
        'fund_life_years': 'Fund life',
        'hy_exposure_max_pct': 'HY exposure max',
        'inflation_assumption_by_asset': 'Inflation assumption by asset',
        'investment_period_end': 'Investment period end',
        'limit_pct': 'Limit',
        'liquidity_stress_multiplier': 'Liquidity stress multiplier',
        'ltv_covenant_threshold_pct': 'LTV covenant threshold',
        'ltv_threshold_by_asset': 'LTV threshold by asset',
        'management_fee_rate': 'Management fee rate',
        'method': 'Method',
        'monitoring': 'Monitoring',
        'pct_adv': 'Pct ADV',
        'performance_scenarios': 'Performance scenarios',
        'project_level_via_covenants': 'Project level via covenants',
        'risk_indicator': 'Risk indicator',
        'sfdr_pai_tracking': 'SFDR PAI tracking',
        'single_borrower_max_pct': 'Single borrower max',
        'sri_class': 'SRI class',
        'track_breaches_and_waivers': 'Track breaches and waivers',
        'track_dscr': 'Track DSCR',
        'track_inflation_linkage_by_asset': 'Track inflation linkage by asset',
        'track_ltv': 'Track LTV',
        'track_ltv_pct': 'Track LTV',
        'track_moic_dpi_rvpi': 'Track MOIC/DPI/RVPI',
        'track_rental_yield_pct': 'Track rental yield',
        'track_vacancy_rate_pct': 'Track vacancy rate',
        'track_weighted_concession_duration': 'Track weighted concession duration',
        'track_xirr': 'Track XIRR',
        'tracking': 'Tracking',
        'unrated_exposure_max_pct': 'Unrated exposure max',
        'vacancy_alarm_threshold_pct': 'Vacancy alarm threshold',
    }

    # Value mappings for readable display of parameter values
    value_mappings = {
        'commitment_exposure_pct_tna': 'Commitment Exposure',
        'absolute_var_pct_tna': 'Absolute VaR',
        'relative_var_pct': 'Relative VaR',
        'absolute_var': 'Absolute VaR',
        'sqrt_time': 'Square Root of Holding Period',
        'student_t': 't-distribution',
        'parametric': 'Parametric',
        'historical': 'Historical',
        'kupiec_pof': 'Kupiec POF',
        'christoffersen': 'Christoffersen',
        'daily_redemption': 'Daily Redemption',
        'global_equity_60_eur_gov_40': '60% Global Equity / 40% EUR Govt Bonds',
        'sp500_reference': 'S&P 500 Reference',
    }

    def format_scenario(scenario):
        """Format a stress scenario dict to readable string."""
        if not isinstance(scenario, dict):
            return str(scenario)

        name = scenario.get('description', scenario.get('name', 'Unknown'))

        # Extract shock magnitude
        if 'shock_pct' in scenario:
            shock = f"({scenario['shock_pct']:.0f}%)"
        elif 'shock_bps' in scenario:
            shock = f"({scenario['shock_bps']:.0f}bps)"
        else:
            shock = ''

        return f"{name} {shock}".strip()

    def format_value(value, field_name=''):
        """Format a value for display."""
        if value is None or value == '' or (isinstance(value, list) and len(value) == 0):
            return None

        if isinstance(value, bool):
            return 'Yes' if value else 'No'
        elif isinstance(value, list):
            # Special handling for stress scenarios
            if field_name == 'scenarios' or any('shock' in str(v) for v in value if isinstance(v, dict)):
                formatted_scenarios = [format_scenario(v) for v in value]
                return ', '.join(formatted_scenarios)
            else:
                return ', '.join(str(v) for v in value)
        elif isinstance(value, (int, float)):
            # Format as percentage if field name contains 'pct'
            if 'pct' in field_name.lower():
                return f'{value:.1f}%'
            # Format as leverage multiplier if field name contains 'leverage'
            if 'leverage' in field_name.lower():
                return f'{value:.2f}x'
            # Format large numbers with thousands separators
            if abs(value) >= 1_000_000:
                return f"{int(value):,}"
            return str(value)
        else:
            # Check if string value has a readable mapping
            if isinstance(value, str) and value in value_mappings:
                return value_mappings[value]
            return str(value)

    def readable_label(field_name):
        """Convert field name to readable label."""
        return field_labels.get(field_name, field_name.replace('_', ' ').title())

    # First, process top-level fields
    top_level_section_added = False
    for field_key, field_title in top_level_fields.items():
        if field_key in rmp:
            field_value = rmp[field_key]
            formatted = format_value(field_value, field_key)
            if formatted is not None:
                if not top_level_section_added:
                    rows.append(('Fund Parameters', ''))
                    top_level_section_added = True
                label = field_title
                rows.append((f'  {label}', formatted))

    if top_level_section_added:
        rows.append(('', ''))  # Spacer

    # Process each top-level section (nested objects)
    for section_key, section_title in section_titles.items():
        if section_key not in rmp:
            continue

        section_data = rmp[section_key]
        if not section_data or (isinstance(section_data, dict) and all(
            k.startswith('_') or v is None or v == '' or (isinstance(v, list) and len(v) == 0)
            for k, v in section_data.items()
        )):
            continue

        # Add section header
        rows.append((section_title, ''))

        # Add parameters under section
        if isinstance(section_data, dict):
            for param_key, param_value in section_data.items():
                # Skip notes and empty values
                if param_key.startswith('_'):
                    notes.append((param_key.lstrip('_'), param_value if isinstance(param_value, str) else str(param_value)))
                    continue

                # Skip internal flags | they're implicit in the section structure
                if param_key in ('use_stress_testing',):
                    continue

                # Handle nested dicts | each field on separate line, scenarios with readable names
                if isinstance(param_value, dict):
                    label = readable_label(param_key)
                    # Make subsection labels bold with marker for stress_testing subsections
                    if section_key == 'stress_testing' and param_key in ('univariate_scenarios', 'most_relevant_historical_scenarios'):
                        label = f'<strong>▸ {label}</strong>'
                    rows.append((f'  {label}', ''))

                    for sub_key, sub_value in param_value.items():
                        if sub_key.startswith('_'):
                            continue

                        # Skip internal flags | they're implicit in the section structure
                        if sub_key in ('requires_holding_period_days', 'use_stress_testing'):
                            continue

                        sub_label = readable_label(sub_key)

                        # Special handling for prescribed_scenarios and selected_scenarios lists
                        if sub_key in ('prescribed_scenarios', 'selected_scenarios') and isinstance(sub_value, list):
                            # Determine which mapping to use based on section context
                            scenario_map = {}
                            scenario_details = {}
                            is_historical = False

                            if 'univariate' in param_key.lower():
                                scenario_map = univariate_scenarios_map
                            elif 'historical' in param_key.lower():
                                scenario_map = historical_scenarios_map
                                is_historical = True
                                # Load full scenario data for holding period
                                try:
                                    hist_data = load_scenario_file('scenario_library_2_historical')
                                    scenario_details = hist_data.get('scenarios', {})
                                except (FileNotFoundError, KeyError, TypeError):
                                    pass

                            # Display all scenarios in HTML list format
                            scenario_html = '<ul style="margin: 0; padding-left: 20px;">\n'
                            for sid in sub_value:
                                name = scenario_map.get(sid, sid)
                                # Append holding period for historical scenarios
                                if is_historical and sid in scenario_details:
                                    holding_period = scenario_details[sid].get('holding_period_days')
                                    if holding_period:
                                        name = f'{name}, hp={holding_period}d'
                                scenario_html += f'  <li>{name}</li>\n'
                            scenario_html += '</ul>'
                            rows.append((f'    {sub_label}', scenario_html))
                        else:
                            formatted = format_value(sub_value, sub_key)
                            if formatted is not None:
                                rows.append((f'    {sub_label}', formatted))
                # Handle lists of dicts (like scenarios)
                elif isinstance(param_value, list) and param_value and isinstance(param_value[0], dict):
                    label = readable_label(param_key)

                    # Special handling for redemption scenarios
                    if param_key == 'redemption_scenarios' and all(isinstance(s.get('redemption_pct'), (int, float, str)) for s in param_value):
                        scenario_html = '<ul style="margin: 0; padding-left: 20px;">\n'
                        for scenario in param_value:
                            formatted_scenario = format_redemption_scenario(scenario)
                            scenario_html += f'  <li>{formatted_scenario}</li>\n'
                        scenario_html += '</ul>'
                        rows.append((f'  {label}', scenario_html))
                    else:
                        formatted = format_value(param_value, param_key)
                        if formatted is not None:
                            rows.append((f'  {label}', formatted))
                else:
                    formatted = format_value(param_value, param_key)
                    if formatted is not None:
                        # Indent parameter name
                        label = readable_label(param_key)
                        rows.append((f'  {label}', formatted))

        # Add spacer after section
        rows.append(('', ''))

    # Add notes at bottom with text wrapping
    if notes:
        for note_key, note_value in notes:
            # Wrap long notes at word boundaries (max 100 chars per line)
            if len(note_value) > 100:
                wrapped_lines = []
                words = note_value.split()
                current_line = []
                current_length = 0

                for word in words:
                    if current_length + len(word) + 1 <= 100:  # +1 for space
                        current_line.append(word)
                        current_length += len(word) + 1
                    else:
                        if current_line:
                            wrapped_lines.append(' '.join(current_line))
                        current_line = [word]
                        current_length = len(word) + 1

                if current_line:
                    wrapped_lines.append(' '.join(current_line))

                note_value = '\n'.join(wrapped_lines)

            rows.append((f"Note: {note_key}", note_value))

    if rows:
        # Remove trailing empty rows
        while rows and rows[-1] == ('', ''):
            rows.pop()

        # Find section header rows (no indentation, no notes)
        highlight_indices = []
        for idx, (param, value) in enumerate(rows):
            if param and not param.startswith('  ') and not param.startswith('Note:') and value == '':
                highlight_indices.append(idx)

        df = pd.DataFrame(rows, columns=['Parameter', 'Value'])

        html = display_dark_table(
            df,
            caption='Risk Management Policy Parameters',
            col_align_override={'Value': 'left'},
            col_widths={'Parameter': '250px', 'Value': '320px'},
            highlight_rows=highlight_indices,
            col_styles={
                'Parameter': lambda v: (
                    C['muted'] if isinstance(v, str) and v and not v.startswith('  ') and not v.startswith('Note:')
                    else None
                ),
            },
            hide_header=True,
            return_html=True,
        )

        display(HTML(html))

        if export_id is not None:
            from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
            title_slug = _slugify('Risk Management Policy Parameters')
            filename = f'{export_id}_{title_slug}'
            save_html_as_png(html, fund_id, filename)
    else:
        display(HTML("<div style='color: #999; font-size: 12px;'>No RMP parameters defined.</div>"))


def display_fund_overview_banner(fund_id: str, engine, export_id: str | None = None):
    """
    Display fund overview: which fund is being studied.

    Queries fund_profile.json to show fund identity and classification.
    No snapshot-specific data (NAV, valuation date, etc).

    Optionally saves rendered output as PNG with deterministic filename when export_id is provided.

    Parameters
    ----------
    fund_id : str
        Fund identifier
    engine : sqlalchemy.engine
        Database engine (passed for consistency with other display functions)
    export_id : str or None, default None
        If provided, save rendered HTML as PNG to reports/<fund_id>/<export_id>_fund_overview.png
        If None, display normally without saving.

    Returns
    -------
    None
    """
    from pathlib import Path
    from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
    from fund_risk_workflow.data.reference_data import load_fund_profile

    # Load fund profile from reference data
    profile = load_fund_profile(fund_id)

    # Regulatory classification
    reg = profile['regulatory_classification']
    if reg['is_ucits']:
        fund_class = 'UCITS'
    elif reg['is_aif']:
        fund_class = 'AIF (AIFM)'
    else:
        fund_class = profile['fund_type']

    # Build banner rows - fund identity only
    long_name = profile.get('fund_name', fund_id)

    # Redemption terms
    redemption_terms = profile.get('redemption_terms', {})
    redemption_display = redemption_terms.get('display', '—')

    rows = [
        ('Fund Name', long_name),
        ('Fund Code', fund_id),
        ('Fund Type', fund_class),
        ('Domicile', profile['domicile']),
        ('Currency', profile['currency']),
    ]

    # Add redemption terms if available
    if redemption_display != '—':
        rows.append(('Redemption terms', redemption_display))

    df = pd.DataFrame(rows, columns=['label', 'value'])

    # Get HTML and display it
    html = display_dark_table(
        df,
        caption='Fund',
        col_align_override={'value': 'left'},
        col_widths={'label': '160px', 'value': '300px'},
        return_html=True,
    )

    # Display in notebook
    display(HTML(html))

    # Save as PNG if export_id is provided
    if export_id is not None:
        title_slug = _slugify('Fund')
        filename = f'{export_id}_{title_slug}'
        save_html_as_png(html, fund_id, filename)


def display_fund_summary(FUND_ID, VALUATION_DATE, positions, risk_df, NAV, valuation_date: str | None = None, export_id: str | None = None):
    if valuation_date is None:
        valuation_date = VALUATION_DATE

    mask_long = risk_df['market_value_eur'] >= 0
    long_exp  = risk_df[mask_long]['market_value_eur'].sum()
    short_exp = risk_df[~mask_long]['market_value_eur'].sum()

    df = pd.DataFrame([
        ('Fund',           FUND_ID),
        ('Valuation Date', str(VALUATION_DATE)),
        ('Positions',      str(len(positions))),
        ('NAV (EUR)',      f'{NAV:,.0f}'),
        ('Asset Classes',  ', '.join(sorted(positions['asset_class'].unique()))),
        ('Long Exposure',  f'{long_exp:,.0f}'),
        ('Short Exposure', f'{short_exp:,.0f}' if short_exp != 0 else '—'),
    ], columns=['Metric', 'Value'])

    html = display_dark_table(
        df,
        caption='Fund Summary',
        col_align_override={'Value': 'right'},
        col_styles=None,
        col_widths={'Metric': '200px', 'Value': '200px'},
        date_str=valuation_date,
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Fund Summary')
        filename = f'{export_id}_{title_slug}'
        save_html_as_png(html, FUND_ID, filename)


def display_asset_class_weights_n_positions(breakdown, NAV):
    df = breakdown.reset_index().rename(columns={'asset_class': 'Asset Class'})

    totals = pd.DataFrame([{
        'Asset Class'      : 'Total / NAV',
        'market_value_eur' : NAV,
        'weight_pct'       : 100.0,
        'n_positions'      : df['n_positions'].sum(),
    }])
    df = pd.concat([df, totals], ignore_index=True)

    display_dark_table(
        df,
        caption='Asset Class Breakdown',
        fmt={
            'market_value_eur': '{:,.0f}',
            'weight_pct'      : '{:.1f}%',
            'n_positions'     : '{:.0f}',
        },
        highlight_rows=[len(df) - 1],
        col_widths={'Asset Class': '180px'},
    )


def display_leverage(risk_df, deriv_notional_commitment, commitment_exposure,
                     gross_limit=3.0, borrowings_eur=0.0):
    NAV = risk_df['market_value_eur'].sum()
    gross_leverage      = (risk_df['gross_exposure'].sum() + borrowings_eur) / NAV
    commitment_leverage = commitment_exposure / NAV

    all_classes = sorted(
        c for c in risk_df['asset_class'].unique() if c != 'Borrowing'
    )

    rows = []
    for ac in all_classes:
        gross_eur  = risk_df[risk_df['asset_class'] == ac]['gross_exposure'].sum()
        if ac == 'Cash':
            commit_eur = 0.0
        elif ac == 'FX':
            commit_eur = risk_df[
                (risk_df['asset_class'] == 'FX') & (risk_df['is_hedge'] == 0)
            ]['market_value_eur'].abs().sum()
        elif ac == 'Derivative':
            commit_eur = abs(deriv_notional_commitment)
        else:
            commit_eur = risk_df[risk_df['asset_class'] == ac]['market_value_eur'].abs().sum()
        rows.append({
            'asset_class' : ac,
            'gross_eur'   : gross_eur,
            'g×nav'       : gross_eur / NAV,
            'commit_eur'  : commit_eur,
            'c×nav'       : commit_eur / NAV,
        })

    if borrowings_eur > 0:
        rows.append({
            'asset_class' : 'Borrowing',
            'gross_eur'   : borrowings_eur,
            'g×nav'       : borrowings_eur / NAV,
            'commit_eur'  : borrowings_eur,
            'c×nav'       : borrowings_eur / NAV,
        })

    rows.append({
        'asset_class' : 'Total',
        'gross_eur'   : risk_df['gross_exposure'].sum() + borrowings_eur,
        'g×nav'       : gross_leverage,
        'commit_eur'  : commitment_exposure,
        'c×nav'       : commitment_leverage,
    })

    df = pd.DataFrame(rows)
    df = df.rename(columns={
        'g×nav': 'Gross\n(×NAV)',
        'c×nav': 'Commit\n(×NAV)',
    })
    total_idx = len(df) - 1

    status = 'OK' if gross_leverage <= gross_limit else 'BREACH'
    caption = (f'Leverage  |  Gross limit: {gross_limit:.0f}×  |  '
               f'Current: {gross_leverage:.2f}×  |  Status: {status}')

    display_dark_table(
        df,
        caption=caption,
        fmt={
            'gross_eur'       : '{:,.0f}',
            'Gross\n(×NAV)'   : '{:.2f}×',
            'commit_eur'      : '{:,.0f}',
            'Commit\n(×NAV)'  : '{:.2f}×',
        },
        col_styles={
            'Gross\n(×NAV)' : lambda v: C['red'] if isinstance(v, float) and v > gross_limit else None,
            'Commit\n(×NAV)': lambda v: C['red'] if isinstance(v, float) and v > 2.0 else None,
        },
        highlight_rows=[total_idx],
        col_widths={'asset_class': '160px'},
    )


def display_var_es(var_result: dict, valuation_date: str = None, fund_id: str | None = None, export_id: str | None = None):
    """
    Display VaR and ES from var_result dict.

    Auto-detects which metrics are present (historical vs parametric) based on dict keys.
    If both are present, displays both in a single table.
    Extracts nav, horizon, and valuation_date from var_result.

    Parameters
    ----------
    var_result : dict
        Dictionary containing VaR/ES metrics from compute_fixed_position_var_1day()
        Must include: nav_eur, var_result metadata (horizon, etc.)
    valuation_date : str, optional
        Override valuation_date from var_result (for display only)
    export_id : str or None, default None
        If provided, save rendered HTML as PNG
    """
    nav = var_result.get('nav_eur', 0)
    horizon = var_result.get('horizon', 20)
    display_date = valuation_date or var_result.get('valuation_date')

    _c = ['Metric', '1D\n(% NAV)', f'{horizon}D\n(% NAV)', '1D\n(EUR)', f'{horizon}D\n(EUR)']
    rows = []

    # Check for historical metrics
    if 'var_hist_pct' in var_result:
        var_1d = var_result.get('var_hist_pct', 0)
        var_scaled = var_result.get('var_hist_scaled_pct', 0)
        es_1d = var_result.get('es_hist_pct', 0)
        es_scaled = var_result.get('es_hist_scaled_pct', 0)
        rows.append((f'VaR Historical', f'{var_1d*100:.2f}%',  f'{var_scaled*100:.2f}%',
                     f'{var_1d*nav:,.0f}',  f'{var_scaled*nav:,.0f}'))
        rows.append((f'ES Historical',  f'{es_1d*100:.2f}%',   f'{es_scaled*100:.2f}%',
                     f'{es_1d*nav:,.0f}',   f'{es_scaled*nav:,.0f}'))

    # Check for parametric metrics
    if 'var_param_pct' in var_result:
        var_1d = var_result.get('var_param_pct', 0)
        var_scaled = var_result.get('var_param_scaled_pct', 0)
        es_1d = var_result.get('es_param_pct', 0)
        es_scaled = var_result.get('es_param_scaled_pct', 0)
        rows.append((f'VaR Parametric', f'{var_1d*100:.2f}%',  f'{var_scaled*100:.2f}%',
                     f'{var_1d*nav:,.0f}',  f'{var_scaled*nav:,.0f}'))
        rows.append((f'ES Parametric',  f'{es_1d*100:.2f}%',   f'{es_scaled*100:.2f}%',
                     f'{es_1d*nav:,.0f}',   f'{es_scaled*nav:,.0f}'))

    df = pd.DataFrame(rows, columns=_c)
    caption = 'VaR & Expected Shortfall'
    html = display_dark_table(
        df,
        caption=caption,
        col_align_override={c: 'right' for c in _c[1:]},
        date_str=display_date,
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('VaR & Expected Shortfall')
        # Use provided fund_id parameter, or fallback to var_result
        fid = fund_id or var_result.get('fund_id', 'unknown')
        filename = f'{export_id}_{title_slug}'
        save_html_as_png(html, fid, filename)

def display_backtest_report(report, window_size=250, valuation_date: str | None = None, model: str = "Historical", fund_id: str | None = None, export_id: str | None = None):
    rep = report.copy()
    rep['breach_rate'] = rep['breach_rate'] * 100
    rep['expected']    = rep['expected'] * 100

    # Replace "Fixed-Position" (case-insensitive) with the provided model parameter
    import re
    rep['model'] = rep['model'].str.replace(r'fixed-position', model, regex=True, case=False)

    rep_filter = rep[['model', 'confidence', 'n_obs', 'n_breaches',
                       'breach_rate', 'expected',
                       'kupiec_p', 'christoffersen_p', 'result']].rename(columns={
        'kupiec_p'        : 'kupiec_pvalue',
        'christoffersen_p': 'christoffersen_pvalue',
        'n_obs'           : 'qtd_obs',
        'n_breaches'      : 'qtd_breaches',
    })

    # Build metadata with window size
    metadata_str = f'{window_size}d window' if valuation_date else None
    if valuation_date and metadata_str:
        date_label_str = f'As of {valuation_date} | {metadata_str}'
    else:
        date_label_str = valuation_date

    html = display_dark_table(
        rep_filter,
        caption='VaR Backtest Report',
        fmt={
            'breach_rate'           : '{:.2f}%',
            'expected'              : '{:.2f}%',
            'kupiec_p_value'        : '{:.4f}',
            'christoffersen_p_value': '{:.4f}',
        },
        col_styles={
            'result': lambda v: (
                C['green'] if str(v).upper() == 'PASS'
                else C['red']
            ),
        },
        col_widths={'model': '100px'},
        date_str=date_label_str,
        date_label='',
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('VaR Backtest Report')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)



def display_esma_report(n, breach_rate, zone):
    zone_color = {'green': C['green'], 'amber': C['amber'], 'red': C['red']}
    df = pd.DataFrame([
        ('Window',       'Last 250 trading days'),
        ('Breaches',     str(n)),
        ('Breach rate',  f'{breach_rate*100:.2f}%  (expected 1.0%)'),
        ('ESMA zone',    zone),
    ], columns=['Metric', 'Value'])
    display_dark_table(
        df,
        caption='ESMA Backtest Report',
        col_styles={'Value': lambda v: zone_color.get(v.lower(), None) if v.lower() in zone_color else None},
        col_align_override={'Value': 'right'},
        col_widths={'Metric': '200px', 'Value': '250px'},
    )


def display_lvar(lvar_result, NAV, valuation_date: str | None = None, fund_id: str | None = None, export_id: str | None = None):
    kpi = pd.DataFrame([
        ('VaR (1d 99%)',   f'{lvar_result["var"]*100:.2f}%',
         f'{lvar_result["var"]*NAV:,.0f}'),
        ('Liquidity cost', f'{lvar_result["liquidity_cost"]*100:.2f}%',
         f'{lvar_result["liquidity_cost"]*NAV:,.0f}'),
        ('LVaR (1d 99%)',  f'{lvar_result["lvar"]*100:.2f}%',
         f'{lvar_result["lvar"]*NAV:,.0f}'),
        ('LVaR increase',  f'+{lvar_result["lvar_pct_increase"]:.1f}%', ''),
    ], columns=['Metric', '% NAV', 'EUR'])
    html = display_dark_table(
        kpi,
        caption='Liquidity-Adjusted VaR',
        col_align_override={'% NAV': 'right', 'EUR': 'right'},
        col_widths={'Metric': '200px'},
        date_str=valuation_date,
        date_label='Valuation Date',
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Liquidity-Adjusted VaR')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)

    bac = lvar_result['by_asset_class']
    html2 = display_dark_table(
        bac,
        caption='LVaR by Asset Class',
        fmt={'market_value_eur': '{:,.0f}', 'liquidity_cost': '{:,.0f}'},
        date_str=valuation_date,
        date_label='Valuation Date',
        return_html=True,
    )

    display(HTML(html2))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('LVaR by Asset Class')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html2, fid, filename)


def display_granular(granular, NAV, valuation_date: str | None = None, fund_id: str | None = None, export_id: str | None = None):
    # prt.print_granular mutates the input in-place (formats strings).
    # Always work on a fresh numeric copy.
    granular = granular.copy()
    if isinstance(granular.index, pd.MultiIndex):
        granular = granular.reset_index()
    for col in ('gross_eur', 'gross_x_nav'):
        if col in granular.columns and not pd.api.types.is_numeric_dtype(granular[col]):
            granular[col] = pd.to_numeric(
                granular[col].astype(str).str.replace(',', '').str.replace('x', ''),
                errors='coerce',
            )

    total_gross = granular['gross_eur'].sum()

    # listed vs OTC
    lot = granular.groupby('listed_otc')['gross_eur'].sum().reset_index()
    lot.columns = ['Category', 'gross_eur']
    lot[_xnav()]    = lot['gross_eur'] / NAV
    lot['pct_leverage'] = lot['gross_eur'] / total_gross * 100
    lot = pd.concat([lot, pd.DataFrame([{
        'Category': 'Total', 'gross_eur': total_gross,
        _xnav(): total_gross / NAV, 'pct_leverage': 100.0,
    }])], ignore_index=True)
    html = display_dark_table(
        lot, caption='Leverage by Listed / OTC',
        fmt={'gross_eur': '{:,.0f}', _xnav(): '{:.2f}×', 'pct_leverage': '{:.1f}%'},
        highlight_rows=[len(lot) - 1],
        date_str=valuation_date,
        return_html=True,
    )
    display(HTML(html))
    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Leverage by Listed / OTC')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)

    # by source
    src = granular.groupby('source')['gross_eur'].sum().reset_index()
    src.columns = ['Source', 'gross_eur']
    src[_xnav()]    = src['gross_eur'] / NAV
    src['pct_leverage'] = src['gross_eur'] / total_gross * 100
    src = pd.concat([src, pd.DataFrame([{
        'Source': 'Total', 'gross_eur': total_gross,
        _xnav(): total_gross / NAV, 'pct_leverage': 100.0,
    }])], ignore_index=True)
    html = display_dark_table(
        src, caption='Leverage by Source',
        fmt={'gross_eur': '{:,.0f}', _xnav(): '{:.2f}×', 'pct_leverage': '{:.1f}%'},
        highlight_rows=[len(src) - 1],
        date_str=valuation_date,
        return_html=True,
    )
    display(HTML(html))
    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Leverage by Source')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)

    # granular detail
    detail = granular[['asset_class', 'sub_asset_class', 'source', 'listed_otc',
                        'gross_eur', 'gross_x_nav', 'n_positions']].copy()
    detail = detail.rename(columns={'gross_x_nav': _xnav('Gross')})
    html = display_dark_table(
        detail, caption='AIFMD II Granular Leverage Breakdown',
        fmt={'gross_eur': '{:,.0f}', _xnav('Gross'): '{:.2f}×', 'n_positions': '{:.0f}'},
        date_str=valuation_date,
        return_html=True,
    )
    display(HTML(html))
    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('AIFMD II Granular Leverage Breakdown')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)


def display_buckets(bucket_full, risk_df_liq, NAV, valuation_date: str | None = None, fund_id: str | None = None, export_id: str | None = None):
    total_abs = risk_df_liq['market_value_eur'].abs().sum()
    total_net = risk_df_liq['market_value_eur'].sum()
    totals = pd.DataFrame([{
        'liquidity_bucket': 'Total',
        'market_value_eur': total_net,
        'abs_exposure'    : total_abs,
        'pct_nav_net'     : total_net / NAV * 100,
        'pct_nav_abs'     : total_abs / NAV * 100,
        'n_positions'     : bucket_full['n_positions'].sum(),
    }])
    df = pd.concat([bucket_full, totals], ignore_index=True)
    html = display_dark_table(
        df,
        caption='Liquidity Profile | AIFMD Annex IV Buckets',
        fmt={
            'market_value_eur': '{:,.0f}',
            'abs_exposure'    : '{:,.0f}',
            'pct_nav_net'     : '{:.1f}%',
            'pct_nav_abs'     : '{:.1f}%',
            'n_positions'     : '{:.0f}',
        },
        highlight_rows=[len(df) - 1],
        date_str=valuation_date,
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Liquidity Profile | AIFMD Annex IV Buckets')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)


def display_inv_concentration(NAV, risk_df_liq, _investors, _conc, _top, _type):
    """Render investor concentration as a hand-built HTML table with colspan support."""
    flag_s = '⚠ ESMA flag'  if _conc['concentration_flag']  else '✓ OK'
    flag_3 = '⚠ High conc.' if _conc['high_concentration']  else '✓ OK'

    _r4 = redemption_stress(risk_df_liq, NAV,
                            redemption_pct=_conc['largest_investor_pct'], notice_days=5)
    _gap = (f"+{_r4['liquidity_gap_eur']/1e6:.1f}M"
            if _r4['liquidity_gap_eur'] >= 0
            else f"{_r4['liquidity_gap_eur']/1e6:.1f}M")

    # | shared styles ||||||||||||||||||||||||||||||||||||||||||||||
    _BG_E   = '#1a1f2e'   # even row
    _BG_O   = '#141929'   # odd row
    _BG_SEP = '#36394F'   # section separator
    _BG_HDR = '#2F3245'   # thead
    _TXT    = '#9ca3af'   # muted body text
    _HDR_C  = '#a5cfdf'   # thead text
    _SEP_C  = '#587580'   # separator text
    _BORDER = '1px solid #0f1729'
    _FONT   = 'font-family:Arial,sans-serif;font-size:11px;'
    _PAD    = 'padding:5px 12px;'

    def _td(text, align='left', color=_TXT, bold=False, colspan=1):
        fw = 'bold' if bold else 'normal'
        cs = f' colspan="{colspan}"' if colspan > 1 else ''
        return (f'<td{cs} style="{_FONT}{_PAD}text-align:{align};'
                f'color:{color};font-weight:{fw};border-bottom:{_BORDER};">'
                f'{text}</td>')

    def _sep_row(label):
        return (f'<tr style="background:{_BG_SEP};">'
                f'<td colspan="5" style="{_FONT}padding:5px 12px;color:{_SEP_C};'
                f'font-weight:bold;letter-spacing:0.05em;text-transform:uppercase;'
                f'text-align:left;border-bottom:{_BORDER};">{label}</td></tr>')

    def _spacer(n):
        bg = _BG_E if n % 2 == 0 else _BG_O
        return (f'<tr style="background:{bg};">'
                f'<td colspan="5" style="padding:3px;border-bottom:{_BORDER};"></td></tr>')

    # | build HTML ||||||||||||||||||||||||||||||||||||||||||||||||
    rows_html = []

    # thead
    headers = ['#', 'INVESTOR', 'TYPE', 'AUM (EUR)', '% NAV']
    th = ''.join(
        f'<th style="{_FONT}background:{_BG_HDR};padding:6px 12px;color:{_HDR_C};'
        f'text-align:{"center" if i==0 else "left" if i<3 else "right"};'
        f'font-weight:bold;letter-spacing:0.05em;border-bottom:2px solid #0f1729;">{h}</th>'
        for i, h in enumerate(headers)
    )
    thead = f'<thead><tr>{th}</tr></thead>'

    # investor ranking rows
    for i, (_, row) in enumerate(_top.reset_index(drop=True).iterrows(), 1):
        bg = _BG_E if i % 2 == 1 else _BG_O
        aum_c = f'{row["aum_eur"]:,.0f}'
        pct_c = f'{row["pct_nav"]*100:.1f}%'
        typ   = _type.get(row['investor_id'], '')
        rows_html.append(
            f'<tr style="background:{bg};">'
            + _td(str(i), 'center')
            + _td(row['investor_name'], 'left')
            + _td(typ, 'left')
            + _td(aum_c, 'right')
            + _td(pct_c, 'right')
            + '</tr>'
        )

    n = len(_top)

    # | concentration flags |
    rows_html.append(_spacer(n)); n += 1
    rows_html.append(_sep_row('ESMA THRESHOLDS: 20% SINGLE / 50% TOP-3'))

    def _flag_color(txt):
        return C['red'] if '⚠' in txt else C['green']

    for label, val in [
        ('Largest investor', f"{_conc['largest_investor_pct']*100:.1f}% NAV   {flag_s}"),
        ('Top 3 investors',  f"{_conc['top3_pct']*100:.1f}% NAV   {flag_3}"),
    ]:
        bg = _BG_E if n % 2 == 0 else _BG_O; n += 1
        rows_html.append(
            f'<tr style="background:{bg};">'
            + _td(f'&nbsp;&nbsp;{label}', 'left')
            + f'<td colspan="4" style="{_FONT}{_PAD}text-align:left;color:{_flag_color(val)};'
              f'font-weight:bold;border-bottom:{_BORDER};">{val}</td>'
            + '</tr>'
        )

    # | 5-day notice stress |
    rows_html.append(_spacer(n)); n += 1
    rows_html.append(_sep_row(f"5-DAY NOTICE STRESS  ({_conc['largest_investor_pct']*100:.1f}% NAV)"))

    for label, val in [
        ('Redemption',    f"EUR {_r4['redemption_amount_eur']:,.0f}"),
        ('Liquid assets', f"EUR {_r4['liquid_assets_eur']:,.0f}"),
        ('Gap / Coverage',f"{_gap}   {_r4['coverage_ratio']:.2f}×"),
        ('Action',        _r4['recommendation']),
    ]:
        bg = _BG_E if n % 2 == 0 else _BG_O; n += 1
        rows_html.append(
            f'<tr style="background:{bg};">'
            + _td(f'&nbsp;&nbsp;{label}', 'left')
            + f'<td colspan="4" style="{_FONT}{_PAD}text-align:left;color:{_TXT};'
              f'border-bottom:{_BORDER};">{val}</td>'
            + '</tr>'
        )

    # | monitoring recommendation |
    rows_html.append(_spacer(n)); n += 1
    rows_html.append(_sep_row('MONITORING RECOMMENDATION'))

    notes = []
    if _conc['high_concentration']:
        notes.append('| Enhanced monitoring: top-3 investors represent significant co-ordinated exit risk')
        notes.append('| Maintain liquidity buffer ≥ largest investor AUM')
    if _conc['concentration_flag']:
        notes.append(f"| Gate-trigger review: largest investor at {_conc['largest_investor_pct']*100:.1f}% NAV")
    if not notes:
        notes.append('| No immediate action. Continue quarterly investor concentration monitoring.')

    for note in notes:
        bg = _BG_E if n % 2 == 0 else _BG_O; n += 1
        rows_html.append(
            f'<tr style="background:{bg};">'
            f'<td colspan="5" style="{_FONT}{_PAD}text-align:left;color:{_TXT};'
            f'border-bottom:{_BORDER};">&nbsp;&nbsp;{note}</td>'
            '</tr>'
        )

    caption_html = (
        f'<caption style="color:{C["cyan"]};font-size:14px;font-weight:bold;'
        f'text-align:left;font-family:Helvetica Neue,Arial,sans-serif;'
        f'padding-bottom:8px;background:#1a2540;">Investor Concentration | NAV: EUR {NAV:,.0f}</caption>'
    )
    table = (
        f'<table style="border-collapse:collapse;width:100%;background:{_BG_E};">'
        f'{caption_html}{thead}<tbody>{"".join(rows_html)}</tbody></table>'
    )
    display(HTML(table))


def display_redemption_stress(
    fund_id,
    notice_days,
    redemption_scenarios,
    nav,
    risk_df_liq,
    valuation_date: str | None = None,
    export_id: str | None = None
):
    """
    Compute and display redemption stress scenarios.

    Parameters
    ----------
    fund_id : str
        Fund identifier
    notice_days : int
        Contractual notice period (days)
    redemption_scenarios : list of tuples
        [(pct, label), ...] e.g. [(0.10, 'Normal'), (0.25, 'Large')]
    nav : float
        Fund NAV in EUR
    risk_df_liq : pd.DataFrame
        Positions with liquidity_bucket column
    export_id : str or None, default None
        If provided, save rendered HTML as PNG
    """
    from fund_risk_workflow.risk.risk_utils import redemption_stress
    from fund_risk_workflow.data.reference_data import load_investor_base_dict
    from fund_risk_workflow.computation.liquidity_calibration import compute_redemption_scenarios, compute_weighted_reference_rates

    # Convert list to work with
    scenarios_list = list(redemption_scenarios) if redemption_scenarios else []

    # Add "Largest investor" scenario if not already present
    if not any(label == 'Largest investor' for _, label in scenarios_list):
        try:
            investor_base = load_investor_base_dict(fund_id)
            investors_list = investor_base.get('investors', [])
            # Filter out aggregates
            actual_investors = [
                inv for inv in investors_list
                if not ('REM' in inv.get('investor_id', '') or
                        'remaining' in inv.get('investor_name', '').lower())
            ]
            if actual_investors:
                largest = max(actual_investors, key=lambda x: x.get('nav_pct', 0))
                largest_pct = largest.get('nav_pct', 0)
                if largest_pct > 0:
                    scenarios_list.append((largest_pct, 'Largest investor'))
        except:
            pass

    # Compute redemption stress for each scenario
    redstress = {}
    for _pct, _label in scenarios_list:
        _r = redemption_stress(risk_df_liq, nav, redemption_pct=_pct, notice_days=notice_days)
        _r['label'] = f'{_label} ({int(_pct*100)}%)' if isinstance(_pct, (int, float)) else _label
        _r['gap'] = f"+{_r['liquidity_gap_eur']/1e6:.1f}M" if _r['liquidity_gap_eur'] >= 0 else f"{_r['liquidity_gap_eur']/1e6:.1f}M"
        redstress[_pct] = _r

    # Display
    rows = []
    for _, v in redstress.items():
        # Extract percentage from label (e.g., "Normal (10%)" → "Normal", "10%")
        label = v['label']
        if '(' in label and '%' in label:
            scenario_name = label.split('(')[0].strip()
            redemption_pct = label.split('(')[1].rstrip(')')
        else:
            scenario_name = label
            redemption_pct = '—'

        rows.append({
            'Scenario':       scenario_name,
            'Redemption %':   redemption_pct,
            'redemption_eur': v['redemption_amount_eur'],
            'liquid_eur':     v['liquid_assets_eur'],
            'gap':            v['gap'],
            'coverage':       v['coverage_ratio'],
            'Action':         v['recommendation'],
        })

    # Add largest 3 investors scenario as last row
    try:
        investor_base = load_investor_base_dict(fund_id)
        investors_list = investor_base.get('investors', [])
        # Filter out aggregates
        actual_investors = [
            inv for inv in investors_list
            if not ('REM' in inv.get('investor_id', '') or
                    'remaining' in inv.get('investor_name', '').lower())
        ]
        if actual_investors:
            # Get top 3 investors
            top_3 = sorted(actual_investors, key=lambda x: x.get('nav_pct', 0), reverse=True)[:3]
            top_3_pct = sum(inv.get('nav_pct', 0) for inv in top_3)
            if top_3_pct > 0:
                _r = redemption_stress(risk_df_liq, nav, redemption_pct=top_3_pct, notice_days=notice_days)
                rows.append({
                    'Scenario':       'Top 3 investors',
                    'Redemption %':   f'{int(top_3_pct*100)}%',
                    'redemption_eur': _r['redemption_amount_eur'],
                    'liquid_eur':     _r['liquid_assets_eur'],
                    'gap':            f"+{_r['liquidity_gap_eur']/1e6:.1f}M" if _r['liquidity_gap_eur'] >= 0 else f"{_r['liquidity_gap_eur']/1e6:.1f}M",
                    'coverage':       _r['coverage_ratio'],
                    'Action':         _r['recommendation'],
                })
    except:
        pass

    df = pd.DataFrame(rows)

    # Build metadata with NAV and notice
    metadata_parts = []
    if valuation_date:
        metadata_parts.append(f'As of {valuation_date}')
    metadata_parts.append(f'NAV: EUR {nav:,.0f}')
    metadata_parts.append(f'Notice: {notice_days}d')
    metadata_str = ' | '.join(metadata_parts)

    html = display_dark_table(
        df,
        caption=f'Redemption Stress | {fund_id}',
        fmt={'redemption_eur': '{:,.0f}', 'liquid_eur': '{:,.0f}', 'coverage': '{:.2f}x'},
        col_styles={'coverage': lambda v: C['green'] if isinstance(v, float) and v >= 1.0 else C['red']},
        col_widths={'Scenario': '120px', 'Redemption %': '60px', 'coverage': '100px', 'Action': '100px'},
        date_str=metadata_str,
        date_label='',
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Redemption Stress')
        filename = f'{export_id}_{title_slug}'
        save_html_as_png(html, fund_id, filename, folder_suffix='_liquidity')


def display_combined_stress_mkt_plus_liq(
    risk_df,
    risk_df_liq,
    nav,
    notice_days,
    delta_equity=-0.20,
    redemption_pct=0.25,
    valuation_date: str | None = None,
    fund_id: str | None = None,
    export_id: str | None = None,
):
    """
    Display combined stress scenario: market shock + simultaneous redemption.

    Stress test: equity market moves by delta_equity (e.g. -20%) AND
    investors simultaneously redeem redemption_pct of NAV.

    Parameters
    ----------
    risk_df : pd.DataFrame
        Risk-ready positions (for stress_equity computation)
    risk_df_liq : pd.DataFrame
        Positions with liquidity buckets (for liquid asset calculation)
    nav : float
        Fund NAV in EUR
    notice_days : int
        Contractual notice period (days)
    delta_equity : float, optional
        Equity market shock (e.g. -0.20 for -20%). Default -0.20.
    redemption_pct : float, optional
        Redemption as fraction of NAV (e.g. 0.25 for 25%). Default 0.25.
    export_id : str or None, default None
        If provided, save rendered HTML as PNG
    """
    from fund_risk_workflow.risk.risk_utils import stress_equity, redemption_stress

    # Market stress
    comb_eq = stress_equity(risk_df, delta_equity=delta_equity)
    comb_mkt_eur = comb_eq['stressed_pnl_eur']
    comb_nav_st = nav + comb_mkt_eur

    # Redemption stress at base redemption_pct
    base_red = redemption_stress(risk_df_liq, nav, redemption_pct=redemption_pct, notice_days=notice_days)

    # Combined: liquid assets shrink by market stress
    comb_liquid_st = base_red['liquid_assets_eur'] * (1 - abs(delta_equity))
    comb_redeem_eur = nav * redemption_pct
    comb_gap_st = comb_liquid_st - comb_redeem_eur
    comb_cov_st = comb_liquid_st / comb_redeem_eur if comb_redeem_eur > 0 else float('inf')
    comb_action = 'Can meet redemption' if comb_gap_st >= 0 else 'Gate / partial suspension required'

    # Display
    rows = [
        {'Metric': 'Market shock', 'Value': f'Equity {delta_equity*100:.0f}%', 'EUR': '', 'Status': ''},
        {'Metric': 'Stressed NAV (post-market)', 'Value': '', 'EUR': f'{comb_nav_st:,.0f}', 'Status': ''},
        {'Metric': '', 'Value': '', 'EUR': '', 'Status': ''},
        {'Metric': 'Redemption stress', 'Value': f'{redemption_pct*100:.0f}% NAV', 'EUR': f'{comb_redeem_eur:,.0f}', 'Status': ''},
        {'Metric': 'Liquid assets (post-market)', 'Value': '', 'EUR': f'{comb_liquid_st:,.0f}', 'Status': ''},
        {'Metric': 'Liquidity gap', 'Value': '', 'EUR': f'{comb_gap_st:,.0f}', 'Status': comb_action},
        {'Metric': 'Coverage ratio', 'Value': f'{comb_cov_st:.2f}x', 'EUR': '', 'Status': '✓ OK' if comb_cov_st >= 1.0 else '⚠ SHORTFALL'},
    ]

    df = pd.DataFrame(rows)

    # Build metadata with NAV
    metadata_parts = []
    if valuation_date:
        metadata_parts.append(f'As of {valuation_date}')
    metadata_parts.append(f'NAV: EUR {nav:,.0f}')
    metadata_str = ' | '.join(metadata_parts)

    html = display_dark_table(
        df,
        caption='Combined Stress Test | Market + Liquidity',
        col_styles={
            'Status': lambda v: (
                C['green'] if isinstance(v, str) and ('✓' in v or 'Can meet' in v) else
                C['red'] if isinstance(v, str) and ('⚠' in v or 'Gate' in v) else None
            )
        },
        date_str=metadata_str,
        date_label='',
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Combined Stress Test | Market + Liquidity')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)


def display_counterparty_stress(NAV, valuation_date: str | None = None, fund_id: str | None = None, export_id: str | None = None, **kwargs):
    """
    Display counterparty stress table.

    Parameters
    ----------
    NAV : float
        Net asset value.
    valuation_date : str, optional
        Valuation date for display.
    export_id : str or None, default None
        If provided, save rendered HTML as PNG
    **kwargs : dict
        Expected keys: 'cp_df', 'worst_cp', 'loss_eur', 'loss_pct'.
        Or pass individual arguments: cp_df, worst_cp, loss_eur, loss_pct.
    """
    # Handle both dict unpacking and individual arguments
    _cp_hf = kwargs.get('cp_df')
    _worst_cp = kwargs.get('worst_cp')
    _cp_loss_eur = kwargs.get('loss_eur')
    _cp_loss_pct = kwargs.get('loss_pct')

    status  = '⚠ BREACH' if _cp_loss_pct > 0.05 else '✓ Within limit'

    # Pre-format all numeric columns as strings so summary rows stay blank.
    cp = _cp_hf[['counterparty', 'type', 'exposure_eur',
                  'collateral_eur', 'net_exposure_eur', 'net_pct_nav']].copy()
    cp['exposure_eur']     = cp['exposure_eur'].map('{:,.0f}'.format)
    cp['collateral_eur']   = cp['collateral_eur'].map('{:,.0f}'.format)
    cp['net_exposure_eur'] = cp['net_exposure_eur'].map('{:,.0f}'.format)
    cp['net_pct_nav_raw'] = cp['net_pct_nav']          # keep raw for color fn
    cp['net_pct_nav']     = cp['net_pct_nav'].map('{:.1%}'.format)

    def _srow(**kw):
        base = {c: '' for c in cp.columns}
        base['net_pct_nav_raw'] = float('nan')
        base.update(kw)
        return base

    # blank spacer + separator row
    cp = pd.concat([cp, pd.DataFrame([
        _srow(),
        _srow(counterparty='WORST-CASE DEFAULT SCENARIO'),
        _srow(counterparty='  Counterparty',               type=_worst_cp['counterparty']),
        _srow(counterparty='  Net loss (post-collateral)', type=f"EUR {_cp_loss_eur:,.0f}"),
        _srow(counterparty='  % of NAV',                  type=f'{_cp_loss_pct*100:.1f}%'),
        _srow(counterparty='  AIFMD limit',               type='5% NAV  (EU 231/2013 Art. 43)'),
        _srow(counterparty='  Status',                    type=status),
    ])], ignore_index=True)

    sep_idx = len(_cp_hf) + 1   # +1 for the blank spacer row

    # Build metadata with NAV
    metadata_parts = []
    if valuation_date:
        metadata_parts.append(f'As of {valuation_date}')
    metadata_parts.append(f'NAV: EUR {NAV:,.0f}')
    metadata_str = ' | '.join(metadata_parts)

    html = display_dark_table(
        cp.drop(columns=['net_pct_nav_raw']),
        caption='Counterparty Register',
        highlight_rows=[sep_idx],
        col_styles={
            'net_pct_nav': lambda v: (
                C['red']   if isinstance(v, str) and '⚠' in v else
                C['green'] if isinstance(v, str) and '✓' in v else None
            ),
            'type': lambda v: (
                C['red']   if isinstance(v, str) and '⚠' in v else
                C['green'] if isinstance(v, str) and '✓' in v else None
            ),
        },
        date_str=metadata_str,
        date_label='',
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Counterparty Register')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)


def display_attribution(attr, flagged):
    df = pd.DataFrame([
        ('Attribution period',         f"{attr.index.min().date()} → {attr.index.max().date()}"),
        ('Days attributed',            str(len(attr))),
        ('Correlation (actual vs expl.)', f"{attr['pnl_actual'].corr(attr['pnl_explained']):.3f}"),
        ('Median % explained',         f"{attr['pct_explained'].median():.1%}"),
        ('Days ≥ 80% explained',       f"{(attr['pct_explained'] >= 0.80).sum()}  ({(attr['pct_explained'] >= 0.80).mean():.1%})"),
        ('Residual vol (EUR)',          f"{attr['pnl_residual'].std():,.0f}"),
        ('Residual / total vol',        f"{attr['pnl_residual'].std() / attr['pnl_actual'].std():.1%}"),
        ('Flagged days',               f"{len(flagged)}  ({len(flagged)/len(attr):.1%})"),
    ], columns=['Metric', 'Value'])
    display_dark_table(
        df,
        caption='P&L Attribution Summary',
        col_align_override={'Value': 'right'},
        col_widths={'Metric': '260px', 'Value': '200px'},
    )


def display_historical_scenarios(historical_scenarios: dict, fund_id: str | None = None, export_id: str | None = None):
    """Render the HISTORICAL_SCENARIOS parameter table (shock definitions, not results)."""
    rows = []
    for _, p in historical_scenarios.items():
        rows.append({
            'Scenario'    : p['name'],
            'Equity'      : f"{p['delta_equity']*100:.0f}%",
            'Rates (bps)' : f"{p['delta_y']*10000:.0f}",
            'Credit (bps)': f"+{p['delta_spread']*10000:.0f}",
            'USD'         : f"{p['fx_shocks'].get('USD', 0)*100:+.0f}%",
            'GBP'         : f"{p['fx_shocks'].get('GBP', 0)*100:+.0f}%",
        })
    df = pd.DataFrame(rows)
    html = display_dark_table(
        df,
        caption='Historical Stress Scenarios | Shock Parameters',
        col_styles={
            'Equity'      : lambda v: C['red']   if isinstance(v, str) and v.startswith('-') else C['green'],
            'Rates (bps)' : lambda v: C['amber'] if isinstance(v, str) and v not in ('0', '+0') else None,
            'Credit (bps)': lambda v: C['amber'] if isinstance(v, str) and v not in ('0', '+0') else None,
            'USD'         : lambda v: C['red']   if isinstance(v, str) and v.startswith('-') else None,
            'GBP'         : lambda v: C['red']   if isinstance(v, str) and v.startswith('-') else None,
        },
        col_widths={'Scenario': '260px'},
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Historical Stress Scenarios | Shock Parameters')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)


def display_ucits_scenarios(risk_df, scenarios_result: dict, valuation_date: str | None = None, fund_id: str | None = None, export_id: str | None = None):
    """
    Render UCITS stress scenario P&L results from loader output.

    Builds custom scenarios dict from UCITS loader output, displays results,
    and shows any warnings.

    Parameters
    ----------
    risk_df : pd.DataFrame
        Position data with market_value_eur column
    scenarios_result : dict
        UCITS loader output with 'results', 'metadata', 'all_warnings' keys
    valuation_date : str, optional
        Display date (e.g., '2026-03-31')
    fund_id : str, optional
        Fund identifier for export
    export_id : str, optional
        Base filename for PNG export
    """
    # Build custom scenarios dict from loader output
    custom_scenarios = {}
    for scenario_id, result in scenarios_result['results'].items():
        metadata_row = scenarios_result['metadata'][
            scenarios_result['metadata']['scenario_id'] == scenario_id
        ]
        if not metadata_row.empty:
            scenario_name = metadata_row.iloc[0]['scenario_name']
            custom_scenarios[scenario_name] = {
                'stressed_pnl_eur': result['stressed_pnl_eur'],
                'stressed_nav_pct': result['stressed_nav_pct'],
            }

    # Display results
    display_scenarios(
        risk_df,
        custom=custom_scenarios,
        add_historical=False,
        valuation_date=valuation_date,
        fund_id=fund_id,
        export_id=export_id
    )

    # Show warnings
    if scenarios_result.get('all_warnings'):
        print("\n⚠ Warnings:")
        for warning in scenarios_result['all_warnings']:
            print(f"  - {warning}")
    else:
        print("\n✓ All scenarios computed without warnings")


def display_scenarios(risk_df, custom: dict | None = None, add_historical: bool = False, valuation_date: str | None = None, fund_id: str | None = None, export_id: str | None = None):
    """Render stress scenario P&L results | custom and/or historical."""
    from fund_risk_workflow.risk.risk_utils import HISTORICAL_SCENARIOS, stress_historical
    TNA  = risk_df['market_value_eur'].sum()

    # Build univariate and historical scenario rows
    univariate_rows = []
    historical_rows = []

    if custom:
        for label, result in custom.items():
            # Detect historical scenarios by date patterns in name (2008, 2020, 2022)
            is_historical = any(year in label for year in ['2008', '2020', '2022'])

            row = {
                'Scenario': f'  {label}',
                'pnl_eur' : result['stressed_pnl_eur'],
                'pct_tna' : result['stressed_pnl_eur'] / TNA * 100,
            }

            if is_historical:
                historical_rows.append(row)
            else:
                univariate_rows.append(row)

    # Also add from HISTORICAL_SCENARIOS if add_historical=True
    if add_historical:
        for key, params in HISTORICAL_SCENARIOS.items():
            result = stress_historical(risk_df, key)
            historical_rows.append({
                'Scenario': f'  {params["name"]}',
                'pnl_eur' : result['stressed_pnl_eur'],
                'pct_tna' : result['stressed_pnl_eur'] / TNA * 100,
            })

    # Assemble final rows with section headers, pre-formatting numeric values
    rows = []
    highlight_indices = []

    if univariate_rows:
        rows.append({'Scenario': 'Univariate Stress Tests', 'pnl_eur': '', 'pct_tna': ''})
        highlight_indices.append(len(rows) - 1)
        for r in univariate_rows:
            # Detect FX scenarios with no exposure
            is_fx_no_exposure = 'Base currency' in r['Scenario'] and r["pnl_eur"] == 0

            rows.append({
                'Scenario': r['Scenario'],
                'pnl_eur': 'no FX exposure' if is_fx_no_exposure else ('—' if r["pnl_eur"] == 0 else f'{r["pnl_eur"]:,.0f}'),
                'pct_tna': '—' if r["pct_tna"] == 0 else f'{r["pct_tna"]:.2f}%',
            })

    if historical_rows:
        rows.append({'Scenario': 'Most Relevant Historical Scenarios', 'pnl_eur': '', 'pct_tna': ''})
        highlight_indices.append(len(rows) - 1)
        for r in historical_rows:
            rows.append({
                'Scenario': r['Scenario'],
                'pnl_eur': '—' if r["pnl_eur"] == 0 else f'{r["pnl_eur"]:,.0f}',
                'pct_tna': '—' if r["pct_tna"] == 0 else f'{r["pct_tna"]:.2f}%',
            })

    df = pd.DataFrame(rows)

    html = display_dark_table(
        df,
        caption='Stress Tests Results',
        col_styles={
            'pnl_eur': lambda v: (C['muted'] if v == 'no FX exposure' else (C['red'] if v.startswith('-') else C['green']) if isinstance(v, str) and v and v != '—' else None),
            'pct_tna': lambda v: (C['red'] if v != '—' and float(v.rstrip('%')) < 0 else C['green']) if isinstance(v, str) and v and v != '—' else None,
        },
        col_align_override={'pnl_eur': 'right', 'pct_tna': 'right'},
        col_header_align_override={'pnl_eur': 'right', 'pct_tna': 'right'},
        highlight_rows=highlight_indices,
        col_widths={'Scenario': '260px'},
        date_str=valuation_date,
        return_html=True,
    )

    # Style "no FX exposure" cells with smaller, regular font
    html = html.replace(
        'no FX exposure',
        '<span style="font-weight: normal; font-size: 9px;">no FX exposure</span>'
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Stress Scenario Results')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)
def display_ptc(result: dict, test_number: int | None = None,
                col_widths_trade: dict | None = None,
                col_widths_metrics: dict | None = None,
                col_widths_breaches: dict | None = None,
                valuation_date: str | None = None,
                fund_id: str | None = None,
                export_id: str | None = None,
                return_html: bool = False) -> str | None:
    """Render pre-trade check as 3 separate independent tables.

    Table 1 (Trade Details): 4 columns
    Table 2 (Metrics): 3 columns (metric | pre-trade | post-trade)
    Table 3 (Breaches): 2 columns

    Parameters
    ----------
    col_widths_trade : dict, optional
        Column widths for trade table: {'label': 'XXXpx', 'value': 'XXXpx', ...}
    col_widths_metrics : dict, optional
        Column widths for metrics table: {'metric': 'XXXpx', 'pre': 'XXXpx', 'post': 'XXXpx'}
    col_widths_breaches : dict, optional
        Column widths for breaches table: {'item': 'XXXpx', 'value': 'XXXpx'}
    return_html : bool, default False
        If True, return combined HTML string instead of displaying. If False, display in notebook.
    """
    from datetime import datetime, timedelta
    import pandas as pd

    t        = result['proposed_trade']
    notional = abs(t['quantity'] * t['price_eur'])
    status   = '✓  PASSED' if result['passed'] else '✗  FAILED'
    pre      = result.get('pre_trade_metrics', {})
    cap_txt  = (f'Pre-Trade Evaluation #{test_number}'
                if test_number is not None else 'Pre-Trade Evaluation')
    if valuation_date:
        cap_txt += f'<br><span style="font-size: 10px; font-weight: normal; color: #999;">Computed on {valuation_date}</span>'

    def _fmt(k: str, v) -> str:
        if not isinstance(v, float): return str(v)
        if v == 0.0: return '—'
        k = k.lower()
        if any(x in k for x in ('leverage', 'multiplier')): return f'{v:.2f}×'
        if any(x in k for x in ('exposure', 'bonds', 'net_eq', 'borrowing',
                                 'fx_exposure', 'notional', 'deriv_')): return f'{v:,.0f}'
        if 'pct' in k or 'var' in k: return f'{v:.2f}%'
        if v > 10_000: return f'{v:,.0f}'
        return f'{v:.2f}'

    # Shared styles
    _BG_E   = '#1a1f2e'
    _BG_O   = '#141929'
    _BG_SEP = '#36394F'
    _TXT    = '#9ca3af'
    _SEP_C  = '#587580'
    _BORDER = '1px solid #0f1729'
    _FONT   = 'font-family:Arial,sans-serif;font-size:11px;'
    _PAD    = 'padding:5px 12px;'

    # ═════════════════════════════════════════════════════════════════════════
    # TABLE 1: TRADE DETAILS (4 columns)
    # ═════════════════════════════════════════════════════════════════════════

    if col_widths_trade is None:
        col_widths_trade = {'label1': '80px', 'value1': '50px', 'label2': '150px', 'value2': '100px'}

    # Compute settlement date
    val_date = pd.to_datetime(VALUATION_DATE)
    settlement_date = (val_date + timedelta(days=2)).strftime('%Y-%m-%d')
    counterparty = t.get('counterparty', '—')
    underlying_risk = t.get('underlying_risk', '—')

    trade_rows = []
    trade_data = [
        ('Fund', result['fund_id'], 'Trade Date', VALUATION_DATE),
        ('Trade', f"{t['direction'].upper()}  {t['quantity']:,} × {t['isin']}", 'Settlement', settlement_date),
        ('Notional', f"EUR {notional:,.0f}   @   EUR {t['price_eur']:,.2f}", 'Counterparty', counterparty),
        ('Result', status, 'Underlying Risk', underlying_risk),
    ]

    result_color = C['green'] if '✓' in status else C['red']

    for label1, val1, label2, val2 in trade_data:
        bg = _BG_E if len(trade_rows) % 2 == 0 else _BG_O
        val1_color = result_color if label1 == 'Result' else _TXT
        trade_rows.append(
            f'<tr style="background:{bg};">'
            f'<td style="{_FONT}{_PAD}color:{_TXT};text-align:right;border-bottom:{_BORDER};">{label1}</td>'
            f'<td style="{_FONT}{_PAD}color:{val1_color};text-align:left;border-bottom:{_BORDER};">{val1}</td>'
            f'<td style="{_FONT}{_PAD}color:{_TXT};text-align:right;border-bottom:{_BORDER};">{label2}</td>'
            f'<td style="{_FONT}{_PAD}color:{_TXT};text-align:left;border-bottom:{_BORDER};">{val2}</td>'
            '</tr>'
        )

    colgroup_trade = (
        f'<colgroup>'
        f'<col style="width:{col_widths_trade["label1"]};"><col style="width:{col_widths_trade["value1"]};"> '
        f'<col style="width:{col_widths_trade["label2"]};"><col style="width:{col_widths_trade["value2"]};"> '
        f'</colgroup>'
    )

    table1_html = (
        f'<table style="border-collapse:collapse;width:auto;table-layout:fixed;background:{_BG_E};">'
        f'<caption style="color:{C["cyan"]};font-size:14px;font-weight:bold;text-align:left;'
        f'font-family:Helvetica Neue,Arial,sans-serif;padding-bottom:8px;background:#1a2540;">{cap_txt}</caption>'
        f'{colgroup_trade}'
        f'<tbody>'
        f'<tr style="background:{_BG_SEP};"><td colspan="4" style="{_FONT}{_PAD}color:{_SEP_C};font-weight:bold;'
        f'letter-spacing:0.05em;text-transform:uppercase;text-align:left;border-bottom:{_BORDER};">FUND AND TRADE DETAILS</td></tr>'
        f'{"".join(trade_rows)}'
        f'</tbody></table>'
    )

    # ═════════════════════════════════════════════════════════════════════════
    # TABLE 2: METRICS (3 columns)
    # ═════════════════════════════════════════════════════════════════════════

    if col_widths_metrics is None:
        col_widths_metrics = {'metric': '120px', 'pre': '150px', 'post': '130px'}

    # Limit thresholds for breach detection
    _LIMITS = {
        'gross_leverage': 3.0,
        'commitment_leverage': 2.0,
        'max_issuer_pct': 25.0,
        'trade_issuer_pct': 25.0,
        'max_sector_pct': 30.0,
        'trade_sector_pct': 30.0,
        'max_net_short_pct': 0.2,
        'wtd_avg_days_to_liquidate': 30.0,
    }

    metrics_rows = []
    for k, v in result['post_trade_metrics'].items():
        bg = _BG_E if len(metrics_rows) % 2 == 0 else _BG_O
        pre_fmt = _fmt(k, pre[k]) if k in pre else ''
        post_fmt = _fmt(k, v)

        # Check if pre-trade metric breached limit
        pre_color = _TXT
        pre_breached = False
        if pre_fmt and k in _LIMITS:
            try:
                pre_val = float(pre[k])
                if pre_val > _LIMITS[k]:
                    pre_fmt = f'⚠ {pre_fmt}'
                    pre_color = '#fbbf24'  # yellow for pre-existing breach
                    pre_breached = True
            except (ValueError, TypeError, KeyError):
                pass

        # Check if post-trade metric breached limit
        post_breached = False
        if k in _LIMITS:
            try:
                post_val = float(v)
                post_breached = post_val > _LIMITS[k]
            except (ValueError, TypeError, KeyError):
                pass

        # Detect changes
        changed = (pre_fmt != post_fmt) and pre_fmt != ''

        # Determine if metric improved (for "lower is better" metrics)
        improved = False
        if changed and not post_breached:
            try:
                pre_val = float(str(pre[k]))
                post_val = float(v)
                # Lower is better for: concentrations, short exposure, days to liquidate, leverage
                lower_is_better = any(
                    x in k.lower() for x in ('pct', 'leverage', 'exposure', 'short', 'days')
                )
                improved = (post_val < pre_val) if lower_is_better else False
            except (ValueError, TypeError, KeyError):
                improved = False

        # Determine if breach worsened (for metrics where higher is worse)
        worsened = False
        if pre_breached and post_breached and changed:
            try:
                pre_val = float(pre[k])
                post_val = float(v)
                # For concentrations/leverage, higher is worse
                worsened = post_val > pre_val
            except (ValueError, TypeError, KeyError):
                worsened = False

        # Apply styling based on breach status | bold only if value changed
        if pre_breached and post_breached:
            if worsened:
                # Breach worsened | red + bold
                post_color = C['red']
                post_weight = 'font-weight:bold;' if changed else ''
            else:
                # Breach continued but not worse | yellow, no bold, with ⚠
                post_fmt = f'⚠ {post_fmt}'
                post_color = '#fbbf24'
                post_weight = ''
        elif not pre_breached and post_breached:
            # New breach | red + bold
            post_color = C['red']
            post_weight = 'font-weight:bold;'
        elif changed:
            # Changed (improved or just changed, no breach) | white + bold
            post_color = '#ffffff'
            post_weight = 'font-weight:bold;'
        else:
            # Unchanged | normal
            post_color = _TXT
            post_weight = ''

        metrics_rows.append(
            f'<tr style="background:{bg};">'
            f'<td style="{_FONT}{_PAD}color:{_TXT};text-align:left;border-bottom:{_BORDER};">&nbsp;&nbsp;{k}</td>'
            f'<td style="{_FONT}{_PAD}color:{pre_color};text-align:right;border-bottom:{_BORDER};">{pre_fmt}</td>'
            f'<td style="{_FONT}{_PAD}color:{post_color};{post_weight}text-align:right;border-bottom:{_BORDER};">{post_fmt}</td>'
            '</tr>'
        )

    colgroup_metrics = (
        f'<colgroup>'
        f'<col style="width:{col_widths_metrics["metric"]};"><col style="width:{col_widths_metrics["pre"]};"><col style="width:{col_widths_metrics["post"]};"> '
        f'</colgroup>'
    )

    table2_html = (
        f'<table style="border-collapse:collapse;width:auto;table-layout:fixed;background:{_BG_E};margin-top:15px;">'
        f'{colgroup_metrics}'
        f'<tbody>'
        f'<tr style="background:{_BG_SEP};"><td style="{_FONT}{_PAD}color:{_SEP_C};font-weight:bold;'
        f'letter-spacing:0.05em;text-transform:uppercase;text-align:left;border-bottom:{_BORDER};">METRICS</td>'
        f'<td style="{_FONT}{_PAD}color:{_SEP_C};font-weight:bold;letter-spacing:0.05em;text-transform:uppercase;'
        f'text-align:right;border-bottom:{_BORDER};">PRE-TRADE</td>'
        f'<td style="{_FONT}{_PAD}color:{_SEP_C};font-weight:bold;letter-spacing:0.05em;text-transform:uppercase;'
        f'text-align:right;border-bottom:{_BORDER};">POST-TRADE</td></tr>'
        f'{"".join(metrics_rows)}'
        f'</tbody></table>'
    )

    # ═════════════════════════════════════════════════════════════════════════
    # TABLE 3: BREACHES & PRE-EXISTING LIMITS
    # ═════════════════════════════════════════════════════════════════════════

    if col_widths_breaches is None:
        col_widths_breaches = {'item': '100px', 'value': '350px'}

    # Detect pre-existing breaches in concentration metrics
    pre_existing_sector_breaches = []
    pre_existing_issuer_breaches = []

    # Check sector breaches from pre-trade exposures
    sector_exp_pre = result.get('sector_exposures_pre', {})
    for sector, pct in sector_exp_pre.items():
        if pct > 30.0:
            pre_existing_sector_breaches.append(f"{sector}: {pct:.1f}%")

    # Check issuer breaches from pre-trade exposures
    issuer_exp_pre = result.get('issuer_exposures_pre', {})
    for issuer, pct in issuer_exp_pre.items():
        if pct > 25.0:
            pre_existing_issuer_breaches.append(f"{issuer}: {pct:.1f}%")

    breaches_rows = []

    if result['breaches']:
        # Trade caused new breaches | show in red
        for b in result['breaches']:
            breaches_rows.append(
                f'<tr style="background:{_BG_SEP};"><td colspan="2" style="{_FONT}{_PAD}color:{C["red"]};'
                f'font-weight:bold;letter-spacing:0.05em;text-transform:uppercase;text-align:left;border-bottom:{_BORDER};">✗&nbsp;{b["check"]}</td></tr>'
            )
            for label, value in [
                ('Limit', f"{b['limit']}{b['unit']}"),
                ('Post Trade', f"{float(b['actual']):.1f}{b['unit']}"),
                ('Detail', b['message']),
            ]:
                bg = _BG_E if len(breaches_rows) % 2 == 0 else _BG_O
                breaches_rows.append(
                    f'<tr style="background:{bg};">'
                    f'<td style="{_FONT}{_PAD}color:{_TXT};text-align:left;border-bottom:{_BORDER};">&nbsp;&nbsp;&nbsp;&nbsp;{label}</td>'
                    f'<td style="{_FONT}{_PAD}color:{_TXT};text-align:left;border-bottom:{_BORDER};">{value}</td>'
                    '</tr>'
                )
    else:
        # Trade approved | check if there are pre-existing breaches
        if pre_existing_sector_breaches or pre_existing_issuer_breaches:
            # Yellow | approved but pre-existing breaches
            status_color = '#fbbf24'  # yellow
            status_text = 'TRADE APPROVED | verify no related breaches below'
        else:
            # Green | no breaches at all
            status_color = C['green']
            status_text = 'NO LIMIT BREACHES | TRADE APPROVED'

        breaches_rows.append(
            f'<tr style="background:{_BG_SEP};"><td colspan="2" style="{_FONT}{_PAD}color:{status_color};'
            f'font-weight:bold;letter-spacing:0.05em;text-transform:uppercase;text-align:left;border-bottom:{_BORDER};">{status_text}</td></tr>'
        )

        # Show pre-existing breaches if any
        if pre_existing_sector_breaches:
            bg = _BG_E if len(breaches_rows) % 2 == 0 else _BG_O
            breaches_rows.append(
                f'<tr style="background:{bg};">'
                f'<td style="{_FONT}{_PAD}color:{_TXT};text-align:left;border-bottom:{_BORDER};">Sector breaches</td>'
                f'<td style="{_FONT}{_PAD}color:#fbbf24;text-align:left;border-bottom:{_BORDER};">{", ".join(pre_existing_sector_breaches)}</td>'
                '</tr>'
            )

        if pre_existing_issuer_breaches:
            bg = _BG_E if len(breaches_rows) % 2 == 0 else _BG_O
            breaches_rows.append(
                f'<tr style="background:{bg};">'
                f'<td style="{_FONT}{_PAD}color:{_TXT};text-align:left;border-bottom:{_BORDER};">Issuer/short breaches</td>'
                f'<td style="{_FONT}{_PAD}color:#fbbf24;text-align:left;border-bottom:{_BORDER};">{", ".join(pre_existing_issuer_breaches)}</td>'
                '</tr>'
            )

    colgroup_breaches = (
        f'<colgroup>'
        f'<col style="width:{col_widths_breaches["item"]};"><col style="width:{col_widths_breaches["value"]};"> '
        f'</colgroup>'
    )

    table3_html = (
        f'<table style="border-collapse:collapse;width:auto;table-layout:fixed;background:{_BG_E};margin-top:15px;">'
        f'{colgroup_breaches}'
        f'<tbody>'
        f'{"".join(breaches_rows)}'
        f'</tbody></table>'
    )

    # Combine all 3 tables into one HTML
    combined_html = table1_html + '<br>' + table2_html + '<br>' + table3_html

    # Return HTML if requested
    if return_html:
        return combined_html

    # Otherwise display in notebook
    display(HTML(table1_html))
    display(HTML(table2_html))
    display(HTML(table3_html))

    # Save as PNG if export_id is provided
    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Pre-Trade Check')
        filename = f'{export_id}_{title_slug}'
        save_html_as_png(combined_html, result.get('fund_id', 'unknown'), filename)


def display_asset_class_breakdown(df: pd.DataFrame, valuation_date: str | None = None, fund_id: str | None = None, export_id: str | None = None) -> None:
    """
    Display asset class breakdown with market value, position count, and weight.

    Parameters
    ----------
    df : pd.DataFrame
        Risk DataFrame with columns: asset_class, market_value_eur, isin.
    export_id : str or None, default None
        If provided, save rendered HTML as PNG

    Returns
    -------
    None
        Displays table via IPython.display.
    """
    # Compute NAV from DataFrame
    nav = float(df['market_value_eur'].sum())

    # Group by asset class
    breakdown = df.groupby('asset_class').agg(
        market_value_eur=('market_value_eur', 'sum'),
        n_positions=('isin', 'count'),
    ).sort_values('market_value_eur', ascending=False)

    breakdown['weight_pct'] = breakdown['market_value_eur'] / nav * 100

    # Format columns
    breakdown['market_value_eur'] = breakdown['market_value_eur'].map('{:,.0f}'.format)
    breakdown['weight_pct'] = breakdown['weight_pct'].map('{:.2f}%'.format)
    breakdown['n_positions'] = breakdown['n_positions'].map('{:d}'.format)
    breakdown = breakdown.reset_index()


    # Rename for display
    breakdown.columns = ['Asset Class', 'Market Value (EUR)', '# Positions', '% NAV']
    

    html = display_dark_table(
        breakdown,
        caption='Asset Class Breakdown',
        col_align_override={'Asset Class': 'left',
                           'Market Value (EUR)': 'right',
                           '# Positions': 'right',
                           '% NAV': 'right'},
        date_str=valuation_date,
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('Asset Class Breakdown')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)


def display_top_positions(df: pd.DataFrame, n_top: int = 100, valuation_date: str | None = None, fund_id: str | None = None, export_id: str | None = None) -> None:
    """
    Display top N positions as an HTML table with asset class, issuer, market value, and weight.

    Parameters
    ----------
    df : pd.DataFrame
        Risk DataFrame with columns: asset_class, issuer, market_value_eur.
    n_top : int
        Number of top positions to display. Default: 100.
    export_id : str or None, default None
        If provided, save rendered HTML as PNG

    Returns
    -------
    None
        Displays table via IPython.display.
    """
    # Compute NAV from DataFrame
    nav = float(df['market_value_eur'].sum())

    # Select available columns
    cols = ['asset_class', 'instrument_name', 'market_value_eur']
    available_cols = [col for col in cols if col in df.columns]

    # Sort by market value descending and take top N
    top_pos = df.nlargest(n_top, 'market_value_eur')[available_cols].copy()

    top_pos['weight_pct'] = top_pos['market_value_eur'] / nav * 100

    # Format columns
    top_pos['market_value_eur'] = top_pos['market_value_eur'].map('{:,.0f}'.format)
    top_pos['weight_pct'] = top_pos['weight_pct'].map('{:.2f}%'.format)
    
    # top_pos = top_pos.reset_index() 

    # Rename for display
    col_names = {'asset_class': 'Asset Class', 'instrument_name': 'Instrument',
                 'market_value_eur': 'Market Value (EUR)', 'weight_pct': '% NAV'}
    top_pos.columns = [col_names.get(col, col) for col in top_pos.columns]

    # Align columns appropriately
    col_align = {col: 'left' if col in ['Asset Class', 'Issuer'] else 'right'
                 for col in top_pos.columns}

    html = display_dark_table(
        top_pos,
        caption=f'Top {n_top} Positions',
        col_align_override=col_align,
        date_str=valuation_date,
        return_html=True,
    )

    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify(f'Top {n_top} Positions')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)


def display_counterparty_risk_ucits(NAV, cp_result: dict, fund_id: str | None = None, valuation_date: str | None = None):
    """Display UCITS counterparty risk exposure.

    Parameters
    ----------
    NAV : float
        Fund NAV in EUR
    cp_result : dict
        Result from compute_counterparty_stress() with keys:
        'cp_df', 'worst_cp', 'loss_eur', 'loss_pct'
    fund_id : str, optional
        Fund identifier for display
    valuation_date : str, optional
        Valuation date for display
    """
    _cp_ucits = cp_result['cp_df']
    _worst_cp = cp_result['worst_cp']
    _cp_loss_eur = cp_result['loss_eur']
    _cp_loss_pct = cp_result['loss_pct']

    status = '⚠ BREACH' if _cp_loss_pct > 0.10 else '✓ Within limit'

    cp = _cp_ucits[['counterparty', 'type', 'exposure_eur',
                     'collateral_eur', 'net_exposure_eur', 'net_pct_nav']].copy()
    cp['exposure_eur']     = cp['exposure_eur'].map('{:,.0f}'.format)
    cp['collateral_eur']   = cp['collateral_eur'].map('{:,.0f}'.format)
    cp['net_exposure_eur'] = cp['net_exposure_eur'].map('{:,.0f}'.format)
    cp['net_pct_nav_raw']  = cp['net_pct_nav']
    cp['net_pct_nav']      = cp['net_pct_nav'].map('{:.1%}'.format)

    def _srow(**kw):
        base = {c: '' for c in cp.columns}
        base['net_pct_nav_raw'] = float('nan')
        base.update(kw)
        return base

    cp = pd.concat([cp, pd.DataFrame([
        _srow(),
        _srow(counterparty='WORST-CASE COUNTERPARTY DEFAULT'),
        _srow(counterparty='  Counterparty',                   type=_worst_cp['counterparty']),
        _srow(counterparty='  Net exposure (post-collateral)', type=f"EUR {_cp_loss_eur:,.0f}"),
        _srow(counterparty='  % of NAV',                      type=f'{_cp_loss_pct*100:.1f}%'),
        _srow(counterparty='  UCITS limit',                   type='10% NAV  (UCITS Dir. Art. 52)'),
        _srow(counterparty='  Status',                        type=status),
    ])], ignore_index=True)

    sep_idx = len(_cp_ucits) + 1

    # Format caption and date string
    caption = f'Counterparty Exposure | {fund_id}' if fund_id else 'Counterparty Exposure'
    date_str = ''
    if valuation_date:
        date_str = f'As of {valuation_date} | NAV: EUR {NAV:,.0f}'
    else:
        date_str = f'NAV: EUR {NAV:,.0f}'

    display_dark_table(
        cp.drop(columns=['net_pct_nav_raw']),
        caption=caption,
        date_str=date_str,
        highlight_rows=[sep_idx],
        col_styles={
            'net_pct_nav': lambda v: (
                C['red']   if isinstance(v, str) and '⚠' in v else
                C['green'] if isinstance(v, str) and '✓' in v else None
            ),
            'type': lambda v: (
                C['red']   if isinstance(v, str) and '⚠' in v else
                C['green'] if isinstance(v, str) and '✓' in v else None
            ),
        },
    )


def display_ucits_compliance_checks(compliance_result: dict, export_id: str | None = None, fund_id: str | None = None, valuation_date: str | None = None):
    """
    Display UCITS position-level compliance checks.

    Parameters
    ----------
    compliance_result : dict
        Result from ucits_compliance_checks.run_ucits_compliance_checks()
    export_id : str, optional
        Export ID for saving output
    fund_id : str, optional
        Fund identifier for output directory
    valuation_date : str, optional
        Valuation date for display header
    """
    # Build summary table
    checks = [
        ['Long-only constraint', compliance_result['long_only']['status']],
        ['10% position limit', compliance_result['concentration']['status']],
        ['Eligible assets', compliance_result['eligible_assets']['status']],
        ['Weights sum to 100%', compliance_result['weights']['status']],
    ]

    summary_df = pd.DataFrame(checks, columns=['Check', 'Status'])

    # Color status
    def _status_color(v):
        if isinstance(v, str):
            if 'OK' in v:
                return C['green']
            elif 'FLAG' in v or 'FAIL' in v:
                return C['red']
        return None

    # Build date_str with status
    date_str = None
    if valuation_date:
        status_text = compliance_result['overall_status']
        date_str = f"{valuation_date} | Status: {status_text}"

    html = display_dark_table(
        summary_df,
        caption="UCITS Compliance Checks",
        col_styles={'Status': _status_color},
        date_str=date_str,
        return_html=True,
    )

    display(HTML(html))

    # Detail any breaches
    if compliance_result['concentration']['breaches']:
        breach_df = pd.DataFrame(compliance_result['concentration']['breaches'])
        breach_df.columns = ['Instrument', 'Weight (%)']
        breach_df['Weight (%)'] = breach_df['Weight (%)'].map('{:.1f}%'.format)
        print("\n⚠ 10% Limit Breaches:")
        display_dark_table(breach_df, caption="Non-ETF positions exceeding 10% NAV")

    if compliance_result['eligible_assets']['illiquid']:
        illiquid_df = pd.DataFrame(compliance_result['eligible_assets']['illiquid'])
        illiquid_df.columns = ['Instrument', 'Asset Class']
        print("\n⚠ Illiquid Instruments:")
        display_dark_table(illiquid_df, caption="Assets with zero ADV")

    # Export if requested
    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('UCITS Compliance Checks')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)


def display_ucits_relative_var(rel_var_result: dict, export_id: str | None = None, fund_id: str | None = None):
    """
    Display UCITS relative VaR analysis.

    Parameters
    ----------
    rel_var_result : dict
        Result from ucits_relative_var.compute_ucits_relative_var()
    export_id : str, optional
        Export ID for saving output
    fund_id : str, optional
        Fund identifier for output directory
    """
    df = pd.DataFrame([
        ['Fund VaR (20d, 99%)', f"{rel_var_result['fund_var_pct']:.3f}%"],
        ['Reference Portfolio VaR', f"{rel_var_result['reference_var_pct']:.3f}%"],
        ['Relative VaR Ratio', f"{rel_var_result['relative_var_ratio']:.2f}x"],
        ['UCITS Limit', f"{rel_var_result['limit_multiplier']:.1f}x"],
        ['Utilisation', f"{rel_var_result['utilisation_pct']:.1f}%"],
        ['Status', rel_var_result['status']],
    ], columns=['Metric', 'Value'])

    # Color status
    def _status_color(v):
        if isinstance(v, str):
            if 'COMPLIANT' in v or 'OK' in v:
                return C['green']
            elif 'BREACH' in v or 'FAIL' in v:
                return C['red']
        return None

    html = display_dark_table(
        df,
        caption='UCITS Relative VaR Limit Monitoring',
        col_styles={'Status': _status_color},
        col_widths={'Metric': '200px', 'Value': '150px'},
        return_html=True,
    )

    display(HTML(html))

    # Export if requested
    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('UCITS Relative VaR')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)


def display_ucits_srri(srri_result: dict, export_id: str | None = None, fund_id: str | None = None):
    """
    Display UCITS Summary Risk Indicator (SRRI) analysis.

    Parameters
    ----------
    srri_result : dict
        Result from ucits_srri.compute_srri_from_nav_history()
    export_id : str, optional
        Export ID for saving output
    fund_id : str, optional
        Fund identifier for output directory
    """
    from fund_risk_workflow.risk.ucits_srri import srri_as_string

    srri_bucket = srri_result['sri_bucket']
    srri_desc = srri_as_string(srri_bucket)

    # Warn if insufficient data
    if srri_result.get('status') == 'INSUFFICIENT_DATA':
        print(f"⚠ SRRI based on {srri_result['observation_count']} weeks (insufficient for standard 260-week window)")

    df = pd.DataFrame([
        ['SRRI Category', f'{srri_bucket} | {srri_desc}'],
        ['Annualised Volatility', f"{srri_result['volatility_annual_pct']:.2f}%"],
        ['Weekly Volatility', f"{srri_result['volatility_weekly_pct']:.2f}%"],
        ['Observation Count', str(srri_result['observation_count'])],
        ['Time Window', f"{srri_result['time_window_years']:.1f} years"],
    ], columns=['Metric', 'Value'])

    html = display_dark_table(
        df,
        caption='UCITS Summary Risk Indicator (SRRI)',
        col_widths={'Metric': '200px', 'Value': '250px'},
        return_html=True,
    )

    display(HTML(html))

    # Export if requested
    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('UCITS SRRI')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)


def display_ucits_relative_var_point_in_time(result: dict, valuation_date: str | None = None,
                                              fund_id: str | None = None, export_id: str | None = None):
    """Display UCITS relative VaR from computed result."""
    import numpy as np

    df = pd.DataFrame([
        [f"Fund VaR {result['var_holding_period']}d",
         f"{result['fund_var_1d_pct'] * np.sqrt(result['var_holding_period'])*100:.3f}%"],
        [f"Reference VaR {result['var_holding_period']}d",
         f"{result['reference_var_1d_pct'] * np.sqrt(result['var_holding_period'])*100:.3f}%"],
        ['Relative VaR Ratio', f"{result['relative_var_ratio']:.2f}x"],
        ['Limit', f"{result['relative_var_limit']:.1f}x"],
        ['Utilisation', f"{result['utilisation_pct']:.1f}%"],
        ['Status', result['status']],
    ], columns=['Metric', 'Value'])

    def _status_color(v):
        if isinstance(v, str):
            if 'BREACH' in v:
                return C['red']
            elif 'WARNING' in v:
                return C['amber']
            elif 'OK' in v:
                return C['green']
        return None

    html = display_dark_table(df, caption='UCITS Relative VaR', col_styles={'Status': _status_color},
                             date_str=valuation_date, return_html=True)
    display(HTML(html))

    if export_id:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        save_html_as_png(html, fund_id or 'unknown', f"{export_id}_{_slugify('UCITS Relative VaR')}")


def display_ucits_srri_point_in_time(result: dict, valuation_date: str | None = None,
                                     fund_id: str | None = None, export_id: str | None = None):
    """Display UCITS SRRI from computed result."""
    from fund_risk_workflow.risk.ucits_srri import srri_as_string

    df = pd.DataFrame([
        ['SRRI Category', f"{result['sri_bucket']} | {srri_as_string(result['sri_bucket'])}"],
        ['Annualised Volatility', f"{result['volatility_annual_pct']:.2f}%"],
        ['Weekly Observations', str(result['observation_count'])],
    ], columns=['Metric', 'Value'])

    html = display_dark_table(df, caption='UCITS Summary Risk Indicator (SRRI)',
                             date_str=valuation_date, return_html=True)
    display(HTML(html))

    if export_id:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        save_html_as_png(html, fund_id or 'unknown', f"{export_id}_{_slugify('UCITS SRRI')}")


def display_srri_monitoring(srri_rolling: dict, current_disclosed_srri: int,
                           fund_id: str | None = None, valuation_date: str | None = None,
                           export_id: str | None = None):
    """
    Display rolling SRRI monitoring: volatility chart with SRRI thresholds and history panel.

    Parameters
    ----------
    srri_rolling : dict
        Result from compute_srri_rolling_monthly()
    current_disclosed_srri : int
        The officially disclosed SRRI bucket (1-7)
    fund_id : str, optional
        Fund ID for export filename
    valuation_date : str, optional
        Valuation date for display
    export_id : str, optional
        Export ID prefix for saving plots
    """
    from fund_risk_workflow.ui.nb_utils import _slugify, save_fig
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
    from fund_risk_workflow.ui.plot_style import ACCENT, C
    import numpy as np

    rolling_df = srri_rolling['rolling_srri_df'].copy()

    if rolling_df.empty:
        print("No rolling SRRI data available")
        return

    # Extract key metrics
    current_srri = srri_rolling['current_srri']
    current_vol = srri_rolling['current_volatility_pct']
    kiid_required = srri_rolling['kiid_update_required']
    latest_date = rolling_df.iloc[-1]['date']
    latest_date_str = latest_date.strftime('%Y-%m-%d') if hasattr(latest_date, 'strftime') else str(latest_date)

    # ===== MAIN FIGURE: Plot LEFT, history panel RIGHT =====
    fig = plt.figure(figsize=(14, 6.5))
    gs = GridSpec(1, 2, figure=fig, width_ratios=[5.4, 1.8], wspace=0.04,
                  left=0.05, right=0.94, top=0.88, bottom=0.12)

    # Main axis: volatility chart with SRRI thresholds
    ax_main = fig.add_subplot(gs[0, 0])

    dates = rolling_df['date'].values
    volatilities = rolling_df['volatility_pct'].values

    # SRRI threshold boundaries (CESR/10-673) and blue color gradient (enhanced contrast)
    srri_boundaries = [0.0, 0.5, 2.0, 5.0, 10.0, 15.0, 25.0, 100.0]
    blues = ['#E6F2FF', '#CCE5FF', '#9ECCFF', '#6699FF', '#3366FF', '#1A4DB8', '#001A66']

    # Plot SRRI threshold bands (alpha=0.12 for stronger visibility)
    for i in range(len(blues)):
        ax_main.axhspan(srri_boundaries[i], srri_boundaries[i+1], alpha=0.12, color=blues[i])

    # Plot volatility line (dominant visual)
    ax_main.plot(dates, volatilities, color=ACCENT, linewidth=2.5, marker='o',
                 markersize=3.5, zorder=5)

    # Mark SRRI category changes with RED markers (no outline, no text)
    has_category_change = False
    for i in range(1, len(rolling_df)):
        prev_srri = int(rolling_df.iloc[i-1]['srri'])
        curr_srri = int(rolling_df.iloc[i]['srri'])
        if prev_srri != curr_srri:
            date_change = rolling_df.iloc[i]['date']
            vol_change = rolling_df.iloc[i]['volatility_pct']
            ax_main.scatter([date_change], [vol_change], s=60, color='#E74C3C', marker='o',
                           zorder=6, edgecolors='none', label='SRRI Category Change' if not has_category_change else '')
            has_category_change = True

    # Mark KIID update trigger dates with red stars (if any)
    if len(srri_rolling['trigger_dates']) > 0:
        for trigger_date in srri_rolling['trigger_dates']:
            mask = rolling_df['date'] == trigger_date
            if mask.any():
                trigger_vol = rolling_df[mask]['volatility_pct'].values[0]
                ax_main.scatter([trigger_date], [trigger_vol], s=120, color='#E74C3C', marker='*',
                               zorder=7, edgecolors='none')

    # Y-axis: ticks ONLY at SRRI boundaries, formatted with % and no .0
    y_max = max(volatilities) * 1.15
    ax_main.set_ylim(0, y_max)
    ax_main.set_yticks(srri_boundaries[1:-1])  # 0.5, 2.0, 5.0, 10.0, 15.0, 25.0

    # Format y-axis labels: remove .0, add %
    y_tick_labels = []
    for v in srri_boundaries[1:-1]:
        if v == int(v):
            y_tick_labels.append(f'{int(v)}%')
        else:
            y_tick_labels.append(f'{v}%')
    ax_main.set_yticklabels(y_tick_labels, fontsize=9)

    # ===== SRRI bucket labels (1-7) on right edge, inside plot, alpha=0.07 =====
    # Only show labels up to the maximum volatility level observed
    max_vol = max(volatilities)
    max_srri_to_show = 7 if max_vol >= 25.0 else 6  # Skip SRRI 7 if max vol < 25%

    label_positions = [(srri_boundaries[i] + srri_boundaries[i+1]) / 2 for i in range(len(blues))]
    ax_lim_right = dates[-1]
    for i in range(max_srri_to_show):
        y_pos = label_positions[i]
        ax_main.text(ax_lim_right, y_pos, f'SRRI {i+1}', fontsize=7.5, ha='right', va='center',
                    bbox=dict(boxstyle='round,pad=0.25', facecolor='white', alpha=0.07,
                             edgecolor='none'))

    ax_main.set_ylabel('Annualised Volatility', fontsize=10, fontweight='bold')
    ax_main.set_xlabel('')  # Remove x-axis label
    ax_main.grid(True, axis='y', alpha=0.2, linestyle='--', linewidth=0.5)
    ax_main.tick_params(labelsize=9)

    # Add legend if there are category changes
    if has_category_change:
        ax_main.legend(fontsize=9, loc='upper left', framealpha=0.9)

    # ===== RIGHT PANEL: 6-month history table (OUTSIDE plot area) =====
    ax_history = fig.add_subplot(gs[0, 1])
    ax_history.axis('off')

    # Title (RIGHT-anchored to prevent overflow)
    ax_history.text(0.88, 1.0, 'Last 6 mo SRRI', transform=ax_history.transAxes, fontsize=9,
                   ha='right', va='top', fontweight='bold', color=C['muted'])

    # Build history table with enhanced spacing and centered columns
    recent_df = rolling_df.tail(6).copy()

    # Column headers (centered)
    header_line = f"{'Date':^8}  {'Vol%':^8}  {'SRRI':^6}  {'Update KIID':^12}"
    history_lines = [header_line]
    history_lines.append('─' * 42)

    # Data rows (centered values)
    for idx, row in recent_df.iterrows():
        date_str = row['date'].strftime('%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])
        srri_val = int(row['srri'])
        vol_pct = row['volatility_pct']
        kiid_flag = 'Yes' if (len(srri_rolling['trigger_dates']) > 0 and row['date'] >= srri_rolling['trigger_dates'][0]) else 'No'

        data_line = f"{date_str:^8}  {vol_pct:^8.2f}  {srri_val:^6}  {kiid_flag:^12}"
        history_lines.append(data_line)

    history_text = '\n'.join(history_lines)

    ax_history.text(0.88, 0.95, history_text, transform=ax_history.transAxes, fontsize=8,
                   ha='right', va='top', family='monospace', linespacing=1.5,
                   bbox=dict(boxstyle='round,pad=0.6', facecolor='white', alpha=0.07,
                            edgecolor='none'))

    # ===== Titles: Following VAR backtest style (cyan suptitle, grey subtitle, LEFT-aligned) =====
    fig.suptitle(
        f'SRRI Monitoring | Rolling Volatility | {fund_id or "Fund"}',
        fontsize=14,
        fontweight='bold',
        color=C['cyan'],
        ha='left',
        x=0.03,
    )

    fig.text(
        0.03, 0.935,
        f'Computation Date {valuation_date}',
        fontsize=11,
        color=C['muted'],
        va='top',
    )

    # Save plot using VAR backtest approach
    if export_id:
        from fund_risk_workflow.ui.nb_utils import _get_project_root
        title_slug = _slugify('SRRI Monitoring')
        filename = f'{export_id}_{title_slug}'
        out_dir = _get_project_root() / 'fig' / fund_id
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f'{filename}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight', pad_inches=0.25, facecolor=fig.get_facecolor())

    plt.show()


def display_ucits_var_monitoring_summary(summary_df: pd.DataFrame, valuation_date: str | None = None, export_id: str | None = None, fund_id: str | None = None):
    """Display UCITS VaR Monitoring Summary table."""
    from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png

    html = display_dark_table(
        summary_df,
        caption='VaR Monitoring Summary',
        date_str=valuation_date,
        date_label='As of',
        col_widths={'Metric': '240px'},
        return_html=True
    )
    display(HTML(html))

    if export_id:
        save_html_as_png(html, fund_id or 'unknown', f"{export_id}_{_slugify('VaR Monitoring Summary')}")


def display_ucits_monthly_report(results: dict, risk_df: pd.DataFrame, limits: dict, valuation_date: str, fund_id: str, col_widths: dict | None = None):
    """
    Display UCITS monthly risk report as HTML table.

    Parameters
    ----------
    results : dict
        Computed risk results with keys:
        - 'var': var_result from compute_fixed_position_var_1day()
        - 'rel_var': rel_var_result from compute_ucits_relative_var_point_in_time()
        - 'srri': srri_result from compute_srri_from_fund()
        - 'backtest': backtest report DataFrame
        - 'scenarios': dict of custom stress scenario results
        - 'srri_rolling': rolling SRRI monitoring result
    risk_df : pd.DataFrame
        Risk dataframe (used to compute historical scenarios)
    limits : dict
        Risk limits with keys: 'absolute_var_pct', 'relative_var'
    valuation_date : str
        Valuation date (YYYY-MM-DD)
    fund_id : str
        Fund identifier
    col_widths : dict, optional
        Column width overrides
    """
    from fund_risk_workflow.risk.risk_utils import stress_historical

    # Extract results
    var_result = results['var']
    rel_var_result = results['rel_var']
    srri_result = results['srri']
    report = results['backtest']
    custom_scenarios = results['scenarios']
    srri_rolling = results['srri_rolling']

    # Extract limits
    absolute_var_limit_pct = limits['absolute_var_pct']
    relative_var_limit = limits['relative_var']

    # Compute metrics
    report_date = pd.Timestamp(valuation_date).strftime('%B %d, %Y')
    nav_eur = risk_df['market_value_eur'].sum()
    abs_var_20d_pct = var_result['var_hist_scaled_pct']
    abs_util = (abs_var_20d_pct / absolute_var_limit_pct) * 100
    rel_var_ratio = rel_var_result['relative_var_ratio']
    rel_util = rel_var_result['utilisation_pct']
    srri_category = srri_result['sri_bucket']
    srri_volatility = srri_result['volatility_annual_pct']

    report_99 = report[report['confidence'] == 99].iloc[0]
    n_breaches = int(report_99['n_breaches'])
    kupiec_p = report_99['kupiec_p']
    chris_p = report_99['christoffersen_p']
    zone = '🟢 Green' if n_breaches <= 4 else '🟡 Amber' if n_breaches <= 9 else '🔴 Red'

    scenario_pcts = {name: result['stressed_nav_pct'] for name, result in custom_scenarios.items()}

    hist_scenario_pcts = {}
    for scenario_key in ['2008', '2020', '2022']:
        result = stress_historical(risk_df, scenario_key)
        hist_scenario_pcts[scenario_key] = result['stressed_nav_pct']

    kiid_update = srri_rolling['kiid_update_required']

    # Build table rows
    rows = []
    rows.append({'Metric': 'IDENTIFICATION', 'Value': '', 'Status': ''})
    rows.append({'Metric': 'Fund Name', 'Value': 'UCITS Balanced', 'Status': '—'})
    rows.append({'Metric': 'Valuation Date', 'Value': report_date, 'Status': '—'})
    rows.append({'Metric': 'NAV (EUR)', 'Value': f'{nav_eur:,.0f}', 'Status': '—'})

    rows.append({'Metric': 'VAR SUMMARY', 'Value': '', 'Status': ''})
    rows.append({'Metric': 'Absolute VaR (20d 99%)', 'Value': f'{abs_var_20d_pct:.2f}%', 'Status': f'Limit {absolute_var_limit_pct:.1f}% — Util {abs_util:.1f}%'})
    rows.append({'Metric': 'Relative VaR (ratio)', 'Value': f'{rel_var_ratio:.2f}x', 'Status': f'Limit {relative_var_limit:.1f}x — Util {rel_util:.1f}%'})
    rows.append({'Metric': 'VaR Model', 'Value': 'Historical (250d)', 'Status': '—'})

    rows.append({'Metric': 'SRRI', 'Value': '', 'Status': ''})
    rows.append({'Metric': 'Current Category', 'Value': str(srri_category), 'Status': '—'})
    rows.append({'Metric': 'Annualised Volatility', 'Value': f'{srri_volatility:.2f}%', 'Status': '—'})
    rows.append({'Metric': 'KIID Update', 'Value': 'YES' if kiid_update else 'NO', 'Status': 'Action required' if kiid_update else '—'})

    rows.append({'Metric': 'BACKTESTS', 'Value': '', 'Status': ''})
    rows.append({'Metric': 'Observation Window', 'Value': '250 trading days', 'Status': '—'})
    rows.append({'Metric': 'Breaches', 'Value': str(n_breaches), 'Status': 'Expected: 2.5'})
    rows.append({'Metric': 'Zone', 'Value': zone, 'Status': '—'})
    rows.append({'Metric': 'Kupiec POF', 'Value': f'{kupiec_p:.4f}', 'Status': 'PASS' if kupiec_p > 0.05 else 'FAIL'})
    rows.append({'Metric': 'Christoffersen', 'Value': f'{chris_p:.4f}', 'Status': 'PASS' if chris_p > 0.05 else 'FAIL'})

    rows.append({'Metric': 'STRESS TESTING', 'Value': '', 'Status': ''})
    rows.append({'Metric': 'Equity crash -30%', 'Value': f'{scenario_pcts["Equity Crash -30%"]:.2f}%', 'Status': '—'})
    rows.append({'Metric': 'Rate shock +200bps', 'Value': f'{scenario_pcts["Rate Shock +200bps"]:.2f}%', 'Status': '—'})
    rows.append({'Metric': 'Credit widening +150bps', 'Value': f'{scenario_pcts["Credit Widening +150bps"]:.2f}%', 'Status': '—'})
    rows.append({'Metric': 'FX stress -15%', 'Value': f'{scenario_pcts["FX Stress USD/GBP -15%"]:.2f}%', 'Status': '—'})
    rows.append({'Metric': 'Combined', 'Value': f'{scenario_pcts["Combined"]:.2f}%', 'Status': '—'})
    rows.append({'Metric': '2008 GFC', 'Value': f'{hist_scenario_pcts["2008"]:.2f}%', 'Status': 'Reference'})
    rows.append({'Metric': '2020 COVID', 'Value': f'{hist_scenario_pcts["2020"]:.2f}%', 'Status': 'Reference'})
    rows.append({'Metric': '2022 Rate Shock', 'Value': f'{hist_scenario_pcts["2022"]:.2f}%', 'Status': 'Reference'})

    abs_status = 'COMPLIANT' if abs_var_20d_pct < absolute_var_limit_pct else 'BREACH'
    rel_status = 'COMPLIANT' if rel_var_ratio < relative_var_limit else 'BREACH'
    rows.append({'Metric': 'COMPLIANCE', 'Value': '', 'Status': ''})
    rows.append({'Metric': 'Absolute VaR Limit', 'Value': abs_status, 'Status': '—'})
    rows.append({'Metric': 'Relative VaR Limit', 'Value': rel_status, 'Status': '—'})
    rows.append({'Metric': 'Backtest Zone', 'Value': zone, 'Status': '—'})
    rows.append({'Metric': 'UCITS Eligible', 'Value': 'YES', 'Status': '—'})

    df = pd.DataFrame(rows)

    # Display
    if col_widths is None:
        col_widths = {'Metric': '200px', 'Value': '150px', 'Status': '150px'}

    col_align_override = {'Metric': 'left', 'Value': 'right', 'Status': 'left'}
    section_headers = [i for i, row in enumerate(df.itertuples()) if row.Value == '']

    display_dark_table(
        df,
        caption='UCITS Balanced Fund | Monthly Risk Report',
        col_widths=col_widths,
        col_align_override=col_align_override,
        highlight_rows=section_headers,
        date_str=valuation_date,
    )
