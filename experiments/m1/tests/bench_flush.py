"""Flush latency with and without fsync — measurement only, no threshold.

ADR-0008 limits the Flush promise to process crashes, for which handing the
data to the OS (H5Fflush) is enough; fsync only matters for power loss / OS
crash. Writes 480 Frames in calls of 8 and flushes after every call.
"""

import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import SRC, Results, TestdataSource, run_dir, scan_definition  # noqa: E402

from ussproto.writer import Writer  # noqa: E402

N, B = 480, 8


def run(path, os_sync, frames):
    groups, fields = scan_definition()
    w = Writer.create(path, workpiece_id="bench-flush", os_sync=os_sync)
    w.begin_scan("s", groups, fields)
    lat, t0 = [], time.perf_counter()
    for a in range(0, N, B):
        s, v, r = frames[a // B]
        w.write_frames({"pa0": s}, {"pa0": v}, r)
        t = time.perf_counter()
        w.flush()
        lat.append(time.perf_counter() - t)
    w.finish_scan()
    w.seal()
    total = time.perf_counter() - t0
    lat.sort()
    return {"flushes": len(lat), "median_ms": round(statistics.median(lat) * 1e3, 2),
            "p95_ms": round(lat[int(len(lat) * 0.95)] * 1e3, 2), "max_ms": round(lat[-1] * 1e3, 2),
            "total_s": round(total, 2), "write_MB_per_s": round(N * 250_000 / total / 1e6, 1)}


def main():
    out = run_dir()
    R = Results("bench_flush")
    src = TestdataSource(SRC)
    frames = [src.frames(a, a + B) for a in range(0, N, B)]
    res = {}
    for os_sync in (False, True, False, True):  # interleaved to reduce drift
        key = "H5Fflush + fsync" if os_sync else "H5Fflush only (ADR-0008)"
        r = run(out / f"bench-flush-{int(os_sync)}.h5", os_sync, frames)
        res.setdefault(key, []).append(r)
    R.note("results", res)
    R.note("filesystem", os.popen(f"stat -f -c %T {out}").read().strip())
    R.check("benchmark ran (measurement only, no threshold)", bool(res))
    return R.finish(out)


if __name__ == "__main__":
    sys.exit(main())
