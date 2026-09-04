#!/usr/bin/env python3
"""Controlled preconditioning check for the bistability claim.

Four convex runs at hetero/poisson/med/primary cap, alternating board state:
cold (idle until T <= 50.0 C) vs hot (300 s three-tenant saturate soak, then
start immediately). If starting temperature causes the binding/slack split,
cold runs should stay slack and hot runs should bind. Reuses campaign2's
execute() so tenants, controller, cgroups, and logging are identical to the
main campaign. Run dirs use rep numbers 91..94 so nothing collides.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.expanduser("~/thermal2"))
import campaign2 as c2

T2 = os.path.expanduser("~/thermal2")
TEMP_SYS = "/sys/class/thermal/thermal_zone0/temp"


def temp():
    return int(open(TEMP_SYS).read()) / 1000.0


def wait_cold(target=50.0, timeout=1200):
    t0 = time.time()
    while time.time() - t0 < timeout:
        t = temp()
        if t <= target:
            return t
        time.sleep(15)
    return temp()


def soak(seconds=300):
    procs = []
    for i, m in enumerate(["mnv2", "resnet18", "squeezenet"]):
        cmd = [c2.PY, f"{T2}/tenant2.py", "--model", c2.MODELS[m],
               "--tenant-id", f"soak{i}", "--arrival", "saturate",
               "--rate", "1", "--duration", str(seconds),
               "--seed", str(7 + i), "--output", f"/tmp/soak_{i}.csv"]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.STDOUT))
    for p in procs:
        try:
            p.wait(timeout=seconds + 60)
        except subprocess.TimeoutExpired:
            p.terminate()
    return temp()


def main():
    calib = json.load(open(f"{T2}/calib.json"))
    caps = c2.caps_from(calib)
    c2.PRIMARY_CAP[0] = caps["primary"]
    c2.setup_cgroups()
    plan = [("cold", 91), ("hot", 92), ("cold", 93), ("hot", 94)]
    results = []
    for cond, rep in plan:
        if cond == "cold":
            t_pre = wait_cold()
        else:
            t_pre = soak(300)
        r = dict(mix="hetero", load="med", rep=rep, mode="convex",
                 arrival="poisson", t_cap=caps["primary"])
        t_start = temp()
        print(f"[preheat] {cond} r{rep}: pre={t_pre:.1f} start={t_start:.1f}",
              flush=True)
        status = c2.execute(r, calib)
        results.append(dict(cond=cond, rep=rep, t_pre=t_pre,
                            t_start=t_start, status=status,
                            run_id=c2.run_id(r)))
        json.dump(results, open(f"{T2}/preheat_results.json", "w"), indent=1)
        time.sleep(10)
    print("[preheat] complete", flush=True)


if __name__ == "__main__":
    main()
