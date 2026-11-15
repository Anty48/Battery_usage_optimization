"""
make_viewer.py — Injects a trajectory into the animated viewer template (self-contained HTML).

    python src/make_viewer.py [results/trajectory_final.csv] [viewer/viewer.html]
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
csv = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "trajectory_final.csv"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "viewer" / "viewer.html"
KAPPA = 0.259

t = pd.read_csv(csv)
r = lambda s, d=1: [round(float(v), d) for v in s]
blocks = []
for b, g in t.groupby("block", sort=True):
    g = g.sort_values("timestamp")
    blocks.append({
        "id": int(b), "t0": g["timestamp"].iloc[0], "n": int(len(g)),
        "ts": g["timestamp"].tolist(),
        "D": r(g["load_kw"]), "S": r(g["pv_kw"]), "pi": r(g["price"], 5), "c": r(g["co2"], 5),
        "u": r(g["u_applied_kw"]), "E": r(g["soc_kwh_start"]),
        "g": r(g["grid_kw"]), "gb": r(g["grid_base_kw"]), "ex": r(g["export_kw"]),
        "eu": r(g["cost_eur"], 3), "eub": r(g["cost_base_eur"], 3),
        "co2k": r(g["co2_kg"], 3), "co2b": r(g["co2_base_kg"], 3),
        "inf": [int(v) for v in g["violations"]],
    })
data = json.dumps({"kappa": KAPPA, "cap": 6000, "pmax": 1500, "source": csv.name, "blocks": blocks}, ensure_ascii=False, separators=(",", ":"))
data = data.replace("</", "<\\/")
html = (ROOT / "viewer" / "template.html").read_text(encoding="utf-8").replace("__DATA__", data)
out.write_text(html, encoding="utf-8")
print(f"{out} written: {len(html)/1024:.0f} KB, {len(blocks)} blocks, {len(t)} hours (data {len(data)/1024:.0f} KB)")
