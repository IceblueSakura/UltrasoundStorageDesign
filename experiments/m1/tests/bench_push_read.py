"""Cost of the two-phase push read (MAP-02 item 5) — measurement only, no threshold.

Compares, on the imported export (warm OS page cache, single thread):
  two-phase push   : fetch + stored-CRC check of all chunks, then decode + decoded-CRC + copy
  single-phase push: decode straight into the target, no checksums
  plain HDF5 read  : h5py read_direct through HDF5's own filter pipeline
for Batch sizes B in {1, 16, 64} at random Frame offsets.
"""

import os
import statistics
import subprocess
import sys
import time

import h5py
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import M1, PY, RECORD_DTYPE, SRC, Results, run_dir  # noqa: E402

from ussproto.reader import Reader  # noqa: E402

FRAME_BYTES = 125 * 1000 * 2


def ensure(out, codec):
    path = out / f"full-{codec}.h5"
    if not path.exists():
        subprocess.run([PY, "-I", str(M1 / "tools" / "import_testdata.py"), str(SRC), str(path), "--codec", codec,
                        "--limit", "1000"], check=True, capture_output=True)
    return path


def bufs(B):
    return {"groups": {"pa0": {"samples": np.empty((B, 125, 1000), np.uint16), "valid": np.empty((B, 125), bool)}},
            "records": np.empty(B, RECORD_DTYPE)}


def main():
    out = run_dir()
    R = Results("bench_push_read")
    table = []
    for codec in ("shuffle-deflate1", "none"):
        path = ensure(out, codec)
        rd = Reader.open(path)
        n = rd.scans()[0]["n_frames"]
        st = rd._states[0]
        f = h5py.File(path, "r")
        ds = f["scans/s0000/g/pa0/samples"]
        rng = np.random.default_rng(5)
        for B in (1, 16, 64):
            reps = 40 if B < 64 else 15
            starts = rng.integers(0, n - B, reps)
            target = bufs(B)
            plain = np.empty((B, 125, 1000), np.uint16)
            res = {}
            for label, fn in (
                ("two-phase push", lambda a: rd.read(0, a, B, out=target)),
                ("single-phase push", lambda a: rd.read(0, a, B, out=target, verify=False)),
                ("plain HDF5 read_direct", lambda a: ds.read_direct(plain, np.s_[a:a + B])),
            ):
                fn(int(starts[0]))  # warm-up
                ts = []
                for a in starts:
                    t0 = time.perf_counter()
                    fn(int(a))
                    ts.append(time.perf_counter() - t0)
                med = statistics.median(ts)
                res[label] = {"median_ms": round(med * 1e3, 2), "MB_per_s": round(B * FRAME_BYTES / med / 1e6, 1)}
            chunks = [(a // st.F, (a + B - 1) // st.F) for a in starts]
            staged = statistics.median(sum(int(st.sums()[c]["stored_len"][0]) for c in range(lo, hi + 1))
                                       for lo, hi in chunks)
            row = {"codec": codec, "B": B, **{k: v for k, v in res.items()},
                   "median_staged_stored_bytes_samples": int(staged), "delivered_bytes": B * FRAME_BYTES}
            table.append(row)
        f.close()
        rd.close()
    R.note("results", table)
    R.note("environment", {"cpu_count": os.cpu_count(), "note": "warm page cache, single thread, Python prototype"})
    R.check("benchmark ran (measurement only, no threshold)", bool(table))
    return R.finish(out)


if __name__ == "__main__":
    sys.exit(main())
