"""Read-side view of one Scan under a chosen commit record (WRT-02)."""

import zlib

import numpy as np

from . import codec as C
from . import layout as L


def commit_candidates(sg):
    """Commit records whose own CRC is valid, newest first."""
    recs = sg["commit"][...]
    ok = [r for r in recs if int(r["seq"]) > 0 and L.record_crc(r) == int(r["record_crc"])]
    return sorted(ok, key=lambda r: -int(r["seq"]))


class IntegrityError(Exception):
    pass


class ScanState:
    def __init__(self, sg, rec):
        self.sg, self.rec = sg, rec
        self.definition = L.loads(sg["definition"][...])
        self.F = self.definition["frames_per_chunk"]
        self.Fs = self.definition["sums_rows_per_chunk"]
        self.names = L.object_names(self.definition)
        self.dsets = [sg[n] for n in self.names]
        self.journals = [sg["journal/" + n.replace("/", "_")] for n in self.names]
        self.codecs = []
        for g in self.definition["groups"]:
            self.codecs += [g["codec"], "none"]
        self.codecs.append("none")
        self.seq = int(rec["seq"])
        self.slot = self.seq % 2
        self.complete = int(rec["scan_state"]) == L.SCAN_COMPLETE
        self.n = int(rec["n_frames"])
        self.data_chunks = int(rec["data_chunks"])
        self.sums_chunks = int(rec["sums_chunks"])
        self.tail_rows = 0 if self.complete else self.n - self.data_chunks * self.F
        self._sums = None
        self._tails = None

    # ---- verified small structures ---------------------------------------
    def tails(self):
        """Journal tails of every object, CRC-checked against the commit record."""
        if self._tails is None:
            out = []
            for i, j in enumerate(self.journals):
                rows = j[self.slot, :self.tail_rows] if self.tail_rows else j[self.slot, :0]
                if C.crc(np.ascontiguousarray(rows).tobytes()) != int(self.rec["tail_crc"][i]):
                    raise IntegrityError(f"journal tail of {self.names[i]} (slot {self.slot}) CRC mismatch")
                out.append(rows)
            self._tails = out
        return self._tails

    def sums(self):
        """Per-chunk checksum rows [data_chunks], chain-checked against the commit record."""
        if self._sums is None:
            main_rows = self.data_chunks if self.complete else self.sums_chunks * self.Fs
            main = self.sg["sums"][:main_rows] if main_rows else self.sg["sums"][:0]
            rows = main
            if not self.complete:
                tail_n = self.data_chunks - main_rows
                tail = self.sg["journal/sums"][self.slot, :tail_n]
                if C.crc(np.ascontiguousarray(tail).tobytes()) != int(self.rec["sums_tail_crc"]):
                    raise IntegrityError("journal tail of sums CRC mismatch")
                rows = np.concatenate([main, tail])
            chain = 0
            for r in rows:
                chain = zlib.crc32(r.tobytes(), chain)
            if chain != int(self.rec["sums_chain"]) or len(rows) != self.data_chunks:
                raise IntegrityError("checksum table does not match the commit record chain")
            self._sums = rows
        return self._sums

    # ---- chunk access --------------------------------------------------------
    def stored_chunk(self, obj, c):
        """Raw stored bytes of chunk c of object obj, verified against the checksum table."""
        d = self.dsets[obj]
        _, data = d.id.read_direct_chunk((c * self.F,) + (0,) * (d.ndim - 1))
        row = self.sums()[c]
        if len(data) != int(row["stored_len"][obj]) or C.crc(data) != int(row["stored_crc"][obj]):
            raise IntegrityError(f"stored chunk {c} of {self.names[obj]} fails its checksum")
        return data

    def decode_chunk(self, obj, c, data, check=True):
        d = self.dsets[obj]
        arr = C.decode(self.codecs[obj], data, d.dtype, (self.F, *d.shape[1:]))
        if check and C.crc(arr.tobytes()) != int(self.sums()[c]["decoded_crc"][obj]):
            raise IntegrityError(f"decoded chunk {c} of {self.names[obj]} fails its checksum")
        return arr
