"""Import testdata/scan.h5 into a test-only ussproto file.

    python -I experiments/m1/tools/import_testdata.py SRC DST [options]

Writes the export as one PA Scan in calls of varying batch size, flushing every
few calls, then finishes the Scan and seals the file. Prints a JSON summary.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.testdata_source import TestdataSource, scan_definition  # noqa: E402
from ussproto.writer import Writer  # noqa: E402

BATCHES = (1, 5, 16, 3, 32, 7)  # crosses chunk boundaries in different phases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--codec", default="shuffle-deflate1")
    ap.add_argument("--frames-per-chunk", type=int, default=16)
    ap.add_argument("--flush-every", type=int, default=8, help="Flush after this many write calls")
    ap.add_argument("--limit", type=int, default=0, help="import only the first N Frames")
    ap.add_argument("--swmr", action="store_true")
    a = ap.parse_args()

    src = TestdataSource(a.src)
    n_total = min(src.n, a.limit) if a.limit else src.n
    groups, fields = scan_definition(a.codec)
    t0 = time.perf_counter()
    w = Writer.create(a.dst, workpiece_id="testdata-pa-export", swmr=a.swmr)
    w.begin_scan("pa-export-scan", groups, fields,
                 {"source-config": ("application/json; origin=testdata export", "unknown", src.config_bytes())},
                 frames_per_chunk=a.frames_per_chunk)
    n, calls, t_read = 0, 0, 0.0
    while n < n_total:
        b = min(BATCHES[calls % len(BATCHES)], n_total - n)
        tr = time.perf_counter()
        samples, valid, rec = src.frames(n, n + b)
        t_read += time.perf_counter() - tr
        w.write_frames({"pa0": samples}, {"pa0": valid}, rec)
        n += b
        calls += 1
        if calls % a.flush_every == 0:
            w.flush()
    w.finish_scan()
    w.seal()
    elapsed = time.perf_counter() - t0
    print(json.dumps({"dst": a.dst, "frames": n, "calls": calls, "codec": a.codec,
                      "frames_per_chunk": a.frames_per_chunk, "swmr": a.swmr,
                      "seconds_total": round(elapsed, 2), "seconds_reading_source": round(t_read, 2),
                      "file_bytes": Path(a.dst).stat().st_size}))


if __name__ == "__main__":
    main()
