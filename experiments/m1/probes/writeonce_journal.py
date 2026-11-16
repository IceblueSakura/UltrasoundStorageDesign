"""Smoke test of the proposed mechanism: write-once full chunks + A/B tail journal.

    python -I writeonce_journal.py drive <outdir>

Same stress as flush_crash.py (szip, 4-frame chunks, chunk cache disabled,
default free-space strategy): 10 frames, Flush, 6 more frames, process exit
without close. Main dataset only ever receives whole chunks written once; on
Flush the partial tail goes to one of two journal slots, and a two-slot commit
record (seq, N, n_full_chunks, crc32 of the tail) points to it.
"""

import json
import os
import subprocess
import sys
import zlib

import h5py
import numpy as np

S, C = 4096, 4
FLUSHED, TOTAL = 10, 16


def frame(n):
    return np.random.default_rng(1000 + n).integers(0, 65536, S, dtype=np.uint16)


class Writer:
    def __init__(self, path, libver, swmr):
        self.f = h5py.File(path, "w", libver=libver, rdcc_nbytes=0)
        self.x = self.f.create_dataset("x", shape=(0, S), maxshape=(None, S), chunks=(C, S),
                                       dtype="u2", compression="szip")
        self.j = self.f.create_dataset("journal", shape=(2, C - 1, S), dtype="u2")  # contiguous
        self.commit = self.f.create_dataset("commit", shape=(2, 4), dtype="u8")       # seq, N, full, crc
        self.f.flush()
        self.f["journal"][...] = 0  # allocate the slots now, before streaming
        self.commit[...] = 0
        if swmr:
            self.f.swmr_mode = True
        self.fd = self.f.id.get_vfd_handle()
        self.tail, self.n, self.full, self.seq = [], 0, 0, 0

    def append(self, data):
        self.tail.append(data)
        self.n += 1
        if len(self.tail) == C:  # whole chunk: first and only write of this chunk
            self.x.resize((self.full + 1) * C, axis=0)
            self.x[self.full * C:(self.full + 1) * C] = np.stack(self.tail)
            self.full += 1
            self.tail = []

    def flush(self):
        self.seq += 1
        slot = self.seq % 2
        tail = np.zeros((C - 1, S), dtype=np.uint16)
        if self.tail:
            tail[:len(self.tail)] = np.stack(self.tail)
        self.j[slot] = tail
        crc = zlib.crc32(tail[:len(self.tail)].tobytes())
        self.f.flush()
        os.fsync(self.fd)  # data + journal durable before the commit record moves
        self.commit[slot] = [self.seq, self.n, self.full, crc]
        self.f.flush()
        os.fsync(self.fd)


def recover(path, swmr):
    with h5py.File(path, "r", swmr=swmr) as f:
        recs = sorted((list(map(int, r)) for r in f["commit"][...]), reverse=True)
        for seq, n, full, crc in recs:
            if seq == 0:
                continue
            slot = seq % 2
            tail = f["journal"][slot][: n - full * C]
            if zlib.crc32(tail.tobytes()) != crc:
                continue
            main = f["x"][: full * C]
            frames = list(main) + list(tail)
            return {"seq": seq, "N": n, "full_chunks": full,
                    "frames_ok": [bool(np.array_equal(frames[i], frame(i))) for i in range(n)]}
    return {"error": "no valid commit record"}


def write(path, libver, swmr):
    w = Writer(path, libver if libver == "latest" else tuple(libver.split(",")), swmr == "1")
    for n in range(TOTAL):
        if n == FLUSHED:
            w.flush()
        w.append(frame(n))
    os._exit(0)


def drive(outdir):
    out = {}
    for name, libver, swmr in (("sb2_fsm", "v108,latest", "0"), ("swmr", "latest", "1")):
        path = os.path.join(outdir, name + ".h5")
        p = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "write", path, libver, swmr],
                           capture_output=True, text=True)
        res = {"writer_rc": p.returncode, "stderr": p.stderr[-300:]}
        try:
            res["recovered"] = recover(path, swmr == "1")
        except Exception as exc:
            res["recover_error"] = str(exc).splitlines()[0][:200]
        out[name] = res
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "write":
        write(*sys.argv[2:5])
    else:
        drive(sys.argv[2])
