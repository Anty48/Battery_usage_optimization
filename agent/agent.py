"""
agent.py — LP-MPC battery agent with forecasting (model v3; built for the hard mode, also runs in standard mode).

What it does every hour
-----------------------
1. Reads the stored energy E_t, the timestamp, the battery limits carried by obs (cap_max_kwh, power_max_kw;
   2000 kWh / 500 kW if missing) and last hour's telemetry (consumption and solar). Keeps a 48 h history
   (indexed by integer hour) to look up "yesterday / the day before at this hour".
2. Effective price lambda = c + kappa*pi over the K known hours (3 in hard mode, 24 in standard mode) and a
   linear FORECAST (coefficients fitted on train, predictors.json) for the rest of the horizon:
     lambda_{t+k} ~ [1, clim(h, weekend, month), anom_yesterday, anom_2days_ago, anom_last_known, anom_now, level_24h]
2b. ANALOG forecast (analogs.json): average of the historical trajectories of lambda and S weighted by how
    similar the current state is (weather, consumption, solar, known lambda anomalies, month, day type),
    w_i = exp(-1/2 sum_j ((f_j - f_ij)/h_j)^2). It is blended with the ridge forecast with weights ALPHA per variable.
3. Forecast of demand D and solar S for k = 0..H-1:
     D_{t+k} ~ [1, clim_D(h, dow, month), anom_D(t-1), anom_D_yesterday]
     S_{t+k} ~ [1, clim_S, clim_S*kt_recent, clim_S*kt_yesterday]   (kt = clearness index measured/climatology)
4. Linear program with variables u+ (charge), u- (discharge) and g (grid import):
       min  sum_k lambda_k g_k + eps*u-_k - V*E_H
       s.t. g_k >= N_k + u+_k - u-_k, g_k >= 0      (exporting neither costs nor saves: g = max(N+u, 0))
            0 <= E_k <= cap, 0 <= u+ <= P, 0 <= u- <= min(P, max(0, N_k - z*sigma_k))
   N_k = D_k - S_k forecast (negative = free solar surplus); sigma_k = std of the k-hour forecast error
   (the z*sigma margin protects the "odd" days on which the real demand turns out lower).
5. Applies u_0 clipped with the exact physical formula of the simulator (zero violations).

Rules: only numpy, pandas (Timestamp), scipy, json, math, pathlib, typing; paths relative to __file__.
"""
import json
import math
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.optimize import linprog

_H_NS = 3_600_000_000_000  # nanoseconds per hour


class BatteryAgent:
    # ---- control parameters (chosen with src/optimize_potential.py; see report section 6) ----
    H = 24            # planning horizon (hours)
    V_FRAC = 1.1113630802705314      # terminal value of stored energy = V_FRAC * mean daily lambda
    Z_SIGMA = 0.4207876895293239     # discharge safety margin, in standard deviations of the forecast error
    EPS_EXPORT = 0.018284408880563575 # small cost per discharged kWh (fraction of mean lambda) to avoid wasting energy
    KAPPA = 0.259
    NO_PREDICTION = False   # True = climatology only (to measure what forecasting is worth)
    ALPHA = {"D": 1.0, "S": 0.0007, "lam": 0.0402}     # ridge weight in the ridge/analog blend (1 = ridge only; 0 = analog only)
    BW_SCALE = {"D": 1.0, "S": 0.9606, "lam": 0.9279}  # scale factor of the analog bandwidths (>1 = smoother)

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k.upper(), v)
        self.eta = 0.9 ** 0.5
        self.eps = 1e-4
        p = json.loads((Path(__file__).parent / "predictors.json").read_text(encoding="utf-8"))
        self.coef = {v: [np.asarray(w, dtype=float) if w is not None else None for w in ws] for v, ws in p["coef"].items()}
        self.sigma = {v: [float(s) if s is not None else 0.0 for s in ss] for v, ss in p["sigma"].items()}
        clim_h = np.asarray(p["clim_lam_h"], dtype=float)
        self.clim_lam_hwm = np.asarray(p.get("clim_lam_hwm", np.tile(clim_h[:, None, None], (1, 2, 12))), dtype=float)
        self.D_hdm = np.asarray(p["D_mean_hdm"], dtype=float)
        self.S_hdm12 = np.asarray(p["S_mean_hdm_x12"], dtype=float)
        self.pv_scale_fit = float(p["_meta"].get("pv_scale", 12.0))
        self.Hfit = int(p["_meta"]["H"])
        self.lam_mean = float(np.mean(clim_h))
        self.hist: Dict[int, Dict[str, float]] = {}      # integer hour -> {lam, D, S}
        self.kt = 1.0
        self.last_t: Optional[int] = None
        self.counter = 0
        self.LT = np.tril(np.ones((int(self.H), int(self.H))))
        self.ana = None
        path = Path(__file__).parent / "analogs.json"
        if path.exists():
            a = json.loads(path.read_text(encoding="utf-8"))
            F = np.array([[np.nan if x is None else x for x in f] for f in a["F"]], dtype=float)
            hour = np.asarray(a["hour"], dtype=int)
            self.ana = {"features": a["_meta"]["features"], "by_hour": {h: np.where(hour == h)[0] for h in range(24)}, "F": F,
                        "T": {v: np.array([[np.nan if x is None else x for x in f] for f in a["T"][v]], dtype=float) for v in a["T"]},
                        "cols": {}, "inv": {}}
            for v, spec in a["bandwidths"].items():
                cols = [a["_meta"]["features"].index(r) for r in spec["features"]]
                inv = np.array([0.0 if h is None else 1.0 / (h * sd) for h, sd in zip(spec["h_std"], spec["sd"])])
                self.ana["cols"][v] = np.array(cols); self.ana["inv"][v] = inv

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _as_list(x, n_max=24) -> List[float]:
        out = []
        try:
            for v in list(x)[:n_max]:
                v = float(v)
                if not math.isfinite(v):
                    break
                out.append(v)
        except Exception:
            return []
        return out

    def _pred(self, var, k, features, default, t=None):
        if self.NO_PREDICTION:
            return default
        ws = self.coef[var]
        kk = min(k, self.Hfit - 1)
        w = ws[kk] if kk < len(ws) else None
        if w is None and var != "lam" and len(ws) > 1:
            w = ws[1]
        if w is None or len(w) != len(features):
            return default
        return float(np.dot(w, features))

    def _analog(self, var, hour, feats, H):
        """Average of the historical trajectories of `var` weighted by their similarity to the current state."""
        if self.ana is None or var not in self.ana["cols"]:
            return None
        cand = self.ana["by_hour"][hour]
        if len(cand) == 0:
            return None
        cols = self.ana["cols"][var]; inv = self.ana["inv"][var] / max(1e-3, float(self.BW_SCALE.get(var, 1.0)))
        fq = np.array([feats[r] for r in self.ana["features"]], dtype=float)[cols]
        d2 = (((self.ana["F"][cand][:, cols] - fq) * inv) ** 2).sum(axis=1)
        w = np.exp(-0.5 * (d2 - d2.min()))
        Y = self.ana["T"][var][cand][:, :H]; m = ~np.isnan(Y)
        num = (np.where(m, Y, 0.0) * w[:, None]).sum(axis=0); den = (m * w[:, None]).sum(axis=0)
        return np.where(den > 0, num / np.maximum(den, 1e-12), np.nan)

    def _sig(self, var, k):
        ss = self.sigma[var]
        kk = min(k, self.Hfit - 1)
        return ss[kk] if kk < len(ss) else 0.0

    def _calendar(self, ts: pd.Timestamp, n_days: int):
        """(dow, month) of today, tomorrow, ... with only n_days date operations."""
        base = ts.normalize()
        out = []
        for d in range(n_days):
            td = base + pd.Timedelta(days=d)
            out.append((td.dayofweek, td.month - 1))
        return out

    # ------------------------------------------------------------------ policy
    def act(self, obs: dict) -> float:
        self.counter += 1
        cap = float(obs.get("cap_max_kwh") or 2000.0)
        pmax = float(obs.get("power_max_kw") or 500.0)
        soc = float(obs.get("soc_kwh", 0.5 * cap))
        if not math.isfinite(soc):
            soc = 0.5 * cap
        soc = min(max(soc, 0.0), cap)
        s_div = self.pv_scale_fit if cap < 5000 else 1.0   # S tables are stored at x12 scale

        # --- robust timestamp (Timestamp, str or missing) ---
        ts = None
        try:
            raw = obs.get("timestamp")
            ts = pd.Timestamp(raw) if raw is not None else None
        except Exception:
            ts = None
        if ts is None:
            h = int(obs.get("hour", 12)) % 24; d = int(obs.get("day_of_week", 0)) % 7
            ts = pd.Timestamp("2026-06-01") + pd.Timedelta(days=d, hours=h)   # 1 June 2026 is a Monday
        t0 = int(ts.value // _H_NS)
        if self.last_t is not None and abs(t0 - self.last_t) > 2:
            self.kt = 1.0                     # time jump: forget the recent clearness index
        self.last_t = t0
        hour0 = ts.hour
        H = int(self.H)
        cal = self._calendar(ts, (hour0 + H + 1) // 24 + 1)
        past = self._calendar(ts - pd.Timedelta(days=2), 2)   # two days ago, yesterday (for past climatologies)

        def dm(k):            # (hour, dow, month) of t+k, k >= -48
            hh = hour0 + k
            if hh >= 0:
                dd, mm = cal[hh // 24]
            else:
                dd, mm = past[2 + (hh // 24)] if hh >= -48 else cal[0]
            return hh % 24, dd, mm

        # --- last hour's telemetry -> history ---
        nd = obs.get("noves_dades_5min") or {}
        try:
            D_prev = float(nd.get("ultim_consum_kw")); S_prev = float(nd.get("ultima_solar_kw", 0.0) or 0.0)
            if math.isfinite(D_prev) and math.isfinite(S_prev):
                self.hist.setdefault(t0 - 1, {}).update({"D": D_prev, "S": S_prev})
                h1, d1, m1 = dm(-1)
                cSp = self.S_hdm12[h1, d1, m1] / s_div
                if cSp > 30.0 / s_div:
                    self.kt = float(min(1.6, max(0.0, S_prev / cSp)))
        except Exception:
            pass
        # --- known lambda ---
        pi = self._as_list(obs.get("preus_properes_24h")); c = self._as_list(obs.get("co2_properes_24h"))
        K = min(len(pi), len(c))
        if K == 0:
            try:
                pi = [float(obs.get("preu_actual"))]; c = [float(obs.get("co2_actual"))]; K = 1
                if not (math.isfinite(pi[0]) and math.isfinite(c[0])):
                    return 0.0
            except Exception:
                return 0.0
        K = min(K, H)
        lam_k = [c[i] + self.KAPPA * pi[i] for i in range(K)]
        for i in range(K):
            self.hist.setdefault(t0 + i, {})["lam"] = lam_k[i]
        if self.counter % 24 == 0:
            for key in [k for k in self.hist if k < t0 - 50]:
                del self.hist[key]

        # --- climatologies over the horizon ---
        hdm = [dm(k) for k in range(H)]
        clim_lam = np.array([self.clim_lam_hwm[h, int(d >= 5), m] for h, d, m in hdm])
        cD = np.array([self.D_hdm[h, d, m] for h, d, m in hdm])
        cS = np.array([self.S_hdm12[h, d, m] for h, d, m in hdm]) / s_div

        def cl_past(k):       # lambda climatology at t+k for k < 0 (yesterday / two days ago)
            h, d, m = dm(k)
            return self.clim_lam_hwm[h, int(d >= 5), m]

        # --- lambda forecast (ridge) ---
        lam = np.empty(H)
        jk = K - 1
        anom = lam_k[jk] - clim_lam[jk]
        an1 = lam_k[0] - clim_lam[0]
        vals = []
        for i in range(23, -1, -1):
            kk = jk - i
            v = self.hist.get(t0 + kk, {}).get("lam")
            if v is not None:
                vals.append(v - (clim_lam[kk] if kk >= 0 else cl_past(kk)))
        level = float(np.mean(vals)) if vals else anom
        for k in range(H):
            if k < K:
                lam[k] = lam_k[k]
            else:
                v24 = self.hist.get(t0 + k - 24, {}).get("lam"); v48 = self.hist.get(t0 + k - 48, {}).get("lam")
                a24 = (v24 - (clim_lam[k - 24] if k >= 24 else cl_past(k - 24))) if v24 is not None else 0.0
                a48 = (v48 - (clim_lam[k - 48] if k >= 48 else cl_past(k - 48))) if v48 is not None else 0.0
                lam[k] = self._pred("lam", k, [1.0, clim_lam[k], a24, a48, anom, an1, level], clim_lam[k], t0 + k)
        # --- lambda forecast (analogs) ---
        feats = None
        if self.ana is not None and not self.NO_PREDICTION:
            h1, d1, m1 = dm(-1); hp0 = self.hist.get(t0 - 1, {})
            month = (cal[0][1]) / 12 * 2 * math.pi
            feats = {"weekend": float(cal[0][0] >= 5), "month_sin": math.sin(month), "month_cos": math.cos(month),
                     "aD": (hp0["D"] - self.D_hdm[h1, d1, m1]) if "D" in hp0 else 0.0, "Dprev": hp0.get("D", self.D_hdm[h1, d1, m1]),
                     "temp": float(nd.get("temp_ambient_c", 20.0) or 20.0), "kt": self.kt, "irr": float(nd.get("irradiancia_wm2", 0.0) or 0.0),
                     "tpan": float(nd.get("temp_panel_c", 20.0) or 20.0), "Sprev": hp0.get("S", 0.0),
                     "lam0": lam_k[0] - clim_lam[0], "lam1": (lam_k[1] - clim_lam[1]) if K > 1 else 0.0,
                     "lam2": (lam_k[2] - clim_lam[2]) if K > 2 else 0.0, "level": level}
            for kk_, vv in feats.items():
                if not math.isfinite(vv):
                    feats[kk_] = 0.0
            la = self._analog("lam", hour0, feats, H)
            if la is not None:
                alpha = float(self.ALPHA.get("lam", 1.0)); ok = ~np.isnan(la)
                lam[K:] = np.where(ok[K:], alpha * lam[K:] + (1 - alpha) * la[K:], lam[K:])
        lam = np.maximum(lam, 0.0)

        # --- net demand forecast ---
        hp = self.hist.get(t0 - 1, {})
        h1, d1, m1 = dm(-1)
        aD = (hp["D"] - self.D_hdm[h1, d1, m1]) if "D" in hp else 0.0
        N = np.empty(H); sig = np.empty(H); D_ridge = np.empty(H); S_ridge = np.empty(H)
        for k in range(H):
            yday = self.hist.get(t0 + k - 24, {})
            h2, d2, m2 = dm(k - 24)
            aD_yday = (yday["D"] - self.D_hdm[h2, d2, m2]) if "D" in yday else 0.0
            cS_yday = self.S_hdm12[h2, d2, m2] / s_div
            kt_yday = min(1.6, max(0.0, yday["S"] / cS_yday)) if ("S" in yday and cS_yday > 30.0 / s_div) else self.kt
            Dk = max(0.0, self._pred("D", k, [1.0, cD[k], aD, aD_yday], cD[k], t0 + k))
            Sk = max(0.0, self._pred("S", k, [1.0, cS[k], cS[k] * self.kt, cS[k] * kt_yday], cS[k], t0 + k))
            D_ridge[k] = Dk; S_ridge[k] = Sk
            N[k] = Dk - Sk
            sig[k] = math.sqrt(self._sig("D", k) ** 2 + (self._sig("S", k) / s_div) ** 2)
        if feats is not None:
            Da = self._analog("D", hour0, feats, H); Sa = self._analog("S", hour0, feats, H)
            if Da is not None and Sa is not None:
                aD_, aS_ = float(self.ALPHA.get("D", 1.0)), float(self.ALPHA.get("S", 1.0))
                Dm = np.where(np.isnan(Da), D_ridge, aD_ * D_ridge + (1 - aD_) * Da)
                Sm = np.where(np.isnan(Sa), S_ridge, aS_ * S_ridge + (1 - aS_) * np.maximum(Sa, 0.0) / s_div)
                N = np.maximum(Dm, 0.0) - np.maximum(Sm, 0.0)

        # --- LP ---
        V = self.V_FRAC * self.lam_mean
        L = self.LT[:H, :H]
        Z = np.zeros((H, H)); I = np.eye(H)
        A_E = np.hstack([self.eta * L, -L / self.eta, Z])
        A_ub = np.vstack([A_E, -A_E, np.hstack([I, -I, -I])])
        b_ub = np.concatenate([np.full(H, cap - soc), np.full(H, soc), -N])
        cost = np.concatenate([np.full(H, -V * self.eta), np.full(H, V / self.eta + self.EPS_EXPORT * self.lam_mean), lam])
        ub_dis = np.clip(N - self.Z_SIGMA * sig, 0.0, pmax)
        bounds = [(0.0, pmax)] * H + [(0.0, float(b)) for b in ub_dis] + [(0.0, None)] * H
        u = 0.0
        try:
            res = linprog(cost, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
            if res.success and res.x is not None:
                u = float(res.x[0] - res.x[H])
        except Exception:
            u = 0.0
        if not math.isfinite(u):
            u = 0.0
        max_c = max(0.0, min(pmax, (cap - soc) / self.eta - self.eps))
        max_d = max(0.0, min(pmax, soc * self.eta - self.eps))
        return float(max(-max_d, min(max_c, u)))
