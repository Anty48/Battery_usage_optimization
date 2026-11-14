# Prueba 1/calcular_climatologia.py
import json
from pathlib import Path
import numpy as np
import pandas as pd

# Rutas
ROOT = Path(__file__).resolve().parent.parent
CACHE_HOURLY = ROOT / 'resultados' / 'hourly_oficial.pkl'
OUT_PARAMS = Path(__file__).resolve().parent / 'parametros.json'

ETA = 0.9 ** 0.5  # ~0.948683298
CAPACIDAD = 2000.0
POTENCIA = 500.0

def load_data():
    if CACHE_HOURLY.exists():
        df = pd.read_pickle(CACHE_HOURLY)
        df = df.rename(columns={'precio': 'precio_eur_per_kwh', 'co2': 'co2_kg_per_kwh'})
    else:
        from src.data import load_hourly
        df = load_hourly()
    return df

def main():
    print('Cargando datos horarios...')
    df = load_data()
    
    # Mascara de pseudo-test (dias 15-21 de cada mes)
    es_val = (df.index.day >= 15) & (df.index.day <= 21)
    train = df[~es_val].copy()
    val = df[es_val].copy()
    
    print(f'Train: {len(train)} horas | Pseudo-test (val): {len(val)} horas')
    
    # Calcular baseline en train para obtener kappa
    train['neto_kw'] = (train['load_kw'] - train['pv_kw']).clip(lower=0)
    co2_base_train = (train['neto_kw'] * train['co2_kg_per_kwh']).sum()
    coste_base_train = (train['neto_kw'] * train['precio_eur_per_kwh']).sum()
    
    # kappa = (0.3 / 0.7) * (CO2_base / Coste_base)
    kappa = (0.3 / 0.7) * (co2_base_train / coste_base_train)
    print(f'CO2 base train: {co2_base_train:.1f} kg')
    print(f'Coste base train: {coste_base_train:.2f} EUR')
    print(f'Factor kappa: {kappa:.6f} kg/EUR')
    
    # Medias historicas de demanda, solar y demanda neta por (hora, dia_semana)
    train['hour'] = train.index.hour
    train['dow'] = train.index.dayofweek
    train['month'] = train.index.month
    
    # 24 horas x 7 dias de la semana
    media_load_hd = np.zeros((24, 7))
    media_pv_hd = np.zeros((24, 7))
    media_neto_hd = np.zeros((24, 7))
    
    for h in range(24):
        for d in range(7):
            sub = train[(train['hour'] == h) & (train['dow'] == d)]
            if len(sub) > 0:
                media_load_hd[h, d] = sub['load_kw'].mean()
                media_pv_hd[h, d] = sub['pv_kw'].mean()
                media_neto_hd[h, d] = sub['neto_kw'].mean()
            else:
                # Fallback por hora
                sub_h = train[train['hour'] == h]
                media_load_hd[h, d] = sub_h['load_kw'].mean()
                media_pv_hd[h, d] = sub_h['pv_kw'].mean()
                media_neto_hd[h, d] = sub_h['neto_kw'].mean()

    # Perfiles mensuales (24x7x12) con encogimiento bayesiano (shrinkage n0=5) hacia (24x7)
    media_neto_hdm = np.zeros((24, 7, 12))
    media_load_hdm = np.zeros((24, 7, 12))
    media_pv_hdm = np.zeros((24, 7, 12))
    n0 = 5.0
    
    for h in range(24):
        for d in range(7):
            fb_neto = media_neto_hd[h, d]
            fb_load = media_load_hd[h, d]
            fb_pv = media_pv_hd[h, d]
            for m in range(1, 13):
                sub_hdm = train[(train['hour'] == h) & (train['dow'] == d) & (train['month'] == m)]
                n = len(sub_hdm)
                if n > 0:
                    media_neto_hdm[h, d, m-1] = (n * sub_hdm['neto_kw'].mean() + n0 * fb_neto) / (n + n0)
                    media_load_hdm[h, d, m-1] = (n * sub_hdm['load_kw'].mean() + n0 * fb_load) / (n + n0)
                    media_pv_hdm[h, d, m-1] = (n * sub_hdm['pv_kw'].mean() + n0 * fb_pv) / (n + n0)
                else:
                    media_neto_hdm[h, d, m-1] = fb_neto
                    media_load_hdm[h, d, m-1] = fb_load
                    media_pv_hdm[h, d, m-1] = fb_pv

    # Perfil medio de precios y CO2 por hora
    perfil_precio_h = train.groupby('hour')['precio_eur_per_kwh'].mean().tolist()
    perfil_co2_h = train.groupby('hour')['co2_kg_per_kwh'].mean().tolist()
    
    # Lambda terminal: valor medio de lambda para el estado final del horizonte
    train['lambda'] = train['co2_kg_per_kwh'] + kappa * train['precio_eur_per_kwh']
    lambda_terminal = float(train['lambda'].median())
    
    parametros = {
        'kappa': float(kappa),
        'lambda_terminal': lambda_terminal,
        'umbral_arbitraje': float(1.0 / (ETA ** 2)),
        'media_load_hd': media_load_hd.tolist(),
        'media_pv_hd': media_pv_hd.tolist(),
        'media_neto_hd': media_neto_hd.tolist(),
        'media_neto_hdm': media_neto_hdm.tolist(),
        'perfil_precio_h': perfil_precio_h,
        'perfil_co2_h': perfil_co2_h,
        'eta': float(ETA),
        'capacidad': CAPACIDAD,
        'potencia': POTENCIA
    }
    
    with open(OUT_PARAMS, 'w', encoding='utf-8') as f:
        json.dump(parametros, f, indent=2)
    print(f'Parametros guardados exitosamente en: {OUT_PARAMS}')

if __name__ == '__main__':
    main()
