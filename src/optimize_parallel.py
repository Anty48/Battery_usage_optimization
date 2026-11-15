"""
optimize_parallel.py — Launches several optimize_potential.py workers in parallel (different seeds, slight
variations of the scenario sample size) plus one in --perfect mode.

    python src/optimize_parallel.py --workers 4 --minutes 40
Results: results/opt/best.json, best_perfect.json, worker_*.jsonl
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE.parent / "results" / "opt"; LOGS.mkdir(parents=True, exist_ok=True)
ap = argparse.ArgumentParser()
ap.add_argument("--workers", type=int, default=4); ap.add_argument("--minutes", type=float, default=40)
ap.add_argument("--no_perfect", action="store_true")
a = ap.parse_args()
procs = []
for i in range(a.workers):
    args = [sys.executable, str(HERE / "optimize_potential.py"), "--seed", str(100 + i), "--minutes", str(a.minutes),
            "--n_real", str(3 + i % 3), "--n_pert", str(3 + (i + 1) % 3), "--maxfev", str(28 + 4 * (i % 2))]
    procs.append(subprocess.Popen(args, stdout=open(LOGS / f"output_{100 + i}.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT))
if not a.no_perfect:
    args = [sys.executable, str(HERE / "optimize_potential.py"), "--seed", "7", "--minutes", str(a.minutes), "--perfect", "--n_real", "4", "--maxfev", "24"]
    procs.append(subprocess.Popen(args, stdout=open(LOGS / "output_perfect.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT))
print(f"{len(procs)} workers launched ({a.minutes} min)")
for p in procs:
    p.wait()
print("all finished")
