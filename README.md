# Edge Thermal-Margin Control: When It Helps and When It Hurts

Reproducible artifact for **"When Thermal-Margin Control Helps and When It Hurts: An
Operating-Regime Study of Convex Allocation for Multi-Tenant Edge Inference"**
(submitted to IEEE Embedded Systems Letters).

## Summary
We ask whether a convex *thermal-margin* controller — which treats the gap to an operator
thermal cap as an allocatable resource — actually beats trivial baselines (equal CPU sharing,
fixed quota) for multi-tenant DNN inference on a Raspberry Pi 5. The answer is deliberately
two-sided: across a load sweep, the controller is **throughput-dominated by equal sharing at
every load level** (0.31–0.96x SLA-met goodput), yet in a moderately-loaded regime it occupies
a distinct operating point — **zero SLA violations vs. 1.1–1.2% for the baselines, and 3.7x
lower p99 tail latency (28 ms vs. 103 ms)** — at ~36% throughput cost. We map the boundary and
give a practitioner rule for when predictive thermal-margin control is worth its cost.

We are explicit that the CPU governor was pinned, so the thermal model reduces to a
single-variable utilization law (T ≈ 45.6 + 0.175·U, R² = 0.93); the allocation result does not
depend on thermal-model sophistication.

## Contents
```
paper/main_v2_honest.pdf   the paper
figures/fig_regime.pdf     operating-regime figure (+ gen_fig_regime.py)
scripts/
  paper1_regime_map.py     goodput/violations/p99 per load level, per controller
  paper1_goodput.py        SLA-met goodput under extreme overcommit
  paper1_goodput2.py       realistic-load + no-control baseline
data/thermal_paper_data.tgz  raw controller/latency telemetry (485 CSVs) + all_results.json
LICENSE                    MIT
```

## Data
`data/thermal_paper_data.tgz` unpacks to per-run directories under `thermal_paper/logs/`
(controller traces + per-tenant latency logs with SLA flags) and `all_results.json` (the
aggregated comparison). Collected on a Raspberry Pi 5 (quad-core Cortex-A76) serving three
concurrent MobileNetV2 tenants under a 80 ms SLA across four load levels with replications.

## Reproduce
```bash
tar xzf data/thermal_paper_data.tgz
pip install numpy
python scripts/paper1_regime_map.py    # the operating-regime table
```

## Citation
Manu Nicholas Jacob, IEEE Embedded Systems Letters, 2026. MIT License.
