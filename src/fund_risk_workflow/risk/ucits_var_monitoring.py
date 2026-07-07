"""
UCITS VaR Monitoring Summary — aggregates VaR, relative VaR, SRRI, and backtest results.
"""

import pandas as pd


def compute_var_monitoring_summary(
    var_result: dict,
    rel_var_result: dict,
    srri_result: dict,
    backtest_report: pd.DataFrame,
    absolute_var_limit_pct: float,
    relative_var_limit: float,
) -> pd.DataFrame:
    """
    Compute UCITS VaR monitoring summary table.

    Parameters
    ----------
    var_result : dict
        Result from compute_fixed_position_var_1day()
    rel_var_result : dict
        Result from compute_ucits_relative_var_point_in_time()
    srri_result : dict
        Result from compute_srri_from_fund()
    backtest_report : pd.DataFrame
        Backtest report from create_backtest_report()
    absolute_var_limit_pct : float
        Absolute VaR limit (e.g., 20.0 for 20%)
    relative_var_limit : float
        Relative VaR limit (e.g., 2.0 for 2.0x)

    Returns
    -------
    pd.DataFrame
        Monitoring summary with columns: Metric, Value, Limit, Util %, Status
    """
    # Extract absolute VaR (20-day scaled)
    abs_var_20d_pct = var_result['var_hist_scaled_pct']
    abs_util = (abs_var_20d_pct / absolute_var_limit_pct) * 100

    # Extract relative VaR
    rel_var_ratio = rel_var_result['relative_var_ratio']
    rel_util = rel_var_result['utilisation_pct']

    # Extract SRRI category
    srri_category = srri_result['sri_bucket']

    # Extract backtest 99% zone
    report_99 = backtest_report[backtest_report['confidence'] == 99].iloc[0]
    n_breaches_99 = int(report_99['n_breaches'])
    breaches_zone = (
        '🟢 Green' if n_breaches_99 <= 4 else
        '🟡 Amber' if n_breaches_99 <= 9 else
        '🔴 Red'
    )

    # Build monitoring summary
    summary_data = [
        {
            'Metric': 'Absolute VaR (20d 99%)',
            'Value': f'{abs_var_20d_pct:.2f}%',
            'Limit': f'{absolute_var_limit_pct:.1f}%',
            'Util %': f'{abs_util:.1f}%',
            'Status': '✓ OK' if abs_var_20d_pct < absolute_var_limit_pct else '✗ BREACH',
        },
        {
            'Metric': 'Relative VaR (ratio)',
            'Value': f'{rel_var_ratio:.2f}x',
            'Limit': f'{relative_var_limit:.1f}x',
            'Util %': f'{rel_util:.1f}%',
            'Status': '✓ OK' if rel_var_ratio < relative_var_limit else '✗ BREACH',
        },
        {
            'Metric': 'SRRI',
            'Value': str(srri_category),
            'Limit': '—',
            'Util %': '—',
            'Status': '—',
        },
        {
            'Metric': 'Backtest Zone (99%, 250d)',
            'Value': breaches_zone,
            'Limit': 'Green',
            'Util %': f'{n_breaches_99} breaches',
            'Status': '✓ OK' if n_breaches_99 <= 4 else 'Review',
        },
    ]

    return pd.DataFrame(summary_data)
