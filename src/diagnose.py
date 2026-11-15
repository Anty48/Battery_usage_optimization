"""
diagnose.py — Where does the gap to the oracle come from? Inside the v3 agent (24 h receding horizon) the
forecast of lambda, of the net demand, or of both is replaced by the TRUTH (taken from the data itself).

    python src/diagnose.py -> results/diagnosis.json
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from hard_env import split_hard, evaluate   # noqa: E402

spec = importlib.util.spec_from_file_location("agent_v3", ROOT / "agent" / "agent.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
_, va = split_hard()
KAPPA = 0.259
HOUR_NS = 3_600_000_000_000
truth = {"lam": (va.co2_kg_per_kwh + KAPPA * va.precio_eur_per_kwh), "D": va.load_kw, "S": va.pv_kw}
truth = {v: {int(pd.Timestamp(ts).value // HOUR_NS): float(x) for ts, x in s.items()} for v, s in truth.items()}


class Omniscient(m.BatteryAgent):
    """The agent's forecasts of the variables in TRUTH are replaced by their real values (the agent passes
    the target hour t as an integer hour index)."""
    TRUTH = ()

    def _pred(self, var, k, features, default, t=None):
        if var in self.TRUTH and t is not None and t in truth[var]:
            return truth[var][t]
        return super()._pred(var, k, features, default, t)

    def _sig(self, var, k):
        return 0.0 if var in self.TRUTH else super()._sig(var, k)

    def _analog(self, var, hour, feats, H):
        return None if var in self.TRUTH else super()._analog(var, hour, feats, H)


out = {}
for name, V in [("forecast (v3)", ()), ("perfect lambda", ("lam",)), ("perfect net demand", ("D", "S")), ("everything perfect (24 h)", ("lam", "D", "S"))]:
    Omniscient.TRUTH = V
    r = evaluate(Omniscient(), va)
    out[name] = {k: float(v) if isinstance(v, (int, float, np.floating)) else v for k, v in r.items()}
    print(f"{name:26s} score={r['score']}  co2={r['co2_pct']}  cost={r['cost_pct']}  violations={r['violations']}", flush=True)
(ROOT / "results" / "diagnosis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
