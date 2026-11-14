"""
Prueba 1/evaluar_agentes.py
Evaluador riguroso sobre el conjunto pseudo-test (dias 15-21 de cada mes).
Compara:
  1. Baseline (sin bateria, u=0)
  2. Plantilla oficial (heuristica de starter_kit)
  3. Modelo de Medias Historicas + LP-MPC (Prueba 1/agent.py)
Genera:
  - Prueba 1/resultados_evaluacion.json
  - Prueba 1/trayectoria_modelo.csv
  - Prueba 1/datos_animacion.json
"""
import sys
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd

# Rutas
ROOT = Path("C:/Projects/Datathon2026")
sys.path.insert(0, str(ROOT))

from src.data import load_hourly, split, bloques
from starter_kit.environment import CampusBatteryEnv
from starter_kit.agent import BatteryAgent as PlantillaAgent
from agent import BatteryAgent as ClimatologiaAgent

class ZeroAgent:
    def act(self, obs: dict) -> float:
        return 0.0

def evaluar(agente, nombre, df_val):
    print(f"\n--- Evaluando {nombre} en {len(df_val)} horas ({len(bloques(df_val))} bloques) ---")
    env = CampusBatteryEnv(df_val)
    obs = env.reset()
    done = False
    
    t0 = time.time()
    latencias = []
    
    # Registros para la trayectoria
    trayectoria = []
    
    while not done:
        soc_ini = float(env.soc)
        t_act0 = time.perf_counter()
        action = agente.act(obs)
        latencias.append((time.perf_counter() - t_act0) * 1000)
        
        cur_t = env.t
        row = env.df.iloc[cur_t]
        
        obs, done = env.step(action)
        soc_fin = float(env.soc)
        
        trayectoria.append({
            "timestamp": str(row["Fecha"]),
            "hour": int(row["Fecha"].hour),
            "day_of_week": int(row["Fecha"].dayofweek),
            "load_kw": float(row["load_kw"]),
            "pv_kw": float(row["pv_kw"]),
            "precio": float(row["precio_eur_per_kwh"]),
            "co2": float(row["co2_kg_per_kwh"]),
            "u_t": float(action),
            "soc_ini_kwh": soc_ini,
            "soc_fin_kwh": soc_fin,
            "grid_kw": float(env.grid[-1]),
            "export_kw": float(env.exports[-1]),
            "infraccion": int(env.infraccions_per_step[-1])
        })
        
    t_total = time.time() - t0
    res = env.evaluate_results()
    res["tiempo_total_s"] = round(t_total, 3)
    res["latencia_media_ms"] = round(float(np.mean(latencias)), 3)
    res["latencia_p95_ms"] = round(float(np.percentile(latencias, 95)), 3)
    
    print(f"Resultado {nombre}:")
    print(f"  Score oficial: {res['score']:.2f} / 100")
    print(f"  Reduccion CO2: {res['co2_estalviat_pct']:.2f}% ({res['co2_estalviat_kg']:.1f} kg)")
    print(f"  Reduccion Coste: {res['cost_estalviat_pct']:.2f}% ({res['cost_estalviat_eur']:.2f} EUR)")
    print(f"  Infracciones fisicas: {res['infraccions']}")
    print(f"  Tiempo total: {res['tiempo_total_s']:.2f} s (media: {res['latencia_media_ms']:.2f} ms/paso)")
    
    return res, pd.DataFrame(trayectoria)

def main():
    df = load_hourly()
    train, val = split(df)
    
    df_val = pd.concat(bloques(val))
    print(f"Pseudo-test preparado con {len(df_val)} horas.")
    
    # 1. Baseline sin bateria
    res_nada, _ = evaluar(ZeroAgent(), "Baseline (sin bateria)", df_val)
    
    # 2. Plantilla
    res_plantilla, _ = evaluar(PlantillaAgent(), "Plantilla Oficial", df_val)
    
    # 3. Modelo Climatologia
    res_clima, df_trayectoria = evaluar(ClimatologiaAgent(), "Modelo Medias Historicas (LP-MPC)", df_val)
    
    # Guardar resultados JSON
    resultados = {
        "baseline_nada": res_nada,
        "plantilla": res_plantilla,
        "modelo_climatologia": res_clima
    }
    
    out_dir = Path("C:/Projects/Datathon2026/Prueba 1")
    with open(out_dir / "resultados_evaluacion.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2)
        
    # Guardar trayectoria completa
    df_trayectoria.to_csv(out_dir / "trayectoria_modelo.csv", index=False)
    print(f"Trayectoria guardada en: {out_dir / 'trayectoria_modelo.csv'}")
    
    # Extraer una semana representativa para la animacion (por ejemplo, bloque 1: 168 horas completas)
    bloques_val = bloques(val)
    b_rep = bloques_val[1] if len(bloques_val) > 1 else bloques_val[0] # Bloque de Octubre o Septiembre
    start_ts = str(b_rep.index[0])
    end_ts = str(b_rep.index[-1])
    
    df_rep = df_trayectoria[(df_trayectoria["timestamp"] >= start_ts) & (df_trayectoria["timestamp"] <= end_ts)].copy()
    
    # Datos para la animacion
    datos_anim = {
        "metadata": {
            "periodo": f"{start_ts} a {end_ts}",
            "n_horas": len(df_rep),
            "capacidad_kwh": 2000.0,
            "potencia_max_kw": 500.0,
            "score_semana": float(res_clima["score"]),
            "d_co2_pct": float(res_clima["co2_estalviat_pct"]),
            "d_coste_pct": float(res_clima["cost_estalviat_pct"])
        },
        "horas": df_rep.to_dict(orient="records")
    }
    
    with open(out_dir / "datos_animacion.json", "w", encoding="utf-8") as f:
        json.dump(datos_anim, f, indent=2)
    print(f"Datos de animacion guardados en: {out_dir / 'datos_animacion.json'}")

if __name__ == "__main__":
    main()