#!/usr/bin/env python3
"""Three-panel figure for the matched-baseline letter: SLA-met goodput, worst
p99, and T_max versus load, per policy (hetero mix, Poisson, primary cap)."""
import json
import os

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RES = json.load(open(os.path.join(HERE, "..", "data", "all_results2.json")))
CAL = json.load(open(os.path.join(HERE, "..", "data", "calib.json")))
P = round(CAL["idle_temp_c"] + 0.60 * (CAL["soak_temp_c"] - CAL["idle_temp_c"]), 1)

LOADS = ["low", "med", "high", "extreme"]
POLICIES = [("equal", "o-", "#444444"), ("convex", "s-", "#c0392b"),
            ("matched", "d--", "#2471a3"), ("admission", "^:", "#1e8449")]


def series(mode, key, path=None):
    ys = []
    for load in LOADS:
        vals = []
        for r in RES.values():
            c = r["config"]
            if (c["mix"], c["load"], c["mode"], c["arrival"], c["t_cap"]) == \
                    ("hetero", load, mode, "poisson", P):
                v = r
                for p in (path or key).split("."):
                    v = v[p]
                vals.append(v)
        ys.append(np.mean(vals) if vals else np.nan)
    return ys


fig, axs = plt.subplots(1, 3, figsize=(7.1, 2.1))
x = np.arange(len(LOADS))
for mode, style, color in POLICIES:
    axs[0].plot(x, series(mode, "goodput_tight"), style, color=color,
                label=mode, ms=3.5, lw=1.1)
    axs[1].semilogy(x, np.array(series(mode, "p99_worst_ms")) / 1000, style,
                    color=color, ms=3.5, lw=1.1)
    axs[2].plot(x, series(mode, "", "controller.T_max"), style, color=color,
                ms=3.5, lw=1.1)
axs[2].axhline(P, color="k", lw=0.7, ls="--")
axs[2].annotate(f"cap {P:g}$^\\circ$C", (0.02, P + 0.25), fontsize=6)
for ax, t, yl in zip(axs, ["(a) SLA-met goodput", "(b) worst-tenant p99",
                           "(c) $T_{max}$"],
                     ["req/s", "seconds (log)", "$^\\circ$C"]):
    ax.set_xticks(x)
    ax.set_xticklabels(LOADS, fontsize=7)
    ax.set_title(t, fontsize=8)
    ax.set_ylabel(yl, fontsize=7)
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.25, lw=0.4)
axs[0].legend(fontsize=6.5, frameon=False, loc="upper right")
fig.tight_layout(pad=0.4)
out = os.path.join(HERE, "..", "figures", "fig_matched.pdf")
fig.savefig(out, bbox_inches="tight")
print("wrote", out)
