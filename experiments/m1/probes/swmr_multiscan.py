"""Can a multi-Scan file use SWMR-write per Scan (objects created outside SWMR)?

    python -I swmr_multiscan.py drive <outdir>

Writer: Scan A is created, written in SWMR mode and the file closed cleanly; the
file is reopened read-write, Scan B objects are created, SWMR mode is entered
again, 6 frames are flushed+fsynced, 4 more are appended and the process exits
without closing (simulated process crash, not power loss).
"""

import json
import os
import subprocess
import sys

import h5py
import numpy as np

S, C = 4096, 4


def frame(scan, n):
    return np.random.default_rng({"A": 1000, "B": 2000}[scan] + n).integers(0, 65536, S, dtype=np.uint16)


def new_scan(f, name):
    g = f.create_group(name)
    return g.create_dataset("x", shape=(0, S), maxshape=(None, S), chunks=(C, S), dtype="u2",
                            compression="szip")


def append(d, scan, start, stop):
    for n in range(start, stop):
        d.resize(n + 1, axis=0)
        d[n] = frame(scan, n)


def write(path):
    f = h5py.File(path, "w", libver="latest", rdcc_nbytes=0)
    d = new_scan(f, "A")
    f.swmr_mode = True
    append(d, "A", 0, 10)
    f.close()
    f = h5py.File(path, "r+", libver="latest", rdcc_nbytes=0)
    d = new_scan(f, "B")
    f.swmr_mode = True
    append(d, "B", 0, 6)
    f.flush()
    os.fsync(f.id.get_vfd_handle())
    append(d, "B", 6, 10)
    os._exit(0)


def inspect(path, swmr):
    out = {"swmr_read": swmr}
    try:
        with h5py.File(path, "r", swmr=swmr) as f:
            for scan in ("A", "B"):
                d = f[scan]["x"]
                ok = [bool(np.array_equal(d[n], frame(scan, n))) for n in range(d.shape[0])]
                out[scan] = {"shape": list(d.shape), "all_frames_ok": all(ok), "ok": ok}
    except Exception as exc:
        out["open_error"] = str(exc).splitlines()[0][:200]
    return out


def drive(outdir):
    path = os.path.join(outdir, "multiscan.h5")
    p = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "write", path],
                       capture_output=True, text=True)
    print(json.dumps({"writer_rc": p.returncode, "writer_stderr": p.stderr[-300:],
                      "plain_read": inspect(path, False), "swmr_read": inspect(path, True)}, indent=1))


if __name__ == "__main__":
    {"write": write, "drive": drive}[sys.argv[1]](sys.argv[2])
