"""Daily workflow helper functions for data pipeline operations."""

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

LOOKBACK_DAYS = 30
VIX_NORMAL_THRESHOLD = 15
VIX_ELEVATED_THRESHOLD = 25

def business_day_offset(date: str, offset: int) -> str:
    """Return a business-day offset as an ISO date string."""
    return (pd.Timestamp(date) + BDay(offset)).strftime("%Y-%m-%d")

def load_workflow_dates(valuation_date: str, lookback_days: int = LOOKBACK_DAYS) -> dict:
    """Return workflow dates and a display table for the data pipeline notebook."""
    dates = {
        "valuation_date": valuation_date,
        "simulated_run_date": business_day_offset(valuation_date, 1),
        "prior_business_date": business_day_offset(valuation_date, -1),
        "lookback_start_date": business_day_offset(valuation_date, -lookback_days),
    }

    dates_table = pd.DataFrame(
        [
            {
            "field": "Valuation date",
            "value": dates["valuation_date"],
            "purpose": "Positions, prices, NAV, and risk inputs",
            },
            {
                "field": "Simulated run date",
                "value": dates["simulated_run_date"],
                "purpose": "Assumed AIFM run date",
            },
            {
                "field": "Prior business date",
                "value": dates["prior_business_date"],
                "purpose": "Overnight comparison checks",
            },
            {
                "field": "Lookback start date",
                "value": dates["lookback_start_date"],
                "purpose": "Market-data exception checks",
            },
        ]
    )

    return {
        **dates,
        "dates_table": dates_table,
    }

def summarise_position_snapshot(
    positions: pd.DataFrame, prior_positions: pd.DataFrame
) -> dict:
    """Summarise position changes and exposures between two snapshots."""
    new_isins = set(positions["isin"]) - set(prior_positions["isin"])
    removed_isins = set(prior_positions["isin"]) - set(positions["isin"])

    nav = positions["market_value_eur"].sum()
    long_exposure = positions.loc[
        positions["market_value_eur"] > 0, "market_value_eur"
    ].sum()
    short_exposure = positions.loc[
        positions["market_value_eur"] < 0, "market_value_eur"
    ].sum()
    gross_exposure = positions["market_value_eur"].abs().sum()

    position_summary = pd.DataFrame(
        {
            "metric": [
                "positions",
                "prior_positions",
                "new_instruments",
                "removed_instruments",
                "nav_eur",
                "long_exposure_eur",
                "short_exposure_eur",
                "gross_exposure_eur",
            ],
            "value": [
                len(positions),
                len(prior_positions),
                len(new_isins),
                len(removed_isins),
                nav,
                long_exposure,
                short_exposure,
                gross_exposure,
            ],
        }
    )

    asset_class_breakdown = (
        positions.groupby("asset_class", as_index=False)["market_value_eur"]
        .sum()
        .assign(weight_pct=lambda df: df["market_value_eur"] / nav * 100)
        .sort_values("market_value_eur", ascending=False)
    )

    # Add weight_pct to positions for instrument_changes display
    positions_with_weight = positions.assign(
        weight_pct=positions["market_value_eur"] / nav * 100
    )
    prior_positions_with_weight = prior_positions.assign(
        weight_pct=prior_positions["market_value_eur"] / nav * 100
    )

    new_instruments = positions_with_weight.loc[
        positions_with_weight["isin"].isin(new_isins),
        ["isin", "instrument_name", "asset_class", "weight_pct"],
    ].copy()
    new_instruments.insert(0, "change_type", "New instrument")

    removed_instruments = prior_positions_with_weight.loc[
        prior_positions_with_weight["isin"].isin(removed_isins),
        ["isin", "instrument_name", "asset_class", "weight_pct"],
    ].copy()
    removed_instruments.insert(0, "change_type", "Removed instrument")

    instrument_changes = pd.concat(
        [new_instruments, removed_instruments],
        ignore_index=True,
    )

    if instrument_changes.empty:
        instrument_changes = pd.DataFrame(
            [
                {
                    "change_type": "No instrument changes",
                    "isin": None,
                    "instrument_name": None,
                    "asset_class": None,
                    "weight_pct": None,
                }
            ]
        )

    return {
        "new_isins": new_isins,
        "removed_isins": removed_isins,
        "nav": nav,
        "position_summary": position_summary,
        "asset_class_breakdown": asset_class_breakdown,
        "instrument_changes": instrument_changes,
    }


def _price_validation_status(row: pd.Series) -> str:
    """Determine price validation status: MANUAL REVIEW, FLAG, or OK."""
    if pd.isna(row["bbg_price"]):
        return "MANUAL REVIEW"

    tolerance = 0.25 if row["asset_class"] == "Bond" else 0.50

    if abs(row["diff_pct"]) > tolerance:
        return "FLAG"

    return "OK"


def validate_prices(
    positions: pd.DataFrame, bbg, valuation_date: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Validate fund administrator prices against Bloomberg prices on valuation date.

    Uses date-aligned Bloomberg history (bdh) to ensure prices are from the same
    date as positions, not raw cached values from later dates.

    Excludes cash positions, which are validated separately via build_cash_price_check().
    """
    # Exclude cash positions from Bloomberg validation (cash is not market-priced)
    price_validation_universe = positions.loc[
        positions["bloomberg_ticker"].notna()
        & ~positions["asset_class"].eq("Cash")
    ].copy()
    tickers = price_validation_universe["bloomberg_ticker"].tolist()

    # Get Bloomberg prices for the valuation date
    # bdp accepts optional date parameter to return point-in-time data
    bbg_prices_list = []
    for ticker in tickers:
        try:
            result = bbg.bdp(ticker, "PX_LAST", date=valuation_date)
            price = result.loc[ticker, "PX_LAST"] if len(result) > 0 else np.nan
            bbg_prices_list.append({
                "bloomberg_ticker": ticker,
                "bbg_price": price
            })
        except Exception:
            bbg_prices_list.append({
                "bloomberg_ticker": ticker,
                "bbg_price": np.nan
            })

    bbg_prices = pd.DataFrame(bbg_prices_list)

    price_validation = price_validation_universe[
        ["instrument_name", "asset_class", "bloomberg_ticker", "price"]
    ].merge(bbg_prices, on="bloomberg_ticker", how="left")

    price_validation = price_validation.rename(columns={"price": "fund_admin_price"})

    price_validation["diff_pct"] = (
        (price_validation["fund_admin_price"] - price_validation["bbg_price"])
        / price_validation["bbg_price"]
        * 100
    ).round(4)

    price_validation["status"] = price_validation.apply(
        _price_validation_status, axis=1
    )

    price_validation = (
    price_validation
    .sort_values(["status", "asset_class", "instrument_name"])
    .reset_index(drop=True)
    )

    flagged_prices = (
        price_validation
        .loc[price_validation["status"] != "OK"]
        .reset_index(drop=True)
    )

    return price_validation, flagged_prices


def build_cash_price_check(positions: pd.DataFrame) -> pd.DataFrame:
    """
    Validate that cash positions have unit price of 1.00.

    Cash is not market-priced and should always have price == 1.0.
    This is checked separately from Bloomberg price validation.

    Returns
    -------
    pd.DataFrame
        Cash price check with columns: instrument_name, asset_class, price, status, message
    """
    cash_positions = positions.loc[positions["asset_class"] == "Cash"].copy()

    if cash_positions.empty:
        return pd.DataFrame(
            columns=["instrument_name", "asset_class", "price", "status", "message"]
        )

    records = []
    for _, row in cash_positions.iterrows():
        price = row["price"]
        is_correct = abs(price - 1.0) < 0.0001  # Allow for floating point precision

        records.append({
            "instrument_name": row["instrument_name"],
            "asset_class": row["asset_class"],
            "price": price,
            "status": "OK" if is_correct else "FLAG",
            "message": "Unit cash price is correct" if is_correct else f"Cash price should be 1.00, got {price:.4f}",
        })

    cash_df = pd.DataFrame(records)
    return cash_df.sort_values(["status", "instrument_name"])


def build_onboarding_review(
    positions: pd.DataFrame, new_isins: set, bbg, valuation_date: str
) -> pd.DataFrame:
    """Build new instrument onboarding review."""
    onboarding_records = []

    for isin in sorted(new_isins):
        # Check if ISIN exists in current fund's positions
        pos_match = positions.loc[positions["isin"] == isin]
        if len(pos_match) == 0:
            onboarding_records.append(
                {
                    "isin": isin,
                    "instrument_name": "NOT FOUND",
                    "bloomberg_ticker": None,
                    "fund_admin_asset_class": "UNKNOWN",
                    "bloomberg_asset_class": None,
                    "duration_check": "not in fund",
                    "status": "NOT IN BBG",
                }
            )
            continue

        row = pos_match.iloc[0]
        ticker = row["bloomberg_ticker"]

        if pd.isna(ticker):
            onboarding_records.append(
                {
                    "isin": isin,
                    "instrument_name": row["instrument_name"],
                    "bloomberg_ticker": None,
                    "fund_admin_asset_class": row["asset_class"],
                    "bloomberg_asset_class": None,
                    "duration_check": "manual review",
                    "status": "MANUAL ONBOARDING",
                }
            )
            continue

        ref = bbg.bdp(
            ticker,
            [
                "NAME",
                "ASSET_CLASS",
                "CRNCY",
                "DUR_ADJ_MID",
                "CONVEXITY",
                "YLD_YTM_MID",
                "BETA",
                "RTG_SP",
                "VOLUME_AVG_20D",
            ],
        )

        bbg_asset_class = ref.loc[ticker, "ASSET_CLASS"]
        bbg_duration = ref.loc[ticker, "DUR_ADJ_MID"]

        asset_class_status = (
            "OK" if str(bbg_asset_class) == str(row["asset_class"]) else "FLAG"
        )

        duration_check = "not applicable"

        if row["asset_class"] == "Bond" and not pd.isna(bbg_duration):
            maturity_years = None

            if row["maturity"]:
                maturity_years = (
                    pd.Timestamp(row["maturity"]) - pd.Timestamp(valuation_date)
                ).days / 365

            if maturity_years and bbg_duration > maturity_years:
                duration_check = "FLAG"
            else:
                duration_check = "OK"

        status = "OK" if asset_class_status == "OK" and duration_check != "FLAG" else "FLAG"

        onboarding_records.append(
            {
                "isin": isin,
                "instrument_name": row["instrument_name"],
                "bloomberg_ticker": ticker,
                "fund_admin_asset_class": row["asset_class"],
                "bloomberg_asset_class": bbg_asset_class,
                "duration_check": duration_check,
                "status": status,
            }
        )

    if onboarding_records:
        return pd.DataFrame(onboarding_records)
    else:
        return pd.DataFrame(
            {
                "control_step": [
                    "Pull Bloomberg reference data",
                    "Validate asset class against fund administrator file",
                    "Check bond duration against remaining maturity",
                    "Flag missing Bloomberg tickers for manual onboarding",
                    "Release instrument to risk dataset after checks pass",
                ]
            }
        )


def build_market_context(
    positions: pd.DataFrame, bbg, valuation_date: str, prior_business_date: str
) -> dict:
    """Build market context review including VIX, yield moves, and credit spreads."""
    vix = bbg.bdp("VIX Index", "PX_LAST")
    vix_level = vix.loc["VIX Index", "PX_LAST"]

    if vix_level > VIX_ELEVATED_THRESHOLD:
        vix_regime = "elevated"
    elif vix_level > VIX_NORMAL_THRESHOLD:
        vix_regime = "normal"
    else:
        vix_regime = "low"

    market_context = pd.DataFrame(
        {
            "metric": ["VIX level", "VIX regime"],
            "value": [round(vix_level, 2), vix_regime],
        }
    )

    bond_tickers = positions.loc[
        (positions["asset_class"] == "Bond")
        & (positions["bloomberg_ticker"].notna()),
        "bloomberg_ticker",
    ].tolist()

    yield_moves = []

    if bond_tickers:
        yields_current = bbg.bdp(bond_tickers, "YLD_YTM_MID", date=valuation_date)
        yields_prior = bbg.bdp(bond_tickers, "YLD_YTM_MID", date=prior_business_date)

        for ticker in bond_tickers:
            name = positions.loc[
                positions["bloomberg_ticker"] == ticker, "instrument_name"
            ].values[0]

            try:
                ytm_current = yields_current.loc[ticker, "YLD_YTM_MID"]
                ytm_prior = yields_prior.loc[ticker, "YLD_YTM_MID"]

                yield_moves.append(
                    {
                        "instrument_name": name,
                        "bloomberg_ticker": ticker,
                        "yield_pct": ytm_current,
                        "overnight_move_bps": (ytm_current - ytm_prior) * 100,
                    }
                )

            except Exception:
                yield_moves.append(
                    {
                        "instrument_name": name,
                        "bloomberg_ticker": ticker,
                        "yield_pct": np.nan,
                        "overnight_move_bps": np.nan,
                    }
                )

    yield_moves = pd.DataFrame(yield_moves)

    corp_tickers = positions.loc[
        (positions["sub_asset_class"].isin(["IG Corporate", "HY Corporate"]))
        & (positions["bloomberg_ticker"].notna()),
        "bloomberg_ticker",
    ].tolist()

    credit_spreads = []

    if corp_tickers:
        spreads = bbg.bdp(corp_tickers, ["Z_SPRD_MID", "RTG_SP"])

        for ticker in corp_tickers:
            name = positions.loc[
                positions["bloomberg_ticker"] == ticker, "instrument_name"
            ].values[0]

            credit_spreads.append(
                {
                    "instrument_name": name,
                    "bloomberg_ticker": ticker,
                    "z_spread_bps": spreads.loc[ticker, "Z_SPRD_MID"],
                    "rating": spreads.loc[ticker, "RTG_SP"],
                }
            )

    credit_spreads = pd.DataFrame(credit_spreads)

    return {
        "market_context": market_context,
        "yield_moves": yield_moves,
        "credit_spreads": credit_spreads,
    }


def build_exception_review(
    positions: pd.DataFrame,
    bbg,
    lookback_start_date: str,
    valuation_date: str,
    nav: float,
) -> dict:
    """Build exception review for price outliers, missing sensitivities, and large positions."""
    liquid_tickers = positions.loc[
        positions["bloomberg_ticker"].notna(), "bloomberg_ticker"
    ].tolist()

    price_outliers = []

    for ticker in liquid_tickers:
        hist = bbg.bdh(ticker, "PX_LAST", lookback_start_date, valuation_date)

        if len(hist) < 5:
            continue

        returns = hist["PX_LAST"].pct_change().dropna()
        vol_20d = returns.rolling(20).std().iloc[-1]
        ret_1d = returns.iloc[-1]

        if vol_20d > 0 and abs(ret_1d) > 2 * vol_20d:
            name = positions.loc[
                positions["bloomberg_ticker"] == ticker, "instrument_name"
            ].values[0]

            price_outliers.append(
                {
                    "instrument_name": name,
                    "bloomberg_ticker": ticker,
                    "return_1d_pct": ret_1d * 100,
                    "vol_20d_pct": vol_20d * 100,
                    "z_score": ret_1d / vol_20d,
                }
            )

    price_outliers = pd.DataFrame(price_outliers)

    missing_sensitivities = []

    for _, row in positions.iterrows():
        if pd.isna(row["bloomberg_ticker"]):
            continue

        issues = []

        if row["asset_class"] == "Bond":
            if pd.isna(row.get("dur_adj_mid")):
                issues.append("duration missing")
            if pd.isna(row.get("convexity")):
                issues.append("convexity missing")

        elif row["asset_class"] == "Equity":
            if pd.isna(row.get("beta")):
                issues.append("beta missing")

        if issues:
            missing_sensitivities.append(
                {
                    "instrument_name": row["instrument_name"],
                    "asset_class": row["asset_class"],
                    "issues": ", ".join(issues),
                }
            )

    missing_sensitivities = pd.DataFrame(missing_sensitivities)

    large_positions = (
        positions.assign(weight_pct=positions["market_value_eur"] / nav * 100)
        .loc[lambda df: df["weight_pct"].abs() > 10]
        .sort_values("weight_pct", key=lambda s: s.abs(), ascending=False)
    )

    large_positions = large_positions[
        ["instrument_name", "asset_class", "market_value_eur", "weight_pct"]
    ]

    exception_summary = pd.DataFrame(
        {
            "check": [
                "price_outliers",
                "missing_sensitivities_before_enrichment",
                "positions_above_10pct_nav",
            ],
            "exceptions": [
                len(price_outliers),
                len(missing_sensitivities),
                len(large_positions),
            ],
        }
    )

    return {
        "price_outliers": price_outliers,
        "missing_sensitivities": missing_sensitivities,
        "large_positions": large_positions,
        "exception_summary": exception_summary,
    }


def summarise_risk_ready_dataset(risk_df: pd.DataFrame) -> dict:
    """Summarise enrichment and sensitivity coverage for risk-ready dataset."""
    enrichment_summary = (
        risk_df.groupby("enrichment_source", as_index=False)["instrument_name"]
        .count()
        .rename(columns={"instrument_name": "positions"})
    )

    sensitivity_coverage = pd.DataFrame(
        {
            "field": ["beta", "dur_adj_mid", "convexity", "adv_eur"],
            "available_positions": [
                risk_df["beta"].notna().sum(),
                risk_df["dur_adj_mid"].notna().sum(),
                risk_df["convexity"].notna().sum(),
                (risk_df["adv_eur"] > 0).sum(),
            ],
            "total_positions": len(risk_df),
        }
    )

    top_positions = risk_df[
        [
            "instrument_name",
            "asset_class",
            "market_value_eur",
            "weight_pct",
            "beta",
            "dur_adj_mid",
            "enrichment_source",
        ]
    ].sort_values("market_value_eur", key=lambda s: s.abs(), ascending=False)

    return {
        "enrichment_summary": enrichment_summary,
        "sensitivity_coverage": sensitivity_coverage,
        "top_positions": top_positions,
    }
