"""
Prueba 1/generar_interfaz.py
Genera la interfaz web animada interactiva y autocontenida: Prueba 1/interfaz_animada.html
"""
import json
from pathlib import Path

DIR_PRUEBA = Path("C:/Projects/Datathon2026/Prueba 1")
DATA_PATH = DIR_PRUEBA / "datos_animacion.json"
HTML_PATH = DIR_PRUEBA / "interfaz_animada.html"

with open(DATA_PATH, "r", encoding="utf-8") as f:
    datos_json = f.read()

html_template = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>UPC Sostenible — Monitor de Control de Batería Industrial</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --card-border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --charge: #22c55e;
      --discharge: #f97316;
      --neutral: #64748b;
      --danger: #ef4444;
      --purple: #a855f7;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 20px; line-height: 1.4; }
    .container { max-width: 1400px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }
    
    header {
      background: var(--card-bg);
      padding: 20px 24px;
      border-radius: 12px;
      border: 1px solid var(--card-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 15px;
    }
    .header-title h1 { font-size: 1.4rem; color: #fff; display: flex; align-items: center; gap: 10px; }
    .header-title p { font-size: 0.9rem; color: var(--text-muted); margin-top: 4px; }
    .badge-live { background: #065f46; color: #34d399; font-size: 0.75rem; font-weight: 700; padding: 4px 10px; border-radius: 20px; text-transform: uppercase; }
    
    /* Panel de Control */
    .controls-card {
      background: var(--card-bg);
      padding: 16px 24px;
      border-radius: 12px;
      border: 1px solid var(--card-border);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 15px;
    }
    .ctrl-group { display: flex; align-items: center; gap: 10px; }
    button.btn {
      background: #2563eb;
      color: white;
      border: none;
      padding: 9px 18px;
      border-radius: 8px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
    }
    button.btn:hover { background: #1d4ed8; transform: translateY(-1px); }
    button.btn-pause { background: #dc2626; }
    button.btn-pause:hover { background: #b91c1c; }
    button.btn-nav { background: #334155; padding: 8px 12px; }
    button.btn-nav:hover { background: #475569; }
    
    .timeline-container { flex: 1; min-width: 280px; display: flex; align-items: center; gap: 12px; }
    input[type=range] { flex: 1; accent-color: var(--accent); cursor: pointer; }
    .time-badge { background: #0f172a; padding: 6px 12px; border-radius: 6px; font-weight: 700; font-variant-numeric: tabular-nums; font-size: 0.95rem; border: 1px solid #334155; }
    
    .day-selector { display: flex; gap: 6px; }
    .day-btn {
      background: #0f172a;
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 0.8rem;
      cursor: pointer;
      font-weight: 600;
    }
    .day-btn.active { background: #2563eb; color: #fff; border-color: #2563eb; }
    
    /* Layout principal */
    .main-grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 20px;
    }
    @media (max-width: 1024px) { .main-grid { grid-template-columns: 1fr; } }
    
    /* Tarjeta Bateria */
    .battery-card {
      background: var(--card-bg);
      border-radius: 12px;
      border: 1px solid var(--card-border);
      padding: 24px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 20px;
    }
    .battery-visual {
      position: relative;
      width: 160px;
      height: 260px;
      border: 4px solid #64748b;
      border-radius: 20px;
      padding: 8px;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      background: #0f172a;
      box-shadow: inset 0 0 20px rgba(0,0,0,0.6);
    }
    .battery-top-terminal {
      position: absolute;
      top: -16px;
      left: 50%;
      transform: translateX(-50%);
      width: 50px;
      height: 12px;
      background: #64748b;
      border-top-left-radius: 6px;
      border-top-right-radius: 6px;
    }
    .battery-liquid {
      width: 100%;
      height: 50%;
      background: linear-gradient(180deg, #38bdf8 0%, #1d4ed8 100%);
      border-radius: 12px;
      transition: height 0.3s ease, background 0.4s ease;
      position: relative;
      overflow: hidden;
    }
    .battery-liquid.charging {
      background: linear-gradient(180deg, #4ade80 0%, #15803d 100%);
      box-shadow: 0 0 20px rgba(74, 222, 128, 0.4);
    }
    .battery-liquid.discharging {
      background: linear-gradient(180deg, #fb923c 0%, #c2410c 100%);
      box-shadow: 0 0 20px rgba(251, 146, 60, 0.4);
    }
    
    .battery-stats { text-align: center; }
    .soc-number { font-size: 2.2rem; font-weight: 800; color: #fff; font-variant-numeric: tabular-nums; }
    .kwh-number { font-size: 1rem; color: var(--text-muted); font-weight: 500; }
    
    .power-gauge {
      width: 100%;
      background: #0f172a;
      border-radius: 8px;
      padding: 12px;
      border: 1px solid var(--card-border);
      text-align: center;
    }
    .gauge-label { font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }
    .gauge-value { font-size: 1.5rem; font-weight: 700; margin: 4px 0; font-variant-numeric: tabular-nums; }
    .gauge-bar-track { height: 10px; background: #334155; border-radius: 5px; position: relative; margin-top: 8px; overflow: hidden; }
    .gauge-bar-fill { position: absolute; height: 100%; width: 0%; left: 50%; transition: all 0.2s ease; border-radius: 4px; }
    
    /* Metrics Grid */
    .dashboard-view { display: flex; flex-direction: column; gap: 20px; }
    .metrics-summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }
    .metric-box {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .metric-box .label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }
    .metric-box .value { font-size: 1.3rem; font-weight: 700; color: #fff; font-variant-numeric: tabular-nums; }
    .metric-box .sub { font-size: 0.75rem; color: var(--text-muted); }
    .metric-box.highlight { border-color: #3b82f6; background: rgba(59, 130, 246, 0.08); }
    .metric-box.highlight .value { color: #60a5fa; }
    .metric-box.score-card { border-color: #10b981; background: rgba(16, 185, 129, 0.08); }
    .metric-box.score-card .value { color: #34d399; font-size: 1.5rem; }
    
    /* Chart Section */
    .chart-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .chart-header { display: flex; justify-content: space-between; align-items: center; }
    .chart-title { font-size: 1rem; font-weight: 700; color: #fff; }
    .chart-legend { display: flex; gap: 14px; font-size: 0.8rem; }
    .legend-item { display: flex; align-items: center; gap: 6px; }
    .legend-dot { width: 10px; height: 10px; border-radius: 50%; }
    
    canvas#chartCanvas { width: 100%; height: 260px; background: #0f172a; border-radius: 8px; border: 1px solid #334155; }
    
    /* Footer */
    footer { text-align: center; color: var(--text-muted); font-size: 0.8rem; margin-top: 10px; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="header-title">
        <h1>
          <span>⚡</span>
          <span>UPC Sostenible — Monitor de Batería Industrial (2 MWh / 500 kW)</span>
          <span class="badge-live">Modelo Climatología Activo</span>
        </h1>
        <p>Optimización simultánea de emisiones de CO2 (70%) y factura eléctrica regulada PVPC (30%)</p>
      </div>
      <div>
        <span style="font-size: 0.85rem; color: #94a3b8;">Datathon 2026 | Transició Energètica</span>
      </div>
    </header>

    <!-- Controles -->
    <div class="controls-card">
      <div class="ctrl-group">
        <button id="btnPlay" class="btn">
          <span id="playIcon">▶</span> <span id="playText">Reproducir</span>
        </button>
        <button id="btnPrev" class="btn btn-nav" title="Paso anterior">⏮</button>
        <button id="btnNext" class="btn btn-nav" title="Paso siguiente">⏭</button>
      </div>

      <div class="timeline-container">
        <input type="range" id="timeSlider" min="0" max="167" value="0">
        <div class="time-badge" id="timeDisplay">Día 1 — 00:00</div>
      </div>

      <div class="ctrl-group">
        <label style="font-size: 0.85rem; color: var(--text-muted); font-weight: 600;">Velocidad:</label>
        <select id="speedSelect" style="background:#0f172a; color:#fff; border:1px solid #334155; padding:6px 10px; border-radius:6px; cursor:pointer;">
          <option value="400">0.5x</option>
          <option value="200" selected>1x</option>
          <option value="100">2x</option>
          <option value="40">5x</option>
          <option value="20">10x</option>
        </select>
      </div>

      <div class="day-selector" id="dayButtons">
        <button class="day-btn active" data-day="0">Lun</button>
        <button class="day-btn" data-day="1">Mar</button>
        <button class="day-btn" data-day="2">Mié</button>
        <button class="day-btn" data-day="3">Jue</button>
        <button class="day-btn" data-day="4">Vie</button>
        <button class="day-btn" data-day="5">Sáb</button>
        <button class="day-btn" data-day="6">Dom</button>
      </div>
    </div>

    <!-- Main Grid -->
    <div class="main-grid">
      <!-- Batería Visual -->
      <div class="battery-card">
        <h3 style="font-size: 1rem; color: #fff; text-align: center;">Estado Físico del Almacenamiento</h3>
        
        <div class="battery-visual">
          <div class="battery-top-terminal"></div>
          <div class="battery-liquid" id="batteryLiquid"></div>
        </div>

        <div class="battery-stats">
          <div class="soc-number" id="socPctText">50.0%</div>
          <div class="kwh-number"><span id="socKwhText">1000.0</span> / 2000.0 kWh</div>
        </div>

        <div class="power-gauge">
          <div class="gauge-label">Consigna Activa $u_t$</div>
          <div class="gauge-value" id="powerKwText">0.0 kW</div>
          <div id="powerStateText" style="font-size: 0.8rem; font-weight: 600; color: var(--text-muted);">En Reposo</div>
          <div class="gauge-bar-track">
            <div class="gauge-bar-fill" id="gaugeFill"></div>
          </div>
        </div>

        <div style="font-size: 0.8rem; color: var(--text-muted); text-align: center; border-top: 1px solid #334155; padding-top: 12px; width: 100%;">
          Dinámica: $E_{t+1} = E_t + \\eta_c u_t^+ - \\frac{u_t^-}{\\eta_d}$<br>
          Rendimiento $\\eta = 90\\%$ ($\\eta_c = \\eta_d = 94.87\\%$)
        </div>
      </div>

      <!-- Métricas y Gráfico -->
      <div class="dashboard-view">
        <!-- Bloque Métricas en Vivo -->
        <div class="metrics-summary">
          <div class="metric-box score-card">
            <div class="label">Score Oficial</div>
            <div class="value" id="metricScore">5.40</div>
            <div class="sub">Objetivo maximizado</div>
          </div>
          <div class="metric-box highlight">
            <div class="label">Reducción CO2</div>
            <div class="value" id="metricCo2Pct">5.05%</div>
            <div class="sub" id="metricCo2Kg">8.805 kg ahorrados</div>
          </div>
          <div class="metric-box highlight">
            <div class="label">Reducción Coste</div>
            <div class="value" id="metricCostPct">6.23%</div>
            <div class="sub" id="metricCostEur">17.670 € ahorrados</div>
          </div>
          <div class="metric-box">
            <div class="label">Infracciones Físicas</div>
            <div class="value" style="color: #34d399;" id="metricInfr">0</div>
            <div class="sub">Cumplimiento estricto</div>
          </div>
        </div>

        <div class="metrics-summary">
          <div class="metric-box">
            <div class="label">Demanda Campus ($D_t$)</div>
            <div class="value" id="metricLoad">0 kW</div>
            <div class="sub">Carga eléctrica actual</div>
          </div>
          <div class="metric-box">
            <div class="label">Generación Solar ($S_t$)</div>
            <div class="value" style="color: #fbbf24;" id="metricSolar">0 kW</div>
            <div class="sub">Planta fotovoltaica</div>
          </div>
          <div class="metric-box">
            <div class="label">Importación Red ($g_t$)</div>
            <div class="value" style="color: #38bdf8;" id="metricGrid">0 kW</div>
            <div class="sub" id="metricGridBase">Base: 0 kW</div>
          </div>
          <div class="metric-box">
            <div class="label">Precio PVPC / CO2</div>
            <div class="value" style="font-size: 1.1rem;" id="metricPriceCo2">0.12 € | 0.15 kg</div>
            <div class="sub" id="metricLambda">Efectivo $\\lambda$: 0.18</div>
          </div>
        </div>

        <!-- Gráfico Multivariable Sincronizado -->
        <div class="chart-card">
          <div class="chart-header">
            <div class="chart-title">Evolución Temporal de Potencias y Nivel de Batería</div>
            <div class="chart-legend">
              <div class="legend-item"><div class="legend-dot" style="background: #94a3b8;"></div> Demanda</div>
              <div class="legend-item"><div class="legend-dot" style="background: #fbbf24;"></div> Solar</div>
              <div class="legend-item"><div class="legend-dot" style="background: #ef4444;"></div> Base sin bat.</div>
              <div class="legend-item"><div class="legend-dot" style="background: #38bdf8;"></div> Red c/bat.</div>
              <div class="legend-item"><div class="legend-dot" style="background: #a855f7;"></div> Batería E(t)</div>
            </div>
          </div>
          <canvas id="chartCanvas" width="900" height="260"></canvas>
        </div>
      </div>
    </div>

    <footer>
      Datathon 2026 — Repte UPC Sostenible | Modelo Climatológico con MPC de Programación Lineal (HiGHS) | 0 Infracciones Garantizadas
    </footer>
  </div>

  <script>
    const SIM_DATA = %DATA_JSON%;

    const horas = SIM_DATA.horas;
    const totalSteps = horas.length;
    let currentStep = 0;
    let isPlaying = false;
    let playTimer = null;
    let playSpeed = 200;

    // Elementos DOM
    const btnPlay = document.getElementById("btnPlay");
    const playIcon = document.getElementById("playIcon");
    const playText = document.getElementById("playText");
    const btnPrev = document.getElementById("btnPrev");
    const btnNext = document.getElementById("btnNext");
    const timeSlider = document.getElementById("timeSlider");
    const timeDisplay = document.getElementById("timeDisplay");
    const speedSelect = document.getElementById("speedSelect");
    const dayButtons = document.querySelectorAll(".day-btn");

    const batteryLiquid = document.getElementById("batteryLiquid");
    const socPctText = document.getElementById("socPctText");
    const socKwhText = document.getElementById("socKwhText");
    const powerKwText = document.getElementById("powerKwText");
    const powerStateText = document.getElementById("powerStateText");
    const gaugeFill = document.getElementById("gaugeFill");

    const metricLoad = document.getElementById("metricLoad");
    const metricSolar = document.getElementById("metricSolar");
    const metricGrid = document.getElementById("metricGrid");
    const metricGridBase = document.getElementById("metricGridBase");
    const metricPriceCo2 = document.getElementById("metricPriceCo2");
    const metricLambda = document.getElementById("metricLambda");

    const canvas = document.getElementById("chartCanvas");
    const ctx = canvas.getContext("2d");

    const diasSemana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

    function updateStep(step) {
      if (step < 0) step = 0;
      if (step >= totalSteps) step = totalSteps - 1;
      currentStep = step;
      timeSlider.value = step;

      const d = horas[step];
      const dow = d.day_of_week;
      const hourStr = String(d.hour).padStart(2, "0") + ":00";
      timeDisplay.textContent = `${diasSemana[dow]} ${hourStr} (Paso ${step + 1}/${totalSteps})`;

      // Actualizar selector de dia
      dayButtons.forEach((b, idx) => {
        b.classList.toggle("active", idx === dow);
      });

      // Bateria SOC
      const socKwh = d.soc_fin_kwh;
      const socPct = (socKwh / 2000.0) * 100.0;
      batteryLiquid.style.height = `${Math.min(100, Math.max(5, socPct))}%`;
      socPctText.textContent = `${socPct.toFixed(1)}%`;
      socKwhText.textContent = `${socKwh.toFixed(1)}`;

      // Accion u_t
      const u = d.u_t;
      powerKwText.textContent = `${u > 0 ? "+" : ""}${u.toFixed(1)} kW`;
      
      batteryLiquid.className = "battery-liquid";
      if (u > 5.0) {
        batteryLiquid.classList.add("charging");
        powerStateText.textContent = "⚡ CARGANDO DESDE RED";
        powerStateText.style.color = "#4ade80";
        gaugeFill.style.background = "#22c55e";
        gaugeFill.style.left = "50%";
        gaugeFill.style.width = `${Math.min(50, (u / 500) * 50)}%`;
      } else if (u < -5.0) {
        batteryLiquid.classList.add("discharging");
        powerStateText.textContent = "🔋 DESCARGANDO AL CAMPUS";
        powerStateText.style.color = "#fb923c";
        gaugeFill.style.background = "#f97316";
        const w = Math.min(50, (-u / 500) * 50);
        gaugeFill.style.left = `${50 - w}%`;
        gaugeFill.style.width = `${w}%`;
      } else {
        powerStateText.textContent = "⏸ EN REPOSO";
        powerStateText.style.color = "var(--text-muted)";
        gaugeFill.style.width = "0%";
      }

      // Metricas en vivo
      metricLoad.textContent = `${d.load_kw.toFixed(1)} kW`;
      metricSolar.textContent = `${d.pv_kw.toFixed(1)} kW`;
      metricGrid.textContent = `${d.grid_kw.toFixed(1)} kW`;
      const baseGrid = Math.max(0, d.load_kw - d.pv_kw);
      metricGridBase.textContent = `Sin batería: ${baseGrid.toFixed(1)} kW`;

      metricPriceCo2.textContent = `${d.precio.toFixed(3)} € | ${d.co2.toFixed(3)} kg`;
      const kappa = 0.246555;
      const lam = d.co2 + kappa * d.precio;
      metricLambda.textContent = `Precio efectivo λ: ${lam.toFixed(4)}`;

      // Redibujar Canvas
      drawChart(step);
    }

    function drawChart(cur) {
      const W = canvas.width;
      const H = canvas.height;
      ctx.clearRect(0, 0, W, H);

      // Encontrar max para escalar
      const padL = 45;
      const padR = 20;
      const padT = 20;
      const padB = 30;
      const plotW = W - padL - padR;
      const plotH = H - padT - padB;

      // Eje X: 0..totalSteps
      const getX = i => padL + (i / (totalSteps - 1)) * plotW;
      
      // Eje Y para potencia: 0..1200 kW
      const maxKw = 1200;
      const getY = val => padT + (1 - val / maxKw) * plotH;

      // Lineas de guia horizontal
      ctx.strokeStyle = "#1e293b";
      ctx.lineWidth = 1;
      ctx.fillStyle = "#64748b";
      ctx.font = "10px sans-serif";
      for (let kw = 0; kw <= maxKw; kw += 300) {
        const y = getY(kw);
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(W - padR, y);
        ctx.stroke();
        ctx.fillText(`${kw}kW`, 6, y + 3);
      }

      // 1. Curva Base sin bateria (rojo discontinuo)
      ctx.beginPath();
      ctx.strokeStyle = "#ef4444";
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1.5;
      for (let i = 0; i < totalSteps; i++) {
        const bg = Math.max(0, horas[i].load_kw - horas[i].pv_kw);
        const x = getX(i);
        const y = getY(bg);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.setLineDash([]);

      // 2. Curva Red con bateria (azul relleno)
      ctx.beginPath();
      ctx.fillStyle = "rgba(56, 189, 248, 0.15)";
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 2;
      ctx.moveTo(getX(0), getY(0));
      for (let i = 0; i < totalSteps; i++) {
        ctx.lineTo(getX(i), getY(horas[i].grid_kw));
      }
      ctx.lineTo(getX(totalSteps - 1), getY(0));
      ctx.closePath();
      ctx.fill();

      ctx.beginPath();
      for (let i = 0; i < totalSteps; i++) {
        const x = getX(i);
        const y = getY(horas[i].grid_kw);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // 3. Demanda Campus (gris claro)
      ctx.beginPath();
      ctx.strokeStyle = "#94a3b8";
      ctx.lineWidth = 1.5;
      for (let i = 0; i < totalSteps; i++) {
        const x = getX(i);
        const y = getY(horas[i].load_kw);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // 4. Solar (amarillo)
      ctx.beginPath();
      ctx.strokeStyle = "#fbbf24";
      ctx.lineWidth = 1.5;
      for (let i = 0; i < totalSteps; i++) {
        const x = getX(i);
        const y = getY(horas[i].pv_kw);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // 5. Nivel de bateria normalizado E(t) en escala lateral (purpura)
      ctx.beginPath();
      ctx.strokeStyle = "#c084fc";
      ctx.lineWidth = 2;
      for (let i = 0; i < totalSteps; i++) {
        const eFrac = horas[i].soc_fin_kwh / 2000.0;
        const x = getX(i);
        const y = padT + (1 - eFrac) * plotH;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Linea de aguja temporal actual (blanco)
      const curX = getX(cur);
      ctx.beginPath();
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.moveTo(curX, padT - 5);
      ctx.lineTo(curX, padT + plotH + 5);
      ctx.stroke();

      // Circulo en la cabeza de la aguja
      ctx.beginPath();
      ctx.fillStyle = "#38bdf8";
      ctx.arc(curX, padT - 5, 5, 0, Math.PI * 2);
      ctx.fill();

      // Marcadores de dias en el eje X
      ctx.fillStyle = "#94a3b8";
      ctx.font = "10px sans-serif";
      for (let d = 0; d < 7; d++) {
        const stepDay = d * 24;
        const x = getX(stepDay);
        ctx.fillText(diasSemana[d].substring(0, 3), x + 2, H - 8);
      }
    }

    function togglePlay() {
      if (isPlaying) {
        pause();
      } else {
        play();
      }
    }

    function play() {
      isPlaying = true;
      playIcon.textContent = "⏸";
      playText.textContent = "Pausar";
      btnPlay.classList.add("btn-pause");
      playTimer = setInterval(() => {
        if (currentStep >= totalSteps - 1) {
          updateStep(0);
        } else {
          updateStep(currentStep + 1);
        }
      }, playSpeed);
    }

    function pause() {
      isPlaying = false;
      playIcon.textContent = "▶";
      playText.textContent = "Reproducir";
      btnPlay.classList.remove("btn-pause");
      if (playTimer) clearInterval(playTimer);
    }

    // Event Listeners
    btnPlay.addEventListener("click", togglePlay);
    btnPrev.addEventListener("click", () => { pause(); updateStep(currentStep - 1); });
    btnNext.addEventListener("click", () => { pause(); updateStep(currentStep + 1); });

    timeSlider.addEventListener("input", e => {
      pause();
      updateStep(parseInt(e.target.value));
    });

    speedSelect.addEventListener("change", e => {
      playSpeed = parseInt(e.target.value);
      if (isPlaying) {
        pause();
        play();
      }
    });

    dayButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        pause();
        const d = parseInt(btn.dataset.day);
        updateStep(d * 24);
      });
    });

    // Inicializar
    updateStep(0);
  </script>
</body>
</html>
"""

html_final = html_template.replace("%DATA_JSON%", datos_json)

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html_final)

print(f"Interfaz animada generada con éxito en: {HTML_PATH}")