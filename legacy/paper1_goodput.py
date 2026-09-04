#!/usr/bin/env python3
"""Verify Paper 1's '4.6x higher goodput-at-SLA under extreme overcommit' claim.
Goodput-at-SLA = SLA-meeting requests per second (throughput of non-violated reqs).
Compute per mode (convex/equal/quota) from per-tenant latency logs under extreme load."""
import glob, os, csv
from collections import defaultdict

BASE=os.path.expanduser("~/thermal_paper/logs")

def goodput(run_dir, dur=150.0):
    """Return (total_reqs, sla_meeting, viol_pct, goodput_rps, mean_ms, p99_ms)."""
    lat=[]; viol=0; sla=None
    for f in glob.glob(os.path.join(run_dir,"latency_model_*.csv")):
        with open(f) as fh:
            for r in csv.DictReader(fh):
                try:
                    L=float(r["latency_ms"]); v=int(float(r.get("sla_violated",0)))
                    if sla is None and r.get("sla_ms"): sla=float(r["sla_ms"])
                except: continue
                lat.append(L); viol+=v
    if not lat: return None
    lat.sort(); n=len(lat); meet=n-viol
    p99=lat[min(n-1,int(0.99*n))]
    return dict(n=n, meet=meet, viol_pct=100*viol/n, gp_rps=meet/dur,
                mean=sum(lat)/n, p99=p99, sla=sla)

print("GOODPUT-AT-SLA under EXTREME overcommit (per-tenant latency logs)\n")
print(f"{'scenario':28s} {'mode':7s} {'reqs':>7s} {'SLA-met':>8s} {'viol%':>6s} {'gp(r/s)':>8s} {'mean':>7s} {'p99':>8s}")
print("-"*84)
scen=defaultdict(dict)
for d in sorted(glob.glob(os.path.join(BASE,"lambda_extreme_*"))):
    name=os.path.basename(d)
    mode=("convex" if "convex" in name else "equal" if "equal" in name else "quota" if "quota" in name else "?")
    g=goodput(d)
    if not g: continue
    scen[name]=(mode,g)
    print(f"{name:28s} {mode:7s} {g['n']:7d} {g['meet']:8d} {g['viol_pct']:5.1f}% "
          f"{g['gp_rps']:7.1f} {g['mean']:6.1f}ms {g['p99']:7.1f}ms")

# aggregate goodput by mode
print("\n=== goodput-at-SLA by mode (mean over replications) ===")
agg=defaultdict(list)
for name,(mode,g) in scen.items(): agg[mode].append(g['gp_rps'])
for mode in ["convex","equal","quota"]:
    if agg[mode]:
        m=sum(agg[mode])/len(agg[mode])
        print(f"  {mode:7s}: {m:.1f} req/s  (n_runs={len(agg[mode])})")
if agg["convex"] and agg["equal"]:
    cv=sum(agg["convex"])/len(agg["convex"]); eq=sum(agg["equal"])/len(agg["equal"])
    qt=sum(agg["quota"])/len(agg["quota"]) if agg["quota"] else eq
    print(f"\n  convex/equal goodput ratio = {cv/eq:.2f}x   (paper claims 4.6x)")
    print(f"  convex/quota goodput ratio = {cv/qt:.2f}x")
    print(f"  convex/best-baseline       = {cv/max(eq,qt):.2f}x")
