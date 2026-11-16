"""Child process for test_io_failure.py: a write fails with EFBIG (RLIMIT_FSIZE).

    python -I io_failure_writer.py MODE H5 SOURCE_DIR

MODE transient : the limit is lifted after the failure, then seal_with_failure()
MODE persistent: the limit stays; seal_with_failure() is expected to fail
Prints one JSON line describing what happened.
"""

import json
import os
import resource
import signal
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import scan_definition  # noqa: E402

from ussproto import StateError, WriteIOError  # noqa: E402
from ussproto.writer import Writer  # noqa: E402


def main():
    mode, path, source_dir = sys.argv[1:4]
    s = np.load(os.path.join(source_dir, "samples.npy"), mmap_mode="r")
    v = np.load(os.path.join(source_dir, "valid.npy"))
    r = np.load(os.path.join(source_dir, "records.npy"))
    log = {"mode": mode}
    groups, fields = scan_definition()
    w = Writer.create(path, workpiece_id="io-failure")
    w.begin_scan("s", groups, fields, frames_per_chunk=16)
    n = 0
    for _ in range(5):
        w.write_frames({"pa0": np.asarray(s[n:n + 8])}, {"pa0": v[n:n + 8]}, r[n:n + 8])
        n += 8
    w.flush()
    log["flushed_n"] = n
    w.write_frames({"pa0": np.asarray(s[n:n + 8])}, {"pa0": v[n:n + 8]}, r[n:n + 8])
    n += 8
    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    limit = os.path.getsize(path) + 1_500_000
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, hard))
    log["fsize_limit"] = limit
    while n + 8 <= len(v):
        try:
            w.write_frames({"pa0": np.asarray(s[n:n + 8])}, {"pa0": v[n:n + 8]}, r[n:n + 8])
            n += 8
        except WriteIOError as e:
            log["write_error"] = str(e)[:300]
            break
    log["committed_n"] = w.scan["N"]
    log["writer_state"] = w.state
    for label, fn in (("write_after_failure", lambda: w.write_frames({"pa0": np.asarray(s[:1])}, {"pa0": v[:1]}, r[:1])),
                      ("flush_after_failure", w.flush), ("seal_after_failure", w.seal)):
        try:
            fn()
            log[label] = "accepted"
        except StateError as e:
            log[label] = f"StateError: {e}"
        except Exception as e:
            log[label] = f"{type(e).__name__}: {e}"
    if mode == "transient":
        resource.setrlimit(resource.RLIMIT_FSIZE, (soft, hard))
    try:
        reports = w.seal_with_failure()
        log["seal_with_failure"] = "ok"
        log["seal_reports"] = reports
    except Exception as e:
        log["seal_with_failure"] = f"{type(e).__name__}: {str(e)[:300]}"
        w.close()
    print(json.dumps(log, default=str))


if __name__ == "__main__":
    main()
