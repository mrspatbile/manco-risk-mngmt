"""
Real estate risk aggregation utilities.

Pure calculations and DataFrame construction for the closed-ended mixed
AIFM_RealEstate monitoring workflow: sleeve classification, direct
property profiling, property/rental/rate/LTV stress aggregation, lease
register linkage, tenant concentration, and tenant default stress.

No database access, file export, or display logic belongs here.
Monetary outputs are EUR; percentage outputs are in percent (0-100)
unless stated otherwise.
"""

import pandas as pd

from fund_risk_workflow.computation.stress import (
    HISTORICAL_SCENARIOS,
    stress_historical,
    stress_ltv,
    stress_property,
    stress_rates,
    stress_rental,
)

SLEEVES = ['Direct Property', 'Listed REIT', 'FX Hedge', 'Cash']


def _validate(risk_df: pd.DataFrame, nav: float) -> None:
    if risk_df is None or risk_df.empty:
        raise ValueError('risk_df is empty — no positions to aggregate')
    if nav is None or nav <= 0:
        raise ValueError(f'NAV must be positive, got {nav}')


def classify_sleeve(row: pd.Series) -> str:
    """Classify one position into the fund's four sleeves.

    Uses only existing fields: is_direct_property, asset_class, and
    sub_asset_class.
    """
    if bool(row.get('is_direct_property')):
        return 'Direct Property'
    if row['asset_class'] == 'Real Estate':
        return 'Listed REIT'
    if row['asset_class'] == 'FX':
        return 'FX Hedge'
    if row['asset_class'] == 'Cash':
        return 'Cash'
    return 'Other'


def sleeve_summary(risk_df: pd.DataFrame, nav: float) -> pd.DataFrame:
    """Aggregate market value and position count by sleeve.

    Sleeves: Direct Property, Listed REIT, FX Hedge, Cash.
    """
    _validate(risk_df, nav)
    df = risk_df.copy()
    df['sleeve'] = df.apply(classify_sleeve, axis=1)
    out = (
        df.groupby('sleeve')
        .agg(market_value_eur=('market_value_eur', 'sum'),
             n_positions=('isin', 'count'))
        .reindex([s for s in SLEEVES + ['Other']])
        .dropna(how='all')
        .reset_index()
    )
    out['pct_nav'] = out['market_value_eur'] / nav * 100
    return out


def direct_property_profile(risk_df: pd.DataFrame, nav: float) -> dict:
    """Per-property monitoring metrics plus value-weighted averages.

    Effective yield = rental yield x (1 - vacancy rate), i.e. the income
    yield after vacancy. All yield/LTV/vacancy figures are in percent.

    Returns dict with keys: properties (DataFrame), weighted_avg (dict).
    """
    _validate(risk_df, nav)
    direct = risk_df[risk_df['is_direct_property'] == True].copy()  # noqa: E712
    if direct.empty:
        raise ValueError('No direct property positions found')

    direct['effective_yield_pct'] = (
        direct['rental_yield_pct'] * (1 - direct['vacancy_rate_pct'] / 100))
    direct['pct_nav'] = direct['market_value_eur'] / nav * 100

    properties = direct[[
        'isin', 'instrument_name', 'property_type', 'country',
        'market_value_eur', 'pct_nav', 'ltv_pct', 'rental_yield_pct',
        'vacancy_rate_pct', 'effective_yield_pct',
    ]].sort_values('market_value_eur', ascending=False).reset_index(drop=True)

    mv = direct['market_value_eur']
    weighted_avg = {
        'market_value_eur': float(mv.sum()),
        'ltv_pct': float((direct['ltv_pct'] * mv).sum() / mv.sum()),
        'rental_yield_pct': float(
            (direct['rental_yield_pct'] * mv).sum() / mv.sum()),
        'vacancy_rate_pct': float(
            (direct['vacancy_rate_pct'] * mv).sum() / mv.sum()),
        'effective_yield_pct': float(
            (direct['effective_yield_pct'] * mv).sum() / mv.sum()),
    }
    return {'properties': properties, 'weighted_avg': weighted_avg}


def property_stress_assumptions(rmp: dict) -> pd.DataFrame:
    """Tabulate the documented stress assumptions from the risk policy.

    Values stay numeric (decimals); display formatting is UI-layer work.
    """
    scen = rmp.get('stress_scenarios') or {}
    required = ('property_value_shock_by_type', 'rental_stress_delta_vacancy',
                'rental_stress_delta_yield', 'rate_shock_delta_y',
                'ltv_stress_property_value_shock',
                'tenant_default_capitalisation_yield')
    missing = [k for k in required if scen.get(k) is None]
    if missing:
        raise ValueError(
            f'risk_policy stress_scenarios missing parameters: {missing}')

    rows = [
        {'scenario': 'Property value stress',
         'parameter': f'{ptype} value shock', 'value': shock}
        for ptype, shock in scen['property_value_shock_by_type'].items()
    ]
    rows += [
        {'scenario': 'Rental stress', 'parameter': 'Vacancy rate increase',
         'value': scen['rental_stress_delta_vacancy']},
        {'scenario': 'Rental stress', 'parameter': 'Rental yield compression',
         'value': scen['rental_stress_delta_yield']},
        {'scenario': 'Rate shock', 'parameter': 'Parallel shift',
         'value': scen['rate_shock_delta_y']},
        {'scenario': 'LTV covenant stress', 'parameter': 'Property value shock',
         'value': scen['ltv_stress_property_value_shock']},
        {'scenario': 'Tenant default', 'parameter': 'Capitalisation yield',
         'value': scen['tenant_default_capitalisation_yield']},
    ]
    out = pd.DataFrame(rows)
    out['source'] = 'Risk policy (migrated notebook assumption)'
    return out


def property_stress_results(risk_df: pd.DataFrame, nav: float,
                            rmp: dict) -> pd.DataFrame:
    """Run property, rental, rate, and historical stresses.

    Property and rental shocks apply to direct properties only. The rate
    shock and historical market scenarios apply only to the listed sleeve
    (listed REITs, FX, cash): direct properties are appraisal-valued and
    must not be shocked as daily-traded securities. All P&L is expressed
    against full fund NAV.
    """
    _validate(risk_df, nav)
    scen = rmp['stress_scenarios']
    listed = risk_df[risk_df['is_direct_property'] != True].copy()  # noqa: E712

    prop = stress_property(
        risk_df, delta_value_by_type=scen['property_value_shock_by_type'])
    rent = stress_rental(
        risk_df,
        delta_vacancy=scen['rental_stress_delta_vacancy'],
        delta_yield=scen['rental_stress_delta_yield'])
    rate = stress_rates(listed, delta_y=scen['rate_shock_delta_y'])

    vac_pp = scen['rental_stress_delta_vacancy'] * 100
    yld_bps = scen['rental_stress_delta_yield'] * 10000
    rows = [
        {'scenario': 'Property value stress (direct properties)',
         'stressed_pnl_eur': prop['stressed_pnl_eur']},
        {'scenario': f'Rental stress: vacancy +{vac_pp:.0f}pp, '
                     f'yield {yld_bps:+.0f}bps (direct properties)',
         'stressed_pnl_eur': rent['stressed_pnl_eur']},
        {'scenario': f'Rate shock {scen["rate_shock_delta_y"] * 10000:+.0f}bps'
                     ' (listed sleeve)',
         'stressed_pnl_eur': rate['stressed_pnl_eur']},
    ]
    for key in HISTORICAL_SCENARIOS:
        hist = stress_historical(listed, key)
        rows.append({'scenario': hist['scenario'] + ' (listed sleeve)',
                     'stressed_pnl_eur': hist['stressed_pnl_eur']})
    out = pd.DataFrame(rows)
    out['pct_nav'] = out['stressed_pnl_eur'] / nav * 100
    return out


def ltv_stress_summary(risk_df: pd.DataFrame, rmp: dict) -> dict:
    """LTV covenant stress on the direct property portfolio.

    Applies the documented severe property value shock and tests each
    property's stressed LTV against the policy stress threshold.

    Returns dict with keys: by_position (DataFrame, stressed LTV in
    decimal), n_breaches, breaching_properties, shock, threshold.
    """
    if risk_df is None or risk_df.empty:
        raise ValueError('risk_df is empty')
    scen = rmp['stress_scenarios']
    threshold = rmp['ltv_monitoring']['ltv_stress_threshold']
    shock = scen['ltv_stress_property_value_shock']
    res = stress_ltv(risk_df, delta_property_value=shock,
                     ltv_threshold=threshold)
    return {
        'by_position': res['by_position'],
        'n_breaches': res['n_breaches'],
        'breaching_properties': res['breaching_properties'],
        'shock': shock,
        'threshold': threshold,
    }


def reconcile_lease_rents(tenant_register: pd.DataFrame,
                          risk_df: pd.DataFrame,
                          tolerance_pct: float = 1.0) -> pd.DataFrame:
    """Reconcile lease-register rent against property valuation inputs.

    Expected rent per property = value x rental yield x (1 - vacancy).
    Raises ValueError if any property deviates beyond tolerance_pct or a
    lease references an unknown property ISIN.
    """
    if tenant_register is None or tenant_register.empty:
        raise ValueError('tenant_register is empty')
    direct = risk_df[risk_df['is_direct_property'] == True].copy()  # noqa: E712

    lease_rent = (tenant_register.groupby('property_isin')['annual_rent_eur']
                  .sum())
    unknown = set(lease_rent.index) - set(direct['isin'])
    if unknown:
        raise ValueError(
            f'Lease register references unknown property ISINs: {sorted(unknown)}')

    rows = []
    for _, prop in direct.iterrows():
        expected = (prop['market_value_eur'] * prop['rental_yield_pct'] / 100
                    * (1 - prop['vacancy_rate_pct'] / 100))
        actual = float(lease_rent.get(prop['isin'], 0.0))
        deviation_pct = (actual / expected - 1) * 100 if expected else float('nan')
        rows.append({
            'property_isin': prop['isin'],
            'property_name': prop['instrument_name'],
            'lease_rent_eur': actual,
            'expected_rent_eur': expected,
            'deviation_pct': deviation_pct,
        })
    out = pd.DataFrame(rows)
    breaches = out[out['deviation_pct'].abs() > tolerance_pct]
    if not breaches.empty:
        raise ValueError(
            'Lease rent does not reconcile with property inputs for: '
            f'{breaches["property_name"].tolist()}')
    return out


def tenant_concentration(tenant_register: pd.DataFrame, nav: float) -> dict:
    """Tenant and property rental concentration from the lease register.

    Returns dict with keys: by_tenant, by_property, by_sector
    (DataFrames with annual rent EUR and % of total rent), total_rent_eur.
    """
    if tenant_register is None or tenant_register.empty:
        raise ValueError('tenant_register is empty')
    if nav is None or nav <= 0:
        raise ValueError(f'NAV must be positive, got {nav}')
    total_rent = float(tenant_register['annual_rent_eur'].sum())

    def _group(col: str) -> pd.DataFrame:
        out = (
            tenant_register.groupby(col)
            .agg(annual_rent_eur=('annual_rent_eur', 'sum'),
                 n_leases=('lease_id', 'count'))
            .reset_index()
            .sort_values('annual_rent_eur', ascending=False)
            .reset_index(drop=True)
        )
        out['pct_total_rent'] = out['annual_rent_eur'] / total_rent * 100
        return out

    return {
        'by_tenant': _group('tenant_name'),
        'by_property': _group('property_name'),
        'by_sector': _group('tenant_sector'),
        'total_rent_eur': total_rent,
    }


def tenant_default_stress(tenant_register: pd.DataFrame, nav: float,
                          capitalisation_yield: float) -> dict:
    """One-year default stress for the largest actual tenant exposure.

    Assumes a full one-year void with no recovery: income loss equals the
    tenant's annual contracted rent. The implied NAV impact capitalises
    the lost income at the documented capitalisation yield. Both the
    register and the assumptions are simulated.
    """
    if tenant_register is None or tenant_register.empty:
        raise ValueError('tenant_register is empty')
    if not 0 < capitalisation_yield < 1:
        raise ValueError(
            f'capitalisation_yield must be in (0, 1), got {capitalisation_yield}')
    if nav is None or nav <= 0:
        raise ValueError(f'NAV must be positive, got {nav}')

    by_tenant = (
        tenant_register.groupby(['tenant_name', 'tenant_sector'])
        .agg(annual_rent_eur=('annual_rent_eur', 'sum'),
             properties=('property_name', lambda s: ', '.join(sorted(set(s)))))
        .reset_index()
        .sort_values('annual_rent_eur', ascending=False)
        .reset_index(drop=True)
    )
    by_tenant['income_loss_eur'] = by_tenant['annual_rent_eur']
    by_tenant['loss_pct_nav'] = by_tenant['income_loss_eur'] / nav * 100
    by_tenant['implied_nav_impact_eur'] = (
        by_tenant['income_loss_eur'] / capitalisation_yield)
    by_tenant['implied_nav_impact_pct'] = (
        by_tenant['implied_nav_impact_eur'] / nav * 100)

    worst_row = by_tenant.iloc[0]
    worst = {
        'tenant_name': worst_row['tenant_name'],
        'properties': worst_row['properties'],
        'income_loss_eur': float(worst_row['income_loss_eur']),
        'loss_pct_nav': float(worst_row['loss_pct_nav']),
        'implied_nav_impact_eur': float(worst_row['implied_nav_impact_eur']),
        'implied_nav_impact_pct': float(worst_row['implied_nav_impact_pct']),
    }
    return {
        'by_tenant': by_tenant,
        'worst': worst,
        'capitalisation_yield': capitalisation_yield,
        'as_of_date': tenant_register.attrs.get('as_of_date'),
    }
