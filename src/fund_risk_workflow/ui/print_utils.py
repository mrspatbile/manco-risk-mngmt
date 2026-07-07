import pandas as pd
from IPython.display import display, HTML
from fund_risk_workflow.risk.risk_utils import stress_historical, redemption_stress

def print_asset_class_weights_n_positions(breakdown, NAV):
    print(f"{'Asset Class':<20} {'MV (EUR)':>15} {'Weight':>8} {'# Pos':>6}")
    print('-' * 52)
    for ac, row in breakdown.iterrows():
        print(f"{ac:<20} {row['market_value_eur']:>15,.0f} {row['weight_pct']:>7.1f}% {row['n_positions']:>6}")
    print('-' * 52)
    print(f"{'NAV':<20} {NAV:>15,.0f} {'100.0%':>8}")

def print_fund_summary(FUND_ID, VALUATION_DATE, positions, risk_df, NAV):
    print(f"Fund           : {FUND_ID}")
    print(f"Valuation date : {VALUATION_DATE}")
    print(f"Positions      : {len(positions)}") # this is for a single day = VALUATION_DATE
    print(f"NAV (EUR)      : {NAV:,.0f}")
    print(f"Asset classes  : {sorted(positions['asset_class'].unique())}")
    mask_long = risk_df['market_value_eur'] >= 0
    print(f"Long exposure  : {risk_df[mask_long]['market_value_eur'].sum():,.0f}")
    print(f"Short exposure : {risk_df[~mask_long]['market_value_eur'].sum():,.0f}")

def print_var_es(var_1d, var_20d, es_1d, es_20d, NAV):
    print(f"{'Metric':<25} {'1d':>10} {'20d':>10}")
    print(f"{'':25} {'(% NAV)':>10} {'(% NAV)':>10}")
    print('-' * 46)
    print(f"{'VaR Historical':<25} {var_1d*100:>9.2f}% {var_20d*100:>9.2f}%")
    print(f"{'ES Historical':<25} {es_1d*100:>9.2f}% {es_20d*100:>9.2f}%")
    print('-' * 46)
    print(f"{'VaR Hist (EUR)':<25} {var_1d*NAV:>10,.0f} {var_20d*NAV:>10,.0f}")



def print_esma_report(n, breach_rate, zone):
    print(f"ESMA regulatory window — last 250 trading days")
    print(f"Breaches    : {n}")
    print(f"Breach rate : {breach_rate*100:.2f}% (expected 1.0%)")
    print(f"ESMA zone   : {zone}")
    print()

def print_lvar(lvar_result, NAV):
    print(f"VaR (1d 99%)        : {lvar_result['var']*100:.2f}%   EUR {lvar_result['var']*NAV:,.0f}")
    print(f"Liquidity cost      : {lvar_result['liquidity_cost']*100:.2f}%   EUR {lvar_result['liquidity_cost']*NAV:,.0f}")
    print(f"LVaR (1d 99%)       : {lvar_result['lvar']*100:.2f}%   EUR {lvar_result['lvar']*NAV:,.0f}")
    print(f"LVaR increase       : +{lvar_result['lvar_pct_increase']:.1f}%")
    print()
    print('-' * 47)

    print(lvar_result['by_asset_class'].to_string())

def print_leverage(risk_df, deriv_notional_commitment, commitment_exposure,
                   gross_limit=3.0, borrowings_eur=0.0):
    # gross_limit set in the RMP, so set GROSS_LIMIT = <VALUE> and pass the arg (here defaults to 3.0)
    # borrowings_eur: PB debit balances / revolving facilities (EU231/2013 Recital 13)

    NAV = risk_df['market_value_eur'].sum()
    gross_leverage      = (risk_df['gross_exposure'].sum() + borrowings_eur) / NAV
    commitment_leverage = commitment_exposure / NAV

    all_classes = sorted(
        c for c in risk_df['asset_class'].unique() if c not in ('Borrowing',)
    )

    leverage_summary = pd.DataFrame({
        'Gross (EUR)'        : [risk_df[risk_df['asset_class']==ac]['gross_exposure'].sum()
                                for ac in all_classes],
        'Gross (x NAV)'      : [risk_df[risk_df['asset_class']==ac]['gross_exposure'].sum()/NAV
                                for ac in all_classes],
        'Commitment (EUR)'   : [
            risk_df[(risk_df['asset_class']==ac) & (risk_df['is_hedge']==0)]['market_value_eur'].abs().sum()
            if ac == 'FX'
            else (0 if ac == 'Cash'
            else (deriv_notional_commitment if ac == 'Derivative'
            else risk_df[risk_df['asset_class']==ac]['market_value_eur'].abs().sum()))
            for ac in all_classes],

        'Commitment (x NAV)' : [
            risk_df[(risk_df['asset_class']==ac) & (risk_df['is_hedge']==0)]['market_value_eur'].abs().sum() / NAV
            if ac == 'FX'
            else (0 if ac == 'Cash'
            else (deriv_notional_commitment / NAV if ac == 'Derivative'
            else risk_df[risk_df['asset_class']==ac]['market_value_eur'].abs().sum() / NAV))
            for ac in all_classes],

    }, index=all_classes)

    leverage_summary['Gross (EUR)']        = leverage_summary['Gross (EUR)'].map('{:,.0f}'.format)
    leverage_summary['Gross (x NAV)']      = leverage_summary['Gross (x NAV)'].map('{:.2f}x'.format)
    leverage_summary['Commitment (EUR)']   = leverage_summary['Commitment (EUR)'].map('{:,.0f}'.format)
    leverage_summary['Commitment (x NAV)'] = leverage_summary['Commitment (x NAV)'].map('{:.2f}x'.format)

    print(f"{'Asset Class':<15} {'Gross (EUR)':>15} {'Gross':>8} {'Commit (EUR)':>15} {'Commit':>8}")
    print('-' * 65)
    for ac in all_classes:
        row = leverage_summary.loc[ac]
        print(f"{ac:<15} {row['Gross (EUR)']:>15} {row['Gross (x NAV)']:>8} "
            f"{row['Commitment (EUR)']:>15} {row['Commitment (x NAV)']:>8}")
    if borrowings_eur > 0:
        print(f"{'Borrowing':<15} {borrowings_eur:>15,.0f} {borrowings_eur/NAV:>7.2f}x "
              f"{borrowings_eur:>15,.0f} {borrowings_eur/NAV:>7.2f}x")
    print('-' * 65)
    print(f"{'Total':<15} {risk_df['gross_exposure'].sum() + borrowings_eur:>15,.0f} {gross_leverage:>7.2f}x "
        f"{commitment_exposure:>15,.0f} {commitment_leverage:>7.2f}x")

    status      = 'OK' if gross_leverage <= gross_limit else 'BREACH'
    print(f"\nGross leverage limit : {gross_limit:.0f}x")
    print(f"Current gross        : {gross_leverage:.2f}x")
    print(f"Status               : {status}")

def print_granular(granular, NAV):
    # listed vs OTC summary 
    total_gross = granular['gross_eur'].sum()
    summary_lot = granular.groupby('listed_otc')['gross_eur'].sum().reset_index()
    summary_lot['x_nav']        = summary_lot['gross_eur'] / NAV
    summary_lot['pct_leverage'] = summary_lot['gross_eur'] / total_gross * 100
    summary_lot['gross_eur']    = summary_lot['gross_eur'].map('{:,.0f}'.format)
    summary_lot['x_nav']        = summary_lot['x_nav'].map('{:.2f}x'.format)
    summary_lot['pct_leverage'] = summary_lot['pct_leverage'].map('{:.1f}%'.format)
    summary_lot.index.name      = None
    summary_lot.columns         = ['Category', 'Gross (EUR)', 'x NAV', '% Leverage']
    summary_lot.set_index('Category', inplace=True)

    header = f"{'':12} {'Gross (EUR)':>15} {'x NAV':>8} {'% Leverage':>12}"
    print(header)
    print('-' * len(header))
    for idx, row in summary_lot.iterrows():
        print(f"{idx:<12} {row['Gross (EUR)']:>15} {row['x NAV']:>8} {row['% Leverage']:>12}")
    print('-' * len(header))
    # add this
    print(f"{'Total':<12} {total_gross:>15,.0f} {total_gross/NAV:>7.2f}x {'100.0%':>12}")
    print()

    summary_src = granular.groupby('source')['gross_eur'].sum().reset_index()
    summary_src['x_nav']        = summary_src['gross_eur'] / NAV
    summary_src['pct_leverage'] = summary_src['gross_eur'] / total_gross * 100
    summary_src['gross_eur']    = summary_src['gross_eur'].map('{:,.0f}'.format)
    summary_src['x_nav']        = summary_src['x_nav'].map('{:.2f}x'.format)
    summary_src['pct_leverage'] = summary_src['pct_leverage'].map('{:.1f}%'.format)
    summary_src.set_index('source', inplace=True)
    summary_src.index.name      = None

    header = f"{'':20} {'Gross (EUR)':>15} {'x NAV':>8} {'% Leverage':>12}"
    print(header)
    print('-' * len(header))
    for idx, row in summary_src.iterrows():
        print(f"{idx:<20} {row['gross_eur']:>15} {row['x_nav']:>8} {row['pct_leverage']:>12}")
    print('-' * len(header))
    print(f"{'Total':<20} {total_gross:>15,.0f} {total_gross/NAV:>7.2f}x {'100.0%':>12}")
    print()

    # granular table
    granular['pct_leverage'] = (granular['gross_eur'] / total_gross * 100).map('{:.1f}%'.format)
    granular['gross_eur']    = granular['gross_eur'].map('{:,.0f}'.format)
    granular['gross_x_nav']  = granular['gross_x_nav'].map('{:.2f}x'.format)
    granular.set_index(['source', 'asset_class', 'sub_asset_class'], inplace=True)


def display_scenarios_2(risk_df, custom=None, add_historical=False):
    """
    hypothetical : dict of {label: result_dict} for ad-hoc scenarios
    historical   : bool — if True, runs and includes all HISTORICAL_SCENARIOS
    """
    NAV = risk_df['market_value_eur'].sum()

    rows = []

    from fund_risk_workflow.risk.risk_utils import HISTORICAL_SCENARIOS

    if custom:
        for label, result in custom.items():
            rows.append({
                'Scenario' : label,
                'P&L (EUR)': result['stressed_pnl_eur'],
                '% NAV'    : result['stressed_pnl_eur'] / NAV * 100,
            })

    if add_historical:
        for key, params in HISTORICAL_SCENARIOS.items():
            result = stress_historical(risk_df, key)
            rows.append({
                'Scenario' : params['name'],
                'P&L (EUR)': result['stressed_pnl_eur'],
                '% NAV'    : result['stressed_pnl_eur'] / NAV * 100,
            })

    summary_raw = pd.DataFrame(rows).set_index('Scenario')
    worst_idx   = summary_raw['% NAV'].idxmin()

    summary_raw['P&L (EUR)'] = summary_raw['P&L (EUR)'].map('{:,.0f}'.format)
    summary_raw['% NAV']     = summary_raw['% NAV'].map('{:.2f}%'.format)

    display(summary_raw.style.apply(lambda x: [
        'background-color: #7f1d1d; color: white' if i == worst_idx else ''
        for i in x.index], axis=0))
    
def print_buckets(bucket_full, risk_df_liq, NAV):
    print(f"{'Bucket':<15} {'Abs Exposure (EUR)':>20} {'% NAV':>8} {'# Pos':>6}")
    print('-' * 55)
    for _, row in bucket_full.iterrows():
        if row['abs_exposure'] > 0:
            print(f"{row['liquidity_bucket']:<15} {row['abs_exposure']:>20,.0f} "
                f"{row['pct_nav_abs']:>7.1f}% {row['n_positions']:>6.0f}")
        else:
            print(f"{row['liquidity_bucket']:<15} {'—':>20} {'—':>8} {'—':>6}")
    print('-' * 55)
    total_abs = risk_df_liq['market_value_eur'].abs().sum()
    print(f"{'Total':<15} {total_abs:>20,.0f} {total_abs/NAV*100:>7.1f}%")

def print_inv_concentration(NAV, risk_df_liq, _investors, _conc, _top, _type):
    print(f'Investor Concentration — AIFM Hedge Fund  |  NAV: EUR {NAV:,.0f}')
    print('ESMA threshold: 20% single / 50% top-3\n')
    print(f"{'':4} {'Investor':<30} {'Type':<18} {'AUM (EUR)':>14} {'% NAV':>8}")
    print('\u2500' * 80)
    for _rank, (_, _row) in enumerate(_top.iterrows(), 1):
        _t = _type.get(_row['investor_id'], '')
        print(f"{_rank:<4} {_row['investor_name']:<30} {_t:<18} {_row['aum_eur']:>14,.0f} {_row['pct_nav']*100:>7.1f}%")
    print('\u2500' * 80)

    _flag_s = '\u26a0 ESMA flag'       if _conc['concentration_flag'] else '\u2713 OK'
    _flag_3 = '\u26a0 High conc.'      if _conc['high_concentration'] else '\u2713 OK'
    print(f"\nLargest investor : {_conc['largest_investor_pct']*100:.1f}% NAV  {_flag_s}")
    print(f"Top 3 investors  : {_conc['top3_pct']*100:.1f}% NAV  {_flag_3}")

    # Largest-investor redemption stress (4th scenario)
    _r4   = redemption_stress(risk_df_liq, NAV, redemption_pct=_conc['largest_investor_pct'], notice_days=5)
    _gap4 = f"+{_r4['liquidity_gap_eur']/1e6:.1f}M" if _r4['liquidity_gap_eur'] >= 0 else f"{_r4['liquidity_gap_eur']/1e6:.1f}M"
    print(f"\nLargest-investor stress ({_conc['largest_investor_pct']*100:.1f}% NAV, 5-day notice):")
    print(f"  Redemption : EUR {_r4['redemption_amount_eur']:,.0f}")
    print(f"  Liquid     : EUR {_r4['liquid_assets_eur']:,.0f}")
    print(f"  Gap        : {_gap4}  |  Coverage: {_r4['coverage_ratio']:.2f}x")
    print(f"  Action     : {_r4['recommendation']}")

    print('\nMonitoring recommendation:')
    if _conc['high_concentration']:
        print('  \u2014 Enhanced monitoring: top-3 investors represent significant co-ordinated exit risk')
        print('  \u2014 Maintain liquidity buffer >= largest investor AUM')
    if _conc['concentration_flag']:
        print(f'  \u2014 Gate-trigger review: largest investor at {_conc["largest_investor_pct"]*100:.1f}% NAV')
    if not _conc['concentration_flag'] and not _conc['high_concentration']:
        print('  \u2014 No immediate action. Continue quarterly investor concentration monitoring.')


def print_redemption_stress(fund_id, notice, redstress, NAV):
    print(f'Fund: {fund_id}  |  NAV: EUR {NAV:,.0f}  |  Notice: {notice} days')
    print()
    print(f"{'':22} {'Redemption (M)':>14} {'Liquid (M)':>12} {'Gap (M)':>12} {'Coverage':>10} Action")
    print('\u2500' * 95)
    for k, v in redstress.items():
        print(f"{v['label']:<22} {v['redemption_amount_eur']/1e6:>13.1f}M {v['liquid_assets_eur']/1e6:>11.1f}M "
              f"{v['gap']:>12} {v['coverage_ratio']:>9.2f}x  {v['recommendation']}")
    print('\u2500' * 95)


def print_counterparty_stress(NAV,_cp_hf,_worst_cp,_cp_loss_eur, _cp_loss_pct):
    print(f"Counterparty Stress — AIFM Hedge Fund  |  NAV: EUR {NAV:,.0f}")
    print(f"Simulated prime brokerage and OTC derivatives counterparty register\n")
    print(f"{'Counterparty':<18} {'Type':<16} {'Exposure':>12} {'Collateral':>12} {'Net Exp.':>12} {'% NAV':>8}")
    print('─' * 82)
    for _, r in _cp_hf.iterrows():
        print(f"{r['counterparty']:<18} {r['type']:<16} {r['exposure_eur']:>11,.0f} "
            f"{r['collateral_eur']:>11,.0f} {r['net_exposure_eur']:>11,.0f} {r['loss_pct_nav']*100:>7.1f}%")
    print('─' * 82)
    print(f"\nWorst-case: {_worst_cp['counterparty']} defaults")
    print(f"  Net loss (post-collateral): EUR {_cp_loss_eur:,.0f}  ({_cp_loss_pct*100:.1f}% of NAV)")
    print(f"  AIFMD limit: no single counterparty net exposure > 5% NAV (UCITS/AIFM guideline)")
    _flag_cp = "⚠ BREACH" if _cp_loss_pct > 0.05 else "✓ Within limit"
    print(f"  Status: {_flag_cp}")

def print_combined_stress_mkt_plus_liq(NAV, _comb_mkt_eur, _comb_nav_st, 
                                       _comb_redeem_eur, _comb_liquid_st, _comb_gap_st, _comb_action, _comb_cov_st):
    print(f"Combined Stress — AIFM Hedge Fund  |  Equity −20% + 25% Redemption")
    print(f"Baseline NAV: EUR {NAV/1e6:,.1f}M\n")
    print(f"  Market shock (equity −20%):")
    print(f"    Portfolio P&L  : EUR {_comb_mkt_eur/1e6:,.1f}M  ({_comb_mkt_eur/NAV*100:.1f}% NAV)")
    print(f"    Stressed NAV   : EUR {_comb_nav_st/1e6:,.1f}M")
    print()
    print(f"  Liquidity impact (25% redemption, liquid assets stressed −20%):")
    print(f"    Redemption     : EUR {_comb_redeem_eur/1e6:,.1f}M  (25% pre-stress NAV)")
    print(f"    Liquid assets  : EUR {_comb_liquid_st/1e6:,.1f}M  (post equity shock)")
    print(f"    Liquidity gap  : EUR {_comb_gap_st/1e6:,.1f}M  |  Coverage: {_comb_cov_st:.2f}x")
    print(f"    Action         : {_comb_action}")
    print()
    _total_stress = _comb_mkt_eur - max(0.0, -_comb_gap_st)
    _total_pct    = _total_stress / NAV * 100
    print(f"  Total combined impact on NAV: EUR {_total_stress/1e6:,.1f}M  ({_total_pct:.1f}% of NAV)")
    print(f"  Regulatory note: ESMA/2020/1498 §48 — combined stress is a mandatory Annex VI scenario")

def print_attribution(attr, flagged):
    print(f"{'Attribution period':<35} {attr.index.min().date()} to {attr.index.max().date()}")
    print(f"{'Days attributed':<35} {len(attr)}")
    print(f"{'Correlation (actual vs expl.)':<35} {attr['pnl_actual'].corr(attr['pnl_explained']):.3f}")
    print(f"{'Median % explained':<35} {attr['pct_explained'].median():.1%}")
    print(f"{'Days >= 80% explained':<35} {(attr['pct_explained'] >= 0.80).sum()} ({(attr['pct_explained'] >= 0.80).mean():.1%})")
    print(f"{'Residual vol (EUR)':<35} {attr['pnl_residual'].std():,.0f}")
    print(f"{'Residual / total vol':<35} {attr['pnl_residual'].std() / attr['pnl_actual'].std():.1%}")
    print(f"{'Flagged days':<35} {len(flagged)} ({len(flagged)/len(attr):.1%})")
    print()
    print("Note: residual = idiosyncratic return not explained by market beta.")


def print_esg_summary(summary):

    print(f"ESG PORTFOLIO SUMMARY")
    print('-' * 45)
    print(f"{'Weighted avg ESG score':<30} {summary['wav_esg']:.1f}/100")
    print(f"{'Weighted avg ENV score':<30} {summary['wav_env']:.1f}/100")
    print(f"{'Weighted avg SOC score':<30} {summary['wav_soc']:.1f}/100")
    print(f"{'Weighted avg GOV score':<30} {summary['wav_gov']:.1f}/100")
    print(f"{'Weighted avg carbon intensity':<30} {summary['wav_carbon']:.1f} tCO2/EURm")
    print(f"{'% exposure below ESG threshold':<30} {summary['pct_low_esg']:.1f}%")
    print(f"{'% exposure with controversy':<30} {summary['pct_controversy']:.1f}%")
    print()
    if len(summary['controversies']) > 0:
        print("Controversy flags:")
        for _, row in summary['controversies'].iterrows():
            print(f"  {row['instrument_name']:<35} ESG: {row['esg_score']:.0f}")

