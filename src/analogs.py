"""
analogs.py — Forecasting by analogy (Nadaraya–Watson kernel regression): the k-hour-ahead forecast is the
average of what happened after the historical hours that "look like" the current state, weighted by similarity
    w_i = exp(-1/2 * sum_j ((f_j - f_ij) / h_j)^2),
where f are features observable in real time (last hour's weather, last hour's consumption and solar, anomalies
of the known effective price, month, day type) and h_j are per-feature bandwidths (the model "coefficients"),
fitted on TRAIN by coordinate descent to minimise the forecast error (excluding the hours within 3 days of the
query). Only hours with the same hour of day are compared.

    python src/analogs.py -> agent/analogs.json, results/analogs_error.json
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from hard_env import split_hard          # noqa: E402
import predictors as PR                   # noqa: E402

H = 24
FEATURES = ["weekend", "month_sin", "month_cos", "aD", "Dprev", "temp", "kt", "irr", "tpan", "Sprev", "lam0", "lam1", "lam2", "level"]
USE = {"D": ["weekend", "month_sin", "month_cos", "aD", "Dprev", "temp", "irr"],
       "S": ["month_sin", "month_cos", "kt", "irr", "tpan", "Sprev", "temp"],
       "lam": ["weekend", "month_sin", "month_cos", "lam0", "lam1", "lam2", "level", "temp", "irr"]}
VARS = ["D", "S", "lam"]


def tables(df):
    """Features and targets (H hours ahead) for every hour t, using only what is observable at t."""
    idx = df.index; n = len(idx)
    D = df.load_kw.to_numpy(); S = df.pv_kw.to_numpy(); lam = (df.co2_kg_per_kwh + PR.KAPPA * df.precio_eur_per_kwh).to_numpy()
    irr = df.irradiancia_wm2.to_numpy(); temp = df.temp_ambient_c.to_numpy(); tpan = df.temp_panel_c.to_numpy()
    cD = np.array([PR.clim(PR.D_HDM, t) for t in idx]); cS = np.array([PR.clim(PR.S_HDM, t) for t in idx]); cL = np.array([PR.clim_lam(t) for t in idx])
    contiguous = np.r_[False, (np.diff(idx.values).astype("timedelta64[h]").astype(int) == 1)]
    kt = np.ones(n); u = 1.0
    for i in range(n):
        if not contiguous[i]: u = 1.0
        if cS[i] > 30: u = float(np.clip(S[i] / cS[i], 0, 1.6))
        kt[i] = u
    F = np.full((n, len(FEATURES)), np.nan); T = {v: np.full((n, H), np.nan) for v in VARS}; hour = idx.hour.to_numpy()
    for i in range(1, n):
        if not contiguous[i] or i + 2 >= n or not (contiguous[i + 1] and contiguous[i + 2]):
            continue
        t = idx[i]; month = (t.month - 1) / 12 * 2 * np.pi
        lo = max(0, i - 21)   # last 24 known hours: t-21 .. t+2
        while lo < i and not contiguous[lo + 1]: lo += 1
        level = float(np.mean(lam[lo:i + 3] - cL[lo:i + 3]))
        F[i] = [float(t.dayofweek >= 5), np.sin(month), np.cos(month), D[i - 1] - cD[i - 1], D[i - 1], temp[i - 1], kt[i - 1], irr[i - 1], tpan[i - 1], S[i - 1],
                lam[i] - cL[i], lam[i + 1] - cL[i + 1], lam[i + 2] - cL[i + 2], level]
        for k in range(H):
            if i + k < n and (k == 0 or contiguous[i + k]):
                T["D"][i, k] = D[i + k]; T["S"][i, k] = S[i + k]; T["lam"][i, k] = lam[i + k]
            else:
                break
    ok = ~np.isnan(F).any(axis=1)
    return hour[ok], F[ok], {v: T[v][ok] for v in VARS}, idx[ok]


def predict(hq, Fq, tq, hb, Fb, Tb, tb, h_band, cols, exclude_days=0):
    """Analog forecast of Tb for every query (hq, Fq). h_band: bandwidths (in feature units) per column."""
    n_q = len(hq); out = np.full((n_q, H), np.nan)
    inv = np.array([0.0 if not np.isfinite(h) else 1.0 / h for h in h_band])
    by_hour = {h: np.where(hb == h)[0] for h in range(24)}
    for q in range(n_q):
        cand = by_hour[hq[q]]
        if exclude_days:
            cand = cand[np.abs((tb[cand] - tq[q]).total_seconds().to_numpy()) > exclude_days * 86400]
        if len(cand) == 0:
            continue
        d2 = (((Fb[cand][:, cols] - Fq[q, cols]) * inv) ** 2).sum(axis=1)
        w = np.exp(-0.5 * (d2 - d2.min()))
        Y = Tb[cand]; m = ~np.isnan(Y)
        num = (np.where(m, Y, 0) * w[:, None]).sum(axis=0); den = (m * w[:, None]).sum(axis=0)
        out[q] = np.where(den > 0, num / np.maximum(den, 1e-12), np.nan)
    return out


def mae(pred, target):
    m = ~np.isnan(pred) & ~np.isnan(target)
    return float(np.mean(np.abs(pred[m] - target[m])))


def fit_bandwidths(var, hq, Fq, Tq, tq, sd):
    """Coordinate descent over a grid of bandwidths (in standard deviations; inf switches the feature off)."""
    cols = [FEATURES.index(r) for r in USE[var]]
    grid = [np.inf, 0.15, 0.25, 0.5, 1.0, 2.0, 4.0]
    h = np.full(len(cols), 2.0)
    def cost(hv):
        return mae(predict(hq, Fq, tq, hq, Fq, Tq[var], tq, hv * sd[cols], cols, exclude_days=3), Tq[var])
    best = cost(h)
    for _ in range(2):
        for j in range(len(cols)):
            for c in grid:
                hv = h.copy(); hv[j] = c
                v = cost(hv)
                if v < best - 1e-9:
                    best, h = v, hv
        print(f"  {var}: train MAE (leave-3-days-out) {best:.4g} | bandwidths {dict(zip(USE[var], [None if not np.isfinite(x) else x for x in h]))}", flush=True)
    return h, best


def main():
    tr, va = split_hard()
    PR.CLIM_LAM_HWM = PR.clim_lam_table(tr)
    htr, Ftr, Ttr, ttr = tables(tr); hva, Fva, Tva, tva = tables(va)
    sd = np.nanstd(Ftr, axis=0); sd[sd == 0] = 1.0
    print(f"train {len(htr)} queries, val {len(hva)}")
    bandwidths = {}; err = {}
    for var in VARS:
        print("fitting", var)
        h, _ = fit_bandwidths(var, htr, Ftr, Ttr, ttr, sd)
        cols = [FEATURES.index(r) for r in USE[var]]
        pv = predict(hva, Fva, tva, htr, Ftr, Ttr[var], ttr, h * sd[cols], cols)
        err[var] = {"MAE_val_analog": mae(pv, Tva[var]), "MAE_val_by_k": [mae(pv[:, k], Tva[var][:, k]) for k in range(H)]}
        bandwidths[var] = {"features": USE[var], "h_std": [None if not np.isfinite(x) else float(x) for x in h], "sd": [float(s) for s in sd[cols]]}
        e = err[var]["MAE_val_by_k"]
        print(f"  {var}: val MAE analog {err[var]['MAE_val_analog']:.4g}  (k=0 {e[0]:.4g}, k=6 {e[6]:.4g}, k=23 {e[23]:.4g})", flush=True)
    # table shipped with the agent (full train set, rounded)
    def r(a, d): return [[None if np.isnan(x) else round(float(x), d) for x in row] for row in a]
    out = {"_meta": {"H": H, "features": FEATURES, "use": USE, "n": int(len(htr))}, "bandwidths": bandwidths,
           "hour": htr.tolist(), "F": r(Ftr, 3), "T": {v: r(Ttr[v], 4 if v == "lam" else 0) for v in VARS}}
    (ROOT / "agent" / (sys.argv[1] if len(sys.argv) > 1 else "analogs.json")).write_text(json.dumps(out), encoding="utf-8")
    (ROOT / "results" / "analogs_error.json").write_text(json.dumps(err, indent=1), encoding="utf-8")
    print("json written")


if __name__ == "__main__":
    main()
