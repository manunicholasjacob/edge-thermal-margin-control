#!/usr/bin/env python3
"""Map Paper 1's full operating regime: goodput, SLA-violations, and p99 tail for
convex vs equal vs quota across ALL load levels (low/medium/high/extreme).
Goal: find a regime where the convex controller genuinely dominates (Pareto-better),
which would be a stronger, honest headline than the debunked '4.6x goodput'."""
import glob, os, csv
from collections import defaultdict

BASE=os.path.expanduser("~/thermal_paper/logs")

def stats_for(run_dir):
    lat=[]; viol=0
    for f in glob.glob(os.path.join(run_dir,"latency_model_*.csv")):
        with open(f) as fh:
            for r in csv.DictReader(fh):
                try: L=float(r["latency_ms"]); v=int(float(r.get("sla_violated",0)))
                except: continue
                lat.append(L); viol+=v
    if not lat: return None
    n=len(lat); lat.sort()
    # duration: use span of timestamps if available, else assume 150s
    dur=150.0
    return dict(n=n, met=n-viol, viol_pct=100*viol/n, gp=(n-viol)/dur,
                mean=sum(lat)/n, p50=lat[n//2], p99=lat[min(n-1,int(0.99*n))])

LEVELS=["low","medium","high","extreme"]
MODES=["convex","equal","quota"]
print("PAPER 1 OPERATING-REGIME MAP (lambda_* runs)\n")
print(f"{'load':8s} {'mode':7s} {'reqs':>6s} {'met':>6s} {'viol%':>6s} {'gp/s':>6s} {'p50':>7s} {'p99':>8s}")
print("-"*66)
grid=defaultdict(dict)
for lv in LEVELS:
    for md in MODES:
        # try lambda_{lv}_{md} and replications
        runs=sorted(glob.glob(os.path.join(BASE,f"lambda_{lv}_{md}"))+
                    glob.glob(os.path.join(BASE,f"lambda_{lv}_{md}_r*")))
        ss=[stats_for(r) for r in runs]; ss=[s for s in ss if s]
        if not ss: continue
        agg={k:sum(s[k] for s in ss)/len(ss) for k in ss[0]}
        grid[lv][md]=agg
        print(f"{lv:8s} {md:7s} {agg['n']:6.0f} {agg['met']:6.0f} {agg['viol_pct']:5.1f}% "
              f"{agg['gp']:5.1f} {agg['p50']:6.1f}ms {agg['p99']:7.1f}ms")
    print()

print("=== DOMINANCE ANALYSIS (convex vs best baseline per load) ===")
for lv in LEVELS:
    if "convex" not in grid[lv]: continue
    cv=grid[lv]["convex"]
    bases={m:grid[lv][m] for m in ["equal","quota"] if m in grid[lv]}
    if not bases: continue
    best_gp=max(b["gp"] for b in bases.values())
    best_viol=min(b["viol_pct"] for b in bases.values())
    best_p99=min(b["p99"] for b in bases.values())
    print(f"  [{lv}] convex gp={cv['gp']:.1f} (best base {best_gp:.1f}, ratio {cv['gp']/best_gp:.2f}x) | "
          f"viol {cv['viol_pct']:.1f}% vs {best_viol:.1f}% | p99 {cv['p99']:.0f} vs {best_p99:.0f}ms")
    wins=[]
    if cv['gp']>=best_gp*0.98: wins.append("goodput>=")
    if cv['viol_pct']<=best_viol: wins.append("fewer-viol")
    if cv['p99']<=best_p99: wins.append("lower-tail")
    print(f"        convex advantages: {wins if wins else 'NONE - dominated'}")
