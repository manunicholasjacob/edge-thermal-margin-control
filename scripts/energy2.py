#!/usr/bin/env python3
"""Energy per unit goodput, the one gap the September campaign cannot fill.

IoT-J Reviewer 2 asked for energy per unit goodput. The released campaign
cannot answer it: data/logs/*/controller.csv carries step, temperature,
frequency, utilization, solver time and per-tenant duty, but no power column.
Borrowing a PMIC calibration from another campaign on this board would mix arms
across campaigns, which is the error class this portfolio has already been
burned by, so the number has to be measured.

This re-runs a targeted subset of the matrix with a 10 Hz PMIC rail sampler
alongside each run, writing power.txt into that run's existing log directory.
Everything else (tenants, controller, cgroup enforcement, arrivals, durations)
is campaign2.py unchanged, so the new runs are comparable with the old ones.

Subset rationale: energy per goodput is only meaningful where goodput is
non-zero, and the policy comparison only bites where the cap binds. That is
low and medium load on the heterogeneous mix under Poisson arrivals. High and
extreme are included at one replication each so the collapsed regime has a
power number too, since "the capped policies spend energy and deliver nothing"
is itself a result worth stating with a measurement behind it.

Run AFTER any other heavy job on this board has finished. One at a time.
"""
import itertools
import os
import signal
import subprocess
import sys

sys.path.insert(0, os.path.expanduser("~/thermal2"))
import campaign2  # noqa: E402

POWER_LOOP = r"""
while true; do
  vcgencmd pmic_read_adc 2>/dev/null | awk '
    /current\(/{split($0,a,"="); c[$1]=a[2]+0}
    /volt\(/{split($0,a,"="); v[$1]=a[2]+0}
    END{p=0; for(k in c){ n=k; sub(/_A$/,"",n); vk=n"_V"; if(vk in v) p+=c[k]*v[vk]} print p}'
  sleep 0.1
done > "%s"
"""


def build_subset(caps):
    runs = []
    # where the cap binds and goodput is non-zero: the comparison that matters
    for load, rep in itertools.product(("low", "med"), (1, 2, 3)):
        for mode in ("convex", "matched", "equal", "admission"):
            runs.append(dict(mix="hetero", load=load, rep=rep, mode=mode,
                             arrival="poisson", t_cap=caps["primary"]))
    # the collapsed regime, one replication, so it carries a power number too
    for load in ("high", "extreme"):
        for mode in ("convex", "equal"):
            runs.append(dict(mix="hetero", load=load, rep=1, mode=mode,
                             arrival="poisson", t_cap=caps["primary"]))
    return runs


_orig_execute = campaign2.execute


def execute(r, calib):
    """campaign2.execute, with a PMIC sampler running for the whole run."""
    d = os.path.join(campaign2.LOGS, campaign2.run_id(r))
    os.makedirs(d, exist_ok=True)
    pf = os.path.join(d, "power.txt")
    p = subprocess.Popen(["bash", "-c", POWER_LOOP % pf],
                         preexec_fn=os.setsid,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        return _orig_execute(r, calib)
    finally:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except Exception:
            pass


# Write to a separate log root. Two reasons: campaign2.execute() skips any run
# whose directory already carries a _DONE marker, and every one of the 124
# September runs does, so reusing the tree would skip the whole subset; and the
# September tree is the released artifact, which should not be written into.
campaign2.LOGS = os.path.expanduser("~/thermal2/logs_energy")
os.makedirs(campaign2.LOGS, exist_ok=True)

# setup_cgroups uses plain os.makedirs under /sys/fs/cgroup, which needs root.
# The rest of the harness already shells out to sudo for the per-tenant
# assignment, so match that rather than running the whole campaign as root and
# leaving root-owned logs behind.
def setup_cgroups(n=3):
    # cgroup v2 delegation, and both halves are needed. A child cgroup only gets
    # a cpu.max interface file if its PARENT lists "cpu" in
    # cgroup.subtree_control; enabling cpu at the cgroup root is not enough.
    # Without this the controller fails with "No such file or directory", and if
    # the directory is created by sudo without handing ownership over it fails
    # with "Permission denied" instead. The original campaign inherited a
    # correctly delegated tree from an earlier manual setup, so neither step was
    # in the script; recreating it from scratch needs both.
    subprocess.run(["sudo", "sh", "-c",
                    'echo +cpu > %s/cgroup.subtree_control' % campaign2.CG],
                   check=False)
    for i in range(n):
        d = "%s/t%d" % (campaign2.CG, i)
        subprocess.run(["sudo", "mkdir", "-p", d], check=True)
        # sudo mkdir leaves the group root-owned, and controller2.py writes
        # cpu.max directly as the invoking user. Hand ownership over rather
        # than running the whole campaign as root, which would leave every log
        # root-owned and break the analysis step.
        subprocess.run(["sudo", "chown", "-R", os.environ.get("USER", "manu"), d],
                       check=True)


campaign2.setup_cgroups = setup_cgroups
campaign2.execute = execute
campaign2.build_matrix = build_subset

if __name__ == "__main__":
    campaign2.main()
