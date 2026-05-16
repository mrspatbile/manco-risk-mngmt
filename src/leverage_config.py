"""
leverage_config.py
==================
AIFMD leverage classification mapping per EU 231/2013 Article 7.

Keyed by (asset_class, sub_asset_class) tuple for precision.

Source of leverage categories:
- Cash Instrument : direct holdings (equities, bonds, loans, real estate)
- Synthetic       : exposure via derivatives (futures, options, forwards, swaps)
- Embedded        : structured products, ETFs and funds requiring look-through
- Repo            : financing via repurchase agreements
- Excluded        : cash and money market instruments

Listed/OTC classification:
- Listed   : exchange-traded instruments
- OTC      : over-the-counter instruments
- Illiquid : direct real estate, private equity, unlisted assets
- Excluded : cash, money market

ESMA guidelines require look-through for ETFs, fund quotas and structured
products where possible. ETFs are classified as Embedded pending look-through.
"""

INSTRUMENT_SOURCE = {

    # ---- Equities ----
    ('Equity', 'Large Cap')      : ('Cash Instrument', 'Listed'),
    ('Equity', 'Mid Cap')        : ('Cash Instrument', 'Listed'),
    ('Equity', 'Small Cap')      : ('Cash Instrument', 'Listed'),
    ('Equity', 'Listed REIT')    : ('Cash Instrument', 'Listed'),

    # ---- ETFs: look-through required ----
    ('Equity', 'ETF')            : ('Embedded',        'Listed'),
    ('Equity', 'Leveraged ETF')  : ('Embedded',        'Listed'),
    ('Equity', 'Inverse ETF')    : ('Synthetic',       'Listed'),

    # ---- Futures and listed derivatives ----
    ('Equity', 'Future')         : ('Synthetic',       'Listed'),
    ('Equity', 'Listed Option')  : ('Synthetic',       'Listed'),
    ('Equity', 'Warrant')        : ('Synthetic',       'Listed'),

    # ---- Bonds: listed ----
    ('Bond', 'Government')       : ('Cash Instrument', 'Listed'),
    ('Bond', 'IG Corporate')     : ('Cash Instrument', 'Listed'),
    ('Bond', 'HY Corporate')     : ('Cash Instrument', 'Listed'),
    ('Bond', 'Convertible')      : ('Embedded',        'Listed'),
    ('Bond', 'ETF')              : ('Embedded',        'Listed'),

    # ---- Loans ----
    ('Loan', 'Senior Secured')   : ('Cash Instrument', 'OTC'),
    ('Loan', 'Second Lien')      : ('Cash Instrument', 'OTC'),
    ('Loan', 'Mezzanine')        : ('Cash Instrument', 'OTC'),
    ('Loan', 'Term Loan')        : ('Cash Instrument', 'OTC'),

    # ---- Structured credit ----
    ('CLO', 'CLO AAA')           : ('Embedded',        'OTC'),
    ('CLO', 'CLO AA')            : ('Embedded',        'OTC'),
    ('CLO', 'CLO A')             : ('Embedded',        'OTC'),
    ('CLO', 'CLO BBB')           : ('Embedded',        'OTC'),
    ('CLO', 'CLO BB')            : ('Embedded',        'OTC'),
    ('CLO', 'CLO Equity')        : ('Embedded',        'OTC'),
    ('ABS', 'ABS')               : ('Embedded',        'OTC'),
    ('MBS', 'MBS')               : ('Embedded',        'OTC'),
    ('CMBS', 'CMBS')             : ('Embedded',        'OTC'),
    ('CDO', 'CDO')               : ('Embedded',        'OTC'),

    # ---- Structured notes ----
    ('Bond', 'Capital Protected Note') : ('Embedded',  'OTC'),
    ('Bond', 'Credit Linked Note')     : ('Embedded',  'OTC'),
    ('Bond', 'Total Return Note')      : ('Embedded',  'OTC'),
    ('Bond', 'Leveraged Note')         : ('Embedded',  'OTC'),
    ('Bond', 'Participation Note')     : ('Embedded',  'OTC'),
    ('Bond', 'Structured Note')        : ('Embedded',  'OTC'),

    # ---- OTC derivatives ----
    ('Derivative', 'Forward')    : ('Synthetic',       'OTC'),
    ('Derivative', 'Swap')       : ('Synthetic',       'OTC'),
    ('Derivative', 'CDS')        : ('Synthetic',       'OTC'),
    ('Derivative', 'IRS')        : ('Synthetic',       'OTC'),
    ('Derivative', 'TRS')        : ('Synthetic',       'OTC'),
    ('Derivative', 'Swaption')   : ('Synthetic',       'OTC'),
    ('Derivative', 'OTC Option') : ('Synthetic',       'OTC'),
    ('Derivative', 'Cap')        : ('Synthetic',       'OTC'),
    ('Derivative', 'Floor')      : ('Synthetic',       'OTC'),
    ('Derivative', 'Collar')     : ('Synthetic',       'OTC'),
    ('Derivative', 'Listed Option'): ('Synthetic',     'Listed'),

    # ---- FX ----
    ('FX', 'Forward')            : ('Synthetic',       'OTC'),
    ('FX', 'Spot')               : ('Cash Instrument', 'OTC'),
    ('FX', 'Option')             : ('Synthetic',       'OTC'),
    ('FX', 'Swap')               : ('Synthetic',       'OTC'),

    # ---- Fund quotas: look-through required ----
    ('Fund', 'UCITS')            : ('Embedded',        'Listed'),
    ('Fund', 'AIF')              : ('Embedded',        'OTC'),
    ('Fund', 'Private Equity')   : ('Embedded',        'Illiquid'),
    ('Fund', 'Venture Capital')  : ('Embedded',        'Illiquid'),
    ('Fund', 'Hedge Fund')       : ('Embedded',        'OTC'),
    ('Fund', 'Money Market')     : ('Excluded',        'Listed'),

    # ---- Real estate ----
    ('Real Estate', 'Direct Property') : ('Cash Instrument', 'Illiquid'),
    ('Real Estate', 'Listed REIT')     : ('Cash Instrument', 'Listed'),

    # ---- Repo financing ----
    ('Repo', 'Repo')             : ('Repo',            'OTC'),
    ('Repo', 'Reverse Repo')     : ('Repo',            'OTC'),
    ('Repo', 'Securities Lending'): ('Repo',           'OTC'),

    # ---- Commodity ----
    ('Commodity', 'ETF')         : ('Embedded',        'Listed'),
    ('Commodity', 'Future')      : ('Synthetic',       'Listed'),
    ('Commodity', 'Spot')        : ('Cash Instrument', 'OTC'),

    # ---- Excluded ----
    ('Cash', 'Cash')             : ('Excluded',        'Excluded'),
    ('Cash', 'Money Market')     : ('Excluded',        'Excluded'),
}