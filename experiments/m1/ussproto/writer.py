"""Test-only Writer implementing the MAP-02 reference mechanism.

- Physical chunks of every frame-axis object are written exactly once with
  H5Dwrite_chunk; the prototype encodes them itself.
- Flush journals the partial tails into one of two slots, hands them to the OS
  (H5Fflush), then writes one of two commit records and flushes again
  (WRT-02/WRT-03). Only process crashes are in scope (ADR-0008); os_sync=True
  additionally fsyncs, for comparison only.
- Any I/O error moves the Writer into the failure state (WRT-01); the only ways
  out are close() or seal_with_failure() (LIF-01).
"""

import datetime
import os
import signal
import zlib

import h5py
import numpy as np

from . import HDF5_LOCK, StateError, ValidationError, WriteIOError
from . import codec as C
from . import layout as L
from .verify import verify_scan

_FAILPOINT_HITS = {}
_IO_ERRORS = (OSError, RuntimeError)


def _failpoint(name):
    """Kill the process at a named point (crash experiments): USS_FAILPOINT=name[@k]."""
    spec = os.environ.get("USS_FAILPOINT")
    if not spec:
        return
    target, _, nth = spec.partition("@")
    if target != name:
        return
    _FAILPOINT_HITS[name] = _FAILPOINT_HITS.get(name, 0) + 1
    if _FAILPOINT_HITS[name] >= int(nth or 1):
        os.kill(os.getpid(), signal.SIGKILL)


class _AxisObject:
    """One frame-axis dataset plus its two-slot tail journal."""

    def __init__(self, dset, journal, codec, rows_per_chunk):
        self.dset, self.journal, self.codec, self.F = dset, journal, codec, rows_per_chunk
        self.row_shape, self.dtype = dset.shape[1:], dset.dtype
        self.tail = np.zeros((rows_per_chunk, *self.row_shape), self.dtype)
        self.n_tail = 0

    def plan(self, rows):
        """Split tail+rows into whole chunks and a new tail, without mutating state."""
        joined = np.concatenate([self.tail[:self.n_tail], rows]) if self.n_tail else rows
        n_full = len(joined) // self.F
        chunks = [joined[i * self.F:(i + 1) * self.F] for i in range(n_full)]
        return chunks, joined[n_full * self.F:]

    def padded_tail(self):
        out = np.zeros((self.F, *self.row_shape), self.dtype)
        out[:self.n_tail] = self.tail[:self.n_tail]
        return out

    def set_tail(self, rows):
        self.tail[:len(rows)] = rows
        self.n_tail = len(rows)

    def write_chunk(self, index, stored):
        need = (index + 1) * self.F
        if self.dset.shape[0] < need:
            self.dset.resize(need, axis=0)
        self.dset.id.write_direct_chunk((index * self.F,) + (0,) * len(self.row_shape), stored)


class Writer:
    def __init__(self, path, f, swmr, os_sync):
        self.path, self.f, self.swmr, self.os_sync = path, f, swmr, os_sync
        self.state = "open"            # open | failed | sealed | closed
        self.failure = None
        self.category = None           # single_element | array_pa | array_fmc
        self.n_scans = 0
        self.scan = None               # active Scan state

    # ---- creation -------------------------------------------------------
    @classmethod
    def create(cls, path, *, workpiece_id, swmr=False, os_sync=False):
        with HDF5_LOCK:
            f = h5py.File(path, "w", libver=L.LIBVER, rdcc_nbytes=0)
            f.attrs["uss_format"] = L.FORMAT
            f.attrs["uss_format_version"] = L.FORMAT_VERSION
            f.attrs["spec_revision"] = L.spec_revision()
            f.attrs["workpiece_id"] = workpiece_id
            f.attrs["created_utc"] = datetime.datetime.now(datetime.UTC).isoformat()
            life = np.zeros(1, L.LIFECYCLE_DTYPE)
            life["failure_scan"] = -1
            life["record_crc"] = L.record_crc(life[0])
            f.create_dataset("lifecycle", data=life)
            f.create_group("scans")
        w = cls(path, f, swmr, os_sync)
        w._sync()
        if os_sync:
            dirfd = os.open(os.path.dirname(os.path.abspath(path)), os.O_RDONLY)
            try:
                os.fsync(dirfd)  # a new file also needs its directory entry synced
            finally:
                os.close(dirfd)
        return w

    # ---- state helpers --------------------------------------------------
    def _require(self, *states):
        if self.state not in states:
            raise StateError(f"writer is {self.state}; allowed: {states}")

    def _fail(self, exc, where):
        self.state = "failed"
        self.failure = {"where": where, "error": f"{type(exc).__name__}: {exc}",
                        "scan": self.scan["index"] if self.scan else -1,
                        "n_frames": self.scan["N"] if self.scan else 0}
        raise WriteIOError(f"{where}: {exc}") from exc

    def _sync(self):
        """Hand library caches to the OS; that survives a process crash (ADR-0008)."""
        self.f.flush()
        if self.os_sync:
            os.fsync(self.f.id.get_vfd_handle())

    # ---- Scan -----------------------------------------------------------
    def begin_scan(self, scan_id, groups, frame_record_fields, metadata=None, *,
                   frames_per_chunk=16, sums_rows_per_chunk=64, strict_invalid=False):
        """groups: [{name, interpretation, K, S, dtype, codec, stream_table}];
        frame_record_fields: [{name, dtype, unit, description}] (raw frame position first)."""
        self._require("open")
        if self.scan is not None:
            raise StateError("previous Scan not finished; it is not completed implicitly (LIF-01)")
        cats = {L.INTERPRETATIONS.get(g["interpretation"]) for g in groups}
        if None in cats or len(cats) != 1 or (self.category and cats != {self.category}):
            raise ValidationError(f"unsupported mix of interpretations {cats} (DOC-01, D-13)")
        names = [g["name"] for g in groups]
        if len(set(names)) != len(names) or not groups:
            raise ValidationError("stream group names must be unique and non-empty")
        for g in groups:
            if g["codec"] not in C.PIPELINES or len(g["stream_table"]) != g["K"]:
                raise ValidationError(f"group {g['name']}: bad codec or stream table length")
        definition = {
            "scan_id": scan_id, "frames_per_chunk": frames_per_chunk,
            "sums_rows_per_chunk": sums_rows_per_chunk, "groups": groups,
            "frame_records": {"fields": frame_record_fields},
            "metadata": sorted((metadata or {}).keys()),
        }
        metadata = metadata or {}
        F, Fs = frames_per_chunk, sums_rows_per_chunk
        index = self.n_scans
        try:
            with HDF5_LOCK:
                if self.swmr and self.f.swmr_mode:
                    # SWMR forbids new objects: leave it, create the Scan, re-enter.
                    self.f.close()
                    self.f = h5py.File(self.path, "r+", libver=L.LIBVER, rdcc_nbytes=0)
                sg = self.f.create_group(L.scan_path(index))
                sg.attrs["scan_id"] = scan_id
                sg.create_dataset("definition", data=L.dumps(definition))
                for name, (ctype, version, content) in metadata.items():
                    d = sg.create_dataset(f"metadata/{name}", data=np.frombuffer(content, np.uint8))
                    d.attrs["content_type"], d.attrs["content_version"] = ctype, version
                objs = []
                for g in groups:
                    K, S, nb = g["K"], g["S"], (g["K"] + 7) // 8
                    objs.append(self._axis(sg, f"g/{g['name']}/samples", (K, S), g["dtype"], g["codec"], F))
                    objs.append(self._axis(sg, f"g/{g['name']}/valid", (nb,), "u1", "none", F))
                rec_dtype = L.record_fields_dtype(definition)
                objs.append(self._axis(sg, "frames/records", (), rec_dtype, "none", F))
                n_obj = len(objs)
                sums = self._axis(sg, "sums", (), L.sums_dtype(n_obj), "none", Fs)
                commit = sg.create_dataset("commit", data=np.zeros(2, L.commit_dtype(n_obj)))
                self._sync()
                _failpoint("begin_scan.after_create")
                if self.swmr and not self.f.swmr_mode:
                    self.f.swmr_mode = True
        except _IO_ERRORS as exc:
            self._fail(exc, "begin_scan")
        self.category = cats.pop()
        self.n_scans += 1
        self.scan = {"index": index, "definition": definition, "groups": groups, "objs": objs,
                     "sums": sums, "commit": commit, "rec_dtype": rec_dtype, "N": 0,
                     "data_chunks": 0, "sums_chunks": 0, "sums_chain": 0, "seq": 0,
                     "strict": strict_invalid}

    def _axis(self, sg, name, row_shape, dtype, codec, rows):
        dset = sg.create_dataset(name, shape=(0, *row_shape), maxshape=(None, *row_shape),
                                 chunks=(rows, *row_shape), dtype=dtype, fillvalue=None,
                                 **C.dataset_filter_kwargs(codec))
        jname = name.replace("/", "_")
        journal = sg.create_dataset(f"journal/{jname}", data=np.zeros((2, rows - 1, *row_shape), dtype))
        return _AxisObject(dset, journal, codec, rows)

    # ---- writing --------------------------------------------------------
    def _validate(self, samples, valid, records):
        sc = self.scan
        if set(samples) != {g["name"] for g in sc["groups"]} or set(valid) != set(samples):
            raise ValidationError("samples and validity bitmaps must be given for exactly the Scan's groups")
        B = None
        rows = []
        for g in sc["groups"]:
            name, K, S = g["name"], g["K"], g["S"]
            v = valid[name]
            if v is None:
                raise ValidationError(f"{name}: validity bitmap missing (ADR-0003)")
            v = np.asarray(v)
            if v.dtype != np.bool_ or v.ndim != 2 or v.shape[1] != K:
                raise ValidationError(f"{name}: bitmap must be bool [B,{K}], got {v.dtype} {v.shape}")
            B = v.shape[0] if B is None else B
            if v.shape[0] != B or B < 1:
                raise ValidationError("inconsistent or empty Frame count")
            x = samples[name]
            if x is None:
                if v.any():
                    raise ValidationError(f"{name}: valid=1 slots without waveforms")
                x = np.zeros((B, K, S), g["dtype"])
            else:
                if x.dtype != np.dtype(g["dtype"]) or x.shape != (B, K, S):
                    raise ValidationError(f"{name}: samples must be {g['dtype']} {(B, K, S)}, got {x.dtype} {x.shape}")
                if sc["strict"] and np.any(x[~v]):
                    raise ValidationError(f"{name}: non-zero samples in valid=0 slots (strict mode)")
                x = np.where(v[:, :, None], x, 0).astype(x.dtype, copy=False)  # STA-01 zero fill
            rows += [np.ascontiguousarray(x), np.packbits(v, axis=1, bitorder="little")]
        r = np.asarray(records)
        if r.dtype != sc["rec_dtype"] or r.shape != (B,):
            raise ValidationError(f"frame records must be {sc['rec_dtype']} [{B}]")
        rows.append(r)
        if sc["N"] + B >= 2**63:
            raise ValidationError("frame count overflow")
        return B, rows

    def _sums_row(self, enc):
        row = np.zeros((), self.scan["sums"].dtype)
        row["stored_len"] = [len(stored) for stored, _ in enc]
        row["stored_crc"] = [C.crc(stored) for stored, _ in enc]
        row["decoded_crc"] = [C.crc(np.ascontiguousarray(chunk).tobytes()) for _, chunk in enc]
        return row

    def _write_chunks(self, encoded):
        """Write whole data chunks once, plus any sums chunks they complete."""
        sc, sums = self.scan, self.scan["sums"]
        rows = np.array([self._sums_row(enc) for enc in encoded], sums.dtype)
        sums_chunks, sums_tail = sums.plan(rows)
        with HDF5_LOCK:
            for i, enc in enumerate(encoded):
                for o, (stored, _) in zip(sc["objs"], enc):
                    o.write_chunk(sc["data_chunks"] + i, stored)
                    _failpoint("write.after_chunk")
            for j, chunk in enumerate(sums_chunks):
                sums.write_chunk(sc["sums_chunks"] + j, C.encode("none", chunk))
        return rows, sums_chunks, sums_tail

    def _publish(self, rows, sums_chunks, sums_tail):
        sc = self.scan
        for r in rows:
            sc["sums_chain"] = zlib.crc32(r.tobytes(), sc["sums_chain"])
        sc["sums"].set_tail(sums_tail)
        sc["data_chunks"] += len(rows)
        sc["sums_chunks"] += len(sums_chunks)

    def write_frames(self, samples, valid, records):
        """Append B complete Frames; the whole call is one commit unit (WRT-01)."""
        self._require("open")
        if self.scan is None:
            raise StateError("no active Scan")
        sc = self.scan
        B, rows = self._validate(samples, valid, records)
        plans = [o.plan(r) for o, r in zip(sc["objs"], rows)]
        # encode outside the HDF5 lock
        encoded = [[(C.encode(o.codec, p[0][i]), p[0][i]) for o, p in zip(sc["objs"], plans)]
                   for i in range(len(plans[0][0]))]
        try:
            written = self._write_chunks(encoded)
        except _IO_ERRORS as exc:
            self._fail(exc, "write_frames")
        # success: publish the new in-memory commit state
        for o, p in zip(sc["objs"], plans):
            o.set_tail(p[1])
        self._publish(*written)
        sc["N"] += B
        return sc["N"]

    # ---- Flush / finish / seal -------------------------------------------
    def _commit(self, scan_state):
        """Journal the tails, sync, write the next commit slot, sync (MAP-02 item 2)."""
        sc = self.scan
        seq = sc["seq"] + 1
        slot = seq % 2
        rec = np.zeros((), L.commit_dtype(len(sc["objs"])))
        with HDF5_LOCK:
            for i, o in enumerate(sc["objs"]):
                if o.n_tail:
                    o.journal[slot, :o.n_tail] = o.tail[:o.n_tail]
                rec["tail_crc"][i] = C.crc(np.ascontiguousarray(o.tail[:o.n_tail]).tobytes())
            s = sc["sums"]
            if s.n_tail:
                s.journal[slot, :s.n_tail] = s.tail[:s.n_tail]
            rec["sums_tail_crc"] = C.crc(np.ascontiguousarray(s.tail[:s.n_tail]).tobytes())
            _failpoint("flush.after_journal")
            self._sync()
            rec["seq"], rec["scan_state"], rec["n_frames"] = seq, scan_state, sc["N"]
            rec["data_chunks"], rec["sums_chunks"], rec["sums_chain"] = sc["data_chunks"], sc["sums_chunks"], sc["sums_chain"]
            rec["record_crc"] = L.record_crc(rec)
            sc["commit"][slot] = rec
            _failpoint("flush.after_commit_write")
            self._sync()
        sc["seq"] = seq

    def flush(self):
        """WRT-03: after success, all earlier successful writes survive a later process crash."""
        self._require("open")
        try:
            if self.scan is not None:
                self._commit(L.SCAN_ACTIVE)
            else:
                with HDF5_LOCK:
                    self._sync()
        except _IO_ERRORS as exc:
            self._fail(exc, "flush")

    def finish_scan(self):
        """Write the last partial chunks once, then an implied Flush with state complete."""
        self._require("open")
        if self.scan is None:
            raise StateError("no active Scan")
        sc = self.scan
        try:
            if sc["objs"][0].n_tail:
                enc = [(C.encode(o.codec, o.padded_tail()), o.padded_tail()) for o in sc["objs"]]
                written = self._write_chunks([enc])
                for o in sc["objs"]:
                    o.n_tail = 0
                self._publish(*written)
            s = sc["sums"]
            if s.n_tail:
                with HDF5_LOCK:
                    s.write_chunk(sc["sums_chunks"], C.encode("none", s.padded_tail()))
                sc["sums_chunks"] += 1
                s.n_tail = 0
            _failpoint("finish.after_final_chunks")
            self._commit(L.SCAN_COMPLETE)
            _failpoint("finish.after_commit")
        except _IO_ERRORS as exc:
            self._fail(exc, "finish_scan")
        self.scan = None

    def _write_lifecycle(self, state, failure=None):
        life = np.zeros(1, L.LIFECYCLE_DTYPE)
        life["state"], life["n_scans"], life["failure_scan"] = state, self.n_scans, -1
        if failure:
            life["failure_scan"] = failure["scan"]
            life["failure_n_frames"] = failure["n_frames"]
            life["failure_code"] = 1
            life["failure_message"] = f"{failure['where']}: {failure['error']}"[:200].encode("utf-8", "replace")
        life["record_crc"] = L.record_crc(life[0])
        with HDF5_LOCK:
            _failpoint("seal.before_lifecycle")
            self.f["lifecycle"][0] = life[0]
            self._sync()
            _failpoint("seal.after_lifecycle")

    def _close_synced(self):
        """H5Fclose rewrites the superblock status flags; sealing ends only after it."""
        with HDF5_LOCK:
            self.f.close()
        if self.os_sync:
            fd = os.open(self.path, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def seal(self):
        self._require("open")
        if self.scan is not None:
            raise StateError("active Scan must be finished before sealing (LIF-01)")
        try:
            self._write_lifecycle(L.SEALED)
            self._close_synced()
        except _IO_ERRORS as exc:
            self._fail(exc, "seal")
        self.state = "sealed"

    def seal_with_failure(self):
        """LIF-01: persist the committed range, verify it, then mark the failure."""
        self._require("failed")
        try:
            if self.scan is not None:
                self._commit(L.SCAN_ACTIVE)
            with HDF5_LOCK:
                reports = [verify_scan(self.f[L.scan_path(i)])[0] for i in range(self.n_scans)]
            bad = [r for r in reports if r["verified_n"] != r["declared_n"] or r["failures"]]
            if bad:
                raise StateError(f"committed data failed verification: {bad}")
            self._write_lifecycle(L.SEALED_WITH_FAILURE, self.failure)
            self._close_synced()
        except _IO_ERRORS as exc:
            raise WriteIOError(f"seal_with_failure: {exc}") from exc
        self.state = "sealed"
        return reports

    def close(self):
        """Close without sealing: the file is left as not normally closed (LIF-01)."""
        if self.state in ("sealed", "closed"):
            return
        with HDF5_LOCK:
            try:
                self.f.close()
            except Exception:
                pass
        self.state = "closed"
