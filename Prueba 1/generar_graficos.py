"""
Prueba 1/generar_graficos.py
Genera todas las figuras analiticas y de resultados del modelo climatologico.
Guarda las figuras en Prueba 1/fig/
"""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Directorios
DIR_PRUEBA = Path("C:/Projects/Datathon2026/Prueba 1")
DIR_FIG = DIR_PRUEBA / "fig"
DIR_FIG.mkdir(parents=True, exist_ok=True)

# Estilo estetico limpio
plt.rcParams.update({
    "font.sans-serif": "Arial",
    "font.family": "sans-serif",
    "figure.titlesize": 14,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.autolayout": False,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "axes.grid": True,
    "grid.alpha": 0.35,
    "grid.linestyle": "--"
})

COLOR_CARGA = "#2ecc71"      # Verde esmeralda
COLOR_DESCARGA = "#e67e22"   # Naranja suave
COLOR_AZUL = "#2980b9"       # Azul corporativo
COLOR_ROJO = "#e74c3c"       # Rojo alerta
COLOR_GRIS = "#7f8c8d"       # Gris neutro
COLOR_MORADO = "#8e44ad"     # Morado

def plot_01_climatologia(params):
    media_load_hd = np.array(params["media_load_hd"])  # 24x7
    media_pv_hd = np.array(params["media_pv_hd"])      # 24x7
    media_neto_hd = np.array(params["media_neto_hd"])  # 24x7
    
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    
    # 1. Demanda
    im0 = axes[0].imshow(media_load_hd, aspect="auto", cmap="YlOrRd", origin="lower")
    axes[0].set_title("Demanda Media D(h, d) [kW]", fontweight="bold")
    axes[0].set_xlabel("Día de la semana")
    axes[0].set_ylabel("Hora del día")
    axes[0].set_xticks(range(7))
    axes[0].set_xticklabels(["L", "M", "X", "J", "V", "S", "D"])
    axes[0].set_yticks(range(0, 24, 2))
    plt.colorbar(im0, ax=axes[0], fraction=0.046, pad=0.04)
    
    # 2. Solar
    im1 = axes[1].imshow(media_pv_hd, aspect="auto", cmap="viridis", origin="lower")
    axes[1].set_title("Generación Solar Media S(h, d) [kW]", fontweight="bold")
    axes[1].set_xlabel("Día de la semana")
    axes[1].set_xticks(range(7))
    axes[1].set_xticklabels(["L", "M", "X", "J", "V", "S", "D"])
    plt.colorbar(im1, ax=axes[1], fraction=0.046, pad=0.04)
    
    # 3. Demanda Neta
    im2 = axes[2].imshow(media_neto_hd, aspect="auto", cmap="magma", origin="lower")
    axes[2].set_title("Demanda Neta Media N(h, d) [kW]", fontweight="bold")
    axes[2].set_xlabel("Día de la semana")
    axes[2].set_xticks(range(7))
    axes[2].set_xticklabels(["L", "M", "X", "J", "V", "S", "D"])
    plt.colorbar(im2, ax=axes[2], fraction=0.046, pad=0.04)
    
    fig.suptitle("Climatología Histórica del Campus: Demanda, Generación Solar y Demanda Neta", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(DIR_FIG / "01_climatologia_demanda_solar.png")
    plt.close()
    print("Guardado: 01_climatologia_demanda_solar.png")

def plot_02_arbitraje_lambda(df_trayectoria, params):
    kappa = params["kappa"]
    umbral = params["umbral_arbitraje"]
    
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    
    # Perfil medio de lambda por hora
    horas = range(24)
    p_h = np.array(params["perfil_precio_h"])
    c_h = np.array(params["perfil_co2_h"])
    l_h = c_h + kappa * p_h
    
    ax0 = axes[0]
    ax0.plot(horas, l_h, color=COLOR_AZUL, lw=2.5, marker="o", label="Precio efectivo medio $\\bar{\\lambda}_h$")
    ax0.axvspan(1, 6, alpha=0.15, color=COLOR_CARGA, label="Valle nocturno (Carga barata)")
    ax0.axvspan(13, 16, alpha=0.15, color=COLOR_CARGA, label="Valle solar (Carga barata)")
    ax0.axvspan(19, 22, alpha=0.15, color=COLOR_DESCARGA, label="Punta nocturna (Descarga)")
    ax0.set_title("Perfil Diario del Precio Efectivo Compuesto $\\lambda = c_t + \\kappa \\pi_t$", fontweight="bold")
    ax0.set_xlabel("Hora del día")
    ax0.set_ylabel("$\\lambda$ [kg eq. / kWh]")
    ax0.set_xticks(range(0, 24, 2))
    ax0.legend(loc="upper left", framealpha=0.9)
    
    # Histograma del ratio lambda_max / lambda_min diario
    df_trayectoria["fecha_dia"] = pd.to_datetime(df_trayectoria["timestamp"]).dt.date
    df_trayectoria["lambda_val"] = df_trayectoria["co2"] + kappa * df_trayectoria["precio"]
    
    ratios = []
    for _, g in df_trayectoria.groupby("fecha_dia"):
        if len(g) >= 20:
            l_min = g["lambda_val"].min()
            l_max = g["lambda_val"].max()
            if l_min > 0:
                ratios.append(l_max / l_min)
                
    ax1 = axes[1]
    ax1.hist(ratios, bins=15, color=COLOR_MORADO, edgecolor="black", alpha=0.75, rwidth=0.85)
    ax1.axvline(umbral, color=COLOR_ROJO, linestyle="--", lw=2, label=f"Umbral rentabilidad $1/\\eta^2 = {umbral:.3f}$")
    ax1.axvline(np.median(ratios), color="black", linestyle="-", lw=2, label=f"Mediana ratio = {np.median(ratios):.2f}")
    ax1.set_title("Oportunidad de Arbitraje Diario (Ratio $\\lambda_{max} / \\lambda_{min}$)", fontweight="bold")
    ax1.set_xlabel("Ratio $\\lambda_{max} / \\lambda_{min}$")
    ax1.set_ylabel("Frecuencia (días)")
    ax1.legend(loc="upper right", framealpha=0.9)
    
    plt.tight_layout()
    plt.savefig(DIR_FIG / "02_arbitraje_lambda_mercado.png")
    plt.close()
    print("Guardado: 02_arbitraje_lambda_mercado.png")

def plot_03_trayectoria_dia(df_trayectoria):
    # Seleccionar un dia representativo completo (ejemplo: dia 3 del pseudo-test, 24 horas)
    df_trayectoria["fecha_dia"] = pd.to_datetime(df_trayectoria["timestamp"]).dt.date
    dias_unicos = df_trayectoria["fecha_dia"].unique()
    dia_rep = dias_unicos[2]
    sub = df_trayectoria[df_trayectoria["fecha_dia"] == dia_rep].sort_values("hour")
    
    fig, (ax0, ax1, ax2) = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    
    horas = sub["hour"].values
    
    # Panel 0: Potencias del campus y red
    ax0.plot(horas, sub["load_kw"], label="Demanda Campus $D_t$", color="black", lw=2)
    ax0.plot(horas, sub["pv_kw"], label="Generación Solar $S_t$", color="#f39c12", lw=2)
    ax0.plot(horas, np.maximum(sub["load_kw"] - sub["pv_kw"], 0), label="Base sin batería $g^{base}_t$", color=COLOR_ROJO, linestyle=":", lw=2)
    ax0.plot(horas, sub["grid_kw"], label="Importación con batería $g_t$", color=COLOR_AZUL, lw=2.5)
    ax0.set_ylabel("Potencia [kW]")
    ax0.set_title(f"Dinámica Diaria en el Campus — Fecha: {dia_rep}", fontweight="bold")
    ax0.legend(loc="upper right", ncol=2, framealpha=0.9)
    
    # Panel 1: Consigna de la bateria u_t
    u_vals = sub["u_t"].values
    colors = [COLOR_CARGA if u > 0 else (COLOR_DESCARGA if u < 0 else COLOR_GRIS) for u in u_vals]
    ax1.bar(horas, u_vals, color=colors, edgecolor="black", alpha=0.85, width=0.7)
    ax1.axhline(0, color="black", lw=1)
    ax1.set_ylabel("Consigna $u_t$ [kW]")
    ax1.set_title("Acción de Control de la Batería: Carga ($u_t > 0$) / Descarga ($u_t < 0$)", fontweight="bold")
    
    # Panel 2: Evolucion de la energia almacenada E_t y E_{t+1}
    ax2.plot(horas, sub["soc_fin_kwh"], color=COLOR_MORADO, lw=2.5, marker="s", label="Energía final $E_{t+1}$ [kWh]")
    ax2.axhline(2000, color=COLOR_ROJO, linestyle="--", alpha=0.7, label="Capacidad máx (2.000 kWh)")
    ax2.axhline(0, color=COLOR_ROJO, linestyle="--", alpha=0.7, label="Límite mín (0 kWh)")
    ax2.set_ylabel("Energía $E$ [kWh]")
    ax2.set_xlabel("Hora del día")
    ax2.set_xticks(range(0, 24))
    ax2.set_ylim(-100, 2100)
    ax2.legend(loc="upper left", ncol=3, framealpha=0.9)
    
    plt.tight_layout()
    plt.savefig(DIR_FIG / "03_trayectoria_dia_tipico.png")
    plt.close()
    print("Guardado: 03_trayectoria_dia_tipico.png")

def plot_04_trayectoria_semana(df_trayectoria):
    # 168 horas continuas (semana de octubre)
    sub = df_trayectoria.iloc[168:168+168].copy().reset_index(drop=True)
    horas = range(len(sub))
    
    fig, (ax0, ax1, ax2) = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    
    # Panel 0: Importacion de red
    base_grid = np.maximum(sub["load_kw"] - sub["pv_kw"], 0)
    ax0.plot(horas, base_grid, color=COLOR_ROJO, linestyle=":", lw=1.5, alpha=0.8, label="Importación Red Baseline (sin batería)")
    ax0.plot(horas, sub["grid_kw"], color=COLOR_AZUL, lw=2, label="Importación Red con Modelo Climatología")
    ax0.set_ylabel("Potencia [kW]")
    ax0.set_title("Trayectoria Semanal (168 Horas): Afeitado de Puntas y Descarbonización", fontweight="bold")
    ax0.legend(loc="upper right", framealpha=0.9)
    
    # Panel 1: Consignas de bateria u_t
    u_vals = sub["u_t"].values
    colors = [COLOR_CARGA if u > 0 else (COLOR_DESCARGA if u < 0 else COLOR_GRIS) for u in u_vals]
    ax1.bar(horas, u_vals, color=colors, width=0.9, alpha=0.85)
    ax1.set_ylabel("Potencia $u_t$ [kW]")
    ax1.set_title("Consignas Horarias de Batería $u_t$ (Verde: Carga en valle, Naranja: Descarga en punta)", fontweight="bold")
    
    # Panel 2: Nivel de carga E_{t+1}
    ax2.plot(horas, sub["soc_fin_kwh"], color=COLOR_MORADO, lw=2)
    ax2.axhline(2000, color=COLOR_ROJO, linestyle="--", alpha=0.5)
    ax2.axhline(0, color=COLOR_ROJO, linestyle="--", alpha=0.5)
    ax2.set_ylabel("Energía $E$ [kWh]")
    ax2.set_xlabel("Hora de la semana (0 a 167)")
    ax2.set_title("Dinámica Continua del Estado de Carga $E_{t+1}$ [kWh]", fontweight="bold")
    ax2.set_xticks(range(0, 168, 24))
    ax2.set_xticklabels([f"Día {i+1} (Lun)" if i==0 else f"Día {i+1}" for i in range(7)])
    
    plt.tight_layout()
    plt.savefig(DIR_FIG / "04_trayectoria_semana_completa.png")
    plt.close()
    print("Guardado: 04_trayectoria_semana_completa.png")

def plot_05_comparativa(eval_res):
    modelos = ["Baseline (u=0)", "Plantilla Oficial", "Modelo Climatología (Ours)"]
    scores = [eval_res["baseline_nada"]["score"], eval_res["plantilla"]["score"], eval_res["modelo_climatologia"]["score"]]
    co2_pct = [eval_res["baseline_nada"]["co2_estalviat_pct"], eval_res["plantilla"]["co2_estalviat_pct"], eval_res["modelo_climatologia"]["co2_estalviat_pct"]]
    cost_pct = [eval_res["baseline_nada"]["cost_estalviat_pct"], eval_res["plantilla"]["cost_estalviat_pct"], eval_res["modelo_climatologia"]["cost_estalviat_pct"]]
    infr = [eval_res["baseline_nada"]["infraccions"], eval_res["plantilla"]["infraccions"], eval_res["modelo_climatologia"]["infraccions"]]
    
    x = np.arange(len(modelos))
    width = 0.25
    
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(13, 5))
    
    # Metricas de ahorro y Score
    b0 = ax0.bar(x - width, scores, width, label="Score Oficial", color=COLOR_AZUL, edgecolor="black")
    b1 = ax0.bar(x, co2_pct, width, label="Reducción CO2 (%)", color=COLOR_CARGA, edgecolor="black")
    b2 = ax0.bar(x + width, cost_pct, width, label="Reducción Coste (%)", color=COLOR_DESCARGA, edgecolor="black")
    
    ax0.set_ylabel("Porcentaje / Puntos")
    ax0.set_title("Comparativa de Rendimiento en Pseudo-Test (1.725 horas)", fontweight="bold")
    ax0.set_xticks(x)
    ax0.set_xticklabels(modelos, fontweight="bold")
    ax0.legend(loc="upper left")
    
    # Etiquetas en barras
    for rects in [b0, b1, b2]:
        for r in rects:
            h = r.get_height()
            ax0.annotate(f"{h:.2f}",
                         xy=(r.get_x() + r.get_width() / 2, h),
                         xytext=(0, 3), textcoords="offset points",
                         ha="center", va="bottom", fontsize=8, fontweight="bold")
                         
    # Infracciones
    colors_infr = [COLOR_AZUL if v == 0 else COLOR_ROJO for v in infr]
    b_infr = ax1.bar(modelos, infr, color=colors_infr, edgecolor="black", width=0.45)
    ax1.set_ylabel("Número de infracciones")
    ax1.set_title("Infracciones Físicas y Penalizaciones Registradas", fontweight="bold")
    for r in b_infr:
        h = r.get_height()
        ax1.annotate(f"{int(h)} infracciones" if h > 0 else "0 (Limpio)",
                     xy=(r.get_x() + r.get_width() / 2, h),
                     xytext=(0, 3), textcoords="offset points",
                     ha="center", va="bottom", fontsize=9, fontweight="bold")
                     
    plt.tight_layout()
    plt.savefig(DIR_FIG / "05_comparativa_modelos.png")
    plt.close()
    print("Guardado: 05_comparativa_modelos.png")

def plot_06_dinamica_ut_soc(df_trayectoria):
    soc = df_trayectoria["soc_ini_kwh"].values
    u = df_trayectoria["u_t"].values
    eta = 0.9 ** 0.5
    
    fig, ax = plt.subplots(figsize=(8, 6))
    
    # Envolvente fisica
    soc_grid = np.linspace(0, 2000, 200)
    max_charge = np.minimum(500.0, (2000.0 - soc_grid) / eta)
    max_discharge = -np.minimum(500.0, soc_grid * eta)
    
    ax.fill_between(soc_grid, max_discharge, max_charge, color="#ecf0f1", label="Región Físicamente Factible")
    ax.plot(soc_grid, max_charge, color=COLOR_ROJO, linestyle="--", lw=1.5, label="Límite saturación carga")
    ax.plot(soc_grid, max_discharge, color=COLOR_ROJO, linestyle="--", lw=1.5, label="Límite saturación descarga")
    
    # Puntos reales operados
    sc = ax.scatter(soc, u, c=df_trayectoria["hour"], cmap="twilight", alpha=0.4, s=15, edgecolors="none")
    plt.colorbar(sc, ax=ax, label="Hora del día")
    
    ax.axhline(0, color="black", lw=1)
    ax.set_xlim(-50, 2050)
    ax.set_ylim(-550, 550)
    ax.set_xlabel("Estado de Carga Inicial $E_t$ [kWh]", fontweight="bold")
    ax.set_ylabel("Consigna Consignada $u_t$ [kW]", fontweight="bold")
    ax.set_title("Espacio de Fases Operacional: $u_t$ vs $E_t$ con Envolvente de Seguridad", fontweight="bold")
    ax.legend(loc="lower left", framealpha=0.9)
    
    plt.tight_layout()
    plt.savefig(DIR_FIG / "06_dinamica_ut_vs_soc.png")
    plt.close()
    print("Guardado: 06_dinamica_ut_vs_soc.png")

def main():
    with open(DIR_PRUEBA / "parametros.json", "r", encoding="utf-8") as f:
        params = json.load(f)
    with open(DIR_PRUEBA / "resultados_evaluacion.json", "r", encoding="utf-8") as f:
        eval_res = json.load(f)
    df_trayectoria = pd.read_csv(DIR_PRUEBA / "trayectoria_modelo.csv")
    
    plot_01_climatologia(params)
    plot_02_arbitraje_lambda(df_trayectoria, params)
    plot_03_trayectoria_dia(df_trayectoria)
    plot_04_trayectoria_semana(df_trayectoria)
    plot_05_comparativa(eval_res)
    plot_06_dinamica_ut_soc(df_trayectoria)
    print("Todas las figuras generadas exitosamente en Prueba 1/fig/")

if __name__ == "__main__":
    main()