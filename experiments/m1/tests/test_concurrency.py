"""Concurrency scope of ADR-0004 / U-16 (part of T-24).

- several threads, each with its own Reader on one sealed file, while another
  thread writes a different file through a Writer (one process-wide HDF5 lock);
- several processes reading the same sealed file at the same time;
- a Reader in another process refused while a Writer still has the file open.
"""

import json
import os
import subprocess
import sys
import threading

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PY, SRC, Results, TestdataSource, run_dir, scan_definition  # noqa: E402
from test_semantics import N, build  # noqa: E402

from ussproto.reader import Reader  # noqa: E402
from ussproto.verify import verify_scan  # noqa: E402
from ussproto.writer import Writer  # noqa: E402

CHILD = r"""
import sys, json, zlib
sys.path.insert(0, sys.argv[2])
from ussproto.reader import Reader
try:
    r = Reader.open(sys.argv[1])
except Exception as e:
    print(json.dumps({"open_error": f"{type(e).__name__}: {e}"[:300]})); sys.exit(0)
n = r.scans()[0]["n_frames"]; c = 0
for a in range(0, n, 50):
    v = r.read(0, a, min(50, n - a)); c = zlib.crc32(v.samples("pa0").tobytes(), c)
print(json.dumps({"n": n, "crc": c}))
"""


def main():
    out = run_dir()
    R = Results("concurrency")
    src = TestdataSource(SRC)
    path = out / "concurrency.h5"
    build(path, src)
    es, ev, _ = src.frames(0, N)
    errors, done = [], []

    def reader_thread(seed):
        try:
            rng = np.random.default_rng(seed)
            rd = Reader.open(path)
            for _ in range(25):
                a = int(rng.integers(0, N - 20))
                b = a + int(rng.integers(1, 20))
                v = rd.read(0, a, b - a)
                if not (np.array_equal(v.samples("pa0"), es[a:b]) and np.array_equal(v.valid("pa0"), ev[a:b])):
                    errors.append(f"reader {seed}: wrong data at [{a},{b})")
            rd.close()
            done.append(seed)
        except Exception as e:
            errors.append(f"reader {seed}: {type(e).__name__}: {e}")

    other = out / "concurrency-writer.h5"

    def writer_thread():
        try:
            groups, fields = scan_definition()
            w = Writer.create(other, workpiece_id="concurrent-writer")
            w.begin_scan("w", groups, fields)
            for a in range(0, 120, 10):
                s, v, r = src.frames(a, a + 10)
                w.write_frames({"pa0": s}, {"pa0": v}, r)
                w.flush()
            w.finish_scan()
            w.seal()
            done.append("writer")
        except Exception as e:
            errors.append(f"writer: {type(e).__name__}: {e}")

    threads = [threading.Thread(target=reader_thread, args=(i,)) for i in range(4)]
    threads.append(threading.Thread(target=writer_thread))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    R.check("4 Reader threads and 1 Writer thread (different file) run without errors", not errors and len(done) == 5,
            errors=errors[:5])
    rd = Reader.open(other)
    rep, _ = verify_scan(rd.f["scans/s0000"])
    R.check("file written concurrently with reads verifies", rep["verified_n"] == 120 and not rep["failures"])
    rd.close()

    m1 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    procs = [subprocess.Popen([PY, "-I", "-c", CHILD, str(path), m1], stdout=subprocess.PIPE, text=True)
             for _ in range(3)]
    results = [json.loads(p.communicate()[0]) for p in procs]
    R.check("3 processes read the same sealed file at the same time with identical results",
            all("crc" in x for x in results) and len({x.get("crc") for x in results}) == 1, results=results)

    groups, fields = scan_definition()
    busy = out / "concurrency-open-writer.h5"
    w = Writer.create(busy, workpiece_id="busy")
    w.begin_scan("b", groups, fields)
    s, v, r = src.frames(0, 10)
    w.write_frames({"pa0": s}, {"pa0": v}, r)
    w.flush()
    p = subprocess.run([PY, "-I", "-c", CHILD, str(busy), m1], capture_output=True, text=True)
    res = json.loads(p.stdout)
    R.check("a Reader in another process is refused while the Writer has the file open", "open_error" in res,
            result=res)
    w.finish_scan()
    w.seal()
    R.note("scope", "h5py also serialises its own API calls; the prototype lock additionally keeps multi-call "
                    "sequences (fetch, journal+commit) atomic. Object-level thread safety is not claimed.")
    return R.finish(out)


if __name__ == "__main__":
    sys.exit(main())
