# MEMORIA TÉCNICA Y DOCUMENTO DE DESARROLLO
## Repte UPC Sostenible — Datathon 2026: Transició Energètica i Descarbonització
### Optimización de Batería Industrial (2 MWh / 500 kW) mediante Modelo de Medias Históricas (Climatología) y Control Predictivo Basado en Modelo (LP-MPC)

**Ubicación de Trabajo:** `C:\Projects\Datathon2026\Prueba 1\`  
**Fecha de Validación:** 14 de Noviembre de 2026  
**Autor:** Antigravity (Equipo UPC Sostenible)  
**Entorno de Ejecución:** Python 3 (NumPy, SciPy HiGHS, Pandas)  

---

## 1. Resumen Ejecutivo y Resultados Oficiales

En este proyecto se ha desarrollado un agente de control óptimo (`BatteryAgent`) diseñado específicamente para gestionar una batería industrial de **2.000 kWh (2 MWh)** y **500 kW** de potencia máxima instalada en el campus universitario de la UPC. 

El modelo aborda el reto formulado por **UPC Sostenible**, cuyo objetivo es maximizar la puntuación global del reto (*Score*):
$$\text{Score} = \max\Big(0,\; 0{,}70 \cdot \Delta\text{CO}_2(\%) + 0{,}30 \cdot \Delta\text{Cost}(\%) - 0{,}20 \cdot \text{Infracciones}\Big)$$

Siguiendo rigurosamente las instrucciones recibidas, la solución implementada adopta el paradigma de **medias históricas (climatología)**: se predice el comportamiento futuro desconocido del campus (demanda eléctrica y generación solar) asumiendo que el sistema reproduce sus valores medios observados en el pasado condicionados a la hora del día, día de la semana y mes. Con estas medias y con la previsión oficial perfecta de 24 horas del precio del mercado eléctrico (PVPC) y del factor de emisión de $\text{CO}_2$ del mix peninsular, el agente resuelve cada hora un problema de **Programación Lineal (LP-MPC)** de horizonte móvil.

### Tabla Comparativa de Rendimiento en el Conjunto de Pseudo-Test (1.725 horas / 12 semanas)

| Estrategia / Modelo | Score Oficial | Reducción $\text{CO}_2$ (%) | Reducción Coste (%) | $\text{CO}_2$ Ahorrado (kg) | Coste Ahorrado (€) | Infracciones Físicas | Tiempo Ejecución (s) | Latencia por Paso (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline (Sin Batería, $u_t=0$)** | **0.00** | 0.00% | 0.00% | 0.0 kg | 0.00 € | 0 | 0.94 s | 0.00 ms |
| **Plantilla Oficial (`starter_kit`)** | **0.00** | 0.98% | 2.20% | 1.701.8 kg | 6.239.05 € | 9 | 0.96 s | 0.01 ms |
| **Modelo Medias Históricas (LP-MPC)** | **5.40** | **5.05%** | **6.23%** | **8.805.0 kg** | **17.670.51 €** | **0 (Limpio)** | **10.06 s** | **5.04 ms** |

### Conclusiones Principales de los Resultados:
1. **Aumento Drástico del Rendimiento:** El modelo de medias históricas alcanza un **Score oficial de 5.40**, multiplicando por más de 5 el ahorro bruto de la heurística base oficial y convirtiendo el resultado final en positivo.
2. **Cero Infracciones Físicas:** A diferencia de la plantilla oficial (que comete 9 infracciones al redondear $\eta = 0.9487 > \sqrt{0.90}$ y provocar *clipping* de descarga en $E=0$), nuestro modelo incorpora una envolvente analítica estricta con margen de seguridad $\epsilon = 10^{-4}$ que garantiza **0 infracciones absolutas**.
3. **Eficiencia Computacional de Grado Industrial:** El tiempo de inferencia medio es de apenas **5.04 ms por hora**. La simulación completa de las 1.725 horas dura 10.06 segundos, quedando muy por debajo del tiempo límite estricto de 60 segundos impuesto por la plataforma del concurso.

---

## 2. Formulación Matemática y Física del Problema

### 2.1. Dinámica del Sistema de Almacenamiento

El sistema corresponde a una batería industrial de iones de litio acoplada a un inversor bidireccional:
* Capacidad nominal máxima: $E_{\max} = 2.000\text{ kWh}$.
* Capacidad mínima: $E_{\min} = 0\text{ kWh}$.
* Estado inicial al comienzo del periodo: $E_0 = 1.000\text{ kWh}$ ($\text{SOC}_0 = 50\%$).
* Potencia máxima del inversor: $P_{\max} = 500\text{ kW}$.
* Rendimiento de ciclo completo (*Round-Trip Efficiency*): $\eta = 0{,}90$ ($90\%$).
* Rendimiento por sentido (carga y descarga simétrica):
  $$\eta_c = \eta_d = \sqrt{\eta} = \sqrt{0{,}90} \approx 0{,}94868329805$$
* Intervalo de decisión discreto: $\Delta t = 1\text{ hora}$.

Para una consigna de potencia $u_t$ (en kW) solicitada a la hora $t$:
* **Modo de Carga ($u_t \ge 0$):** La potencia absorbida de la red interna incrementa la energía interna de la batería según la eficiencia de carga $\eta_c$:
  $$E_{t+1} = E_t + u_t \cdot \Delta t \cdot \eta_c$$
  La cota física máxima de potencia de carga admisible antes de saturar el límite superior es:
  $$u_t^{\text{max\_carga}} = \min\left(500{,}0,\; \frac{E_{\max} - E_t}{\Delta t \cdot \eta_c}\right)$$

* **Modo de Descarga ($u_t < 0$):** La batería suministra energía al campus, sufriendo pérdidas de descarga según $\eta_d$:
  $$E_{t+1} = E_t + \frac{u_t \cdot \Delta t}{\eta_d} = E_t - \frac{|u_t| \cdot \Delta t}{\eta_d}$$
  La cota física máxima de potencia de descarga admisible antes de agotar la capacidad inferior es:
  $$u_t^{\text{max\_descarga}} = \min\left(500{,}0,\; \frac{(E_t - E_{\min}) \cdot \eta_d}{\Delta t}\right)$$

### 2.2. Balance de Potencia en el Punto de Conexión Común (PCC)

A cada hora $t$, denotando por $D_t$ la demanda bruta del campus (kW) y por $S_t$ la generación solar fotovoltaica local (kW), la potencia neta intercambiada con la red exterior peninsular viene gobernada por:
$$g_t = \max(D_t - S_t + u_t,\; 0)$$

* Si $g_t > 0$: El campus importa electricidad de la red externa a un coste horario regulado $\pi_t$ (€/kWh, precio PVPC) y genera emisiones equivalentes asociadas al mix eléctrico marginal peninsular $c_t$ (kg $\text{CO}_2$/kWh).
* Si $D_t - S_t + u_t < 0$: El excedente es inyectado a la red de distribución. Las bases del concurso establecen explícitamente que **la exportación no recibe retribución económica alguna (precio de venta = 0 €/kWh)**. Por lo tanto, cualquier descarga de la batería que supere la demanda neta instantánea ($|u_t| > D_t - S_t$) destruye energía útil sin aportar beneficio económico ni ecológico.

### 2.3. Demostración del Precio Efectivo Compuesto $\lambda_t$

El objetivo oficial busca maximizar la reducción relativa ponderada:
$$\Delta\text{CO}_2(\%) = \frac{\sum_t g_t^{\text{base}} c_t - \sum_t g_t c_t}{\sum_t g_t^{\text{base}} c_t} \times 100$$
$$\Delta\text{Cost}(\%) = \frac{\sum_t g_t^{\text{base}} \pi_t - \sum_t g_t \pi_t}{\sum_t g_t^{\text{base}} \pi_t} \times 100$$

Dado que las trayectorias de referencia $\sum_t g_t^{\text{base}} c_t = \text{CO2}_{\text{base}}$ y $\sum_t g_t^{\text{base}} \pi_t = \text{Coste}_{\text{base}}$ son constantes invariables que no dependen de la política de control, maximizar el *Score* es exactamente equivalente a **minimizar la suma ponderada del flujo de red**:
$$\min_{\{u_t\}} \sum_t g_t \left( 0{,}70 \frac{c_t}{\text{CO2}_{\text{base}}} + 0{,}30 \frac{\pi_t}{\text{Coste}_{\text{base}}} \right)$$

Dividiendo la función objetivo por el factor constante $0{,}70 / \text{CO2}_{\text{base}}$, obtenemos la formulación unificada en función de un **precio efectivo compuesto horaria** $\lambda_t$:
$$\min_{\{u_t\}} \sum_t \lambda_t \cdot g_t$$
donde:
$$\lambda_t = c_t + \kappa \cdot \pi_t$$
$$\kappa = \frac{0{,}30}{0{,}70} \times \frac{\text{CO2}_{\text{base}}}{\text{Coste}_{\text{base}}}$$

A partir de las 4.268 horas del conjunto de entrenamiento (`data/train`):
* $\text{CO2}_{\text{base, train}} = 377.456{,}83\text{ kg CO}_2$
* $\text{Coste}_{\text{base, train}} = 656.109{,}99\text{ €}$
* Factor de escala óptimo:
  $$\kappa = \frac{0{,}30}{0{,}70} \times \frac{377.456{,}83}{656.109{,}99} = 0{,}246555\text{ kg/€}$$

### 2.4. Condición Analítica de Arbitraje Rentable

Si cargamos $1\text{ kWh}$ de energía en la batería en una hora barata $t_1$ e inyectamos dicha energía para mitigar demanda en una hora cara $t_2$:
* Consumo efectivo de red al cargar: $1 / \eta_c\text{ kWh}$, con coste efectivo $\frac{\lambda_{t_1}}{\eta_c}$.
* Reducción neta de red al descargar: $\eta_d\text{ kWh}$, con ahorro efectivo $\lambda_{t_2} \cdot \eta_d$.
* La operación resulta estrictamente rentable y genera incremento neto de Score si y solo si:
  $$\lambda_{t_2} \cdot \eta_d > \frac{\lambda_{t_1}}{\eta_c} \iff \frac{\lambda_{t_2}}{\lambda_{t_1}} > \frac{1}{\eta_c \cdot \eta_d} = \frac{1}{\eta} = \frac{1}{0{,}90} \approx 1{,}1111$$

En los datos de mercado peninsular de nuestro estudio:
* Ratio mediano diario: $\lambda_{\max} / \lambda_{\min} = 2{,}66$.
* En el **100% de los días** se supera holgadamente el umbral de rentabilidad de $1{,}1111$.
* El mínimo diario de $\lambda$ ocurre de forma predominante a las **14:00 horas** (gran penetración solar fotovoltaica peninsular que deprime tanto el precio PVPC como las emisiones marginales) y secundariamente entre las **02:00 y las 05:00 horas** (valle de demanda eólica nocturna). El máximo diario de $\lambda$ se concentra de manera sistemática entre las **20:00 y las 22:00 horas** (pico de demanda vespertina sin energía solar y entrada de ciclos combinados de gas).

---

## 3. Metodología: Modelo de Medias Históricas (Climatología)

En estricta observancia del mandato de diseño del usuario:
> *"Haz un modelo con los datos que maximice el score. Primero tomando sencillamente las medias y esperando que se comporte siempre como se ha comportado en el pasado."*

Construimos un modelo de predicción climatológica pura para las variables exógenas que el agente no conoce a futuro ($D_{t \dots t+23}$ y $S_{t \dots t+23}$):

1. **Agregación por Hora y Día de la Semana:**
   Se calcula la matriz de medias históricas $24 \times 7$ sobre el conjunto de entrenamiento:
   $$\bar{D}(h, d) = \mathbb{E}[D \mid \text{hora}=h, \text{día}=d]$$
   $$\bar{S}(h, d) = \mathbb{E}[S \mid \text{hora}=h, \text{día}=d]$$
   $$\bar{N}(h, d) = \mathbb{E}[\max(D - S, 0) \mid \text{hora}=h, \text{día}=d]$$

2. **Contracción Bayesiana (*Shrinkage*) con Estacionalidad Mensual ($24 \times 7 \times 12$):**
   Debido a que el año escolar y los patrones de irradiación solar presentan diferencias notables entre invierno y verano (en enero el pico solar ronda los 150 kW mientras que en junio alcanza los 350 kW), se calculan las celdas mensuales $\bar{N}(h, d, m)$.
   Para evitar sobreajuste en meses con pocas semanas de train, se aplica una regularización por contracción empírica con $n_0 = 5$ pseudo-muestras hacia la tabla global sin mes:
   $$\hat{N}(h, d, m) = \frac{n \cdot \bar{N}_{\text{muestra}}(h, d, m) + n_0 \cdot \bar{N}(h, d)}{n + n_0}$$

3. **Uso de la Demanda Neta Climatológica como Cota Superior de Descarga:**
   Dado que en el campus la generación solar nunca excede la demanda total, la cota de descarga para evitar verter energía a la red a precio nulo viene dada por:
   $$u_\tau^- \le \min\big(500{,}0,\; \hat{N}_\tau\big)$$

---

## 4. Arquitectura del Controlador Predictivo (LP-MPC)

A cada hora $t$, el método `act(obs)` recibe el estado actual y formula un problema de Programación Lineal con horizonte rodante de $H = 24$ horas:

### 4.1. Variables de Decisión
Para cada paso temporal del horizonte $\tau \in \{0, 1, \dots, H-1\}$:
* $u_\tau^+ \ge 0$: Potencia de carga solicitada a la red en kW.
* $u_\tau^- \ge 0$: Potencia de descarga aportada al campus en kW.

### 4.2. Función Objetivo
$$\min_{\{u_\tau^+, u_\tau^-\}} \sum_{\tau=0}^{H-1} \lambda_\tau \big(u_\tau^+ - u_\tau^-\big) - \lambda_{\text{terminal}} \cdot \eta_d \cdot \big(E_H - E_0\big)$$
Dado que la dinámica energética relaciona el balance final mediante:
$$E_H - E_0 = \eta_c \sum_{\tau=0}^{H-1} u_\tau^+ - \frac{1}{\eta_d} \sum_{\tau=0}^{H-1} u_\tau^-$$
Sustituyendo y simplificando con $\eta = \eta_c \cdot \eta_d = 0{,}90$:
$$\min \sum_{\tau=0}^{H-1} \Big( (\lambda_\tau - \lambda_{\text{term}} \cdot \eta) u_\tau^+ + (-\lambda_\tau + \lambda_{\text{term}}) u_\tau^- \Big)$$
Donde $\lambda_{\text{term}} = \text{media}(\lambda_{0 \dots H-1})$ valora de forma justa la energía remanente al final del horizonte, evitando descargas prematuras si el día siguiente presenta costes elevados.

### 4.3. Restricciones Físicas y Acumuladas
Para todo $\tau \in \{1, \dots, H\}$:
* **Capacidad máxima (no saturación):**
  $$E_\tau = E_0 + \eta_c \sum_{i=0}^{\tau-1} u_i^+ - \frac{1}{\eta_d} \sum_{i=0}^{\tau-1} u_i^- \le 2.000\text{ kWh}$$
* **Capacidad mínima (no vaciado):**
  $$E_\tau = E_0 + \eta_c \sum_{i=0}^{\tau-1} u_i^+ - \frac{1}{\eta_d} \sum_{i=0}^{\tau-1} u_i^- \ge 0\text{ kWh}$$
* **Límites de potencias instantáneas:**
  $$0 \le u_\tau^+ \le 500\text{ kW}$$
  $$0 \le u_\tau^- \le \min\big(500\text{ kW},\; \hat{N}_\tau\big)$$

### 4.4. Capa de Seguridad Física (*Clamping* Estricto)
Una vez resuelto el problema con el motor HiGHS (`scipy.optimize.linprog`), se toma la primera acción calculada $u_0 = u_0^+ - u_0^-$ y se somete a un filtro de seguridad contra tolerancias numéricas:
$$u_t = \max\Big(-\min(500{,}0,\; E_t \cdot \eta_d - \epsilon),\; \min\Big(\min\big(500{,}0,\; (2.000 - E_t)/\eta_c - \epsilon\big),\; u_0\Big)\Big)$$
con $\epsilon = 10^{-4}\text{ kW}$. Esto garantiza de forma matemática e incondicional que el simulador jamás registrará penalizaciones ni recortes forzados.

---

## 5. Galería de Gráficos Analíticos Generados

Todas las figuras han sido generadas a alta resolución (300 DPI) y residen en `Prueba 1/fig/`:

1. **`01_climatologia_demanda_solar.png`**:
   Muestra los mapas de calor (*heatmaps*) de la demanda horaria $D(h, d)$, de la generación solar $S(h, d)$ y de la demanda neta resultante $N(h, d)$ a lo largo de los días laborables y fines de semana. Se aprecia con nitidez la reducción de demanda los sábados y domingos (de 700 kW a 350 kW) y la ventana solar concentrada entre las 10:00 y las 17:00.
2. **`02_arbitraje_lambda_mercado.png`**:
   Ilustra la evolución media de $\lambda_h$ a lo largo del día con las dos ventanas de carga identificadas (valle solar a las 14:00 y valle nocturno) frente al pico vespertino (21:00). A la derecha, el histograma de ratios diarios confirma que el 100% de los días supera el umbral crítico $1/\eta^2 = 1{,}1111$.
3. **`03_trayectoria_dia_tipico.png`**:
   Trayectoria detallada de 24 horas continuas en la que se aprecian las tres bandas temporales:
   - Carga matinal/solar hasta el 100% de capacidad ($E=2.000\text{ kWh}$).
   - Descarga programada de 500 kW durante las horas punta nocturnas (19:00 a 22:00) coincidiendo con la máxima intensidad de $\text{CO}_2$.
   - Retorno al estado de reposo al agotar la energía disponible.
4. **`04_trayectoria_semana_completa.png`**:
   Evolución continua a lo largo de 168 horas (7 días completos). Se observa cómo el agente modula la profundidad de ciclo entre días laborables y de fin de semana, manteniendo un afeitado de picos sostenido.
5. **`05_comparativa_modelos.png`**:
   Comparativa de barras entre Baseline, Plantilla Oficial y el Modelo de Medias Históricas. Pone en evidencia las 9 infracciones cometidas por la plantilla frente a las 0 infracciones de nuestra propuesta.
6. **`06_dinamica_ut_vs_soc.png`**:
   Espacio de fases operacional que grafica la consigna devuelta $u_t$ frente al estado de carga previo $E_t$, superpuesto a la envolvente teórica de saturación física. Demuestra que todos los puntos operados se encuentran rigurosamente confinados en el interior de la región factible.

---

## 6. Interfaz Web Interactiva y Animación Temporal

Para dar cumplimiento directo al requerimiento:
> *"en una interfaz intuitiva permite ver como las cosas de forma animada progresan a lo largo del dia y de la semana"*

Se ha creado la aplicación web interactiva autocontenida:
📁 **`C:\Projects\Datathon2026\Prueba 1\interfaz_animada.html`**

### Características de la Interfaz:
* **Autocontenida y Offline:** No requiere conexión a Internet ni servidor web activo; se puede abrir haciendo doble clic directamente en el archivo HTML desde cualquier explorador (Chrome, Edge, Firefox).
* **Controles de Reproducción:**
  - Botón interactivo de Reproducir / Pausar.
  - Selector de velocidad dinámica (0.5x, 1x, 2x, 5x, 10x).
  - Barra deslizadora temporal (*Scrubber*) para navegar por las 168 horas de la semana.
  - Selector rápido de días (Lunes a Domingo).
* **Visualizador Físico de la Batería:**
  - Tanque animado de batería industrial que sube y baja mostrando el nivel exacto de energía $E_{t+1}$ (kWh) y porcentaje SOC.
  - Cambio reactivo de color y partículas: verde resplandeciente durante la carga ($u_t > 0$), naranja/ámbar durante la descarga ($u_t < 0$) y neutro en reposo.
  - Indicador dinámico de potencia activa $u_t$ (kW).
* **Panel de Telemetría en Vivo:**
  - Demanda $D_t$, Solar $S_t$, Importación de red $g_t$ vs Baseline sin batería $g^{\text{base}}_t$.
  - Precio PVPC horaria, factor de emisión $\text{CO}_2$ peninsular y precio compuesto $\lambda_t$.
  - Tarjetas de impacto acumulado: Score oficial (5.40), kg de $\text{CO}_2$ ahorrados e importe económico en euros.
* **Gráfica Dinámica Multivariable Sincronizada:**
  - Lienzo HTML5 Canvas a 60 fps que proyecta las curvas semanales completas junto a una aguja temporal vertical que se desplaza en sincronía con la animación.

---

## 7. Verificación de Normas y Preparación del Paquete de Entrega

El desarrollo se ha sometido a una auditoría estricta de cumplimiento normativo:
1. **Inspección AST del Código (`check_submission.py`):**
   - No se importan librerías prohibidas (`os`, `sys`, `subprocess`, `urllib`, `requests`, `threading`, etc.).
   - Se utiliza únicamente la biblioteca estándar autorizada (`json`, `math`, `pathlib`) y librerías científicas aprobadas (`numpy`, `scipy.optimize.linprog`).
2. **Pruebas de Aislamiento y Rutas:**
   - Carga de parámetros mediante `Path(__file__).parent / "parametros.json"`.
   - Incorporación de mecanismo de respaldo (*fallback*) autónomo para operar sin fallos incluso si `agent.py` se evalúa de manera aislada sin archivos auxiliares.
3. **Paquete Oficial Comprimido:**
   Se ha generado el archivo `Prueba 1/submission.zip` conteniendo:
   - `agent.py`
   - `parametros.json`
   El paquete ha sido verificado satisfactoriamente con la herramienta oficial:
   ```bash
   python starter_kit/check_submission.py "Prueba 1/submission.zip"
   # >>> RESULTAT: LA SOLUCIÓ ÉS VÀLIDA I ESTÀ A PUNT PER SER LLIURADA A LA WEB! <<<
   ```

---

## 8. Estructura de Ficheros en `Prueba 1`

Todos los entregables, modelos, scripts, resultados y gráficos residen exclusivamente dentro de la carpeta asignada:

```text
C:\Projects\Datathon2026\Prueba 1\
├── agent.py                      # Clase BatteryAgent lista para competición
├── parametros.json               # Tablas climatológicas y constantes calculadas
├── submission.zip                # Paquete verificado listo para subir a la web
├── calcular_climatologia.py      # Pipeline de extracción de medias históricas
├── evaluar_agentes.py            # Validador comparativo sobre pseudo-test
├── generar_graficos.py           # Generador de figuras de alta resolución
├── generar_interfaz.py           # Compilador de la interfaz web interactiva
├── resultados_evaluacion.json    # Métricas y tiempos de evaluación oficiales
├── trayectoria_modelo.csv        # Registro horario completo de variables (1.725 h)
├── datos_animacion.json          # Datos horarios extraídos para la animación
├── interfaz_animada.html         # Interfaz interactiva y animada del progreso diario/semanal
├── DOCUMENTO_MODELO.md           # La presente memoria técnica completa
└── fig\                          # Carpeta con las 6 figuras analíticas
    ├── 01_climatologia_demanda_solar.png
    ├── 02_arbitraje_lambda_mercado.png
    ├── 03_trayectoria_dia_tipico.png
    ├── 04_trayectoria_semana_completa.png
    ├── 05_comparativa_modelos.png
    └── 06_dinamica_ut_vs_soc.png
```