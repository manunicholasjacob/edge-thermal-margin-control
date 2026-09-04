#!/usr/bin/env python3
"""Thermal-margin controller redo: five policies, cgroup-v2 duty enforcement.

Modes
  convex    the paper's mechanism: maximize sum_i w_i log(mu_i(x_i)) subject to
            the coupling-law temperature cap, solved with cvxpy each tick
  admission the simple aggregate alternative (Bamberg's hypothesis): invert the
            coupling law once per tick to an aggregate duty budget, split equally
  matched   equal split replaying the per-second aggregate duty trace of a
            given convex run (utilization-matched control)
  quota     static per-tenant duty cap (0.6)
  equal     conventional CPU sharing: no caps at all (OS scheduler fair-shares)

Duty x_i in [0.05, 1.0] core-units enforced as cgroup cpu.max quota per tenant.
Thermal model: T_ss = b0 + slope * U_agg with U_agg (0-100) ~= 25 * sum(x) + U_bg.
"""
import argparse, csv, json, os, signal, time

import numpy as np
import psutil

THERMAL = "/sys/class/thermal/thermal_zone0/temp"
FREQ = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
CG = "/sys/fs/cgroup/thermal2"


def read_temp():
    return int(open(THERMAL).read()) / 1000.0


def read_freq():
    return int(open(FREQ).read()) / 1000.0


def set_duty(idx, duty):
    quota = "max" if duty >= 0.999 else str(max(int(duty * 100000), 5000))
    with open(f"{CG}/t{idx}/cpu.max", "w") as f:
        f.write(f"{quota} 100000")


def concave_mu(curve):
    """Return cvxpy-ready affine segments (slopes, intercepts) of the concave
    envelope of measured (duty, rate) points."""
    pts = sorted(curve)
    segs = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        a = (y2 - y1) / (x2 - x1)
        segs.append((a, y1 - a * x1))
    return segs


def solve_convex(segs_per_tenant, x_budget, n):
    import cvxpy as cp
    x = cp.Variable(n)
    mus = []
    for i, segs in enumerate(segs_per_tenant):
        exprs = [a * x[i] + b for a, b in segs]
        mus.append(cp.minimum(*exprs) if len(exprs) > 1 else exprs[0])
    obj = cp.Maximize(cp.sum([cp.log(m + 1e-3) for m in mus]) / n)
    cons = [x >= 0.05, x <= 1.0, cp.sum(x) <= x_budget]
    prob = cp.Problem(obj, cons)
    try:
        prob.solve()
    except Exception:
        try:
            prob.solve(solver=cp.SCS)
        except Exception:
            pass
    if x.value is None or prob.status not in ("optimal", "optimal_inaccurate"):
        return [min(1.0, x_budget / n)] * n
    return [float(np.clip(v, 0.05, 1.0)) for v in x.value]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["convex", "admission", "matched", "quota", "equal"], required=True)
    ap.add_argument("--calib", default=os.path.expanduser("~/thermal2/calib.json"))
    ap.add_argument("--models", nargs="+", required=True, help="model keys per tenant, in cgroup order")
    ap.add_argument("--t-cap", type=float, default=60.0)
    ap.add_argument("--duration", type=float, default=180.0)
    ap.add_argument("--replay", help="controller csv of a convex run (matched mode)")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    calib = json.load(open(args.calib))
    b0 = calib["idle_temp_c"]
    slope = calib["slope_c_per_pct"]
    u_bg = calib.get("bg_util_pct", 3.0)
    n = len(args.models)
    segs = [concave_mu(calib["models"][m]["duty_curve"]) for m in args.models]

    # aggregate duty budget from the steady-state coupling law
    u_max = max((args.t_cap - b0) / slope - u_bg, 5.0)      # percent, 0-100
    x_budget = min(max(u_max / 25.0, n * 0.05), float(n))    # core-units

    replay = None
    if args.mode == "matched":
        rows = list(csv.DictReader(open(args.replay)))
        replay = [float(r["agg_duty"]) for r in rows]

    running = [True]
    signal.signal(signal.SIGTERM, lambda *_: running.__setitem__(0, False))
    signal.signal(signal.SIGINT, lambda *_: running.__setitem__(0, False))
    psutil.cpu_percent(interval=None)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    t0 = time.time()
    step = 0
    with open(args.output, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["step", "t_s", "T_c", "T_pred_c", "freq_mhz", "util_pct",
                    "solver_ms", "mode", "agg_duty"] + [f"duty{i}" for i in range(n)])
        while running[0] and time.time() - t0 < args.duration:
            tick = time.time()
            T = read_temp()
            util = psutil.cpu_percent(interval=None)
            s0 = time.perf_counter()
            if args.mode in ("convex", "admission") and step > 0:
                # integral action: the steady-state law seeds the budget, the
                # measured temperature error trims it (identical for both modes,
                # so they differ only in how the budget is split)
                x_budget = float(np.clip(x_budget + 0.05 * (args.t_cap - T),
                                         n * 0.05, float(n)))
            if args.mode == "convex":
                duties = solve_convex(segs, x_budget, n)
            elif args.mode == "admission":
                duties = [min(1.0, x_budget / n)] * n
            elif args.mode == "matched":
                agg = replay[min(step, len(replay) - 1)]
                duties = [float(np.clip(agg / n, 0.05, 1.0))] * n
            elif args.mode == "quota":
                duties = [0.6] * n
            else:  # equal = conventional sharing, no caps
                duties = [1.0] * n
            solver_ms = (time.perf_counter() - s0) * 1000
            for i, d in enumerate(duties):
                set_duty(i, d)
            agg = sum(duties)
            t_pred = b0 + slope * (25.0 * agg + u_bg)
            w.writerow([step, f"{tick - t0:.2f}", f"{T:.2f}", f"{t_pred:.2f}",
                        f"{read_freq():.0f}", f"{util:.1f}", f"{solver_ms:.2f}",
                        args.mode, f"{agg:.4f}"] + [f"{d:.4f}" for d in duties])
            f.flush()
            step += 1
            time.sleep(max(0.0, 1.0 - (time.time() - tick)))

    for i in range(n):  # leave cgroups open
        set_duty(i, 1.0)


if __name__ == "__main__":
    main()
