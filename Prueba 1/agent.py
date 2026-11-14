"""
Prueba 1/agent.py
Agente de control optimo para el reto de la bateria de UPC Sostenible (Datathon 2026).
Modelo basado en medias historicas (climatologia) y optimizacion predictiva (LP-MPC de horizonte movil).
"""
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
from scipy.optimize import linprog

class BatteryAgent:
    def __init__(self):
        # Constantes fisicas
        self.capacidad = 2000.0  # kWh
        self.potencia_max = 500.0  # kW
        self.eta = 0.9 ** 0.5  # Rendimiento sqrt(0.90) ~= 0.948683298
        self.eta_c = self.eta
        self.eta_d = self.eta
        self.epsilon = 1e-4  # Margen de seguridad estricto para evitar infracciones
        
        # Cargar parametros climatologicos (con fallback robusto si se evalua el .py aislado)
        param_path = Path(__file__).parent / "parametros.json"
        if param_path.exists():
            with open(param_path, "r", encoding="utf-8") as f:
                params = json.load(f)
            self.kappa = float(params.get("kappa", 0.246555))
            self.media_neto_hd = np.array(params["media_neto_hd"], dtype=np.float64)  # 24x7
            self.media_neto_hdm = np.array(params["media_neto_hdm"], dtype=np.float64)  # 24x7x12
            self.lambda_term_default = float(params.get("lambda_terminal", 0.15))
        else:
            self.kappa = 0.246555
            self.media_neto_hd = np.full((24, 7), 400.0, dtype=np.float64)
            self.media_neto_hdm = np.full((24, 7, 12), 400.0, dtype=np.float64)
            self.lambda_term_default = 0.15
        
        # Pre-construir matrices de restriccion para horizonte H=24
        self.H = 24
        self.A_ub = np.zeros((2 * self.H, 2 * self.H), dtype=np.float64)
        for tau in range(1, self.H + 1):
            # Restriccion E_tau <= 2000
            self.A_ub[tau - 1, :tau] = self.eta_c
            self.A_ub[tau - 1, self.H:self.H + tau] = -1.0 / self.eta_d
            # Restriccion E_tau >= 0 ==> -E_tau <= 0
            self.A_ub[self.H + tau - 1, :tau] = -self.eta_c
            self.A_ub[self.H + tau - 1, self.H:self.H + tau] = 1.0 / self.eta_d
            
    def _parse_time(self, obs: dict):
        """Extrae hora, dia de la semana y mes de forma robusta."""
        hour = int(obs.get("hour", 12))
        dow = int(obs.get("day_of_week", 0))
        month = 6  # Mes por defecto si no esta disponible
        
        ts = obs.get("timestamp")
        if ts is not None:
            if hasattr(ts, "month"):
                month = int(ts.month)
            elif isinstance(ts, str) and len(ts) >= 7:
                try:
                    month = int(ts[5:7])
                except Exception:
                    pass
        return hour, dow, month

    def act(self, obs: dict) -> float:
        """Calcula la consigna u_t optima en kW."""
        # 1. Lectura del estado actual
        soc_kwh = float(obs.get("soc_kwh", 1000.0))
        h0, d0, month = self._parse_time(obs)
        
        # Precios y CO2 de las proximas 24 horas
        prices = obs.get("preus_properes_24h", [])
        co2s = obs.get("co2_properes_24h", [])
        
        H = min(self.H, len(prices), len(co2s))
        if H < 2:
            return 0.0  # Fallback si no hay horizonte
            
        # 2. Vector de precio efectivo lambda = CO2 + kappa * Precio
        lambdas = np.array([co2s[i] + self.kappa * prices[i] for i in range(H)], dtype=np.float64)
        
        # 3. Prediccion de demanda neta esperada a partir de las medias historicas (climatologia)
        N_hat = np.zeros(H, dtype=np.float64)
        for tau in range(H):
            h_tau = (h0 + tau) % 24
            d_tau = (d0 + (h0 + tau) // 24) % 7
            if 1 <= month <= 12:
                N_hat[tau] = self.media_neto_hdm[h_tau, d_tau, month - 1]
            else:
                N_hat[tau] = self.media_neto_hd[h_tau, d_tau]
                
        # 4. Formulacion del problema LP de horizonte movil (MPC)
        A_ub = self.A_ub[:2 * H, :2 * H] if H == self.H else np.zeros((2 * H, 2 * H))
        if H != self.H:
            for tau in range(1, H + 1):
                A_ub[tau - 1, :tau] = self.eta_c
                A_ub[tau - 1, H:H + tau] = -1.0 / self.eta_d
                A_ub[H + tau - 1, :tau] = -self.eta_c
                A_ub[H + tau - 1, H:H + tau] = 1.0 / self.eta_d
                
        b_ub = np.zeros(2 * H, dtype=np.float64)
        b_ub[:H] = self.capacidad - soc_kwh  # E_tau <= 2000
        b_ub[H:] = soc_kwh                   # E_tau >= 0
        
        # Limites en u+ y u-
        bounds = []
        for tau in range(H):
            bounds.append((0.0, self.potencia_max))
        for tau in range(H):
            bounds.append((0.0, min(self.potencia_max, float(N_hat[tau]))))
            
        # Coste del estado terminal E_H
        lambda_term = float(np.mean(lambdas))
        c = np.zeros(2 * H, dtype=np.float64)
        c[:H] = lambdas - lambda_term * self.eta_d * self.eta_c
        c[H:] = -lambdas + lambda_term
        
        # 5. Resolucion con HiGHS
        try:
            res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
            if res.success:
                u_opt = float(res.x[0] - res.x[H])
            else:
                u_opt = 0.0
        except Exception:
            u_opt = 0.0
            
        # 6. Clamp fisico estricto contra infracciones y clipping
        max_charge = max(0.0, min(self.potencia_max, (self.capacidad - soc_kwh) / self.eta_c - self.epsilon))
        max_discharge = max(0.0, min(self.potencia_max, soc_kwh * self.eta_d - self.epsilon))
        
        u_final = float(max(-max_discharge, min(max_charge, u_opt)))
        return u_final