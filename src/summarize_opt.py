"""
summarize_opt.py — Summarises the potential optimisation (results/opt/*) in a figure and a LaTeX macro.

    python src/summarize_opt.py -> report/fig/potential.pdf, report/macros_opt.tex, results/opt/summary.json
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import glob
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from src.style import plt, PALETTE, INK, INK2, RED   # noqa: E402

OPT = ROOT / "results" / "opt"; FIG = ROOT / "report" / "fig"; FIG.mkdir(parents=True, exist_ok=True)
START = {"theta": [0.5, 1.0, 0.02, 1.0, 0.0, 0.0, 1.0, 1.0], "real_score": 18.26}   # hand-tuned analog agent
best = json.loads((OPT / "best.json").read_text(encoding="utf-8"))
perf = json.loads((OPT / "best_perfect.json").read_text(encoding="utf-8")) if (OPT / "best_perfect.json").exists() else None
oracle = json.loads((ROOT / "results" / "oracle.json").read_text(encoding="utf-8"))["global_oracle"]["score"]
recs = [json.loads(line) for f in sorted(glob.glob(str(OPT / "worker_*.jsonl"))) for line in open(f, encoding="utf-8") if line.strip()]
normal = [r for r in recs if not r["perfect"]]; perfect = [r for r in recs if r["perfect"]]
print(f"{len(normal)} local optimisations, {len(perfect)} perfect-information ones; record {best['real_score']:.3f}; perfect {perf['real_score'] if perf else '-'}")

fig, ax = plt.subplots(1, 2, figsize=(7.0, 2.6), gridspec_kw={"wspace": 0.3})
for i, seed in enumerate(sorted({r["seed"] for r in normal})):
    rs = [r for r in normal if r["seed"] == seed]
    ax[0].plot([r["iter"] for r in rs], [r["real_score"] for r in rs], "o-", color=PALETTE[i % len(PALETTE)], label=f"worker {seed}", ms=4)
ax[0].axhline(START["real_score"], color="#898781", ls="--", lw=1)
ax[0].text(1, START["real_score"] + 0.01, f"starting point {START['real_score']:.2f}", fontsize=7, color=INK2)
ax[0].set_title("Real score per local optimisation", fontsize=9); ax[0].set_xlabel("worker iteration")
ax[0].legend(fontsize=6.5, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.28), handlelength=1.2, columnspacing=0.8)
if perfect:
    ax[1].plot([r["iter"] for r in perfect], [r["real_score"] for r in perfect], "o-", color=INK, ms=4)
    ax[1].axhline(oracle, color=RED, ls="--", lw=1); ax[1].text(1, oracle + 0.01, f"global oracle {oracle:.2f}", fontsize=7, color=INK2)
ax[1].set_title("Perfect information (control only)", fontsize=9); ax[1].set_xlabel("iteration")
fig.savefig(FIG / "potential.pdf"); fig.savefig(FIG / "potential.png", dpi=150)


def row(name, th, sc):
    return name + " & " + " & ".join(f"{v:.{3 if j == 2 else 2}f}" for j, v in enumerate(th)) + f" & {sc:.2f}\\\\\n"


table = row("starting point", START["theta"], START["real_score"]) + row("\\textbf{potential optimum}", best["theta"], best["real_score"])
if perf:
    table += row("perfect information (control)", perf["theta"], perf["real_score"])
text = f"""\\begin{{table}}[H]\\centering\\small
\\begin{{tabular}}{{l{'c' * 8}c}}\\toprule
 & $z$ & $V/\\bar\\lambda$ & $\\varepsilon$ & $\\alpha_D$ & $\\alpha_S$ & $\\alpha_\\lambda$ & $s_S$ & $s_\\lambda$ & \\textbf{{Real score}}\\\\\\midrule
{table}\\bottomrule\\end{{tabular}}
\\caption{{Coefficients before and after optimising the potential ({len(normal)} local Nelder--Mead runs in {len({r['seed'] for r in normal})} workers;
{sum(r['n_eval'] for r in normal)} scenario-set evaluations). ``Real score'': the 12 concatenated pseudo-test weeks. The last row is the
perfect-information case: the ceiling of the controller, with the global oracle at {oracle:.2f}.}}
\\end{{table}}
\\begin{{figure}}[H]\\centering\\includegraphics[width=\\linewidth]{{fig/potential.pdf}}
\\caption{{Left: real score reached by each worker after each local optimisation (the shared record only goes up). Right: the perfect-information worker.}}\\end{{figure}}
"""
(ROOT / "report" / "macros_opt.tex").write_text("\\newcommand{\\optResults}{" + text + "}\n", encoding="utf-8")
(OPT / "summary.json").write_text(json.dumps({"best": best, "perfect": perf, "n_normal": len(normal), "n_perfect": len(perfect)}, indent=1), encoding="utf-8")
print("macros_opt.tex and figure written")
