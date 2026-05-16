"""
plot_style.py
=============
Shared matplotlib dark theme and accent colours for all risk notebooks.

Usage
-----
    from src.plot_style import ACCENT, ACCENT2, ACCENT3
"""
import matplotlib.pyplot as plt

ACCENT  = '#2563EB'
ACCENT2 = '#DC2626'
ACCENT3 = '#16A34A'

plt.rcParams.update({
    'figure.facecolor' : '#0f0f0f',
    'axes.facecolor'   : '#1a1a1a',
    'axes.edgecolor'   : '#333333',
    'axes.labelcolor'  : '#cccccc',
    'xtick.color'      : '#888888',
    'ytick.color'      : '#888888',
    'text.color'       : '#cccccc',
    'grid.color'       : '#2a2a2a',
    'grid.linestyle'   : '--',
    'font.family'      : 'monospace',
    'figure.dpi'       : 120,
})