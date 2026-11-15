"""
finalize.py — Freezes the final configuration of the v3 agent, builds agent/submission.zip, runs the organisers'
check_submission.py, evaluates (normal and strict, with trajectory) and writes results/comparison.json,
results/final.json and the LaTeX macros of the report.

    python src/finalize.py --best results/opt/best.json       # z, V, eps, ALPHA and BW_SCALE from the optimiser
    python src/finalize.py --z_sigma 0.5 --v_frac 1.0 --eps_export 0.02
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import importlib.util
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from hard_env import split_hard, evaluate   # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--h", type=int, default=24); ap.add_argument("--v_frac", type=float, default=1.0)
ap.add_argument("--z_sigma", type=float, default=0.5); ap.add_argument("--eps_export", type=float, default=0.02)
ap.add_argument("--best", default=None, help="path to results/opt/best.json: applies z, V, eps, ALPHA and BW_SCALE from it")
a = ap.parse_args()
ALPHA = BW_SCALE = None
if a.best:
    kw = json.loads(Path(a.best).read_text(encoding="utf-8"))["kwargs"]
    a.z_sigma, a.v_frac, a.eps_export = kw["z_sigma"], kw["v_frac"], kw["eps_export"]; ALPHA, BW_SCALE = kw["alpha"], kw["bw_scale"]
AG = ROOT / "agent"; RES = ROOT / "results"; REP = ROOT / "report"

# 1) freeze the configuration inside agent.py
src = (AG / "agent.py").read_text(encoding="utf-8")
src = re.sub(r"^    H = \d+", f"    H = {a.h}", src, flags=re.M)
src = re.sub(r"^    V_FRAC = [\d.]+", f"    V_FRAC = {a.v_frac}", src, flags=re.M)
src = re.sub(r"^    Z_SIGMA = [\d.]+", f"    Z_SIGMA = {a.z_sigma}", src, flags=re.M)
src = re.sub(r"^    EPS_EXPORT = [\d.]+", f"    EPS_EXPORT = {a.eps_export}", src, flags=re.M)
if ALPHA:
    src = re.sub(r"^    ALPHA = \{[^}]*\}", "    ALPHA = " + json.dumps({k: round(float(v), 4) for k, v in ALPHA.items()}), src, flags=re.M)
    src = re.sub(r"^    BW_SCALE = \{[^}]*\}", "    BW_SCALE = " + json.dumps({k: round(float(v), 4) for k, v in BW_SCALE.items()}), src, flags=re.M)
(AG / "agent.py").write_text(src, encoding="utf-8")

# 2) submission.zip + official checker
zp = AG / "submission.zip"
with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
    for f in ("agent.py", "predictors.json", "analogs.json"):
        z.write(AG / f, f)
kb = zp.stat().st_size / 1024
env = dict(os.environ, PYTHONIOENCODING="utf-8")
r = subprocess.run([sys.executable, str(ROOT / "starter_kit" / "check_submission.py"), str(zp)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
checker = re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout or "") + (r.stderr or ""))
ok = "VÀLIDA" in checker          # the official checker prints its verdict in Catalan
print(checker.strip().splitlines()[-1] if checker.strip() else "(no output)")

# 3) evaluation on the pseudo-test (normal and strict)
spec = importlib.util.spec_from_file_location("agent_final", AG / "agent.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
_, va = split_hard()
rn = evaluate(m.BatteryAgent(), va, trajectory=RES / "trajectory_final.csv")
rs = evaluate(m.BatteryAgent(), va, strict=True)
r_ridge = evaluate(m.BatteryAgent(alpha={"D": 1.0, "S": 1.0, "lam": 1.0}, z_sigma=0.5, v_frac=1.0, eps_export=0.02), va)  # v3a: no analogs
print("normal:", rn); print("strict:", rs); print("ridge only (v3a):", r_ridge)

# 4) comparison table
orc = json.loads((RES / "oracle.json").read_text(encoding="utf-8"))
dia = json.loads((RES / "diagnosis.json").read_text(encoding="utf-8")) if (RES / "diagnosis.json").exists() else {}
cal = json.loads((RES / "calibration.json").read_text(encoding="utf-8"))["rows"] if (RES / "calibration.json").exists() else []
nopred = [f for f in cal if f.get("no_prediction")]
comp = [{"name": "No battery", "score": 0.0, "co2_pct": 0, "cost_pct": 0},
        {"name": "Climatology only (no forecasting)", "score": nopred[0]["val"] if nopred else None,
         "co2_pct": nopred[0]["val_co2"] if nopred else None, "cost_pct": nopred[0]["val_cost"] if nopred else None},
        {"name": "Ridge forecasts only (v3a)", "score": float(r_ridge["score"]), "co2_pct": float(r_ridge["co2_pct"]), "cost_pct": float(r_ridge["cost_pct"])},
        {"name": "Agent v3 (final)", "score": float(rn["score"]), "co2_pct": float(rn["co2_pct"]), "cost_pct": float(rn["cost_pct"]), "final": True},
        {"name": "Agent v3, strict mode", "score": float(rs["score"]), "co2_pct": float(rs["co2_pct"]), "cost_pct": float(rs["cost_pct"])}]
for k, v in dia.items():
    if k != "forecast (v3)":
        comp.append({"name": f"v3 with {k}", "score": v["score"], "co2_pct": v["co2_pct"], "cost_pct": v["cost_pct"], "oracle": True})
for key, name in [("global_oracle", "Global oracle (everything known)"), ("oracle_standard_battery", "Oracle with the standard 2 MWh battery")]:
    comp.append({"name": name, "score": orc[key]["score"], "co2_pct": orc[key]["co2_pct"], "cost_pct": orc[key]["cost_pct"], "oracle": True})
(RES / "comparison.json").write_text(json.dumps(comp, indent=1, default=float), encoding="utf-8")
(RES / "final.json").write_text(json.dumps({"normal": rn, "strict": rs, "config": vars(a), "zip_kb": kb, "check_ok": ok}, indent=1, default=float), encoding="utf-8")


# 5) LaTeX macros
def f2(x, d=2): return f"{float(x):.{d}f}"


t = pd.read_csv(RES / "trajectory_final.csv"); u = t.u_applied_kw
calib = "".join(f"{f2(c['z_sigma'], 1)} & {f2(c['v_frac'], 1)} & {f2(c['eps_export'], 2)} & {'no' if c.get('no_prediction') else 'yes'} & {f2(c['train'])} & {f2(c['val'])}\\\\\n" for c in cal)
macros = f"""\\newcommand{{\\scoreFinal}}{{{f2(rn['score'])}}}
\\newcommand{{\\scoreStrict}}{{{f2(rs['score'])}}}
\\newcommand{{\\coFinal}}{{{f2(rn['co2_pct'])}}}
\\newcommand{{\\costFinal}}{{{f2(rn['cost_pct'])}}}
\\newcommand{{\\timeFinal}}{{{f2(rn['time_s'], 1)}}}
\\newcommand{{\\timeExtrap}}{{{f2(rn['time_s'] * 2016 / 1725, 0)}}}
\\newcommand{{\\zipKB}}{{{kb:.0f}}}
\\newcommand{{\\cyclesDay}}{{{f2((-u[u < 0]).sum() / 6000 / (len(t) / 24))}}}
\\newcommand{{\\exported}}{{{f2(t.export_kw.sum(), 0)}}}
\\newcommand{{\\configFinal}}{{$H={a.h}$ h, $V={f2(a.v_frac)}\\,\\bar\\lambda$, $z={f2(a.z_sigma)}$, $\\varepsilon={f2(a.eps_export, 3)}$}}
\\newcommand{{\\calibTable}}{{{calib}}}
\\newcommand{{\\scoreRidge}}{{{f2(r_ridge['score'])}}}
\\newcommand{{\\scoreNoPred}}{{{f2(nopred[0]['val']) if nopred else '--'}}}
\\newcommand{{\\scoreLamPerf}}{{{f2(dia.get('perfect lambda', {}).get('score', 0))}}}
\\newcommand{{\\scoreNPerf}}{{{f2(dia.get('perfect net demand', {}).get('score', 0))}}}
\\newcommand{{\\scoreAllPerf}}{{{f2(dia.get('everything perfect (24 h)', {}).get('score', 0))}}}
\\newcommand{{\\scoreOracle}}{{{f2(orc['global_oracle']['score'])}}}
\\newcommand{{\\scoreOracleStd}}{{{f2(orc['oracle_standard_battery']['score'])}}}
"""
REP.mkdir(exist_ok=True)
(REP / "macros_results.tex").write_text(macros, encoding="utf-8")
(RES / "final_log.md").write_text("# Final run — agent v3 (hard mode)\n\nConfig: " + json.dumps(vars(a)) + f"\n\nzip {kb:.0f} KB\n\n```\n{checker.strip()}\n```\n\n"
                                  f"normal: {json.dumps(rn, default=float)}\n\nstrict: {json.dumps(rs, default=float)}\n", encoding="utf-8")
print("done; check", "OK" if ok else "REVIEW", "| zip", f"{kb:.0f} KB")
