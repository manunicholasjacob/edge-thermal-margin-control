#!/usr/bin/env python3
"""Check realistic_extreme + no-control baseline for Paper 1's 4.6x goodput claim."""
import glob, os, csv
from collections import defaultdict
BASE = os.path.expanduser("~/thermal_paper/logs")

def gp(d, dur=150.0):
    lat=[]; viol=0
    for f in glob.glob(os.path.join(d,"latency_model_*.csv")):
        with open(f) as fh:
            for r in csv.DictReader(fh):
                try:
                    L=float(r["latency_ms"]); v=int(float(r.get("sla_violated",0)))
                except: continue
                lat.append(L); viol+=v
    if not lat: return None
    n=len(lat); lat.sort()
    return dict(n=n, meet=n-viol, viol=100*viol/n, gp=(n-viol)/dur,
                mean=sum(lat)/n, p99=lat[int(0.99*n)])

hdr = "{:34s} {:>6s} {:>6s} {:>6s} {:>6s} {:>8s} {:>8s}".format(
    "scenario","reqs","met","viol%","gp/s","mean","p99")
print("REALISTIC scenarios + no-control baseline\n"); print(hdr); print("-"*78)
by=defaultdict(list)
dirs = sorted(glob.glob(os.path.join(BASE,"realistic_*")))
for d in dirs:
    name=os.path.basename(d); g=gp(d)
    if not g: continue
    load = "extreme" if "extreme" in name else ("high" if "high" in name else "?")
    mode = name.split("_")[-1]
    by[(load,mode)].append(g["gp"])
    print("{:34s} {:6d} {:6d} {:5.1f}% {:5.1f} {:6.1f}ms {:7.1f}ms".format(
        name, g["n"], g["meet"], g["viol"], g["gp"], g["mean"], g["p99"]))
print()
for load in ["extreme","high"]:
    cv=by.get((load,"convex"),[]); eq=by.get((load,"equal"),[])
    qt=by.get((load,"quota"),[]); nc=by.get((load,"noctl"),[])
    if not cv: continue
    c=sum(cv)/len(cv)
    print(f"[{load}] convex goodput = {c:.2f} r/s")
    if eq: print(f"   convex/equal = {c/(sum(eq)/len(eq)):.2f}x")
    if qt: print(f"   convex/quota = {c/(sum(qt)/len(qt)):.2f}x")
    if nc: print(f"   convex/noctl = {c/(sum(nc)/len(nc)):.2f}x  (paper claims 4.6x vs baselines)")
