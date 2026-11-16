"""Test-only Reader: Core I/O by Scan, Frame range and stream group (CORE-01).

poll returns a BatchView borrowed from the Reader; push copies into caller
buffers. Every sample read ends the previous poll borrow at its start (BUF-01).
push uses the two-phase read of MAP-02: all stored chunks are fetched and
checksum-verified before the caller's buffers are touched (IO-01).
"""

import ctypes
import os
import shutil
import subprocess
import tempfile

import h5py
import numpy as np

from . import HDF5_LOCK, BorrowExpired, InternalDecodeError, ReadIOError, StateError, ValidationError
from . import layout as L
from .scan import IntegrityError, ScanState, commit_candidates
from .verify import lifecycle, verify_scan


RECOVERY_METHODS = ("read-only", "swmr-read", "clear-flags-in-memory", "h5clear-on-copy")


def _libhdf5():
    """The libhdf5 that h5py is linked to, for the one call h5py does not expose."""
    for line in open("/proc/self/maps"):
        p = line.split()[-1]
        if "/libhdf5.so" in p:
            lib = ctypes.CDLL(p)
            lib.H5Pexist.argtypes = lib.H5Pset.argtypes = [ctypes.c_int64, ctypes.c_char_p, ctypes.c_void_p]
            lib.H5Pexist.restype = lib.H5Pset.restype = ctypes.c_int
            return lib
    raise OSError("libhdf5 is not loaded")


def _open_clearing_status_flags(path):
    """Read-only open of a file a crashed writer left marked "open for write".

    Sets the fapl property h5clear uses ("clear_status_flags", private to HDF5
    but registered on every fapl). H5F_open clears the superblock flags in
    memory before its read-only consistency check; nothing is written to the
    file, so LIF-02 holds without copying it.
    """
    lib, name = _libhdf5(), b"clear_status_flags"
    fapl = h5py.h5p.create(h5py.h5p.FILE_ACCESS)
    if lib.H5Pexist(fapl.id, name, None) <= 0 or lib.H5Pset(fapl.id, name, ctypes.byref(ctypes.c_bool(True))) < 0:
        raise OSError("this HDF5 build has no clear_status_flags property")
    return h5py.File(h5py.h5f.open(os.fsencode(path), h5py.h5f.ACC_RDONLY, fapl=fapl))


class BatchView:
    """Borrowed poll result; valid until the Reader's next sample read or close."""

    def __init__(self, reader, gen, scan, start, arrays, records):
        self._reader, self._gen = reader, gen
        self.scan, self.start = scan, start
        self._arrays, self._records = arrays, records

    @property
    def alive(self):
        return not self._reader.closed and self._reader._gen == self._gen

    def _check(self):
        if not self.alive:
            raise BorrowExpired("poll view used after its borrow ended")

    @property
    def count(self):
        self._check()
        return len(self._records)

    def samples(self, group):
        self._check()
        return self._arrays[group][0]

    def valid(self, group):
        self._check()
        return self._arrays[group][1]

    def records(self):
        self._check()
        return self._records


class Reader:
    def __init__(self, f, states, life, recovery_reports=None, opened_path=None):
        self.f, self._states, self._life = f, states, life
        self.recovery_reports = recovery_reports
        self.opened_path = opened_path
        self.closed = False
        self._gen = 0

    # ---- opening ------------------------------------------------------------
    @classmethod
    def open(cls, path):
        """Normal read of a sealed (or sealed-with-failure) file (LIF-01)."""
        with HDF5_LOCK:
            f = h5py.File(path, "r")
            life = lifecycle(f)
            if life["state"] not in ("sealed", "sealed_with_failure"):
                f.close()
                raise StateError(f"file is {life['state']}; normal reading needs a sealed file, use recovery")
            states = []
            for i in range(life["n_scans"]):
                cands = commit_candidates(f[L.scan_path(i)])
                if not cands:
                    f.close()
                    raise StateError(f"Scan {i} has no commit record")
                states.append(ScanState(f[L.scan_path(i)], cands[0]))
        return cls(f, states, life, opened_path=path)

    @classmethod
    def open_recovery(cls, path, *, h5clear="h5clear", workdir=None, methods=RECOVERY_METHODS):
        """LIF-02: read-only recovery; the source file is never modified.

        Tries the open methods in order; "h5clear-on-copy" copies the whole file.
        """
        with HDF5_LOCK:
            f, how = None, None
            for label in methods:
                try:
                    if label == "read-only":
                        f = h5py.File(path, "r")
                    elif label == "swmr-read":
                        f = h5py.File(path, "r", swmr=True)
                    elif label == "clear-flags-in-memory":
                        f = _open_clearing_status_flags(path)
                    else:
                        tmp = tempfile.mkdtemp(dir=workdir, prefix="uss-recovery-")
                        copy = os.path.join(tmp, os.path.basename(path))
                        shutil.copyfile(path, copy)
                        subprocess.run([h5clear, "-s", copy], check=True, capture_output=True)
                        f, path = h5py.File(copy, "r"), copy
                    how = label
                    break
                except OSError:
                    continue
            if f is None:
                raise OSError(f"no recovery open method succeeded: {methods}")
            life = lifecycle(f)
            states, reports = [], []
            n = 0
            while L.scan_path(n) in f:
                n += 1
            for i in range(n):
                rep, st = verify_scan(f[L.scan_path(i)])
                reports.append(rep)
                if st is not None:
                    st.n = rep["verified_n"]  # expose only the verified prefix
                states.append(st)
        return cls(f, states, life, {"open_method": how, "lifecycle": life, "scans": reports}, opened_path=path)

    # ---- catalogue (does not end a poll borrow) -------------------------------
    def lifecycle(self):
        return dict(self._life)

    def scans(self):
        return [None if st is None else {"index": i, "scan_id": st.sg.attrs["scan_id"], "n_frames": st.n,
                                          "state": "complete" if st.complete else "active",
                                          "definition": st.definition}
                for i, st in enumerate(self._states)]

    def layout(self, scan):
        """Storage geometry for sizing and aligning caller buffers (catalogue query).

        Per group: frames per storage chunk and bytes per Frame of each delivered
        array (samples, bool bitmap), plus bytes per Frame of the frame records.
        """
        st = self._states[scan]
        groups = {}
        for g in st.definition["groups"]:
            groups[g["name"]] = {"frames_per_chunk": st.F, "K": g["K"], "S": g["S"], "dtype": g["dtype"],
                                 "samples_bytes_per_frame": g["K"] * g["S"] * np.dtype(g["dtype"]).itemsize,
                                 "valid_bytes_per_frame": g["K"]}
        return {"n_frames": st.n, "groups": groups,
                "records_bytes_per_frame": L.record_fields_dtype(st.definition).itemsize}

    def metadata(self, scan, name):
        with HDF5_LOCK:
            d = self._states[scan].sg["metadata/" + name]
            return d.attrs["content_type"], d.attrs["content_version"], d[...].tobytes()

    # ---- Core I/O -----------------------------------------------------------
    def read(self, scan, start, count, groups=None, out=None, *, verify=True):
        """Read Frames [start, start+count) of the given stream groups.

        out=None -> poll (returns BatchView); out=dict -> push into caller buffers:
        {"groups": {g: {"samples": [B,K,S], "valid": bool [B,K]}}, "records": [B]}.
        """
        if self.closed:
            raise StateError("reader closed")
        self._gen += 1  # BUF-01: ends the previous poll borrow, whatever happens next
        st = self._states[scan] if 0 <= scan < len(self._states) else None
        if st is None:
            raise ValidationError(f"no readable Scan {scan}")
        gdefs = {g["name"]: g for g in st.definition["groups"]}
        groups = list(gdefs) if groups is None else list(groups)
        if not groups or any(g not in gdefs for g in groups) or len(set(groups)) != len(groups):
            raise ValidationError(f"unknown or repeated stream groups {groups}")
        if count < 1 or start < 0 or start + count > st.n:
            raise ValidationError(f"Frames [{start},{start + count}) outside [0,{st.n})")
        rec_dtype = L.record_fields_dtype(st.definition)
        if out is not None:
            for g in groups:
                K, S = gdefs[g]["K"], gdefs[g]["S"]
                o = out["groups"][g]
                if o["samples"].shape != (count, K, S) or o["samples"].dtype != np.dtype(gdefs[g]["dtype"]):
                    raise ValidationError(f"push target for {g} must be {gdefs[g]['dtype']} {(count, K, S)}")
                if o["valid"].shape != (count, K) or o["valid"].dtype != np.bool_:
                    raise ValidationError(f"push bitmap target for {g} must be bool {(count, K)}")
            if out["records"].shape != (count,) or out["records"].dtype != rec_dtype:
                raise ValidationError("push record target has the wrong dtype/shape")
        objs = []
        for g in groups:
            i = st.names.index(f"g/{g}/samples")
            objs += [i, i + 1]
        objs.append(len(st.names) - 1)
        try:
            staged = self._fetch(st, objs, start, count, verify)
        except Exception as exc:  # IntegrityError, h5py/OS errors
            raise ReadIOError(f"read failed before delivery: {type(exc).__name__}: {exc}") from exc
        if out is None:
            targets = self._alloc(st, gdefs, groups, count, rec_dtype)
        else:
            targets = [out["groups"][g][k] for g in groups for k in ("samples", "valid")] + [out["records"]]
        try:
            self._deliver(st, objs, staged, start, count, targets, verify)
        except IntegrityError as exc:
            raise InternalDecodeError(f"decoded data disagrees after verified fetch; target undefined: {exc}") from exc
        except Exception as exc:  # decoder failure after a verified fetch
            raise InternalDecodeError(f"decoder failed after verified fetch; target undefined: {exc}") from exc
        if out is not None:
            return None
        for t in targets:
            t.setflags(write=False)
        arrays = {g: (targets[2 * k], targets[2 * k + 1]) for k, g in enumerate(groups)}
        return BatchView(self, self._gen, scan, start, arrays, targets[-1])

    def _alloc(self, st, gdefs, groups, count, rec_dtype):
        t = []
        for g in groups:
            t += [np.empty((count, gdefs[g]["K"], gdefs[g]["S"]), gdefs[g]["dtype"]),
                  np.empty((count, gdefs[g]["K"]), np.bool_)]
        return t + [np.empty(count, rec_dtype)]

    def _fetch(self, st, objs, start, count, verify):
        """Phase 1: stored bytes of every needed chunk (checksum-verified) and journal tails."""
        F, end = st.F, start + count
        main_end = min(end, st.data_chunks * st.F)
        chunks = range(start // F, (main_end - 1) // F + 1) if start < main_end else range(0)
        staged = {}
        with HDF5_LOCK:
            for obj in objs:
                for c in chunks:
                    if verify:
                        staged[obj, c] = st.stored_chunk(obj, c)
                    else:
                        d = st.dsets[obj]
                        staged[obj, c] = d.id.read_direct_chunk((c * F,) + (0,) * (d.ndim - 1))[1]
            if end > st.data_chunks * F:
                tails = st.tails()
                for obj in objs:
                    staged[obj, "tail"] = tails[obj]
        return staged

    def _deliver(self, st, objs, staged, start, count, targets, verify):
        """Phase 2: decode and copy rows into the targets (no HDF5 calls)."""
        F, end, base = st.F, start + count, st.data_chunks * st.F
        for obj, target in zip(objs, targets):
            is_valid = st.names[obj].endswith("/valid")
            K = target.shape[1] if is_valid else None
            for key, data in ((k, v) for k, v in staged.items() if k[0] == obj):
                c = key[1]
                if c == "tail":
                    rows, lo = data, base
                else:
                    rows, lo = st.decode_chunk(obj, c, data, check=verify), c * F
                a, b = max(start, lo), min(end, lo + len(rows))
                if a >= b:
                    continue
                part = rows[a - lo:b - lo]
                if is_valid:
                    part = np.unpackbits(part, axis=1, bitorder="little", count=K).astype(bool)
                target[a - start:b - start] = part

    def close(self):
        if not self.closed:
            self._gen += 1
            with HDF5_LOCK:
                self.f.close()
            self.closed = True
