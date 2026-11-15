"""
hard_env.py — Hard mode, locally: data (pv x12 + hourly weather), a simulator that reveals only 3 h of market
forecast and puts the weather in obs, and normal / strict evaluation with the official score formula.

    from hard_env import load_hard, split_hard, SPEC_HARD, HardEnv, evaluate
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent            # src/
ROOT = HERE.parent                                 # repository root
sys.path.insert(0, str(ROOT))
from src.data import load_hourly, is_pseudotest, blocks          # noqa: E402
from starter_kit.environment import CampusBatteryEnv              # noqa: E402

PV_SCALE = 12.0
SPEC_HARD = {"capacity_kwh": 6000.0, "power_kw": 1500.0, "efficiency": 0.90, "soc_init": 0.50,
             "soc_min": 0.0, "soc_max": 1.0, "dt_hours": 1.0, "forecast_horizon": 3}
CACHE = ROOT / "results" / "cache" / "hourly_hard.pkl"
WEATHER = {"irradiancia_wm2": "Atersa - IRRADIANCIA (W/m2)",
           "temp_ambient_c": "Atersa - TEMPERATURA AMBIENTE (SENSOR 1) (ºC)",
           "temp_panel_c": "Atersa - TEMPERATURA PANEL (SENSOR 1) (ºC)",
           "vent_ms": "Atersa - VELOCIDAD VIENTO (SENSOR 1) (m/s)"}


def load_hard(force=False) -> pd.DataFrame:
    """Official hourly table with pv_kw x12 and the 4 weather variables (hourly mean). Index: Fecha."""
    if CACHE.exists() and not force:
        return pd.read_pickle(CACHE)
    df = load_hourly().copy()
    df["pv_kw"] = df["pv_kw"] * PV_SCALE
    m = pd.read_csv(ROOT / "data" / "train" / "meteo.csv", parse_dates=["Fecha"], low_memory=False, encoding="utf-8").set_index("Fecha")
    cols = {}
    for k, c in WEATHER.items():
        c2 = c if c in m.columns else [x for x in m.columns if c.split(" - ")[1].split(" (")[0] in x][0]
        cols[k] = pd.to_numeric(m[c2], errors="coerce").resample("1h").mean()
    df = df.join(pd.DataFrame(cols))
    for k in WEATHER:
        df[k] = df[k].interpolate(limit=3).fillna(0.0)
    df["irradiancia_wm2"] = df["irradiancia_wm2"].clip(lower=0)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(CACHE)
    return df


def split_hard(df=None):
    """(train, val) with the same calendar split as src/data.py."""
    df = load_hard() if df is None else df
    m = is_pseudotest(df.index).values
    return df[~m].copy(), df[m].copy()


class HardEnv(CampusBatteryEnv):
    """Official simulator + hard-mode obs (3 h horizon, weather, cap_max_kwh, power_max_kw)."""
    def _get_obs(self):
        obs = super()._get_obs()
        if obs is None:
            return None
        h = int(self.spec.get("forecast_horizon", 24))
        obs["preus_properes_24h"] = obs["preus_properes_24h"][:h]
        obs["co2_properes_24h"] = obs["co2_properes_24h"][:h]
        i = self.t - 1 if self.t > 0 else self.t
        row = self.df.iloc[i]
        nd = obs.setdefault("noves_dades_5min", {})
        for k in WEATHER:
            nd[k] = float(row[k]) if k in self.df.columns else 0.0
        obs["cap_max_kwh"] = float(self.cap)
        obs["power_max_kw"] = float(self.power)
        return obs


def _totals(env, b):
    g = np.asarray(env.grid); pr = b["precio_eur_per_kwh"].to_numpy(); co = b["co2_kg_per_kwh"].to_numpy()
    gb = np.maximum(b["load_kw"].to_numpy() - b["pv_kw"].to_numpy(), 0.0)
    return float((g * co).sum()), float((g * pr).sum()), float((gb * co).sum()), float((gb * pr).sum())


def evaluate(agent, df, strict=False, spec=None, trajectory=None):
    """Official score over df (concatenated blocks). strict=True: one env per block, SOC carried over and
    the market forecast truncated at the end of each block."""
    spec = dict(spec or SPEC_HARD)
    t0 = time.perf_counter()
    tot = np.zeros(4); violations = 0; rows = []
    parts = blocks(df) if strict else [df]
    soc = spec["soc_init"] * spec["capacity_kwh"]
    for b in parts:
        s = dict(spec); s["soc_init"] = soc / spec["capacity_kwh"]
        env = HardEnv(b, spec=s)
        obs = env.reset(); done = False
        while not done:
            obs, done = env.step(agent.act(obs))
        tot += np.array(_totals(env, b)); violations += env.clipped + env.violations; soc = env.soc
        if trajectory is not None:
            soc_start = np.concatenate([[s["soc_init"] * spec["capacity_kwh"]], np.asarray(env.soc_series[:-1])])
            rows.append(pd.DataFrame({"timestamp": b.index, "load_kw": b.load_kw.values, "pv_kw": b.pv_kw.values,
                                      "price": b.precio_eur_per_kwh.values, "co2": b.co2_kg_per_kwh.values,
                                      "u_kw": env.actions, "soc_kwh_start": soc_start, "soc_kwh_end": env.soc_series,
                                      "grid_kw": env.grid, "export_kw": env.exports,
                                      "grid_base_kw": np.maximum(b.load_kw.values - b.pv_kw.values, 0)}))
    gc, gp, bc, bp = tot
    d_c = 100 * (bc - gc) / bc; d_p = 100 * (bp - gp) / bp
    res = dict(score=round(max(0.0, 0.7 * d_c + 0.3 * d_p - 0.2 * violations), 2), co2_pct=round(d_c, 2), cost_pct=round(d_p, 2),
               violations=int(violations), hours=int(len(df)), time_s=round(time.perf_counter() - t0, 1), strict=strict)
    if trajectory is not None:
        t = pd.concat(rows, ignore_index=True)
        t["block"] = (t.timestamp.diff().dt.total_seconds().div(3600).fillna(1) > 2).cumsum() + 1
        t["hour"] = t.timestamp.dt.hour; t["day_of_week"] = t.timestamp.dt.dayofweek
        dE = t.soc_kwh_end - t.soc_kwh_start
        t["u_applied_kw"] = np.where(dE >= 0, dE / 0.9 ** 0.5, dE * 0.9 ** 0.5)
        t["cost_eur"] = t.grid_kw * t.price; t["cost_base_eur"] = t.grid_base_kw * t.price
        t["co2_kg"] = t.grid_kw * t.co2; t["co2_base_kg"] = t.grid_base_kw * t.co2; t["violations"] = 0
        t.to_csv(trajectory, index=False)
    return res


if __name__ == "__main__":
    df = load_hard(force=True)
    tr, va = split_hard(df)
    print(df[["load_kw", "pv_kw", "irradiancia_wm2", "temp_ambient_c"]].describe().round(1))
    n = df.load_kw - df.pv_kw
    print(f"hours with surplus (S>D): {(n < 0).sum()} of {len(df)} ({100*(n<0).mean():.1f}%) | mean surplus in those hours {(-n[n<0]).mean():.0f} kW, max {(-n).max():.0f} kW")
    print(f"net demand: p10 {n.quantile(.1):.0f}, median {n.median():.0f}, p90 {n.quantile(.9):.0f} kW")

    class NoBattery:
        def act(self, obs): return 0.0
    print("no battery:", evaluate(NoBattery(), va))
