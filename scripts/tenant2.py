#!/usr/bin/env python3
"""Real-inference tenant for the thermal-margin redo campaign.

One single-threaded ONNX Runtime session serving requests under an arrival
process. Open-loop modes (poisson, onoff) measure latency = completion - arrival
(queueing included); the closed-loop saturate mode measures service time and
throughput. A bounded FIFO queue drops arrivals past --queue-cap; drops are
logged and count as SLA violations in analysis.
"""
import argparse, collections, csv, os, signal, threading, time

import numpy as np


def build_session(model_path):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = 1
    so.inter_op_num_threads = 1
    sess = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    shape = [d if isinstance(d, int) else 1 for d in inp.shape]
    x = np.random.randn(*shape).astype(np.float32)
    return sess, inp.name, x


running = True


def stop(_sig, _frm):
    global running
    running = False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tenant-id", required=True)
    ap.add_argument("--arrival", choices=["poisson", "onoff", "saturate"], required=True)
    ap.add_argument("--rate", type=float, default=10.0, help="mean arrival rate req/s")
    ap.add_argument("--on-s", type=float, default=10.0)
    ap.add_argument("--off-s", type=float, default=5.0)
    ap.add_argument("--duration", type=float, default=180.0)
    ap.add_argument("--warmup-s", type=float, default=20.0)
    ap.add_argument("--queue-cap", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    rng = np.random.default_rng(args.seed)
    sess, iname, x = build_session(args.model)
    # warm the session before the clock starts
    for _ in range(3):
        sess.run(None, {iname: x})

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    q = collections.deque()
    lock = threading.Lock()
    dropped = [0]
    t0 = time.time()
    end_at = t0 + args.duration

    def arrivals():
        if args.arrival == "saturate":
            return
        state_on, switch_at = True, t0 + args.on_s
        while running and time.time() < end_at:
            now = time.time()
            if args.arrival == "onoff":
                if state_on and now >= switch_at:
                    state_on, switch_at = False, now + args.off_s
                elif not state_on and now >= switch_at:
                    state_on, switch_at = True, now + args.on_s
                if not state_on:
                    time.sleep(0.02)
                    continue
            gap = rng.exponential(1.0 / max(args.rate, 0.1))
            time.sleep(gap)
            with lock:
                if len(q) < args.queue_cap:
                    q.append(time.time())
                else:
                    dropped[0] += 1

    at = threading.Thread(target=arrivals, daemon=True)
    at.start()

    with open(args.output, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "tenant", "latency_ms", "service_ms", "qdepth", "warmup"])
        while running and time.time() < end_at:
            if args.arrival == "saturate":
                arrival = time.time()
            else:
                with lock:
                    arrival = q.popleft() if q else None
                if arrival is None:
                    time.sleep(0.005)
                    continue
            start = time.time()
            sess.run(None, {iname: x})
            done = time.time()
            with lock:
                depth = len(q)
            warm = 1 if (done - t0) < args.warmup_s else 0
            w.writerow([f"{done - t0:.3f}", args.tenant_id,
                        f"{(done - arrival) * 1000:.3f}",
                        f"{(done - start) * 1000:.3f}", depth, warm])
        f.flush()

    # summary trailer picked up by the orchestrator
    with open(args.output + ".meta", "w") as f:
        f.write(f"dropped={dropped[0]}\n")


if __name__ == "__main__":
    main()
