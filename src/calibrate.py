"""
calibrate.py — Grid sweep of the controller knobs of the v3 agent on TRAIN (hard mode); val only reports.

    python src/calibrate.py -> results/calibration.json
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import importlib.util
import itertools
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))
from hard_env import split_hard, evaluate   # noqa: E402
from src.data import blocks                  # noqa: E402

spec = importlib.util.spec_from_file_location("agent_v3", ROOT / "agent" / "agent.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
tr, va = split_hard(); tr = pd.concat(blocks(tr))

configs = [dict(z_sigma=z, v_frac=1.0, eps_export=e) for z, e in itertools.product([0.0, 0.5, 1.0], [0.02, 0.06])]
configs += [dict(z_sigma=0.5, v_frac=0.6, eps_export=0.02), dict(z_sigma=0.5, v_frac=1.0, eps_export=0.02, no_prediction=True)]
rows = []
for cfg in configs:
    rt = evaluate(m.BatteryAgent(**cfg), tr); rv = evaluate(m.BatteryAgent(**cfg), va)
    row = dict(cfg, train=float(rt["score"]), val=float(rv["score"]), val_co2=float(rv["co2_pct"]), val_cost=float(rv["cost_pct"]),
               violations=int(rt["violations"] + rv["violations"]), t_val=rv["time_s"])
    rows.append(row); print(json.dumps(row), flush=True)
best = max(rows, key=lambda f: f["train"])
print("BEST (train):", json.dumps(best))
(ROOT / "results" / "calibration.json").write_text(json.dumps({"rows": rows, "best": best}, indent=1), encoding="utf-8")
