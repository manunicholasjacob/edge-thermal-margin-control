# Edge Thermal-Margin Control: a Matched-Baseline Study

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21844861.svg)](https://doi.org/10.5281/zenodo.21844861)

Reproducible artifact for **"When Thermal-Margin Control Helps and When It Hurts: A
Matched-Baseline Study of Convex Allocation for Multi-Tenant Edge Inference"** (revised
manuscript for IEEE Embedded Systems Letters, September 2026).

## Correction notice (September 2026)

An earlier version of this repository and manuscript reported that a convex thermal-margin
controller achieved zero SLA violations and a 3.7x p99 tail-latency reduction in a moderate-load
regime. **That claim is retracted.** Three flaws in the original March 2026 evaluation caused it,
found during the revision that an IEEE ESL Area Editor's review prompted:

1. The "inference tenants" were synthetic matrix-multiply processes, although the manuscript
   described them as MobileNetV2 tenants.
2. The thermal cap was set to 46.0 C, 0.4 C above the platform's idle intercept, so the
   controller throttled tenants to near-idle by construction. The manuscript did not state the
   cap value.
3. Per-request latency was measured as service time under closed-loop saturating tenants, so
   queueing delay did not exist by construction. The tail "win" was an artifact of never
   counting waiting time.

The September 2026 campaign redoes the experiment with real single-threaded ONNX tenants
(MobileNetV2, ResNet-18, SqueezeNet), open-loop Poisson / on-off / saturating arrivals with
latency measured from arrival to completion, cgroup-v2 `cpu.max` duty enforcement, caps placed
inside the platform's measured thermal band, and the two baselines the question actually needs:

- **matched** replays the convex allocator's own per-second aggregate duty trace as an equal
  split, isolating tenant-level allocation at identical aggregate throttling;
- **admission** computes the same coupling-law + integral-feedback aggregate budget and splits it
  equally, with no solver and no rate curves.

**Findings.** Where the cap binds, matched and admission reproduce the convex allocator on
goodput, violation rate, and tail latency: the aggregate budget carries every effect, and
tenant-level convexity is redundant. Equal sharing dominates goodput and tails wherever the cap
binds; what the cap buys is temperature (roughly 4-5 C of T_max at high load); and under
open-loop load, duty throttling converts thermal margin into queue depth, inflating p99 by an
order of magnitude at medium load. No cap placement or arrival process reproduces the retracted
result. Practitioner rule: enforce thermal caps by request-level admission, not duty throttling,
and skip the per-tenant solver if throttling is used.

The March 2026 logs and the superseded manuscript are retained under `legacy/` for provenance.

## Contents

```
paper/main_v3_matched.pdf    the revised letter
figures/fig_matched.pdf      load sweep: goodput / p99 / T_max per policy
scripts/
  tenant2.py                 ONNX tenant: open-loop queue, arrival->completion latency
  controller2.py             five policies; cgroup cpu.max enforcement; law+feedback budget
  calib2.py                  idle intercept, 150 s soak, per-model duty->rate curves
  campaign2.py               the 124-run matrix, resumable
  analyze2.py                per-run aggregation -> all_results2.json
  fill_numbers.py            all_results2.json -> every number in the manuscript
  gen_fig_matched.py         the figure
data/
  all_results2.json          aggregated results, all runs
  calib.json                 campaign calibration
  logs_convex_controllers/   per-second controller traces of the convex runs
legacy/                      March 2026 campaign (superseded; see correction notice)
```

## Reproduce

Analysis needs only numpy:

```bash
python scripts/fill_numbers.py   # regenerates every number in the manuscript
python scripts/gen_fig_matched.py
```

Re-running the campaign needs a Raspberry Pi 5 with onnxruntime, cvxpy, psutil, cgroup v2, and
sudo for cgroup process placement: `calib2.py` then `campaign2.py` (~7 hours).

## Citation

Manu Nicholas Jacob, 2026. MIT License. ORCID
[0009-0007-6589-6572](https://orcid.org/0009-0007-6589-6572).

## Preconditioning check (preheat/)

Four additional convex runs at medium load and the primary cap, run after the
main campaign at warmer daytime ambient (idle floor 48.5 C vs the calibrated
45.8 C), alternating idle-cooled starts with 300 s three-tenant pre-soaks
(`preheat2.py`). All four entered the binding state, the idle-cooled runs from
first ticks of 52.4-52.9 C, the same first-tick temperature at which an
overnight campaign run had stayed slack. Board history and ambient jointly set
the entry state; no start-time signal cleanly predicts it.

Note: in preheat_results.json, t_pre/t_start record board temperature when the
runner returned from preconditioning, before tenant warm-up; first-control-tick
temperatures are the first T_c row of each run controller.csv.
