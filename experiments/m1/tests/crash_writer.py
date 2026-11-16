"""Child process for test_crash.py; it is killed with SIGKILL at a random time.

    python -I crash_writer.py MODE H5 SIDECAR SOURCE_DIR SEED

MODE: ussproto | ussproto-swmr  (two Scans A and B, MAP-02 mechanism)
      naive | naive-swmr        (one dataset group appended with ordinary HDF5
                                 writes; Flush = H5Fflush + fsync)
After every successful Flush the child appends "<scan> <N>" to SIDECAR and
fsyncs it, so the parent knows which prefix the Flush promise covers.
"""

import os
import sys

import h5py
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import scan_definition  # noqa: E402

from ussproto.writer import Writer  # noqa: E402

F = 16


class Sidecar:
    def __init__(self, path):
        self.fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)

    def log(self, line):
        os.write(self.fd, (line + "\n").encode())
        os.fsync(self.fd)


def load(source_dir):
    s = np.load(os.path.join(source_dir, "samples.npy"), mmap_mode="r")
    v = np.load(os.path.join(source_dir, "valid.npy"))
    r = np.load(os.path.join(source_dir, "records.npy"))
    return s, v, r


def batches(rng, n0, n1):
    n, calls = n0, 0
    while n < n1:
        b = min(int(rng.integers(1, 13)), n1 - n)
        yield n, n + b, calls
        n += b
        calls += 1


def run_ussproto(path, side, src, rng, swmr):
    s, v, r = src
    n_total = len(v)
    split = n_total // 2
    groups, fields = scan_definition()
    w = Writer.create(path, workpiece_id="crash", swmr=swmr)
    for name, lo, hi in (("A", 0, split), ("B", split, n_total)):
        w.begin_scan(name, groups, fields, frames_per_chunk=F)
        every = int(rng.integers(2, 7))
        for a, b, calls in batches(rng, lo, hi):
            w.write_frames({"pa0": np.asarray(s[a:b])}, {"pa0": v[a:b]}, r[a:b])
            if calls % every == every - 1:
                w.flush()
                side.log(f"{name} {b - lo}")
        w.finish_scan()
        side.log(f"{name} complete {hi - lo}")
    w.seal()
    side.log("sealed")


def run_naive(path, side, src, rng, swmr):
    s, v, r = src
    K, S = s.shape[1:]
    f = h5py.File(path, "w", libver=("v110", "v114"))
    g = f.create_group("A")
    ds = g.create_dataset("samples", shape=(0, K, S), maxshape=(None, K, S), chunks=(F, K, S),
                          dtype="<u2", shuffle=True, compression="gzip", compression_opts=1)
    dv = g.create_dataset("valid", shape=(0, K), maxshape=(None, K), chunks=(F, K), dtype="u1")
    dr = g.create_dataset("records", shape=(0,), maxshape=(None,), chunks=(F,), dtype=r.dtype)
    if swmr:
        f.swmr_mode = True
    fd = f.id.get_vfd_handle()
    every = int(rng.integers(2, 7))
    for a, b, calls in batches(rng, 0, len(v)):
        for d in (ds, dv, dr):
            d.resize(b, axis=0)
        ds[a:b] = np.where(v[a:b, :, None], s[a:b], 0)
        dv[a:b] = v[a:b]
        dr[a:b] = r[a:b]
        if calls % every == every - 1:
            f.flush()
            os.fsync(fd)
            side.log(f"A {b}")
    f.close()
    side.log("sealed")


def main():
    mode, path, sidecar, source_dir, seed = sys.argv[1:6]
    rng = np.random.default_rng(int(seed))
    side = Sidecar(sidecar)
    src = load(source_dir)
    if mode.startswith("ussproto"):
        run_ussproto(path, side, src, rng, mode.endswith("swmr"))
    else:
        run_naive(path, side, src, rng, mode.endswith("swmr"))


if __name__ == "__main__":
    main()
