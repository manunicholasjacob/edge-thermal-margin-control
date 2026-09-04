#!/usr/bin/env python3
"""Calibration for the redo campaign.

Measures, per model: solo service rate at duty levels {0.25, 0.5, 0.75, 1.0}
(cgroup-enforced, single-threaded ORT), giving the mu_i(x) curves the convex
controller uses. Also measures idle temperature (law intercept for this ambient
and cooling) and background utilization. Writes ~/thermal2/calib.json.
"""
import json, os, subprocess, time

import numpy as np
import psutil

MODELS = {
    "mnv2": "/home/manu/multi_constraint_edge_inference/models/mobilenetv2.onnx",
    "resnet18": "/home/manu/multi_constraint_edge_inference/models/resnet18.onnx",
    "squeezenet": "/home/manu/multi_constraint_edge_inference/models/squeezenet.onnx",
}
CG = "/sys/fs/cgroup/thermal2"
SLOPE = 0.1748  # degC per % aggregate utilization, from the 13-hour campaign


def read_temp():
    return int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000.0


def measure_idle(seconds=45):
    psutil.cpu_percent(interval=None)
    temps, utils = [], []
    for _ in range(seconds):
        time.sleep(1)
        temps.append(read_temp())
        utils.append(psutil.cpu_percent(interval=None))
    return float(np.median(temps)), float(np.median(utils))


def rate_at_duty(model_path, duty, seconds=18):
    import onnxruntime as ort
    quota = "max" if duty >= 0.999 else str(int(duty * 100000))
    with open(f"{CG}/t0/cpu.max", "w") as f:
        f.write(f"{quota} 100000")
    pid = os.getpid()
    subprocess.run(["sudo", "tee", f"{CG}/t0/cgroup.procs"],
                   input=str(pid), text=True, stdout=subprocess.DEVNULL)
    try:
        so = ort.SessionOptions()
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        s = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
        inp = s.get_inputs()[0]
        shape = [d if isinstance(d, int) else 1 for d in inp.shape]
        x = np.random.randn(*shape).astype(np.float32)
        for _ in range(3):
            s.run(None, {inp.name: x})
        lats = []
        t0 = time.perf_counter()
        n = 0
        while time.perf_counter() - t0 < seconds:
            a = time.perf_counter()
            s.run(None, {inp.name: x})
            lats.append((time.perf_counter() - a) * 1000)
            n += 1
        rate = n / (time.perf_counter() - t0)
        return rate, float(np.median(lats))
    finally:
        # move self back out and lift the cap
        subprocess.run(["sudo", "tee", "/sys/fs/cgroup/cgroup.procs"],
                       input=str(pid), text=True, stdout=subprocess.DEVNULL)
        with open(f"{CG}/t0/cpu.max", "w") as f:
            f.write("max 100000")


def soak(seconds=150):
    """Three saturating single-thread tenants, uncapped; measure the hot end of
    today's thermal band and refit the coupling slope for this environment."""
    procs = []
    for i, path in enumerate(MODELS.values()):
        p = subprocess.Popen(
            [os.path.expanduser("~/multi_constraint_edge_inference/venv/bin/python"),
             os.path.expanduser("~/thermal2/tenant2.py"),
             "--model", path, "--tenant-id", f"soak{i}", "--arrival", "saturate",
             "--duration", str(seconds), "--warmup-s", "0",
             "--output", f"/tmp/soak_{i}.csv"],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        procs.append(p)
    temps, utils = [], []
    psutil.cpu_percent(interval=None)
    t0 = time.time()
    while time.time() - t0 < seconds:
        time.sleep(1)
        temps.append(read_temp())
        utils.append(psutil.cpu_percent(interval=None))
    for p in procs:
        p.wait(timeout=30)
    k = len(temps) * 2 // 5          # last 60% = settled
    return float(np.median(temps[-k:])), float(np.median(utils[-k:]))


def main():
    idle_t, bg_u = measure_idle()
    soak_t, soak_u = soak()
    slope_today = max((soak_t - idle_t) / max(soak_u - bg_u, 1.0), 0.005)
    out = {"idle_temp_c": idle_t, "bg_util_pct": bg_u,
           "soak_temp_c": soak_t, "soak_util_pct": soak_u,
           "slope_c_per_pct": round(slope_today, 4),
           "slope_mar2026_c_per_pct": SLOPE,
           "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "models": {}}
    time.sleep(45)  # cool back toward idle before the duty curves
    for key, path in MODELS.items():
        curve = []
        for duty in (0.25, 0.5, 0.75, 1.0):
            r, med = rate_at_duty(path, duty)
            curve.append([duty, round(r, 2)])
            if duty == 1.0:
                out["models"][key] = {"solo_rate": round(r, 2),
                                      "solo_med_ms": round(med, 2),
                                      "duty_curve": curve}
            time.sleep(3)
    with open(os.path.expanduser("~/thermal2/calib.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
