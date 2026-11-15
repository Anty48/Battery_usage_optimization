# Campus battery control: forecasting + linear programming

**Datathon FME 2026 — AED × UPC Sostenible battery challenge · Team EngIAnyers**

Every hour, a `BatteryAgent` decides how much to charge or discharge the battery of the UPC campus so as to
cut CO₂ emissions (weight 0.7) and the electricity bill (weight 0.3) with respect to the campus without a
battery:

```
Score = max(0, 0.70·ΔCO2% + 0.30·ΔCost% − 0.20·violations)
```

| Mode | Battery | Market forecast in `obs` | Agent | Leaderboard | Local pseudo-test | Perfect-information oracle (local) |
|---|---|---|---|---|---|---|
| Standard | 2 MWh, ±500 kW | 24 h | LP-MPC + climatology (`standard_mode/`) | **6.43** (plateau 6.44) | 5.52 | 5.58 |
| Hard | 6 MWh, ±1500 kW, solar ×12 | 3 h | LP-MPC + ridge & analog forecasts (`agent/`) | 20.24 (ridge) → **21.78** (analogs) | **18.30** (strict 18.20) | 19.92 |

Zero violations in every configuration; about 16 s for the 2016 test hours (limit 60 s).
The final hard-mode configuration (coefficients tuned by the potential optimisation) scores 18.30 locally
against 18.26 for the version that got 21.78 on the server; it is the one in `agent/submission.zip`.

📄 **Full write-up:** [`report/report.pdf`](report/report.pdf) · 🎞️ **Interactive viewer:** `viewer/viewer.html`
(download and open in a browser: hour-by-hour animation of a pseudo-test week, with power flows, set point
`u_t`, stored energy `E_t+1`, prices and cumulative savings).

## The idea in one paragraph

The score is *linear* in the energy imported from the grid, `g_t = max(D_t − S_t + u_t, 0)`. Maximising it is
therefore the same as minimising `Σ λ_t g_t` with a single **effective price** `λ_t = c_t + κ·π_t`
(CO₂ intensity plus κ times the electricity price, with `κ = (0.3/0.7)·CO2₀/Cost₀ ≈ 0.259 kg/€` the
exchange rate implied by the score). With λ known, the optimal schedule is a small **linear program** over
the battery dynamics `E_{t+1} = E_t + η u⁺ − u⁻/η` (η = √0.9), solved every hour on a receding horizon
(MPC) with only the first set point applied. In standard mode λ is given 24 h ahead and the LP is already at
the physical ceiling. In hard mode only 3 h are given, so the agent **forecasts** λ, the demand and the solar
for the next 24 h — with ridge regressions on anomalies and with **forecasting by analogy** (a kernel-weighted
average of the most similar historical days: Nadaraya–Watson) — and discharges only down to the net demand it
is reasonably sure of (a `z·σ` safety margin), because energy exported to the grid is worth nothing.

## Repository layout

```
agent/            FINAL hard-mode agent: agent.py + predictors.json + analogs.json, and submission.zip (validated)
standard_mode/    standard-mode agent (v1, 6.43 on the leaderboard) + parameters.json + submission.zip (validated)
src/              everything needed to rebuild the agent, the results and the figures
  data.py             official hourly pipeline + local validation split (days 15–21 of each month)
  hard_env.py         hard-mode data and simulator (3 h horizon, weather in obs), normal/strict evaluation
  predictors.py       ridge forecasts of lambda, demand and solar for every horizon k
  analogs.py          forecasting by analogy (kernel bandwidths fitted on train)
  oracle.py           perfect-information ceiling (one global LP)
  diagnose.py         gap analysis: perfect lambda / net demand / everything inside the agent
  calibrate.py        grid sweep of the controller knobs on train
  optimize_potential.py, optimize_parallel.py   Nelder–Mead on a scenario-averaged score (the "potential")
  finalize.py         freezes the configuration, builds and checks submission.zip, writes results + LaTeX macros
  figures.py, summarize_opt.py, make_viewer.py, style.py
results/          JSON summaries, final trajectory, optimisation logs
report/           LaTeX source, figures and report.pdf
viewer/           template.html + generated viewer.html
```

## Reproducing

The challenge data and the organisers' starter kit are **not** included (they belong to the organisers).
Download the participants' package from the challenge website and unzip it at the repository root, so that
`data/train/*.csv` and `starter_kit/environment.py` exist. Then (Python ≥ 3.10):

```bash
pip install -r requirements.txt
python src/hard_env.py                # builds the hard-mode hourly table (pv ×12 + weather)
python src/predictors.py              # -> agent/predictors.json
python src/analogs.py                 # -> agent/analogs.json
python src/oracle.py                  # perfect-information ceiling
python src/diagnose.py                # where the gap to the ceiling comes from
python src/calibrate.py               # controller grid sweep
python src/optimize_parallel.py --minutes 40           # optional: potential optimisation
python src/finalize.py --best results/opt/best.json     # agent/submission.zip + results + macros
python src/figures.py && python src/summarize_opt.py && python src/make_viewer.py
cd report && pdflatex report.tex && pdflatex report.tex
```

To submit, upload `agent/submission.zip` (hard mode) or `standard_mode/submission.zip` (standard mode); both pass
the official `check_submission.py`.

## Challenge rules respected

Only `numpy`, `pandas`, `scipy`, `json`, `math`, `pathlib`, `typing` inside the agents; no forbidden calls; paths
relative to `__file__`; robust to missing keys, textual timestamps and the time jumps between test weeks; exact
physical clipping (η = √0.9) so that no set point is ever clipped by the simulator; the submission passes the
official `check_submission.py`. The forecasting models (climatologies, ridge coefficients, analog bandwidths) are
fitted on the training days only; the 8 control/blend coefficients of the potential optimisation were selected by
their score on the pseudo-test weeks, so the local 18.30 is slightly optimistic (the hand-tuned 18.26 was not).

## License

Code under the MIT License (see `LICENSE`). The challenge data and starter kit are property of the organisers.
