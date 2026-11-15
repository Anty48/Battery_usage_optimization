"""
figures.py — Report figures built from results/trajectory_final.csv and the other results/*.json.

    python src/figures.py -> report/fig/*.pdf|png
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from src.style import plt, BLUE, ORANGE, VIOLET, RED, GREY, INK, AXES, GRID   # noqa: E402

FIG = ROOT / "report" / "fig"; FIG.mkdir(parents=True, exist_ok=True)
RES = ROOT / "results"
KAPPA = 0.259; CAP = 6000; PMAX = 1500
t = pd.read_csv(RES / "trajectory_final.csv", parse_dates=["timestamp"])
t["lam"] = t.co2 + KAPPA * t.price; t["E1"] = t.soc_kwh_end


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf"); fig.savefig(FIG / f"{name}.png", dpi=150); plt.close(fig); print("fig", name)


# 1) one pseudo-test week
b = t[t.block == 8].reset_index(drop=True)
x = np.arange(len(b))
fig, ax = plt.subplots(4, 1, figsize=(7.0, 6.8), sharex=True, gridspec_kw={"height_ratios": [1.5, 1, 1, 1], "hspace": 0.4})
ax[0].plot(x, b.load_kw, color=BLUE, label="Demand $D_t$"); ax[0].plot(x, b.grid_kw, color=GREY, lw=1.1, label="Grid import with battery")
ax[0].plot(x, b.pv_kw, color=ORANGE, lw=1.3, label="Solar $S_t$ (×12)")
ax[0].fill_between(x, b.load_kw, b.pv_kw, where=b.pv_kw > b.load_kw, color=ORANGE, alpha=0.25, lw=0, label="surplus")
ax[0].set_ylim(bottom=0); ax[0].set_title("Power (kW)"); ax[0].legend(ncol=4, fontsize=7.5, loc="upper right")
ax[1].bar(x, b.u_applied_kw, color=np.where(b.u_applied_kw >= 0, VIOLET, RED), width=0.9); ax[1].axhline(0, color=AXES, lw=0.8)
ax[1].set_ylim(-PMAX * 1.05, PMAX * 1.05); ax[1].set_title("Set point $u_t$ (kW): charge (violet) / discharge (red)")
ax[2].fill_between(x, 0, b.E1, color=VIOLET, alpha=0.15, lw=0); ax[2].plot(x, b.E1, color=VIOLET); ax[2].set_ylim(0, CAP * 1.03)
ax[2].set_title("Stored energy $E_{t+1}$ (kWh)")
ax[3].plot(x, b.lam, color=INK, lw=1.4); ax[3].set_title("Real effective price $\\lambda_t$ (the agent only sees 3 h; it forecasts the rest)")
days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]; ticks = [i for i in range(len(b)) if b.timestamp.iloc[i].hour == 0]
ax[3].set_xticks(ticks); ax[3].set_xticklabels([f"{days[b.timestamp.iloc[i].dayofweek]} {b.timestamp.iloc[i].day}" for i in ticks])
for a in ax:
    for i in ticks: a.axvline(i - 0.5, color=GRID, lw=0.6)
fig.suptitle(f"Hard mode — pseudo-test week ({b.timestamp.iloc[0]:%d/%m/%Y} – {b.timestamp.iloc[-1]:%d/%m})", x=0.01, ha="left", fontsize=10, fontweight="bold")
save(fig, "week")

# 2) comparison / diagnosis
comp = json.loads((RES / "comparison.json").read_text(encoding="utf-8"))
comp = sorted([c for c in comp if c["score"] is not None], key=lambda r: r["score"])
fig, ax = plt.subplots(figsize=(7.0, 0.4 * len(comp) + 0.8))
cols = [INK if r.get("oracle") else (BLUE if r.get("final") else "#9ec5f4") for r in comp]
ax.barh([r["name"] for r in comp], [r["score"] for r in comp], color=cols, height=0.65)
for i, r in enumerate(comp): ax.text(r["score"] + 0.15, i, f'{r["score"]:.2f}', va="center", fontsize=8)
ax.set_xlim(0, max(r["score"] for r in comp) * 1.15); ax.set_title("Score on the pseudo-test, hard mode (1725 h)")
ax.grid(axis="y", visible=False); ax.grid(axis="x", color=GRID)
save(fig, "comparison")

# 3) ridge forecast error vs horizon
err = json.loads((RES / "predictors_error.json").read_text(encoding="utf-8"))["val"]
fig, ax = plt.subplots(1, 3, figsize=(7.0, 2.3), gridspec_kw={"wspace": 0.4})
for a, var, col, title in [(ax[0], "lam", INK, "$\\lambda$ (kg CO$_2$ eq/kWh)"), (ax[1], "D", BLUE, "$D$ (kW)"), (ax[2], "S", ORANGE, "$S$ ×12 (kW)")]:
    ks = sorted(int(k) for k in err[var]); a.plot(ks, [err[var][str(k)]["MAE_model"] for k in ks], "o-", color=col, label="ridge")
    a.plot(ks, [err[var][str(k)]["MAE_climatology"] for k in ks], "s--", color=GREY, label="climatology")
    a.set_title("MAE " + title); a.set_xlabel("hours ahead $k$"); a.set_ylim(bottom=0)
ax[0].legend(fontsize=7.5)
save(fig, "predictors")

# 4) surplus and battery usage
fig, ax = plt.subplots(1, 2, figsize=(7.0, 2.3), gridspec_kw={"wspace": 0.35})
n = t.load_kw - t.pv_kw
ax[0].hist(n, bins=50, color=BLUE, alpha=0.85); ax[0].axvline(0, color=RED, lw=1); ax[0].set_title("Net demand $D-S$ (kW), pseudo-test")
ax[0].set_xlabel("kW (negative = solar surplus)")
ax[1].hist(t.E1, bins=40, color=VIOLET, alpha=0.85); ax[1].set_title("Distribution of $E_{t+1}$ (kWh)"); ax[1].set_xlabel("kWh")
save(fig, "usage")
print("exported kWh:", round(t.export_kw.sum()), "| surplus hours:", int((n < 0).sum()),
      "| cycles/day:", round((-t.u_applied_kw[t.u_applied_kw < 0]).sum() / CAP / (len(t) / 24), 2))
