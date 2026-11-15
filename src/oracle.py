"""
oracle.py — Upper bound of the hard mode: one global LP with perfect information (real D, S, pi, c) and the
import variable g = max(N+u, 0). Also the same oracle with the standard battery (2 MWh / 500 kW), to see how
much of the margin comes from the battery size.

    python src/oracle.py -> results/oracle.json, results/trajectory_oracle.csv
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from hard_env import split_hard, evaluate, SPEC_HARD   # noqa: E402

ETA = 0.9 ** 0.5; KAPPA = 0.259


def lp_global(lam, N, cap, pmax, soc0):
    H = len(lam); L = np.tril(np.ones((H, H)))
    A_E = np.hstack([ETA * L, -L / ETA, np.zeros((H, H))]); A_g = np.hstack([np.eye(H), -np.eye(H), -np.eye(H)])
    A_ub = np.vstack([A_E, -A_E, A_g]); b_ub = np.concatenate([np.full(H, cap - soc0), np.full(H, soc0), -N])
    cost = np.concatenate([np.zeros(H), np.full(H, 1e-6), lam])
    bounds = [(0, pmax)] * H + [(0, pmax)] * H + [(0, None)] * H
    res = linprog(cost, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    return res.x[:H] - res.x[H:2 * H]


class Plan:
    """Replays a precomputed set-point sequence with the exact physical clamp."""
    def __init__(self, u): self.u, self.i = u, 0

    def act(self, obs):
        soc = float(obs["soc_kwh"]); cap = float(obs["cap_max_kwh"]); p = float(obs["power_max_kw"])
        u = float(self.u[self.i]); self.i += 1
        return float(max(-max(0, min(p, soc * ETA - 1e-4)), min(max(0, min(p, (cap - soc) / ETA - 1e-4)), u)))


def main():
    _, va = split_hard()
    lam = (va.co2_kg_per_kwh + KAPPA * va.precio_eur_per_kwh).to_numpy(); N = (va.load_kw - va.pv_kw).to_numpy()
    out = {}
    u = lp_global(lam, N, SPEC_HARD["capacity_kwh"], SPEC_HARD["power_kw"], 3000.0)
    r = evaluate(Plan(u), va, trajectory=ROOT / "results" / "trajectory_oracle.csv"); out["global_oracle"] = r; print("global oracle", r)
    u = lp_global(lam, N, 2000.0, 500.0, 1000.0)
    spec = dict(SPEC_HARD, capacity_kwh=2000.0, power_kw=500.0)
    r = evaluate(Plan(u), va, spec=spec); out["oracle_standard_battery"] = r; print("oracle with 2 MWh / 500 kW", r)
    (ROOT / "results" / "oracle.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
