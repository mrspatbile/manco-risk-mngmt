"""
Regulatory and risk framework constants.

Constants used across all fund notebooks and risk modules,
implementing requirements from UCITS Directive, AIFMD, and CSSF guidance.

Regulatory basis:
    UCITS Directive (2009/65/EC) — SRRI, VaR limits
    AIFMD (Directive 2011/61/EU) — Art. 15 (liquidity), Art. 7 (leverage)
    CSSF Regulation 10-04 — organizational requirements
"""

# Risk metrics (UCITS SRRI, AIFMD Art. 46-49)
CONFIDENCE = 0.99      # VaR confidence level (99%)
HORIZON = 20           # VaR holding period in trading days

# Liquidity management (AIFMD Art. 15)
NOTICE = 5             # Redemption notice period in days

# Leverage limits (AIFMD Art. 7, Delegated Regulation EU231/2013)
GROSS_LIMIT = 3.0      # AIFM leverage limit (gross method)

# Concentration thresholds
RESIDUAL_THRESHOLD_PCT = 0.20  # Position size threshold for 5/10/40 rule analysis
