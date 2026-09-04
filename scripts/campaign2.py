#!/usr/bin/env python3
"""Orchestrator for the thermal-margin redo campaign.

Builds the run matrix, executes runs sequentially (one heavy job at a time),
places each tenant in its cgroup, starts the controller, waits, and marks each
run dir with _DONE so the campaign is resumable. matched runs replay the convex
run of the same cell/rep and are ordered after it.
"""
import csv, itertools, json, os, signal, subprocess, sys, time

HOME = os.path.expanduser("~")
T2 = f"{HOME}/thermal2"
LOGS = f"{T2}/logs"
CG = "/sys/fs/cgroup/thermal2"
PY = f"{HOME}/multi_constraint_edge_inference/venv/bin/python"

MODELS = {
    "mnv2": f"{HOME}/multi_constraint_edge_inference/models/mobilenetv2.onnx",
    "resnet18": f"{HOME}/multi_constraint_edge_inference/models/resnet18.onnx",
    "squeezenet": f"{HOME}/multi_constraint_edge_inference/models/squeezenet.onnx",
}
MIXES = {"homo": ["mnv2", "mnv2", "mnv2"],
         "hetero": ["mnv2", "resnet18", "squeezenet"]}
LOAD_FRACS = {"low": 0.3, "med": 0.5, "high": 0.7, "extreme": 1.0}
DUR = 180
GAP = 10


def caps_from(calib):
    lo, hi = calib["idle_temp_c"], calib["soak_temp_c"]
    band = lambda f: round(lo + f * (hi - lo), 1)
    return {"primary": band(0.60), "tight": band(0.35), "loose": band(0.85)}


def build_matrix(caps):
    runs = []
    # core: poisson x {convex, matched, equal, admission} x mixes x 3 reps
    for mix, load, rep in itertools.product(("homo", "hetero"),
                                            ("low", "med", "high", "extreme"),
                                            (1, 2, 3)):
        for mode in ("convex", "matched", "equal", "admission"):
            runs.append(dict(mix=mix, load=load, rep=rep, mode=mode,
                             arrival="poisson", t_cap=caps["primary"]))
    # secondary
    for mode in ("convex", "matched", "equal", "admission"):
        for rep in (1, 2):
            runs.append(dict(mix="hetero", load="med", rep=rep, mode=mode,
                             arrival="onoff", t_cap=caps["primary"]))
    for mix in ("homo", "hetero"):
        for mode in ("convex", "equal"):
            for rep in (1, 2):
                runs.append(dict(mix=mix, load="extreme", rep=rep, mode=mode,
                                 arrival="saturate", t_cap=caps["primary"]))
    for load in ("med", "high"):
        for rep in (1, 2):
            runs.append(dict(mix="hetero", load=load, rep=rep, mode="quota",
                             arrival="poisson", t_cap=caps["primary"]))
    for t_cap in (caps["tight"], caps["loose"]):
        for mode in ("convex", "admission"):
            for rep in (1, 2):
                runs.append(dict(mix="hetero", load="med", rep=rep, mode=mode,
                                 arrival="poisson", t_cap=t_cap))
    return runs


PRIMARY_CAP = [None]


def run_id(r):
    cap = ("" if PRIMARY_CAP[0] is None or r["t_cap"] == PRIMARY_CAP[0]
           else f"_cap{r['t_cap']:.0f}".replace(".", "p"))
    return f"{r['mix']}_{r['arrival']}_{r['load']}_{r['mode']}{cap}_r{r['rep']}"


def convex_partner(r):
    p = dict(r, mode="convex")
    return run_id(p)


def setup_cgroups(n=3):
    for i in range(n):
        os.makedirs(f"{CG}/t{i}", exist_ok=True)


def execute(r, calib):
    rid = run_id(r)
    d = f"{LOGS}/{rid}"
    if os.path.exists(f"{d}/_DONE"):
        return "skip"
    os.makedirs(d, exist_ok=True)
    models = MIXES[r["mix"]]
    rates = {m: calib["models"][m]["solo_rate"] * LOAD_FRACS[r["load"]]
             for m in set(models)}
    json.dump({**r, "run_id": rid, "duration": DUR,
               "rates": rates, "models": models,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
              open(f"{d}/config.json", "w"), indent=1)

    tenants = []
    for i, m in enumerate(models):
        cmd = [PY, f"{T2}/tenant2.py", "--model", MODELS[m],
               "--tenant-id", f"t{i}_{m}", "--arrival", r["arrival"],
               "--rate", str(rates[m]), "--duration", str(DUR + 5),
               "--seed", str(100 * r["rep"] + i),
               "--output", f"{d}/latency_t{i}_{m}.csv"]
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.STDOUT)
        subprocess.run(["sudo", "tee", f"{CG}/t{i}/cgroup.procs"],
                       input=str(p.pid), text=True, stdout=subprocess.DEVNULL)
        tenants.append(p)

    time.sleep(2)  # let sessions load before control starts
    ctrl_cmd = [PY, f"{T2}/controller2.py", "--mode", r["mode"],
                "--models", *models, "--t-cap", str(r["t_cap"]),
                "--duration", str(DUR),
                "--output", f"{d}/controller.csv"]
    if r["mode"] == "matched":
        ctrl_cmd += ["--replay", f"{LOGS}/{convex_partner(r)}/controller.csv"]
    ctrl = subprocess.run(ctrl_cmd, capture_output=True, text=True)
    if ctrl.returncode != 0:
        open(f"{d}/controller.err", "w").write(ctrl.stdout + ctrl.stderr)

    for p in tenants:
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.terminate()
    ok = ctrl.returncode == 0 and all(
        os.path.getsize(f"{d}/latency_t{i}_{m}.csv") > 500
        for i, m in enumerate(models))
    if ok:
        open(f"{d}/_DONE", "w").write("ok\n")
    return "ok" if ok else "FAIL"


def main():
    calib = json.load(open(f"{T2}/calib.json"))
    caps = caps_from(calib)
    PRIMARY_CAP[0] = caps["primary"]
    print(f"[campaign] caps: {caps} (band {calib['idle_temp_c']}-{calib['soak_temp_c']} C)")
    setup_cgroups()
    runs = build_matrix(caps)
    # order: convex before matched inside each cell, otherwise stable
    runs.sort(key=lambda r: (run_id(r).rsplit("_", 2)[0].replace("convex", "0convex")
                             .replace("matched", "1matched"), r["rep"]))
    print(f"[campaign] {len(runs)} runs planned")
    done = 0
    for r in runs:
        rid = run_id(r)
        t0 = time.time()
        status = execute(r, calib)
        done += 1
        print(f"[{done}/{len(runs)}] {rid}: {status} ({time.time() - t0:.0f}s)",
              flush=True)
        if status != "skip":
            time.sleep(GAP)
    print("[campaign] complete")


if __name__ == "__main__":
    main()
