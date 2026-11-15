"""
agent.py — Climatological LP-MPC agent (model v1) for the UPC Sostenible battery challenge, standard mode
(2000 kWh / ±500 kW battery, 24 h perfect market forecast). Scored 6.43 on the public leaderboard.

Physics
-------
The score is linear in the imported energy g_t = max(D_t - S_t + u_t, 0), so maximising it is the same as
minimising  sum_t lambda_t * g_t  with the effective price  lambda_t = c_t + kappa * pi_t
(kappa = (0.3/0.7) * CO2_base / Cost_base, estimated from the data).

Every hour we solve a linear program (LP) over the K <= 24 hours in which lambda is known (perfect forecast
given in obs), extended by H_EXT hours with the climatological lambda profile, and apply only the first set
point (receding-horizon control, MPC).

The only unknown is the future net demand N = D - S: we replace it with its historical mean (hour x weekday
x month climatology), used only as an upper bound on discharge (discharging above the net demand exports
energy at price 0 and with no CO2 credit).

Challenge rules respected: only numpy/scipy/json/pathlib/typing, paths relative to __file__, exact physical
clamp with eta = sqrt(0.9) before returning, native float, never NaN.
"""
import json
import math
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from scipy.optimize import linprog


class BatteryAgent:
    # --- control parameters (tuned on train) ---
    H_EXT = 12          # extra horizon hours with climatological lambda (0 = only the 24 known hours)
    V_FRAC = 1.0        # terminal value of the stored energy, as a fraction of the mean daily lambda
    KAPPA = 0.259       # kg CO2/EUR: (0.3/0.7)·CO2_base/Cost_base. Train: 0.2466; public test (71 816 kg / 118 746 EUR): 0.2592

    def __init__(self, **kw):
        for k, v in kw.items():            # lets the tuning scripts try other configurations
            setattr(self, k.upper(), v)
        self.cap = 2000.0
        self.pmax = 500.0
        self.eta = 0.9 ** 0.5              # exactly the same value as the simulator
        self.eps = 1e-4

        path = Path(__file__).parent / "parameters.json"
        p: Dict[str, Any] = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                p = json.load(f)
        self.kappa = float(self.KAPPA) if self.KAPPA else float(p.get("kappa", 0.2466))
        self.lambda_profile = np.asarray(p.get("lambda_profile_h", [0.115] * 24), dtype=float)
        self.N_mean_hdm = np.asarray(p.get("N_mean_hdm", np.full((24, 7, 12), 900.0)), dtype=float)
        self.lambda_mean = float(np.mean(self.lambda_profile))

        # lower-triangular matrix precomputed for the maximum horizon (cumulative energy)
        self.Hmax = 24 + int(self.H_EXT)
        L = np.tril(np.ones((self.Hmax, self.Hmax)))
        self.A_top = np.hstack([self.eta * L, -L / self.eta])    # E_k - E_0 <= cap - soc
        self.A_bot = -self.A_top                                 # -(E_k - E_0) <= soc

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _time(obs: dict):
        """Hour, weekday and month, robustly (timestamp may be a str, a Timestamp or missing)."""
        hour = int(obs.get("hour", 12)) % 24
        dow = int(obs.get("day_of_week", 0)) % 7
        month = 0
        ts = obs.get("timestamp")
        try:
            if hasattr(ts, "month"):
                month = int(ts.month)
            elif isinstance(ts, str) and len(ts) >= 7:
                month = int(ts[5:7])
        except Exception:
            month = 0
        return hour, dow, month

    @staticmethod
    def _as_list(x, n_max=24) -> List[float]:
        out = []
        if x is None:
            return out
        try:
            for v in list(x)[:n_max]:
                v = float(v)
                if math.isfinite(v):
                    out.append(v)
                else:
                    break
        except Exception:
            return []
        return out

    def _discharge_bound(self, hour, dow, month, H):
        """Climatological net demand (kW) over the next H hours, used as the discharge bound."""
        n = np.empty(H)
        for k in range(H):
            h = (hour + k) % 24
            d = (dow + (hour + k) // 24) % 7
            if 1 <= month <= 12:
                n[k] = self.N_mean_hdm[h, d, month - 1]
            else:
                n[k] = float(np.mean(self.N_mean_hdm[h, d, :]))
        return np.clip(n, 0.0, self.pmax)

    # ------------------------------------------------------------------ policy
    def act(self, obs: dict) -> float:
        soc = float(obs.get("soc_kwh", 1000.0))
        if not math.isfinite(soc):
            soc = 1000.0
        soc = min(max(soc, 0.0), self.cap)
        hour, dow, month = self._time(obs)

        pi = self._as_list(obs.get("preus_properes_24h"))
        c = self._as_list(obs.get("co2_properes_24h"))
        K = min(len(pi), len(c))
        if K == 0:                                   # no forecast: use the current hour if available
            try:
                pi = [float(obs.get("preu_actual"))]
                c = [float(obs.get("co2_actual"))]
                K = 1 if math.isfinite(pi[0]) and math.isfinite(c[0]) else 0
            except Exception:
                K = 0
        if K == 0:
            return 0.0

        lam = np.array(c[:K]) + self.kappa * np.array(pi[:K])
        # climatological extension of the horizon
        H_ext = int(self.H_EXT)
        if H_ext > 0:
            hours = (hour + K + np.arange(H_ext)) % 24
            lam = np.concatenate([lam, self.lambda_profile[hours]])
        H = len(lam)

        bound = self._discharge_bound(hour, dow, month, H)
        V = self.V_FRAC * self.lambda_mean

        # LP: variables x = [u+_0..u+_{H-1}, u-_0..u-_{H-1}] >= 0
        cost = np.concatenate([lam - V * self.eta, -lam + V / self.eta])
        idx = np.r_[0:H, self.Hmax:self.Hmax + H]
        A_ub = np.vstack([self.A_top[:H][:, idx], self.A_bot[:H][:, idx]])
        b_ub = np.concatenate([np.full(H, self.cap - soc), np.full(H, soc)])
        bounds = [(0.0, self.pmax)] * H + [(0.0, float(b)) for b in bound]

        u = 0.0
        try:
            res = linprog(cost, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
            if res.success and res.x is not None:
                u = float(res.x[0] - res.x[H])
        except Exception:
            u = 0.0
        if not math.isfinite(u):
            u = 0.0

        # exact physical clamp (same formula as the simulator) -> 0 violations
        max_c = max(0.0, min(self.pmax, (self.cap - soc) / self.eta - self.eps))
        max_d = max(0.0, min(self.pmax, soc * self.eta - self.eps))
        return float(max(-max_d, min(max_c, u)))
