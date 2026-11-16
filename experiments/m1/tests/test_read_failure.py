"""Read failure atomicity on a corrupted copy (IO-01, BUF-01, VAL-01, LIF-02).

One stored samples chunk (Frames 48..63) of a sealed file copy is corrupted.
push must leave the caller's buffers byte-identical, poll must publish nothing,
the earlier poll borrow must have ended, and deep verification must stop the
verified prefix at Frame 48. Plain HDF5 reads of the same chunk are recorded
for contrast.
"""

import os
import shutil
import sys

import h5py
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import H5CLEAR, RECORD_DTYPE, SRC, Results, TestdataSource, run_dir, scan_definition  # noqa: E402

from ussproto import InternalDecodeError, ReadIOError  # noqa: E402
from ussproto.reader import Reader  # noqa: E402
from ussproto.writer import Writer  # noqa: E402

N, F, BAD = 200, 16, 3


def build(path, src, codec):
    groups, fields = scan_definition(codec)
    w = Writer.create(path, workpiece_id="read-failure")
    w.begin_scan("s", groups, fields, frames_per_chunk=F)
    for a in range(0, N, 50):
        s, v, r = src.frames(a, a + 50)
        w.write_frames({"pa0": s}, {"pa0": v}, r)
    w.finish_scan()
    w.seal()


def corrupt(path):
    with h5py.File(path, "r") as f:
        info = f["scans/s0000/g/pa0/samples"].id.get_chunk_info_by_coord((BAD * F, 0, 0))
    off = info.byte_offset + info.size // 2
    with open(path, "r+b") as fh:
        fh.seek(off)
        old = fh.read(64)
        fh.seek(off)
        fh.write(bytes(b ^ 0x5A for b in old))
    return {"chunk_offset": int(info.byte_offset), "chunk_size": int(info.size), "flipped_at": int(off)}


def buffers(count):
    return {"groups": {"pa0": {"samples": np.full((count, 125, 1000), 0xBEEF, np.uint16),
                               "valid": np.ones((count, 125), bool)}},
            "records": np.full(count, -7, RECORD_DTYPE)}


def same(a, b):
    return (np.array_equal(a["groups"]["pa0"]["samples"], b["groups"]["pa0"]["samples"])
            and np.array_equal(a["groups"]["pa0"]["valid"], b["groups"]["pa0"]["valid"])
            and np.array_equal(a["records"], b["records"]))


def main():
    out = run_dir()
    R = Results("read_failure")
    src = TestdataSource(SRC)
    es, ev, er = src.frames(0, N)
    for codec in ("none", "shuffle-deflate1"):
        good, bad = out / f"rf-{codec}.h5", out / f"rf-{codec}-corrupt.h5"
        build(good, src, codec)
        shutil.copyfile(good, bad)
        R.note(f"{codec} corruption", corrupt(bad))
        r = Reader.open(bad)
        v1 = r.read(0, 0, 16)
        tgt, ref = buffers(32), buffers(32)
        try:
            r.read(0, 40, 32, out=tgt)
            R.check(f"{codec}: push over the corrupt chunk fails", False)
        except ReadIOError as e:
            R.check(f"{codec}: push over the corrupt chunk fails", not isinstance(e, InternalDecodeError),
                    error=str(e)[:200])
        R.check(f"{codec}: push target (samples, bitmap, records) byte-identical after failure", same(tgt, ref))
        R.check(f"{codec}: the earlier poll borrow ended at the failed read", not v1.alive)
        try:
            r.read(0, 40, 32)
            R.check(f"{codec}: poll over the corrupt chunk publishes nothing", False)
        except ReadIOError:
            R.check(f"{codec}: poll over the corrupt chunk publishes nothing", True)
        ok = buffers(48)
        r.read(0, 0, 48, out=ok)
        R.check(f"{codec}: Frames before the corrupt chunk still read correctly",
                np.array_equal(ok["groups"]["pa0"]["samples"], es[:48]))
        # contrast: single-phase delivery (no stored-checksum pass) may modify the target before failing
        tgt2 = buffers(32)
        try:
            r.read(0, 40, 32, out=tgt2, verify=False)
            outcome = "returned without error"
        except ReadIOError as e:
            outcome = type(e).__name__
        changed = not same(tgt2, ref)
        wrong = not np.array_equal(tgt2["groups"]["pa0"]["samples"], es[40:72])
        R.note(f"{codec}: single-phase read without checksums", {"outcome": outcome, "target_modified": changed,
                                                                 "delivered_wrong_values": wrong})
        r.close()

        rec = Reader.open_recovery(bad, h5clear=H5CLEAR, workdir=out)
        rep = rec.recovery_reports["scans"][0]
        R.check(f"{codec}: deep verification stops the verified prefix at the corrupt chunk",
                rep["declared_n"] == N and rep["verified_n"] == BAD * F and rep["failures"],
                declared=rep["declared_n"], verified=rep["verified_n"], failures=rep["failures"][:2])
        R.check(f"{codec}: recovery view exposes only the verified prefix", rec.scans()[0]["n_frames"] == BAD * F)
        rec.close()

        with h5py.File(bad, "r") as f:
            try:
                x = f["scans/s0000/g/pa0/samples"][BAD * F:(BAD + 1) * F]
                plain = "silently wrong values" if not np.array_equal(x, es[BAD * F:(BAD + 1) * F]) else "correct"
            except Exception as e:
                plain = f"error: {type(e).__name__}"
        R.note(f"{codec}: plain HDF5 read of the corrupt chunk", plain)
    return R.finish(out)


if __name__ == "__main__":
    sys.exit(main())
