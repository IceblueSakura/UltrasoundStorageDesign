"""Read semantics on a sealed file built from the first frames of the export.

Covers UC-14-like equivalence (poll/push, single Frame/Batch, selection layer),
BUF-01 borrow end conditions, READ-02 ordered selections and bounds, and
independent borrows of two Readers (ADR-0004).
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RECORD_DTYPE, SRC, Results, TestdataSource, run_dir, scan_definition  # noqa: E402

from ussproto import BorrowExpired, ValidationError  # noqa: E402
from ussproto import select as sel  # noqa: E402
from ussproto.reader import Reader  # noqa: E402
from ussproto.writer import Writer  # noqa: E402

N = 300


def build(path, src):
    groups, fields = scan_definition()
    w = Writer.create(path, workpiece_id="semantics")
    w.begin_scan("s", groups, fields, {"note": ("text/plain", "1", b"m1")}, frames_per_chunk=16)
    for a in range(0, N, 23):
        s, v, r = src.frames(a, min(a + 23, N))
        w.write_frames({"pa0": s}, {"pa0": v}, r)
    w.finish_scan()
    w.seal()


def push_buffers(count, fill=0xA5A5):
    return {"groups": {"pa0": {"samples": np.full((count, 125, 1000), fill, np.uint16),
                               "valid": np.ones((count, 125), bool)}},
            "records": np.zeros(count, RECORD_DTYPE)}


def main():
    out = run_dir()
    R = Results("semantics")
    src = TestdataSource(SRC)
    path = out / "semantics.h5"
    build(path, src)
    es, ev, er = src.frames(0, N)
    r = Reader.open(path)

    # equivalence: Batch poll, Batch push, single-Frame reads, A-scan through the selection layer
    a, b = 37, 37 + 50
    v = r.read(0, a, b - a)
    poll_s, poll_v, poll_r = v.samples("pa0").copy(), v.valid("pa0").copy(), v.records().copy()
    R.check("poll Batch equals the export", np.array_equal(poll_s, es[a:b]) and np.array_equal(poll_v, ev[a:b])
            and np.array_equal(poll_r, er[a:b]))
    buf = push_buffers(b - a)
    r.read(0, a, b - a, out=buf)
    R.check("push Batch equals poll Batch", np.array_equal(buf["groups"]["pa0"]["samples"], poll_s)
            and np.array_equal(buf["groups"]["pa0"]["valid"], poll_v) and np.array_equal(buf["records"], poll_r))
    single = [r.read(0, n, 1) for n in (a, a + 17, b - 1)]
    R.check("single-Frame poll after later reads: earlier views expired", [x.alive for x in single] == [False, False, True])
    ok = True
    for n in range(a, b):
        x = r.read(0, n, 1)
        ok &= np.array_equal(x.samples("pa0")[0], poll_s[n - a]) and np.array_equal(x.valid("pa0")[0], poll_v[n - a])
    R.check("single-Frame reads equal the Batch rows", ok)
    s3, v3 = sel.ascan(poll_s, poll_v, 5, 124)
    R.check("A-scan from the selection layer equals the export", np.array_equal(s3, es[a + 5, 124]) and v3 == ev[a + 5, 124])

    # READ-02 ordered selections keep order and repetitions; bounds are checked per group
    ss, vv = sel.streams(poll_s, poll_v, [2, 0, 2])
    R.check("stream list [2,0,2] keeps order and repetition",
            np.array_equal(ss[:, 0], es[a:b, 2]) and np.array_equal(ss[:, 1], es[a:b, 0])
            and np.array_equal(ss[:, 2], es[a:b, 2]) and vv.shape == (b - a, 3))
    R.check("sample list [3,1,3] keeps order", np.array_equal(sel.sample_list(poll_s, [3, 1, 3]),
                                                               es[a:b][..., [3, 1, 3]]))
    for label, fn in (("sample window beyond S", lambda: sel.sample_window(poll_s, 990, 1001)),
                      ("stream index beyond K", lambda: sel.streams(poll_s, poll_v, [0, 125])),
                      ("Batch beyond N", lambda: r.read(0, N - 5, 10)),
                      ("empty Batch", lambda: r.read(0, 0, 0)),
                      ("unknown group", lambda: r.read(0, 0, 1, groups=["nope"]))):
        try:
            fn()
            R.check(f"{label} is rejected, not truncated", False)
        except ValidationError:
            R.check(f"{label} is rejected, not truncated", True)

    # BUF-01 borrow end conditions
    v1 = r.read(0, 0, 4)
    r.scans()
    r.metadata(0, "note")
    r.lifecycle()
    lay = r.layout(0)
    R.check("catalogue/lifecycle/layout queries keep the borrow", v1.alive)
    R.check("layout reports chunk frames and per-Frame sizes",
            lay["groups"]["pa0"]["frames_per_chunk"] == 16 and lay["groups"]["pa0"]["samples_bytes_per_frame"] == 250000
            and lay["records_bytes_per_frame"] == 24, layout=lay)
    r.read(0, 4, 4, out=push_buffers(4))
    R.check("a push read ends the poll borrow", not v1.alive)
    try:
        v1.samples("pa0")
        R.check("expired view refuses access", False)
    except BorrowExpired:
        R.check("expired view refuses access", True)
    v2 = r.read(0, 0, 4)
    try:
        r.read(0, N, 1)
    except ValidationError:
        pass
    R.check("a rejected read also ends the borrow", not v2.alive)
    v3 = r.read(0, 0, 4)
    r2 = Reader.open(path)
    w2 = r2.read(0, 8, 4)
    R.check("a second Reader's read does not end the first Reader's borrow", v3.alive and w2.alive)
    r.close()
    R.check("closing the Reader ends its borrow; the other Reader is unaffected", not v3.alive and w2.alive)
    keep = push_buffers(4)
    r2.read(0, 8, 4, out=keep)
    r2.close()
    R.check("push target stays usable after its Reader closes", np.array_equal(keep["groups"]["pa0"]["samples"], es[8:12]))
    try:
        np.asarray(w2._arrays["pa0"][0])[0, 0, 0] = 1
        R.check("poll arrays are read-only", False)
    except ValueError:
        R.check("poll arrays are read-only", True)
    R.note("limits", "raw numpy arrays exported from a view cannot be revoked; only BatchView accessors are checked")
    return R.finish(out)


if __name__ == "__main__":
    sys.exit(main())
