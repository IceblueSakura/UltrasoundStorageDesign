"""Writer-side rejections and lifecycle rules (WRT-01, STA-01/ADR-0003, LIF-01, DOC-01).

Every rejected call must leave N, the commit record and the file's committed
data unchanged; valid=0 slots are zero-filled whatever input they carried.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import SRC, Results, TestdataSource, run_dir, scan_definition  # noqa: E402

from ussproto import StateError, ValidationError  # noqa: E402
from ussproto.reader import Reader  # noqa: E402
from ussproto.writer import Writer  # noqa: E402


def rejected(R, label, fn, w, exc=ValidationError):
    before = w.scan["N"] if w.scan else None
    try:
        fn()
        R.check(label, False, note="call accepted")
    except exc as e:
        after = w.scan["N"] if w.scan else None
        R.check(label, before == after, error=str(e)[:160], n_before=before, n_after=after)


def main():
    out = run_dir()
    R = Results("validation")
    src = TestdataSource(SRC)
    s, v, r = src.frames(0, 40)
    groups, fields = scan_definition()
    path = out / "validation.h5"
    w = Writer.create(path, workpiece_id="validation")
    rejected(R, "write before any Scan is rejected", lambda: w.write_frames({"pa0": s[:1]}, {"pa0": v[:1]}, r[:1]),
             w, StateError)
    w.begin_scan("a", groups, fields, frames_per_chunk=16)
    w.write_frames({"pa0": s[:10]}, {"pa0": v[:10]}, r[:10])

    bad_dtype = s[:2].astype("<i4")
    rejected(R, "bitmap missing (None) rejects the whole call",
             lambda: w.write_frames({"pa0": s[10:12]}, {"pa0": None}, r[10:12]), w)
    rejected(R, "bitmap absent from the call rejects it",
             lambda: w.write_frames({"pa0": s[10:12]}, {}, r[10:12]), w)
    rejected(R, "bitmap with wrong length (K-1) rejects the call",
             lambda: w.write_frames({"pa0": s[10:12]}, {"pa0": v[10:12, :124]}, r[10:12]), w)
    rejected(R, "bitmap as uint8 instead of explicit bool rejects the call",
             lambda: w.write_frames({"pa0": s[10:12]}, {"pa0": v[10:12].astype("u1")}, r[10:12]), w)
    rejected(R, "Frame count mismatch between bitmap and samples rejects the call",
             lambda: w.write_frames({"pa0": s[10:12]}, {"pa0": v[10:13]}, r[10:12]), w)
    rejected(R, "samples with a converted dtype are rejected (no implicit conversion)",
             lambda: w.write_frames({"pa0": bad_dtype}, {"pa0": v[10:12]}, r[10:12]), w)
    rejected(R, "S+1 samples are rejected",
             lambda: w.write_frames({"pa0": np.zeros((2, 125, 1001), "<u2")}, {"pa0": v[10:12]}, r[10:12]), w)
    rejected(R, "valid=1 slots without waveforms are rejected",
             lambda: w.write_frames({"pa0": None}, {"pa0": v[10:12]}, r[10:12]), w)
    rejected(R, "missing frame records are rejected",
             lambda: w.write_frames({"pa0": s[10:12]}, {"pa0": v[10:12]}, r[10:11]), w)
    rejected(R, "frame records with another layout are rejected",
             lambda: w.write_frames({"pa0": s[10:12]}, {"pa0": v[10:12]}, np.zeros(2, [("encoder_a", "<i8")])), w)
    rejected(R, "unknown stream group is rejected",
             lambda: w.write_frames({"pa0": s[10:12], "x": s[10:12]}, {"pa0": v[10:12], "x": v[10:12]}, r[10:12]), w)

    # STA-01: valid=0 slots are zero-filled even when non-zero input was supplied
    vv = v[10:12].copy()
    vv[0, 7] = False
    w.write_frames({"pa0": s[10:12]}, {"pa0": vv}, r[10:12])  # N = 12
    allinv = np.zeros((1, 125), bool)
    w.write_frames({"pa0": None}, {"pa0": allinv}, r[12:13])  # waveforms omitted, all invalid
    rejected(R, "begin_scan while a Scan is active is rejected (no implicit finish)",
             lambda: w.begin_scan("b", groups, fields), w, StateError)
    rejected(R, "seal with an active Scan is rejected", w.seal, w, StateError)
    w.finish_scan()
    rejected(R, "write after finish_scan is rejected", lambda: w.write_frames({"pa0": s[:1]}, {"pa0": v[:1]}, r[:1]),
             w, StateError)
    fmc = [dict(groups[0], interpretation="txrx_matrix")]
    rejected(R, "a PA file refuses a Tx×Rx matrix group (DOC-01 category limit)",
             lambda: w.begin_scan("b", fmc, fields), w)
    single = [dict(groups[0], interpretation="channel_group")]
    rejected(R, "an array file refuses a single-element channel group", lambda: w.begin_scan("b", single, fields), w)

    # strict mode: non-zero input in a valid=0 slot is an error
    w.begin_scan("strict", groups, fields, frames_per_chunk=16, strict_invalid=True)
    rejected(R, "strict mode rejects non-zero samples in valid=0 slots",
             lambda: w.write_frames({"pa0": s[10:12]}, {"pa0": vv}, r[10:12]), w)
    z = s[10:12].copy()
    z[0, 7] = 0
    w.write_frames({"pa0": z}, {"pa0": vv}, r[10:12])
    w.finish_scan()
    w.seal()

    rd = Reader.open(path)
    sc = rd.scans()
    R.check("committed prefixes are exactly the accepted calls", [x["n_frames"] for x in sc] == [13, 2],
            n=[x["n_frames"] for x in sc])
    x = rd.read(0, 0, 13)
    xs, xv = x.samples("pa0"), x.valid("pa0")
    R.check("accepted Frames are stored unchanged", np.array_equal(xs[:10], s[:10])
            and np.array_equal(x.records()[:10], r[:10]))
    R.check("valid=0 slot with non-zero input is zero-filled, bit 0", not xv[10, 7] and not xs[10, 7].any()
            and bool(s[10, 7].any()))
    R.check("valid=1 neighbours in the same Frame are untouched", np.array_equal(xs[10, 8], s[10, 8]))
    R.check("all-invalid Frame with omitted waveforms reads as zeros with bits 0",
            not xv[12].any() and not xs[12].any())
    rd.close()
    return R.finish(out)


if __name__ == "__main__":
    sys.exit(main())
