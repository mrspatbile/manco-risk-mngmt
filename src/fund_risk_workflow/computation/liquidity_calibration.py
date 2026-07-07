"""Liquidity calibration and redemption scenario computation.

Handles:
- Redemption schedule generation from investor base assumptions
- Redemption scenario calibration (Base, Large, Stress)
- Largest investor scenario extraction
- LMT trigger analysis coordination
"""

import numpy as np
import pandas as pd
from scipy.stats import beta


def beta_params_from_mean_concentration(
    mean: float,
    concentration: float,
) -> tuple[float, float]:
    """Convert mean redemption rate and concentration into beta parameters.

    Uses the method-of-moments parametrisation for a beta distribution:
    - mean is the expected redemption rate
    - concentration controls the dispersion around the mean

    Higher concentration produces sharper distributions (less dispersed).
    Lower concentration produces flatter distributions (more dispersed).

    Parameters
    ----------
    mean : float
        Expected redemption rate (must be between 0 and 1, exclusive).
    concentration : float
        Concentration parameter (must be positive).
        Typical range: 1–10 for fund redemption calibrations.

    Returns
    -------
    tuple[float, float]
        (alpha, beta) for scipy.stats.beta.

    Raises
    ------
    ValueError
        If mean is not in (0, 1) or concentration <= 0.
    """
    if not 0 < mean < 1:
        raise ValueError("mean must be strictly between 0 and 1.")
    if concentration <= 0:
        raise ValueError("concentration must be positive.")

    alpha = mean * concentration
    beta_val = (1.0 - mean) * concentration
    return alpha, beta_val


def build_redemption_schedule(
    calibration_config: dict,
    n_months: int = 12,
) -> list:
    """Generate monthly redemption schedule from investor base parameters.

    For normal months: AUM-weighted beta distribution draw per investor type,
    where E[draw] = base_redemption_rate. The beta distribution keeps
    simulated redemption rates bounded between 0 and 1.

    For stress months: AUM-weighted stress rates (deterministic override).

    Parameters
    ----------
    calibration_config : dict
        Dict with keys:
        - 'investors': list of dicts with 'weight', 'base_redemption_rate', 'stress_redemption_rate'
        - 'stress_months': set or list of month numbers (1-indexed) to use stress rates
        - 'redemption_concentration': concentration parameter for beta distribution
        - 'seed': random seed for reproducibility

    n_months : int, default 12
        Number of periods to simulate.

    Returns
    -------
    list
        Monthly redemption rates as fractions of NAV (n_months floats).
    """
    rng = np.random.default_rng(calibration_config['seed'])
    concentration = calibration_config['redemption_concentration']
    stress_months = set(calibration_config['stress_months'])
    investors = calibration_config['investors']

    schedule = []
    for m in range(1, n_months + 1):
        rate = 0.0
        for inv in investors:
            w = inv['weight']
            if m in stress_months:
                rate += w * inv['stress_redemption_rate']
            else:
                # Beta distribution: bounded [0,1] with mean = base_redemption_rate
                base_rate = inv['base_redemption_rate']
                alpha, beta_val = beta_params_from_mean_concentration(base_rate, concentration)
                rate += w * float(rng.beta(alpha, beta_val))
        schedule.append(float(np.clip(rate, 0.0, 1.0)))

    return schedule


def compute_weighted_reference_rates(calibration_config: dict) -> tuple:
    """Compute expected aggregate redemption rates under normal and stress conditions.

    Parameters
    ----------
    calibration_config : dict
        Investor calibration config (same as for build_redemption_schedule).

    Returns
    -------
    tuple
        (weighted_normal_rate, weighted_stress_rate) as floats.
    """
    investors = calibration_config['investors']

    normal_rate = sum(inv['weight'] * inv['base_redemption_rate'] for inv in investors)
    stress_rate = sum(inv['weight'] * inv['stress_redemption_rate'] for inv in investors)

    return normal_rate, stress_rate


def compute_redemption_scenarios(
    investor_base: dict,
    calibration_config: dict,
) -> dict:
    """Compute redemption scenarios (Base, Large, Stress) and extract largest investor.

    Parameters
    ----------
    investor_base : dict
        Investor register dict with 'investors' list. Each investor has 'nav_pct'.

    calibration_config : dict
        Calibration config with investors (type, weight, rates) and stress_months.

    Returns
    -------
    dict
        Dict with keys:
        - 'redemption_scenarios': list of dicts with 'name' and 'redemption_pct'
        - 'largest_investor_pct': float, largest single investor as % of NAV
        - 'largest_investor_name': str
        - 'weighted_normal_rate': float
        - 'weighted_stress_rate': float
    """
    # Get weighted rates from calibration
    normal_rate, stress_rate = compute_weighted_reference_rates(calibration_config)

    # Find largest investor from investor base (exclude "Remaining" aggregates)
    investors_list = investor_base.get('investors', [])
    if investors_list:
        # Filter out aggregate "Remaining" entries
        actual_investors = [
            inv for inv in investors_list
            if not ('REM' in inv.get('investor_id', '') or
                    'remaining' in inv.get('investor_name', '').lower())
        ]
        if actual_investors:
            largest = max(actual_investors, key=lambda x: x.get('nav_pct', 0))
        else:
            # Fallback: if all are aggregates, use the largest
            largest = max(investors_list, key=lambda x: x.get('nav_pct', 0))
        largest_investor_pct = largest.get('nav_pct', 0)
        largest_investor_name = largest.get('investor_name', 'Unknown')
    else:
        largest_investor_pct = 0.0
        largest_investor_name = 'Unknown'

    # Calibrate scenarios
    # Base: use weighted normal rate
    # Large: heuristic — 1.5x normal (moderate escalation)
    # Stress: use weighted stress rate
    scenarios = [
        {'name': 'Base', 'redemption_pct': normal_rate},
        {'name': 'Large', 'redemption_pct': min(1.5 * normal_rate, 0.40)},  # cap at 40%
        {'name': 'Stress', 'redemption_pct': stress_rate},
        {'name': 'Largest investor', 'redemption_pct': largest_investor_pct},
    ]

    return {
        'redemption_scenarios': scenarios,
        'largest_investor_pct': largest_investor_pct,
        'largest_investor_name': largest_investor_name,
        'weighted_normal_rate': normal_rate,
        'weighted_stress_rate': stress_rate,
    }


def summarize_investor_base_by_type(investor_base: dict) -> pd.DataFrame:
    """Summarize investor base by investor type.

    Parameters
    ----------
    investor_base : dict
        Investor register with 'investors' list.
        Investors may have 'aggregate_count' field: if present and > 1, used instead of counting as 1.

    Returns
    -------
    pd.DataFrame
        Summary with columns: investor_type, count, aum_pct, aum_eur.
    """
    if not investor_base.get('investors'):
        return pd.DataFrame()

    df = pd.DataFrame(investor_base['investors'])
    nav_eur = investor_base.get('target_nav_eur', 1.0)

    # Use aggregate_count if present, otherwise count as 1
    df['investor_count'] = df['aggregate_count'].fillna(1) if 'aggregate_count' in df.columns else 1

    summary = (
        df.groupby('investor_type', as_index=False)
        .agg({
            'investor_count': 'sum',
            'nav_pct': 'sum',
        })
        .rename(columns={'investor_count': 'count', 'nav_pct': 'aum_pct'})
    )
    summary['aum_eur'] = summary['aum_pct'] * nav_eur
    summary = summary[['investor_type', 'count', 'aum_pct', 'aum_eur']]

    return summary


def format_scenario_for_display(scenario: dict) -> str:
    """Format a redemption scenario dict for display.

    Converts {'name': 'Base', 'redemption_pct': 0.10} to 'Base (10%)'.
    Special case: 'Largest investor' scenarios show actual % from investor register.

    Parameters
    ----------
    scenario : dict
        Dict with 'name' and 'redemption_pct' keys.

    Returns
    -------
    str
        Formatted scenario string.
    """
    name = scenario.get('name', '')
    pct = scenario.get('redemption_pct')

    if isinstance(pct, (int, float)):
        return f"{name} ({int(pct * 100)}%)"
    else:
        return name


def prepare_investor_assumptions_calibration(
    investors_enriched: list,
) -> pd.DataFrame:
    """Prepare investor assumptions with computed weights for display.

    Parameters
    ----------
    investors_enriched : list
        List of investor dicts with type, weight, base_redemption_rate, stress_redemption_rate.

    Returns
    -------
    pd.DataFrame
        Formatted dataframe with columns:
        - Calibration Type
        - Computed Weight %
        - Base Rate %
        - Stress Rate %
    """
    df_investors = pd.DataFrame(investors_enriched)

    display_df = df_investors[['type', 'weight', 'base_redemption_rate', 'stress_redemption_rate']].copy()
    display_df.columns = ['Calibration Type', 'Computed Weight', 'Base Rate', 'Stress Rate']

    # Format as percentages
    display_df['Computed Weight %'] = (display_df['Computed Weight'] * 100).round(1).astype(str) + '%'
    display_df['Base Rate %'] = (display_df['Base Rate'] * 100).round(1).astype(str) + '%'
    display_df['Stress Rate %'] = (display_df['Stress Rate'] * 100).round(1).astype(str) + '%'

    return display_df[['Calibration Type', 'Computed Weight %', 'Base Rate %', 'Stress Rate %']]
