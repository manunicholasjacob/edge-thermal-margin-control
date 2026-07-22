#!/usr/bin/env python3
"""Paper 1 honest figure: the operating-regime map. (a) goodput vs load shows the
convex controller is throughput-dominated by equal-share; (b) in the moderate regime
it buys a large tail-latency / SLA-violation reduction. All values measured on Pi 5."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, numpy as np

plt.rcParams.update({"font.size":8,"font.family":"serif","figure.dpi":300})
CVX="#c05621"; EQ="#2b6cb0"; QT="#718096"; INK="#1a1a1a"

# lambda sweep (measured): goodput r/s and violation %
loads=["low","medium","high","extreme"]
gp={"convex":[10.5,11.8,6.9,1.8],"equal":[34.0,24.9,9.9,1.8],"quota":[30.2,21.6,9.1,1.7]}
x=np.arange(len(loads)); w=0.26

fig,(ax1,ax2)=plt.subplots(1,2,figsize=(7.0,2.6))

# (a) goodput vs load
ax1.bar(x-w, gp["convex"],w,label="convex (ours)",color=CVX,edgecolor=INK,lw=.4)
ax1.bar(x,   gp["equal"], w,label="equal-share",color=EQ,edgecolor=INK,lw=.4)
ax1.bar(x+w, gp["quota"], w,label="CPU quota",color=QT,edgecolor=INK,lw=.4)
ax1.set_xticks(x); ax1.set_xticklabels(loads,fontsize=7)
ax1.set_ylabel("SLA-met goodput (req/s)")
ax1.set_title("(a) Throughput regime: convex is dominated",fontsize=8)
ax1.legend(fontsize=6.5,loc="upper right"); ax1.spines[["top","right"]].set_visible(False)

# (b) moderate-regime tradeoff (comparison scenario): p99 and violations
metrics=["p99 tail (ms)","SLA viol. (%)","goodput (r/s)"]
cvx=[28,0.0,109.5]; eq=[103,1.1,171.8]
# normalize each metric to equal-share=1 for a paired view; annotate raw
xb=np.arange(len(metrics)); wb=0.36
cvx_n=[c/e if e else 0 for c,e in zip(cvx,eq)]
eq_n=[1,1,1]
b1=ax2.bar(xb-wb/2,cvx_n,wb,label="convex",color=CVX,edgecolor=INK,lw=.4)
b2=ax2.bar(xb+wb/2,eq_n,wb,label="equal-share",color=EQ,edgecolor=INK,lw=.4)
for xi,(c,e) in enumerate(zip(cvx,eq)):
    ax2.text(xi-wb/2,(c/e if e else 0)+0.03,f"{c:g}",ha="center",fontsize=6,color=CVX)
    ax2.text(xi+wb/2,1.03,f"{e:g}",ha="center",fontsize=6,color=EQ)
ax2.set_xticks(xb); ax2.set_xticklabels(metrics,fontsize=6.5)
ax2.set_ylabel("relative to equal-share")
ax2.axhline(1.0,color=INK,lw=.6,ls="--")
ax2.set_title("(b) Moderate regime: tail/violation win,\nthroughput cost",fontsize=8)
ax2.legend(fontsize=6.5); ax2.spines[["top","right"]].set_visible(False)
ax2.set_ylim(0,2.0)

fig.tight_layout(pad=0.6)
fig.savefig("fig_regime.pdf",bbox_inches="tight"); fig.savefig("fig_regime.png",bbox_inches="tight",dpi=150)
print("wrote fig_regime.pdf/.png")
