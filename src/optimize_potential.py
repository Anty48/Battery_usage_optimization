"""
optimize_potential.py — Continuous optimisation of the v3 agent coefficients by maximising a POTENTIAL:

    Phi(theta) = mean official Score over a set of scenarios
               = { real pseudo-test weeks } U { randomly perturbed weeks }

theta = (z_sigma, v_frac, eps_export, alpha_D, alpha_S, alpha_lam, bw_scale_S, bw_scale_lam)

Each worker takes the best known theta (results/opt/best.json) plus a jitter, samples scenarios with its own
seed, runs Nelder–Mead on -Phi and evaluates the optimum on the 12 real weeks; if it beats the record, it is
written to best.json. Repeats until --minutes run out.

    python src/optimize_potential.py --seed 1 --minutes 40 [--perfect]
--perfect: the agent receives the REAL lambda, D and S (no forecasting) and only z, V, eps are optimised:
           the ceiling of the controller when "we know how the day will go".
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import importlib.util
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))
from hard_env import split_hard, evaluate   # noqa: E402
from src.data import blocks                  # noqa: E402

OPT = ROOT / "results" / "opt"; OPT.mkdir(parents=True, exist_ok=True)
NAMES = ["z_sigma", "v_frac", "eps_export", "alpha_D", "alpha_S", "alpha_lam", "bw_scale_S", "bw_scale_lam"]
LIM = np.array([[0.0, 2.0], [0.0, 2.0], [0.0, 0.10], [0.0, 1.0], [0.0, 1.0], [0.0, 1.0], [0.3, 3.0], [0.3, 3.0]])
THETA0 = np.array([0.5, 1.0, 0.02, 1.0, 0.0, 0.0, 1.0, 1.0])
KAPPA = 0.259
HOUR_NS = 3_600_000_000_000


def load_agent_class():
    spec = importlib.util.spec_from_file_location("agent_v3", ROOT / "agent" / "agent.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.BatteryAgent


def kwargs_of(theta):
    t = np.clip(theta, LIM[:, 0], LIM[:, 1])
    return dict(z_sigma=float(t[0]), v_frac=float(t[1]), eps_export=float(t[2]),
                alpha={"D": float(t[3]), "S": float(t[4]), "lam": float(t[5])}, bw_scale={"D": 1.0, "S": float(t[6]), "lam": float(t[7])})


def perturb(b, rng):
    """An 'odd' week built from a real one: random levels, autocorrelated noise, per-day clouds, sensor drop-outs."""
    b = b.copy(); n = len(b)
    ar = np.zeros(n); e = rng.normal(0, 1, n)
    for i in range(1, n): ar[i] = 0.9 * ar[i - 1] + e[i]
    ar /= max(ar.std(), 1e-6)
    fD = rng.lognormal(0, 0.12); b["load_kw"] = np.clip(b.load_kw * fD * (1 + 0.08 * ar), 0, 5000)
    if rng.random() < 0.3:                                   # sensor drop-out / closure: 6-12 h of low demand
        i0 = rng.integers(0, n - 12); L = rng.integers(6, 13); b.iloc[i0:i0 + L, b.columns.get_loc("load_kw")] *= 0.3
    day = (np.arange(n) // 24); f_day = rng.uniform(0.45, 1.2, day.max() + 1)[day]
    fS = rng.uniform(0.7, 1.25); b["pv_kw"] = b.pv_kw * fS * f_day
    if "irradiancia_wm2" in b: b["irradiancia_wm2"] = b.irradiancia_wm2 * fS * f_day
    if "temp_ambient_c" in b: b["temp_ambient_c"] = b.temp_ambient_c + rng.normal(0, 3)
    if "temp_panel_c" in b: b["temp_panel_c"] = b.temp_panel_c + rng.normal(0, 4)
    b["precio_eur_per_kwh"] = np.clip(b.precio_eur_per_kwh * rng.lognormal(0, 0.15) * (1 + 0.10 * ar) + rng.normal(0, 0.01), 0.001, None)
    b["co2_kg_per_kwh"] = np.clip(b.co2_kg_per_kwh * rng.lognormal(0, 0.10) * (1 + 0.08 * np.roll(ar, 5)), 0.01, None)
    return b


class Omniscient:
    """Wrapper: the agent receives the truth (lambda, D, S) of the week being simulated."""
    def __init__(self, Agent, df, **kw):
        self.a = Agent(**kw)
        self.a.ALPHA = {"D": 1.0, "S": 1.0, "lam": 1.0}
        truth = {"lam": (df.co2_kg_per_kwh + KAPPA * df.precio_eur_per_kwh).to_dict(), "D": df.load_kw.to_dict(), "S": df.pv_kw.to_dict()}
        # the agent passes the target hour as an integer hour index
        truth = {var: {int(pd.Timestamp(ts).value // HOUR_NS): val for ts, val in d.items()} for var, d in truth.items()}

        def _pred(var, k, features, default, t=None):
            return float(truth[var][t]) if (t is not None and t in truth[var]) else default

        def _sig(var, k): return 0.0
        self.a._pred = _pred; self.a._sig = _sig

    def act(self, obs): return self.a.act(obs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--n_real", type=int, default=4); ap.add_argument("--n_pert", type=int, default=4)
    ap.add_argument("--maxfev", type=int, default=30); ap.add_argument("--perfect", action="store_true")
    a = ap.parse_args()
    Agent = load_agent_class()
    _, va = split_hard(); blq = [b for b in blocks(va) if len(b) >= 100]
    rng = np.random.default_rng(a.seed)
    best_path = OPT / ("best_perfect.json" if a.perfect else "best.json")
    log_path = OPT / f"worker_{'perfect_' if a.perfect else ''}{a.seed}.jsonl"
    t_end = time.time() + a.minutes * 60
    it = 0

    def run(theta, df):
        kw = kwargs_of(theta)
        ag = Omniscient(Agent, df, **kw) if a.perfect else Agent(**kw)
        return float(evaluate(ag, df)["score"])

    def real_score(theta):
        return run(theta, va)      # official score over the 12 concatenated weeks (as the server does)

    while time.time() < t_end:
        it += 1
        scen = [blq[i] for i in rng.choice(len(blq), min(a.n_real, len(blq)), replace=False)]
        if not a.perfect:
            scen += [perturb(blq[i], rng) for i in rng.choice(len(blq), a.n_pert, replace=True)]
        # starting point: global record + jitter
        best = json.loads(best_path.read_text(encoding="utf-8")) if best_path.exists() else None
        x0 = np.array(best["theta"]) if best else THETA0.copy()
        x0 = np.clip(x0 + rng.normal(0, 0.08, len(x0)) * (LIM[:, 1] - LIM[:, 0]) * (it > 1 or best is not None), LIM[:, 0], LIM[:, 1])
        free = [0, 1, 2] if a.perfect else list(range(len(NAMES)))
        history = []

        def f(xl):
            x = x0.copy(); x[free] = xl; x = np.clip(x, LIM[:, 0], LIM[:, 1])
            phi = float(np.mean([run(x, d) for d in scen]))
            history.append({"theta": x.tolist(), "phi": phi}); return -phi

        t0 = time.time()
        res = minimize(f, x0[free], method="Nelder-Mead", options=dict(maxfev=a.maxfev, xatol=1e-3, fatol=1e-3))
        x = x0.copy(); x[free] = res.x; x = np.clip(x, LIM[:, 0], LIM[:, 1])
        sr = real_score(x)
        best = json.loads(best_path.read_text(encoding="utf-8")) if best_path.exists() else None
        rec = {"iter": it, "seed": a.seed, "phi": -float(res.fun), "real_score": sr, "theta": x.tolist(), "names": NAMES,
               "n_eval": len(history), "minutes": round((time.time() - t0) / 60, 1), "perfect": a.perfect}
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        if best is None or sr > best["real_score"] + 1e-9:
            best_path.write_text(json.dumps(dict(rec, kwargs=kwargs_of(x)), indent=1), encoding="utf-8")
            print(f"[seed {a.seed} it {it}] NEW RECORD real_score={sr:.3f} phi={-res.fun:.3f} theta={np.round(x, 3).tolist()}", flush=True)
        else:
            print(f"[seed {a.seed} it {it}] real_score={sr:.3f} (record {best['real_score']:.3f}) phi={-res.fun:.3f}", flush=True)


if __name__ == "__main__":
    main()
