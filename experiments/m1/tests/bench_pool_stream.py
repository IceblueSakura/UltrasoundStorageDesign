"""Caller-owned reusable buffer pool over a sealed file — measurement only.

Models the planned host-side memory pool: a few push targets sized from
Reader.layout() are reused for the whole Scan. Measures
  - resident memory while streaming every Frame (must not grow with N),
  - sequential streaming with chunk-aligned vs misaligned Batches,
  - random Batch reads aligned vs misaligned to storage chunks.
"""

import os
import statistics
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import M1, PY, RECORD_DTYPE, SRC, Results, run_dir  # noqa: E402

from ussproto.reader import Reader  # noqa: E402


def rss_mb():
    for line in open("/proc/self/status"):
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return float("nan")


def pool(lay, B, P):
    g = lay["groups"]["pa0"]
    return [{"groups": {"pa0": {"samples": np.zeros((B, g["K"], g["S"]), g["dtype"]),
                                "valid": np.zeros((B, g["K"]), bool)}},
             "records": np.zeros(B, RECORD_DTYPE)} for _ in range(P)]


def stream(rd, bufs, B, offset):
    """Read every Frame in Batches of B starting at `offset`; consume each with a reduction."""
    n = rd.layout(0)["n_frames"]
    starts = ([0] if offset else []) + list(range(offset, n, B))
    marks, peak, t0, i = {}, rss_mb(), time.perf_counter(), 0
    per_frame = np.zeros(n, np.uint64)  # consumer: per-Frame sum of samples
    for k, a in enumerate(starts):
        b = min(n, starts[k + 1] if k + 1 < len(starts) else n)
        if b <= a:
            continue
        buf = bufs[i % len(bufs)]
        if b - a != B:  # head/tail Batches use a view of a pool buffer of the exact size
            view = {"groups": {"pa0": {"samples": buf["groups"]["pa0"]["samples"][:b - a],
                                       "valid": buf["groups"]["pa0"]["valid"][:b - a]}},
                    "records": buf["records"][:b - a]}
            rd.read(0, a, b - a, out=view)
            per_frame[a:b] = view["groups"]["pa0"]["samples"].reshape(b - a, -1).sum(axis=1)
        else:
            rd.read(0, a, B, out=buf)
            per_frame[a:b] = buf["groups"]["pa0"]["samples"].reshape(B, -1).sum(axis=1)
        i += 1
        peak = max(peak, rss_mb())
        for q in (0.25, 0.5, 1.0):
            if q not in marks and b >= q * n:
                marks[q] = round(rss_mb(), 1)
    dt = time.perf_counter() - t0
    return {"seconds": round(dt, 2), "MB_per_s": round(n * 250_000 / dt / 1e6, 1), "batches": i,
            "rss_mb_at_25_50_100pct": [marks.get(q) for q in (0.25, 0.5, 1.0)], "peak_rss_mb": round(peak, 1),
            "per_frame": per_frame}


def main():
    out = run_dir()
    R = Results("bench_pool_stream")
    path = out / "full-shuffle-deflate1.h5"
    if not path.exists():
        subprocess.run([PY, "-I", str(M1 / "tools" / "import_testdata.py"), str(SRC), str(path)], check=True,
                       capture_output=True)
    base = rss_mb()
    rd = Reader.open(path)
    lay = rd.layout(0)
    F, n = lay["groups"]["pa0"]["frames_per_chunk"], lay["n_frames"]
    B, P = 4 * F, 3
    bufs = pool(lay, B, P)
    pool_mb = sum(x["groups"]["pa0"]["samples"].nbytes + x["groups"]["pa0"]["valid"].nbytes + x["records"].nbytes
                  for x in bufs) / 2**20
    aligned = stream(rd, bufs, B, 0)
    misaligned = stream(rd, bufs, B, F // 2)
    R.check("resident memory stays flat while streaming the whole Scan through a fixed pool",
            max(aligned["rss_mb_at_25_50_100pct"]) - min(aligned["rss_mb_at_25_50_100pct"]) < 32,
            rss=aligned["rss_mb_at_25_50_100pct"])
    R.check("misaligned streaming delivers the same data",
            np.array_equal(misaligned.pop("per_frame"), aligned.pop("per_frame")))
    R.note("sequential", {"frames": n, "decoded_MB": round(n * 250_000 / 1e6), "batch_frames": B, "pool_buffers": P,
                          "pool_MB": round(pool_mb, 1), "rss_before_open_MB": round(base, 1),
                          "aligned": aligned, "misaligned_by_half_chunk": misaligned})

    rng = np.random.default_rng(11)
    rand = {}
    for label, shift in (("aligned", 0), ("misaligned", F // 2)):
        for Bq in (F, 4 * F):
            starts = rng.integers(0, (n - Bq - F) // F, 40) * F + shift
            buf = pool(lay, Bq, 1)[0]
            rd.read(0, int(starts[0]), Bq, out=buf)
            ts = []
            for a in starts:
                t0 = time.perf_counter()
                rd.read(0, int(a), Bq, out=buf)
                ts.append(time.perf_counter() - t0)
            rand[f"B={Bq} {label}"] = {"median_ms": round(statistics.median(ts) * 1e3, 2),
                                       "chunks_decoded_per_read": (Bq + shift + F - 1) // F if shift else Bq // F}
    R.note("random", rand)
    rd.close()
    return R.finish(out)


if __name__ == "__main__":
    sys.exit(main())
