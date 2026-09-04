#!/usr/bin/env python3
"""Aggregate the redo campaign into all_results2.json.

Per run: per-tenant goodput/violation/latency percentiles under two post-hoc
SLA levels (tight = 2.5x solo median service latency, loose = 6x), drops, and
controller-side thermal adherence. Warmup rows are discarded.
"""
import csv, glob, json, os

import numpy as np

T2 = os.path.expanduser("~/thermal2")
CALIB = json.load(open(f"{T2}/calib.json"))
SLA_FACTORS = {"tight": 2.5, "loose": 6.0}


def tenant_stats(path, model_key, run_dur):
    solo = CALIB["models"][model_key]["solo_med_ms"]
    lat = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row["warmup"] == "1":
                continue
            lat.append(float(row["latency_ms"]))
    meta = path + ".meta"
    drops = 0
    if os.path.exists(meta):
        for line in open(meta):
            if line.startswith("dropped="):
                drops = int(line.split("=")[1])
    lat = np.array(lat)
    span = run_dur - 20.0
    out = {"n": int(len(lat)), "drops": drops,
           "p50_ms": float(np.percentile(lat, 50)) if len(lat) else None,
           "p95_ms": float(np.percentile(lat, 95)) if len(lat) else None,
           "p99_ms": float(np.percentile(lat, 99)) if len(lat) else None,
           "throughput": len(lat) / span}
    for name, k in SLA_FACTORS.items():
        sla = k * solo
        met = int((lat <= sla).sum()) if len(lat) else 0
        out[f"sla_{name}_ms"] = sla
        out[f"goodput_{name}"] = met / span
        # dropped requests are violated requests
        out[f"viol_{name}"] = 1.0 - met / max(len(lat) + drops, 1)
    return out


def controller_stats(path, t_cap):
    T, agg, solver = [], [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            if float(row["t_s"]) < 20.0:
                continue
            T.append(float(row["T_c"]))
            agg.append(float(row["agg_duty"]))
            solver.append(float(row["solver_ms"]))
    T = np.array(T)
    return {"T_mean": float(T.mean()), "T_max": float(T.max()),
            "cap_exceed_frac": float((T > t_cap + 0.5).mean()),
            "agg_duty_mean": float(np.mean(agg)),
            "solver_ms_mean": float(np.mean(solver))}


def main():
    results = {}
    for d in sorted(glob.glob(f"{T2}/logs/*/")):
        rid = os.path.basename(d.rstrip("/"))
        if not os.path.exists(f"{d}/_DONE"):
            continue
        cfg = json.load(open(f"{d}/config.json"))
        r = {"config": cfg, "tenants": {}, }
        for i, m in enumerate(cfg["models"]):
            r["tenants"][f"t{i}_{m}"] = tenant_stats(
                f"{d}/latency_t{i}_{m}.csv", m, cfg["duration"])
        r["controller"] = controller_stats(f"{d}/controller.csv", cfg["t_cap"])
        # system-level rollups
        ts = r["tenants"].values()
        for name in SLA_FACTORS:
            r[f"goodput_{name}"] = sum(t[f"goodput_{name}"] for t in ts)
            r[f"viol_{name}"] = float(np.mean([t[f"viol_{name}"] for t in ts]))
        r["p99_worst_ms"] = max(t["p99_ms"] or 0 for t in ts)
        r["throughput"] = sum(t["throughput"] for t in ts)
        results[rid] = r
    out = f"{T2}/all_results2.json"
    json.dump(results, open(out, "w"), indent=1)
    print(f"{len(results)} runs -> {out}")

    # quick regime table on primary-cap poisson cells
    print("\nmix load mode | goodput_t viol_t% p99w | T_max aggduty (mean over reps)")
    cells = {}
    for rid, r in results.items():
        c = r["config"]
        if c["arrival"] != "poisson" or "cap" in rid.replace(c["mix"], ""):
            pass
        key = (c["mix"], c["load"], c["mode"], c["t_cap"])
        cells.setdefault(key, []).append(r)
    for key in sorted(cells):
        rs = cells[key]
        gp = np.mean([r["goodput_tight"] for r in rs])
        vi = np.mean([r["viol_tight"] for r in rs]) * 100
        p99 = np.mean([r["p99_worst_ms"] for r in rs])
        tm = np.mean([r["controller"]["T_max"] for r in rs])
        ad = np.mean([r["controller"]["agg_duty_mean"] for r in rs])
        print(f"{key[0]:6s} {key[1]:7s} {key[2]:9s} cap{key[3]:.0f} | "
              f"{gp:6.1f} {vi:5.1f} {p99:7.0f} | {tm:5.1f} {ad:4.2f} (n={len(rs)})")


if __name__ == "__main__":
    main()
