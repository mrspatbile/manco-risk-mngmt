"""
esg_utils.py
============
ESG risk indicator utilities for all fund notebooks.

Functions
---------
build_esg_df(risk_df, bbg, engine, fund_id, position_date)
    Builds position-level ESG DataFrame with look-through for derivatives.

build_private_esg_df(fund_id, quarter, asset_type, engine)
    Builds position-level ESG DataFrame for private asset funds (PE or infrastructure).

esg_portfolio_summary(esg_df, nav)
    Computes portfolio-level weighted ESG metrics and flags

ESG_THRESHOLD_LOW : int
    Internal RMP threshold below which ESG score is flagged. Default 30.
    Not prescribed by regulation; defined in the Risk Management Policy.
 
ESG_THRESHOLD_HIGH : int
"""

import json
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
from fund_risk_workflow.ui.nb_utils import save_fig
from fund_risk_workflow.ui.plot_style import sup_title, C, ACCENT, ACCENT2, ACCENT3, FONT
from fund_risk_workflow.ui.print_html_utils import display_dark_table
from fund_risk_workflow.ui.plot_style import C
from fund_risk_workflow.data.database import (
    query_positions,
    PEValuationReport, PEPortfolioCompany, PEFundInvestment,
    InfraValuationReport, InfraAsset, InfraFundInvestment,
)
from fund_risk_workflow.computation.derivatives import compute_derivative_exposures_portfolio
from fund_risk_workflow.data.reference_data import (
    load_derivative_contracts,
    load_esg_scores,
)
from sqlalchemy.orm import Session

# from PRM - policy risk management
ESG_THRESHOLD_LOW  = 40   
ESG_THRESHOLD_HIGH = 70   


ESG_FIELDS = ['ESG_SCORE', 'ENV_SCORE', 'SOC_SCORE', 'GOV_SCORE',
              'CONTROVERSY_FLAG', 'CARBON_INTENSITY']


def build_esg_df(
    risk_df: pd.DataFrame,
    bbg,
    engine,
    fund_id: str,
    position_date: str,
    use_reference_scores_for_unlisted: bool = False,
    ) -> pd.DataFrame:
    """
    Build position-level ESG DataFrame with look-through for derivatives.

    For liquid instruments: ESG data fetched from Bloomberg via bdp.
    For illiquid instruments: ESG data from fund admin embedded in positions.
    For equity derivatives: delta-adjusted notional used as ESG exposure weight.
    For FX derivatives: zero ESG exposure (not ESG-relevant).
    For futures: full notional used (delta = 1) if underlying is Equity.

    Parameters
    ----------
    risk_df : pd.DataFrame
        Enriched positions from get_risk_ready_df.
    bbg : MockBloomberg
        Bloomberg connection.
    engine : sa.Engine
        SQLAlchemy engine.
    fund_id : str
        Fund identifier.
    position_date : str
        Position snapshot date used to retrieve holdings from the positions table.
    use_reference_scores_for_unlisted : bool, default False
        When true, no-ticker instruments are enriched from the existing
        ``reference_data/instruments/esg_scores.json`` file using ISIN. The
        default is false to preserve the established hedge-fund and UCITS
        notebook behavior.

    Returns
    -------
    pd.DataFrame with columns:
        instrument_name, asset_class, market_value_eur, weight_pct,
        esg_score, env_score, soc_score, gov_score, controversy_flag,
        carbon_intensity, esg_exposure_eur
    """
    raw_positions = query_positions(engine, fund_id, position_date=position_date)
    ticker_map    = dict(zip(raw_positions['isin'],
                             raw_positions['bloomberg_ticker']))
    deriv_contracts = load_derivative_contracts()  # Load once, use in loop
    reference_scores = (
        load_esg_scores() if use_reference_scores_for_unlisted else {}
    )
    esg_rows = []

    for _, pos in risk_df.iterrows():
        row = {
            'isin'            : pos['isin'],
            'instrument_name' : pos['instrument_name'],
            'asset_class'     : pos['asset_class'],
            'sub_asset_class' : pos.get('sub_asset_class', ''),
            'market_value_eur': pos['market_value_eur'],
            'weight_pct'      : pos['weight_pct'],
        }
        ticker = ticker_map.get(pos['isin'])

        # fetch ESG from Bloomberg or use fund admin data
        if ticker and pd.notna(ticker):
            bbg_esg = bbg.bdp(ticker, ESG_FIELDS)
            for f in ESG_FIELDS:
                row[f.lower()] = bbg_esg.loc[ticker, f]
        else:
            reference_score = reference_scores.get(pos['isin'], {})
            for f in ESG_FIELDS:
                field = f.lower()
                row[field] = reference_score.get(field, pos.get(field))

        # ESG exposure: delta-adjusted for derivatives with ESG-relevant underlyings, full notional otherwise
        if pos['asset_class'] == 'Derivative':
            # Check underlying asset class: only Equity derivatives contribute to ESG
            isin = pos['isin']
            if isin in deriv_contracts:
                underlying_class = deriv_contracts[isin].get('underlying_asset_class', '')
                if underlying_class == 'Equity':
                    row['esg_exposure_eur'] = None  # Will be filled by helper (delta-adjusted)
                else:
                    # FX or other non-ESG-relevant underlying
                    row['esg_exposure_eur'] = 0.0
            else:
                # Unknown derivative: zero ESG exposure
                row['esg_exposure_eur'] = 0.0
        elif pos['asset_class'] == 'FX':
            row['esg_exposure_eur'] = 0.0
        elif pos['asset_class'] == 'Cash':
            row['esg_exposure_eur'] = 0.0
        else:
            row['esg_exposure_eur'] = abs(pos['market_value_eur'])

        esg_rows.append(row)

    # Compute derivative exposures using canonical helper
    derivatives = [r for r in esg_rows if r['esg_exposure_eur'] is None]
    if len(derivatives) > 0:
        try:
            # Filter risk_df to derivatives and add Bloomberg ticker from ISIN mapping
            deriv_risk_df = risk_df[risk_df['asset_class'] == 'Derivative'].copy()
            deriv_risk_df['bloomberg_ticker'] = deriv_risk_df['isin'].map(ticker_map)

            # Load contract reference data and call helper
            deriv_contracts = load_derivative_contracts()
            helper_result = compute_derivative_exposures_portfolio(
                deriv_risk_df, bbg, deriv_contracts, currency_bbg_map=None
            )

            # Map helper exposures back to esg_rows
            for _, exp_row in helper_result['by_position'].iterrows():
                isin = exp_row['isin']
                esg_row = next((r for r in esg_rows if r.get('isin') == isin), None)
                if esg_row and esg_row.get('esg_exposure_eur') is None:
                    # Only set exposure for derivatives marked for helper fill (Equity derivatives)
                    # Use absolute value of delta-adjusted notional for ESG weighting
                    esg_row['esg_exposure_eur'] = abs(exp_row['delta_adjusted_notional_eur'])

        except ValueError as e:
            raise ValueError(
                f"ESG exposure computation failed for derivatives. "
                f"Error: {str(e)}"
            ) from e

    # Fill any remaining None values (should not happen if helper succeeds)
    for r in esg_rows:
        if r.get('esg_exposure_eur') is None:
            r['esg_exposure_eur'] = 0.0

    return pd.DataFrame(esg_rows)

def build_private_esg_df(
    fund_id: str,
    quarter: str,
    asset_type: str,
    engine,
    ) -> pd.DataFrame:
    """
    Build position-level ESG DataFrame for private asset funds.

    Parallel to build_esg_df() for listed funds. Output columns are a superset
    of build_esg_df() output so esg_portfolio_summary() can consume both without
    changes. ESG scores come from reference_data/instruments/esg_scores.json, keyed by
    company_id (PE) or asset_id (infra), simulating fund-admin or independent
    appraiser data.

    The esg_reporter column identifies the data source so the notebook can flag
    manager estimates vs third-party assessors. A manager estimate is less
    reliable than an independent appraiser and should be noted in reporting.

    Parameters
    ----------
    fund_id : str
        Fund identifier, e.g. 'AIFM_PE_Buyout' or 'AIFM_Infra_Core'.
    quarter : str
        Quarter-end date string, e.g. '2026-03-31'. Must match a date in the
        valuation report table.
    asset_type : str
        'pe' or 'infra'.
    engine : sa.Engine
        SQLAlchemy engine.

    Returns
    -------
    pd.DataFrame with columns:
        instrument_name, asset_class, sub_asset_class, market_value_eur,
        weight_pct, esg_score, env_score, soc_score, gov_score,
        controversy_flag, carbon_intensity, esg_exposure_eur,
        esg_reporter, esg_report_date

    Raises
    ------
    ValueError
        If asset_type is not 'pe' or 'infra'.
    """
    if asset_type not in ('pe', 'infra'):
        raise ValueError(
            f"asset_type must be 'pe' or 'infra', got {asset_type!r}"
        )

    from fund_risk_workflow.data.reference_data import load_esg_scores
    _esg_ref = load_esg_scores()

    rows = []

    if asset_type == 'pe':
        with Session(engine) as session:
            reports = (
                session.query(PEValuationReport)
                .filter(
                    PEValuationReport.fund_id == fund_id,
                    PEValuationReport.valuation_date == quarter,
                )
                .all()
            )
            companies = {
                c.company_id: c
                for c in session.query(PEPortfolioCompany).all()
            }

        total_nav = sum(r.appraised_nav_eur or 0.0 for r in reports)

        for r in reports:
            co  = companies.get(r.company_id)
            esg = _esg_ref.get(r.company_id, {})
            nav = r.appraised_nav_eur or 0.0
            rows.append({
                'instrument_name' : co.company_name if co else r.company_id,
                'asset_class'     : 'Private Equity',
                'sub_asset_class' : co.investment_stage if co else None,
                'market_value_eur': nav,
                'weight_pct'      : nav / total_nav * 100 if total_nav else 0.0,
                'esg_score'       : esg.get('esg_score'),
                'env_score'       : esg.get('env_score'),
                'soc_score'       : esg.get('soc_score'),
                'gov_score'       : esg.get('gov_score'),
                'controversy_flag': esg.get('controversy_flag'),
                'carbon_intensity': esg.get('carbon_intensity'),
                'esg_exposure_eur': nav,
                'esg_reporter'    : r.appraiser or 'Management estimate',
                'esg_report_date' : r.valuation_date,
            })

    else:  # infra
        with Session(engine) as session:
            reports = (
                session.query(InfraValuationReport)
                .filter(
                    InfraValuationReport.fund_id == fund_id,
                    InfraValuationReport.valuation_date == quarter,
                )
                .all()
            )
            assets = {
                a.asset_id: a
                for a in session.query(InfraAsset).all()
            }

        total_nav = sum(r.implied_equity_eur or 0.0 for r in reports)

        for r in reports:
            asset = assets.get(r.asset_id)
            esg   = _esg_ref.get(r.asset_id, {})
            nav   = r.implied_equity_eur or 0.0
            rows.append({
                'instrument_name' : asset.asset_name if asset else r.asset_id,
                'asset_class'     : 'Infrastructure',
                'sub_asset_class' : asset.sector if asset else None,
                'market_value_eur': nav,
                'weight_pct'      : nav / total_nav * 100 if total_nav else 0.0,
                'esg_score'       : esg.get('esg_score'),
                'env_score'       : esg.get('env_score'),
                'soc_score'       : esg.get('soc_score'),
                'gov_score'       : esg.get('gov_score'),
                'controversy_flag': esg.get('controversy_flag'),
                'carbon_intensity': esg.get('carbon_intensity'),
                'esg_exposure_eur': nav,
                'esg_reporter'    : r.appraiser or 'Independent appraiser',
                'esg_report_date' : r.valuation_date,
            })

    return pd.DataFrame(rows)

def esg_portfolio_summary(
    esg_df: pd.DataFrame,
    nav: float,
    ) -> dict:
    """
    Compute portfolio-level weighted ESG metrics and flags.

    Parameters
    ----------
    esg_df : pd.DataFrame
        Output of build_esg_df.
    nav : float
        Fund NAV in EUR.

    Returns
    -------
    dict with keys:
        wav_esg, wav_env, wav_soc, wav_gov, wav_carbon,
        pct_low_esg, pct_controversy, controversies
    """
    scored = esg_df[esg_df['esg_score'].notna()].copy()
    total  = scored['esg_exposure_eur'].sum()

    if total == 0:
        return {}

    wav_esg   = (scored['esg_score'] *
                 scored['esg_exposure_eur']).sum() / total
    wav_env   = (scored['env_score'] *
                 scored['esg_exposure_eur']).sum() / total
    wav_soc   = (scored['soc_score'] *
                 scored['esg_exposure_eur']).sum() / total
    wav_gov   = (scored['gov_score'] *
                 scored['esg_exposure_eur']).sum() / total
    wav_carb  = (scored['carbon_intensity'].fillna(0) *
                 scored['esg_exposure_eur']).sum() / total

    low_esg      = scored[scored['esg_score'] < ESG_THRESHOLD_LOW]
    controversies = esg_df[esg_df['controversy_flag'] == True]

    pct_low_esg  = low_esg['esg_exposure_eur'].sum() / total * 100
    pct_controv  = (controversies['esg_exposure_eur'].sum() /
                    esg_df['esg_exposure_eur'].sum() * 100
                    if esg_df['esg_exposure_eur'].sum() > 0 else 0)

    return {
        'wav_esg'       : round(wav_esg, 1),
        'wav_env'       : round(wav_env, 1),
        'wav_soc'       : round(wav_soc, 1),
        'wav_gov'       : round(wav_gov, 1),
        'wav_carbon'    : round(wav_carb, 1),
        'pct_low_esg'   : round(pct_low_esg, 1),
        'pct_controversy': round(pct_controv, 1),
        'controversies' : controversies,
    }

##### PRINT HTML TABLES ##########
esgl = ESG_THRESHOLD_LOW
esgh = ESG_THRESHOLD_HIGH

ESG_COL_STYLES = {
    'esg_score'       : lambda v: None if pd.isna(v) else (C['green'] if v >= esgh else (C['amber'] if v >= esgl else C['red'])),
    'env_score'       : lambda v: None if pd.isna(v) else (C['green'] if v >= esgh else (C['amber'] if v >= esgl else C['red'])),
    'soc_score'       : lambda v: None if pd.isna(v) else (C['green'] if v >= esgh else (C['amber'] if v >= esgl else C['red'])),
    'gov_score'       : lambda v: None if pd.isna(v) else (C['green'] if v >= esgh else (C['amber'] if v >= esgl else C['red'])),
    'controversy_flag': lambda v: C['red'] if v else None,
}

ESG_FMT = {
    'market_value_eur' : '{:,.0f}',
    'weight_pct'       : '{:.2f}%',
    'esg_score'        : '{:.0f}',
    'env_score'        : '{:.0f}',
    'soc_score'        : '{:.0f}',
    'gov_score'        : '{:.0f}',
    'carbon_intensity' : '{:.1f}',
    'esg_exposure_eur' : '{:,.0f}',
}

ESG_COL_ALIGN_OVERRIDE = {
    'esg_score': 'center', 
    'env_score': 'center',
    'soc_score': 'center', 
    'gov_score': 'center', 
}

ESG_HEADER_ALIGN_OVERRIDE = {
    'market_value_eur': 'center', 
    'esg_exposure_eur': 'center', 
}


def display_esg_assets(esg_df, valuation_date: str | None = None, fund_id: str | None = None, export_id: str | None = None):

    html = display_dark_table(
        esg_df,
        caption='ESG Portfolio Profile',
        fmt=ESG_FMT,
        col_styles=ESG_COL_STYLES,
        col_align_override=ESG_COL_ALIGN_OVERRIDE,
        col_header_align_override=ESG_HEADER_ALIGN_OVERRIDE,
        date_str=valuation_date,
        return_html=True,
        )

    from IPython.display import display, HTML
    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('ESG Portfolio Profile')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)

def display_esg_summary(esg_df: pd.DataFrame, valuation_date: str | None = None, fund_id: str | None = None, export_id: str | None = None) -> None:
    scored = esg_df[esg_df['esg_score'].notna()].copy()
    total  = scored['esg_exposure_eur'].sum()

    if total == 0:
        return

    wav_esg  = (scored['esg_score'] * scored['esg_exposure_eur']).sum() / total
    wav_env  = (scored['env_score'] * scored['esg_exposure_eur']).sum() / total
    wav_soc  = (scored['soc_score'] * scored['esg_exposure_eur']).sum() / total
    wav_gov  = (scored['gov_score'] * scored['esg_exposure_eur']).sum() / total
    wav_carb = (scored['carbon_intensity'].fillna(0) * scored['esg_exposure_eur']).sum() / total

    low_esg       = scored[scored['esg_score'] < ESG_THRESHOLD_LOW]
    controversies = esg_df[esg_df['controversy_flag'] == True]
    pct_low_esg   = low_esg['esg_exposure_eur'].sum() / total * 100
    pct_controv   = (controversies['esg_exposure_eur'].sum() /
                     esg_df['esg_exposure_eur'].sum() * 100
                     if esg_df['esg_exposure_eur'].sum() > 0 else 0)

    rows = [
        ('ESG score',           f'{wav_esg:.1f}/100'),
        ('ENV score',           f'{wav_env:.1f}/100'),
        ('SOC score',           f'{wav_soc:.1f}/100'),
        ('GOV score',           f'{wav_gov:.1f}/100'),
        ('Carbon intensity',    f'{wav_carb:.1f} tCO2/EURm'),
        ('', ''),
        ('% exposure', ''),
        ('Below ESG threshold', f'{pct_low_esg:.1f}%'),
        ('With controversy',    f'{pct_controv:.1f}%'),
    ]

    highlight = [6]  # '% exposure' header row

    if len(controversies) > 0:
        rows.append(('', ''))
        rows.append(('Controversy flags', ''))
        highlight.append(len(rows) - 1)
        for _, row in controversies.iterrows():
            rows.append((f"  {row['instrument_name']}", f"ESG: {row['esg_score']:.0f}"))

    df = pd.DataFrame(rows, columns=['Metric', 'Value'])
    html = display_dark_table(df, caption='ESG Portfolio Summary', highlight_rows=highlight, date_str=valuation_date, return_html=True)

    from IPython.display import display, HTML
    display(HTML(html))

    if export_id is not None:
        from fund_risk_workflow.ui.nb_utils import _slugify, save_html_as_png
        title_slug = _slugify('ESG Portfolio Summary')
        filename = f'{export_id}_{title_slug}'
        fid = fund_id or 'unknown'
        save_html_as_png(html, fid, filename)

def plot_esg_profile(esg_df, FUND_ID, plot_title="06. ESG profile - HF", valuation_date: str | None = None, export_id: str | None = None):

    esg_scored = esg_df[esg_df['esg_score'].notna()].copy()
    total_scored_mv = esg_scored['esg_exposure_eur'].sum()
    ac_esg = esg_scored.groupby('asset_class').agg(
        wav_esg=('esg_score', lambda x: (x * esg_scored.loc[x.index, 'esg_exposure_eur']).sum() /
                esg_scored.loc[x.index, 'esg_exposure_eur'].sum()),
        exposure=('esg_exposure_eur', 'sum')
    ).reset_index()
    ac_esg['pct_total'] = ac_esg['exposure'] / total_scored_mv * 100

    fig,(ax1, ax2) = plt.subplots(2, 1, figsize=(12, 5))

    # Main title as figure suptitle
    fig.suptitle(
        'ESG Profile by Asset Class',
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
            f'As of {valuation_date}',
            fontsize=11,
            color=C['muted'],
            va='top',
        )

    colors = [C['muted'], C['dim'], C['border'], C['border'], C['text'], C['text']]
    left = 0
    for i, (_, row) in enumerate(ac_esg.iterrows()):
        ax1.barh(0, row['pct_total'], left=left,
                    color=colors[i % len(colors)], alpha=0.85, height=0.2)
        if row['pct_total'] > 3:
            ax1.text(left + row['pct_total']/2, 0,
                        f"{row['asset_class']}\n{row['pct_total']:.1f}%",
                        ha='center', va='center', fontsize=8, color='white', fontweight='bold')
        left += row['pct_total']

    ax1.set_xlim(0, 100)
    ax1.set_yticks([])
    ax1.set_xlabel('% of ESG-scored exposure', fontsize=9)
    ax1.spines[['top', 'right', 'left', 'bottom']].set_visible(False)
    ax1.tick_params(labelsize=9, length=0)

    bars = ax2.barh(ac_esg['asset_class'], ac_esg['wav_esg'],
                        color=[C['amber'] if v < 50 else C['blue2'] if v < 70 else C['green']
                            for v in ac_esg['wav_esg']],
                        height=0.4, alpha=0.85)
    ax2.axvline(ESG_THRESHOLD_LOW, color=ACCENT2, lw=1, linestyle='--',
                    label=f'Low ESG threshold ({ESG_THRESHOLD_LOW})')
    ax2.axvline(70, color=ACCENT3, lw=1, linestyle='--', label='Good ESG threshold (70)')
    ax2.set_xlim(0, 100)
    ax2.set_xlabel('Weighted avg ESG score', fontsize=9)
    ax2.spines[['top', 'right', 'left', 'bottom']].set_visible(False)
    ax2.grid(False)
    ax2.tick_params(labelsize=9, length=0)
    ax2.legend(fontsize=7)
    for bar, val in zip(bars, ac_esg['wav_esg']):
        ax2.text(val + 1, bar.get_y() + bar.get_height()/2,
                    f'{val:.1f}', va='center', fontsize=9)
    plt.tight_layout(rect=[0, 0, 1, 0.97])

    if export_id is not None:
        from pathlib import Path
        from fund_risk_workflow.ui.nb_utils import _slugify, _get_project_root
        title_slug = _slugify(plot_title.split('.', 1)[-1].strip() if '.' in plot_title else plot_title)
        filename = f'{export_id}_{title_slug}'
        out_dir = _get_project_root() / 'fig' / FUND_ID
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f'{filename}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    else:
        save_fig(fig, FUND_ID, plot_title)

    plt.show()
