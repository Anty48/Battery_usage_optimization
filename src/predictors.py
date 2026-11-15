"""
predictors.py — Fits by regularised least squares (ridge) the 24 h-ahead predictors used by the hard-mode
agent and stores them in agent/predictors.json. Everything is fitted on train ONLY.

For every horizon k the variable is predicted as a linear combination of "features" that the agent can
compute in real time with the same formulas (mirrored line by line in agent/agent.py):

  lambda_{t+k}  ~  [1, clim_lam(t+k), anom_yesterday(t+k), anom_2days_ago(t+k), anom_last_known, anom_now, level_24h]
  D_{t+k}       ~  [1, clim_D(t+k), anom_D(t-1), anom_D_yesterday(t+k)]
  S_{t+k}       ~  [1, clim_S(t+k), clim_S(t+k)*kt_recent, clim_S(t+k)*kt_yesterday(t+k)]

where clim = historical mean (standard_mode/parameters.json, with pv x12), anom = value - clim and
kt = measured / climatological solar in the last daylight hour (clearness index).
It also stores the standard deviation of the error per horizon (used for the discharge safety margin).

    python src/predictors.py      -> agent/predictors.json + results/predictors_error.json
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from hard_env import split_hard, PV_SCALE   # noqa: E402

PARAM = json.loads((ROOT / "standard_mode" / "parameters.json").read_text(encoding="utf-8"))
KAPPA = 0.259
H = 36            # longest horizon fitted (the agent plans 24 h)
K_KNOWN = 3       # hours of market forecast revealed in hard mode
RIDGE = 1e-3


def table(name):
    return np.asarray(PARAM[name], dtype=float)


D_HDM = table("D_mean_hdm"); S_HDM = table("S_mean_hdm") * PV_SCALE
CLIM_LAM_H = table("c_profile_h") + KAPPA * table("pi_profile_h")


def clim_lam_table(df_train):
    """Lambda climatology by hour x (weekday/weekend) x month, shrunk towards hour x weekend (n0 = 5)."""
    lam = df_train.co2_kg_per_kwh + KAPPA * df_train.precio_eur_per_kwh
    h = df_train.index.hour; we = (df_train.index.dayofweek >= 5).astype(int); mo = df_train.index.month - 1
    t2 = np.zeros((24, 2)); t3 = np.zeros((24, 2, 12))
    for (hh, ff), v in lam.groupby([h, we]).mean().items():
        t2[hh, ff] = v
    g3 = lam.groupby([h, we, mo]); m3 = g3.mean(); n3 = g3.size()
    for hh in range(24):
        for ff in range(2):
            for mm in range(12):
                n = n3.get((hh, ff, mm), 0); v = m3.get((hh, ff, mm), t2[hh, ff])
                t3[hh, ff, mm] = (n * v + 5 * t2[hh, ff]) / (n + 5)
    return t3


CLIM_LAM_HWM = None


def clim_lam(ts):
    return float(CLIM_LAM_HWM[ts.hour, int(ts.dayofweek >= 5), ts.month - 1])


def clim(tab, ts):
    return tab[ts.hour, ts.dayofweek, ts.month - 1]


def build_samples(df):
    """For every hour t of df (never crossing a gap), returns features and targets for k = 0..H-1."""
    idx = df.index
    lam = (df.co2_kg_per_kwh + KAPPA * df.precio_eur_per_kwh).to_numpy()
    D = df.load_kw.to_numpy(); S = df.pv_kw.to_numpy()
    cD = np.array([clim(D_HDM, t) for t in idx]); cS = np.array([clim(S_HDM, t) for t in idx]); cL = np.array([clim_lam(t) for t in idx])
    pos = {t: i for i, t in enumerate(idx)}
    X = {v: [[] for _ in range(H)] for v in ("lam", "D", "S")}; Y = {v: [[] for _ in range(H)] for v in ("lam", "D", "S")}
    kt_rec = np.ones(len(idx))      # clearness index of the last daylight hour (<= 24 h back)
    last = 1.0
    for i, t in enumerate(idx):
        if i > 0 and (t - idx[i - 1]).total_seconds() > 7200:
            last = 1.0
        if cS[i] > 30.0:
            last = float(np.clip(S[i] / cS[i], 0.0, 1.6))
        kt_rec[i] = last
    for i, t in enumerate(idx):
        if i == 0:
            continue
        for k in range(0, H):          # k = 0: hour t itself (D and S are still unknown when deciding)
            tk = t + pd.Timedelta(hours=k); j = pos.get(tk)
            if j is None or j != i + k:        # target outside the series or across a gap
                break
            # lambda: last known hour = t+K_KNOWN-1 (hours up to it are known, not predicted)
            if k >= K_KNOWN:
                jk = i + K_KNOWN - 1
                anom = lam[jk] - cL[jk]
                jy = pos.get(tk - pd.Timedelta(hours=24)); jy2 = pos.get(tk - pd.Timedelta(hours=48))
                a_y = (lam[jy] - cL[jy]) if jy is not None else 0.0
                a_y2 = (lam[jy2] - cL[jy2]) if jy2 is not None else 0.0
                an1 = lam[i] - cL[i]
                lo = max(0, jk - 23)
                level = float(np.mean(lam[lo:jk + 1] - cL[lo:jk + 1])) if (idx[jk] - idx[lo]).total_seconds() <= 24 * 3600 else anom
                X["lam"][k].append([1.0, cL[j], a_y, a_y2, anom, an1, level]); Y["lam"][k].append(lam[j])
            # demand: anomaly of the previous hour (t-1) and of yesterday at the same hour
            jy = pos.get(tk - pd.Timedelta(hours=24))
            aD = D[i - 1] - cD[i - 1]; aD_y = (D[jy] - cD[jy]) if jy is not None else 0.0
            X["D"][k].append([1.0, cD[j], aD, aD_y]); Y["D"][k].append(D[j])
            kt_y = (S[jy] / cS[jy]) if (jy is not None and cS[jy] > 30) else kt_rec[i - 1]
            X["S"][k].append([1.0, cS[j], cS[j] * kt_rec[i - 1], cS[j] * float(np.clip(kt_y, 0, 1.6))]); Y["S"][k].append(S[j])
    return X, Y


def fit(X, Y):
    coef, sigma = {}, {}
    for v in X:
        coef[v], sigma[v] = [], []
        for k in range(H):
            if len(X[v][k]) < 50:
                coef[v].append(None); sigma[v].append(None); continue
            A = np.asarray(X[v][k]); y = np.asarray(Y[v][k])
            w = np.linalg.solve(A.T @ A + RIDGE * np.eye(A.shape[1]) * len(A), A.T @ y)
            coef[v].append(w.tolist()); sigma[v].append(float(np.std(y - A @ w)))
    return coef, sigma


def error(X, Y, coef):
    out = {}
    for v in X:
        out[v] = {}
        for k in (1, 3, 6, 12, 23):
            if k >= H or coef[v][k] is None or not X[v][k]:
                continue
            A = np.asarray(X[v][k]); y = np.asarray(Y[v][k]); w = np.asarray(coef[v][k])
            out[v][k] = {"MAE_model": float(np.mean(np.abs(y - A @ w))), "MAE_climatology": float(np.mean(np.abs(y - A[:, 1])))}
    return out


def main():
    global CLIM_LAM_HWM
    tr, va = split_hard()
    CLIM_LAM_HWM = clim_lam_table(tr)
    Xtr, Ytr = build_samples(tr); Xva, Yva = build_samples(va)
    coef, sigma = fit(Xtr, Ytr)
    err = {"train": error(Xtr, Ytr, coef), "val": error(Xva, Yva, coef)}
    for v in err["val"]:
        for k, e in err["val"][v].items():
            print(f"{v:3s} k={k:2d}  MAE model {e['MAE_model']:.4g}   climatology {e['MAE_climatology']:.4g}")
    out = {"_meta": {"H": H, "K_known": K_KNOWN, "kappa": KAPPA, "pv_scale": PV_SCALE, "ridge": RIDGE,
                     "features": {"lam": "[1, clim_lam_hwm, anom_yesterday, anom_2days_ago, anom_last_known, anom_now, level_24h]",
                                  "D": "[1, clim_D, anom_D(t-1), anom_D_yesterday]",
                                  "S": "[1, clim_S, clim_S*kt_recent, clim_S*kt_yesterday]"}},
           "coef": coef, "sigma": sigma, "clim_lam_h": CLIM_LAM_H.tolist(), "clim_lam_hwm": CLIM_LAM_HWM.tolist(),
           "D_mean_hdm": D_HDM.tolist(), "S_mean_hdm_x12": S_HDM.tolist()}
    (ROOT / "agent").mkdir(exist_ok=True)
    (ROOT / "agent" / "predictors.json").write_text(json.dumps(out), encoding="utf-8")
    (ROOT / "results" / "predictors_error.json").write_text(json.dumps(err, indent=1), encoding="utf-8")
    print("predictors.json:", (ROOT / "agent" / "predictors.json").stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
