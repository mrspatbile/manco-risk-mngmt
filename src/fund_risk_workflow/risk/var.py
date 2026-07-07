"""
var.py
======
Backward compatibility shim for VaR functions.

DEPRECATED: This module re-exports from fund_risk_workflow.computation.var for backward compatibility.
New code should import directly from fund_risk_workflow.computation.var.

The canonical VaR computation module is now in src/computation/var.py.
This module will be removed in a future refactoring phase.
"""

# Import canonical implementations from fund_risk_workflow.computation.var
from fund_risk_workflow.computation.var import (
    var_scale,
    es_from_var,
    var_historical,
    var_parametric,
    es_historical,
    es_parametric,
    es_scale,
    kupiec_test,
    christoffersen_test,
)

__all__ = [
    'var_scale',
    'es_from_var',
    'var_historical',
    'var_parametric',
    'es_historical',
    'es_parametric',
    'es_scale',
    'kupiec_test',
    'christoffersen_test',
]
