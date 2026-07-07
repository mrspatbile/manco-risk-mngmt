"""
Project-level configuration for fund risk analysis.

Date Semantics
==============
- VALUATION_DATE: Static business date for all computations (fund snapshot date)
                  "As of" date used for positions, market data, NAV, and risk calculations.
                  Intentionally static and point-in-time by design.
                  Example: 2026-03-31 (Q1 reporting period)
                  Do not make dynamic.

- COMPUTATION_DATE: Audit trail - when analysis was actually performed
                    Metadata only, does not affect calculations
                    Set to None to use today's date at runtime

- QUARTER: Reporting quarter in YYYY-MM-DD format (quarter end date)
           Usually same as VALUATION_DATE for quarterly reporting

All computations (VaR, attribution, liquidity, etc.) use VALUATION_DATE.
All plots and reports show VALUATION_DATE, not COMPUTATION_DATE.
"""

# ================================================================
# VALUATION_DATE: Primary date for all computations (STATIC)
# ================================================================
# Static business date used for positions, market data, NAV, and risk calculations.
# Intentionally static and point-in-time by design.
#
# Examples:
# - 2026-03-31 for Q1 reporting
# - 2026-06-30 for Q2 reporting
#
# Do NOT make this dynamic. Each reporting period has a fixed valuation date.

VALUATION_DATE = '2026-03-31'

# For backward compatibility
REFERENCE_DATE = VALUATION_DATE

# ================================================================
# COMPUTATION_DATE: Audit trail (metadata, optional)
# ================================================================
# When this analysis was actually performed.
# Does not affect calculations, only used for audit/logging.
#
# Set to None to use today's date at runtime.
# Set to specific date for reproducible runs.

COMPUTATION_DATE = None

# ================================================================
# QUARTER: Reporting period
# ================================================================
# Reporting quarter in YYYY-MM-DD format (quarter end date).
# Usually same as VALUATION_DATE for quarterly reporting.

QUARTER = VALUATION_DATE


# ================================================================
# Risk Management Constants
# ================================================================

# # Value-at-Risk (VaR) confidence levels
# VaR_CONFIDENCE_LEVEL = 0.99  # Standard regulatory confidence for VaR/ES

# # VaR holding periods
# VAR_HORIZON_BASEL = 10          # Basel III regulatory horizon (days)
# VAR_HORIZON_UCITS_AIFM = 20    # UCITS and AIFMD standard horizon (days)

# # Expected Shortfall (ES)
# ES_CONFIDENCE_LEVEL = 0.99

# Liquidity bucket display order
LIQUIDITY_BUCKET_ORDER = [
    "1 day",
    "2-7 days",
    "8-30 days",
    "31-90 days",
    "91-365 days",
    "> 1 year",
]


