"""
Pipeline module.

Reusable workflows that orchestrate data loading, enrichment, and computation.
"""

try:
    from fund_risk_workflow.pipeline.fixed_position_var import compute_fixed_position_var_1day
    __all__ = [
        'compute_fixed_position_var_1day',
    ]
except ImportError:
    # If dependencies missing, still allow module to be imported
    __all__ = []
