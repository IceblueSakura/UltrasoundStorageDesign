"""Process-crash tests of the Flush promise (WRT-03, LIF-02, D-05). Not power loss.

A child writer (crash_writer.py) is killed with SIGKILL at random times or at
named failpoints. After each kill the file is opened in recovery mode and
checked: every Flush that returned before the kill must be covered by the
verified prefix, every recovered Frame must equal the source bit-exactly, and
recovery must leave the source byte-identical (LIF-02). Files that need their
status flags cleared are recovered both in place (flags cleared in memory) and
from an h5clear'ed copy; the two reports must agree.
The same harness runs a naive writer (ordinary HDF5 appends, Flush = H5Fflush
+ fsync) for contrast.
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time

import h5py
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import H5CLEAR, PY, SRC, Results, TestdataSource, run_dir  # noqa: E402

from ussproto.reader import Reader  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
N_SRC = int(os.environ.get("USS_CRASH_FRAMES", 800))
ITER = int(os.environ.get("USS_CRASH_ITER", 60))
FAILPOINTS = ["begin_scan.after_create@2", "write.after_chunk@5", "flush.after_journal@1",
              "flush.after_journal@4", "flush.after_commit_write@1", "flush.after_commit_write@5",
              "finish.after_final_chunks@1", "finish.after_commit@1", "finish.after_final_chunks@2",
              "seal.before_lifecycle@1", "seal.after_lifecycle@1"]


def prepare(out):
    d = out / f"crash-source-{N_SRC}"
    if not (d / "valid.npy").exists():
        d.mkdir(exist_ok=True)
        s, v, r = TestdataSource(SRC).frames(0, N_SRC)
        np.save(d / "samples.npy", s)
        np.save(d / "valid.npy", v)
        np.save(d / "records.npy", r)
    return d, np.load(d / "samples.npy", mmap_mode="r"), np.load(d / "valid.npy"), np.load(d / "records.npy")


def sidecar_state(path):
    flushed, complete, sealed = {}, {}, False
    if os.path.exists(path):
        for line in open(path).read().split("\n"):
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "sealed":
                sealed = True
            elif parts[1] == "complete":
                complete[parts[0]] = int(parts[2])
                flushed[parts[0]] = int(parts[2])
            else:
                flushed[parts[0]] = int(parts[1])
    return flushed, complete, sealed


def run_child(mode, h5, side, src_dir, seed, kill_after=None, failpoint=None):
    for p in (h5, side):
        if os.path.exists(p):
            os.unlink(p)
    env = dict(os.environ)
    if failpoint:
        env["USS_FAILPOINT"] = failpoint
    t0 = time.perf_counter()
    p = subprocess.Popen([PY, "-I", os.path.join(HERE, "crash_writer.py"), mode, str(h5), str(side), str(src_dir),
                          str(seed)], env=env, stderr=subprocess.PIPE)
    if kill_after is not None:
        try:
            p.wait(timeout=kill_after)
        except subprocess.TimeoutExpired:
            p.send_signal(signal.SIGKILL)
    _, err = p.communicate()
    return p.returncode, time.perf_counter() - t0, err.decode()[-300:]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def report_core(reports):
    return [{k: x.get(k) for k in ("scan_id", "declared_n", "verified_n", "scan_state", "failures")}
            for x in reports["scans"]]


def analyse_ussproto(h5, side, s, v, r, workdir):
    flushed, complete, sealed = sidecar_state(side)
    split = len(v) // 2
    ranges = {"A": (0, split), "B": (split, len(v))}
    res = {"flushed": flushed, "complete": complete, "sealed": sealed, "violations": [], "scans": {}}
    if not os.path.exists(h5):
        if flushed:
            res["violations"].append("file missing after a successful Flush")
        return res
    before = sha256(h5)
    try:
        rd = Reader.open_recovery(h5, h5clear=H5CLEAR, workdir=workdir)
    except Exception as e:
        if flushed:
            res["violations"].append(f"recovery open failed: {type(e).__name__}: {e}")
        res["open_error"] = str(e)[:200]
        return res
    res["open_method"] = rd.recovery_reports["open_method"]
    if res["open_method"] == "clear-flags-in-memory":
        cp = Reader.open_recovery(h5, h5clear=H5CLEAR, workdir=workdir, methods=("h5clear-on-copy",))
        res["same_as_copy"] = report_core(cp.recovery_reports) == report_core(rd.recovery_reports)
        cp.close()
        if not res["same_as_copy"]:
            res["violations"].append("in-place and h5clear-on-copy recovery disagree")
    res["lifecycle"] = rd.recovery_reports["lifecycle"]["state"]
    by_id = {}
    for rep, sc in zip(rd.recovery_reports["scans"], rd.scans()):
        by_id[rep["scan_id"]] = (rep, sc)
    for name, (lo, hi) in ranges.items():
        need = flushed.get(name, 0)
        if name not in by_id:
            if need:
                res["violations"].append(f"Scan {name} missing although {need} Frames were flushed")
            continue
        rep, sc = by_id[name]
        nr = rep["verified_n"]
        res["scans"][name] = {"declared": rep["declared_n"], "verified": nr, "flushed": need,
                              "state": rep["scan_state"], "failures": rep["failures"]}
        if nr < need:
            res["violations"].append(f"Scan {name}: verified {nr} < flushed {need}")
        if rep["declared_n"] != nr:
            res["violations"].append(f"Scan {name}: declared {rep['declared_n']} but verified {nr}")
        if name in complete and rep["scan_state"] != "complete":
            res["violations"].append(f"Scan {name}: completed before the crash but recovered as active")
        idx = next((i for i, x in enumerate(rd.scans()) if x and x["scan_id"] == name), None)
        for a in range(0, nr, 64):
            b = min(a + 64, nr)
            x = rd.read(idx, a, b - a)
            if not (np.array_equal(x.samples("pa0"), np.where(v[lo + a:lo + b, :, None], s[lo + a:lo + b], 0))
                    and np.array_equal(x.valid("pa0"), v[lo + a:lo + b])
                    and np.array_equal(x.records(), r[lo + a:lo + b])):
                res["violations"].append(f"Scan {name}: recovered Frames [{a},{b}) differ from the source")
                break
    if sealed and res["lifecycle"] != "sealed":
        res["violations"].append("sealed before the crash but lifecycle is not sealed")
    rd.close()
    if sha256(h5) != before:
        res["violations"].append("recovery modified the source file")
    return res


def analyse_naive(h5, side, s, v, r, workdir):
    flushed, _, sealed = sidecar_state(side)
    need = flushed.get("A", 0)
    res = {"flushed": need, "sealed": sealed, "violations": []}
    f = None
    for kw, how in (({}, "read-only"), ({"swmr": True}, "swmr-read")):
        try:
            f, res["open_method"] = h5py.File(h5, "r", **kw), how
            break
        except OSError:
            pass
    if f is None:
        copy = os.path.join(workdir, "naive-cleared.h5")
        shutil.copyfile(h5, copy)
        subprocess.run([H5CLEAR, "-s", copy], capture_output=True)
        try:
            f, res["open_method"] = h5py.File(copy, "r"), "h5clear-on-copy"
        except OSError as e:
            res["violations"].append(f"cannot open: {e}")
            return res
    with f:
        g = f["A"]
        res["extent"] = int(g["samples"].shape[0])
        if res["extent"] < need:
            res["violations"].append(f"extent {res['extent']} < flushed {need}")
            need = res["extent"]
        bad = []
        for a in range(0, need, F_NAIVE):
            b = min(a + F_NAIVE, need)
            try:
                ok = (np.array_equal(g["samples"][a:b], np.where(v[a:b, :, None], s[a:b], 0))
                      and np.array_equal(g["valid"][a:b], v[a:b].astype("u1"))
                      and np.array_equal(g["records"][a:b], r[a:b]))
                if not ok:
                    bad.append([a, b, "wrong values"])
            except Exception as e:
                bad.append([a, b, f"read error {type(e).__name__}"])
        if bad:
            res["violations"].append(f"flushed Frames unreadable or wrong: {bad[:4]}")
        res["bad_ranges"] = bad
    return res


F_NAIVE = 16


def main():
    out = run_dir()
    R = Results("crash")
    src_dir, s, v, r = prepare(out)
    work = out / "crash"
    work.mkdir(exist_ok=True)
    h5, side = work / "c.h5", work / "c.side"
    log = []
    rng = np.random.default_rng(20261024)

    for mode in ("ussproto", "ussproto-swmr", "naive", "naive-swmr"):
        rc, dur, err = run_child(mode, h5, side, src_dir, 1)
        an = (analyse_ussproto if mode.startswith("ussproto") else analyse_naive)(h5, side, s, v, r, work)
        R.check(f"{mode}: uninterrupted run seals and verifies", rc == 0 and not an["violations"],
                seconds=round(dur, 2), rc=rc, stderr=err, violations=an["violations"])
        runs = []
        for i in range(ITER):
            seed = int(rng.integers(1, 1 << 30))
            delay = float(rng.uniform(0.3, dur * 1.05))
            rc, _, err = run_child(mode, h5, side, src_dir, seed, kill_after=delay)
            an = (analyse_ussproto if mode.startswith("ussproto") else analyse_naive)(h5, side, s, v, r, work)
            runs.append({"seed": seed, "kill_after": round(delay, 3), "rc": rc, **an})
        killed = [x for x in runs if x["rc"] == -signal.SIGKILL]
        viol = [x for x in runs if x["violations"]]
        with_flush = [x for x in killed if (x["flushed"] if isinstance(x["flushed"], int) else sum(x["flushed"].values()))]
        methods = {}
        for x in killed:
            methods[str(x.get("open_method"))] = methods.get(str(x.get("open_method")), 0) + 1
        summary = {"iterations": len(runs), "killed": len(killed), "killed_after_a_flush": len(with_flush),
                   "runs_with_violations": len(viol), "open_methods": methods,
                   "compared_with_copy": sum(1 for x in runs if "same_as_copy" in x),
                   "examples": [x["violations"][:2] for x in viol[:5]]}
        if mode.startswith("ussproto"):
            R.check(f"{mode}: random SIGKILL never loses a flushed Frame or recovers a wrong one", not viol, **summary)
        else:
            R.note(f"{mode}: random SIGKILL (contrast, no promise)", summary)
        log.append({"mode": mode, "runs": runs})

    for mode in ("ussproto", "ussproto-swmr"):
        for fp in FAILPOINTS:
            rc, _, err = run_child(mode, h5, side, src_dir, 7, failpoint=fp)
            an = analyse_ussproto(h5, side, s, v, r, work)
            R.check(f"{mode}: failpoint {fp}", rc == -signal.SIGKILL and not an["violations"],
                    rc=rc, open_method=an.get("open_method"), scans=an.get("scans"), violations=an["violations"],
                    stderr=err if rc not in (0, -signal.SIGKILL) else "")
            log.append({"mode": mode, "failpoint": fp, "rc": rc, **an})
    (out / "crash-runs.json").write_text(json.dumps(log, indent=1, default=str))
    return R.finish(out)


if __name__ == "__main__":
    sys.exit(main())
