"""
src/style.py — Common matplotlib style for every figure of the report.

  * Agg backend, DejaVu Sans, 7.0 in wide (A4 with 2 cm margins);
  * ink #0b0b0b / #52514e, axes #c3c2b7, thin y-only grid #e1e0d9, no top/right spines;
  * 1.6 pt lines, bold left-aligned panel titles, English labels;
  * fixed categorical palette: blue (demand / main series), orange (solar), aqua (price), yellow (CO2),
    magenta, green, violet, red.

Usage:
    import src.style                       # sets the rcParams on import
    from src.style import BLUE, ORANGE, ...
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BLUE = "#2a78d6"      # demand / main series
ORANGE = "#eb6834"    # solar
AQUA = "#1baf7a"      # price
YELLOW = "#eda100"    # CO2
MAGENTA = "#e87ba4"
GREEN = "#008300"
VIOLET = "#4a3aa7"
RED = "#e34948"
GREY = "#7a8290"
PALETTE = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED]
INK = "#0b0b0b"
INK2 = "#52514e"
AXES = "#c3c2b7"
GRID = "#e1e0d9"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.labelsize": 9, "axes.labelcolor": INK2, "axes.edgecolor": AXES, "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.prop_cycle": matplotlib.cycler(color=PALETTE),
    "xtick.color": INK2, "ytick.color": INK2, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "xtick.major.size": 3, "ytick.major.size": 3,
    "lines.linewidth": 1.6, "legend.frameon": False, "legend.fontsize": 8, "text.color": INK,
    "figure.dpi": 100, "savefig.bbox": "tight", "savefig.pad_inches": 0.03, "pdf.fonttype": 42,
})
