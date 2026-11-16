"""Probe HDF5 behaviour for "Flush, keep appending, then the process dies".

Writer mode (run as a child process):
    python -I flush_crash.py write <cfg> <h5path> <sidecar.json>
Driver mode:
    python -I flush_crash.py drive <outdir> <h5clear>

The writer appends frames one at a time into a chunked dataset, makes the first
FLUSHED frames durable (H5Fflush + fsync), keeps appending without a flush and
then exits via os._exit() so HDF5 never closes the file (simulated process
crash; this is NOT a power-loss test). The driver then inspects what a
read-only reader can see of the flushed frames.
"""

import json
import os
import shutil
import subprocess
import sys

import h5py
import numpy as np

S = 4096          # samples per frame (u16) -> 8 KiB per frame
C = 4             # frames per chunk
FLUSHED = 10      # frames 0..9 flushed; chunk 2 holds frames 8,9 (partial)
TOTAL = 16        # frames 10..15 appended after the flush, never flushed

SB2 = ("v108", "latest")
BASE = {"libver": SB2, "comp": "szip", "fs": None, "rdcc": 0, "swmr": False, "spacer": False, "probe": True}
CONFIGS = {
    "sb2_szip_fsm_nocache": {},
    "sb2_szip_none_nocache": {"fs": "none"},
    "sb2_szip_fsm_cache_noprobe": {"rdcc": None, "probe": False},
    "sb2_szip_fsm_nocache_spacer": {"spacer": True},
    "sb2_szip_none_nocache_spacer": {"fs": "none", "spacer": True},
    "sb2_raw_fsm_nocache": {"comp": None},
    "sb3_szip_fsm_nocache": {"libver": ("v110", "latest")},
    "swmr_szip_nocache": {"libver": "latest", "swmr": True},
}
CONFIGS = {k: {**BASE, **v} for k, v in CONFIGS.items()}


def frame(n):
    return np.random.default_rng(1000 + n).integers(0, 65536, S, dtype=np.uint16)


def chunk_info(dset, row):
    try:
        info = dset.id.get_chunk_info_by_coord((row, 0))
        return {"byte_offset": int(info.byte_offset), "size": int(info.size)}
    except Exception as exc:  # chunk not allocated yet
        return {"error": repr(exc)}


def write(cfg, path, sidecar):
    c = CONFIGS[cfg]
    kw = {"libver": c["libver"]}
    if c["fs"]:
        kw["fs_strategy"] = c["fs"]
    if c["rdcc"] is not None:
        kw["rdcc_nbytes"] = c["rdcc"]
    log = {"cfg": cfg, "events": []}
    f = h5py.File(path, "w", **kw)
    d = f.create_dataset("x", shape=(0, S), maxshape=(None, S), chunks=(C, S),
                         dtype="u2", compression=c["comp"])
    log["fs_strategy_in_file"] = list(f.id.get_create_plist().get_file_space_strategy())
    if c["swmr"]:
        f.swmr_mode = True
    fd = f.id.get_vfd_handle()
    for n in range(TOTAL):
        if n == FLUSHED:
            if c["spacer"]:  # make sure chunk 2 is not the last block before EOA
                pad = f.create_dataset("pad", shape=(65536,), dtype="u1")
                pad[...] = 1
                log["pad_offset"] = int(pad.id.get_offset())
            f.flush()
            os.fsync(fd)
            log["flushed_chunk2"] = chunk_info(d, 8)
            log["flushed_file_size"] = os.path.getsize(path)
        d.resize(n + 1, axis=0)
        d[n] = frame(n)
        if n >= FLUSHED and c["probe"]:
            log["events"].append({"after_frame": n, "chunk2": chunk_info(d, 8),
                                  "chunk3": chunk_info(d, 12)})
    log["crash_file_size"] = os.path.getsize(path)
    with open(sidecar, "w") as fh:
        json.dump(log, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os._exit(0)  # simulate a crash: no H5Fclose, no atexit handlers


def inspect(path, swmr=False):
    res = {"path": os.path.basename(path), "swmr_read": swmr}
    try:
        with h5py.File(path, "r", swmr=swmr) as f:
            d = f["x"]
            res["shape"] = list(d.shape)
            frames = {}
            for n in range(min(d.shape[0], TOTAL)):
                try:
                    ok = bool(np.array_equal(d[n], frame(n)))
                    frames[n] = "ok" if ok else "MISMATCH"
                except Exception as exc:
                    frames[n] = "READ_ERROR: " + str(exc).splitlines()[0][:120]
            res["frames"] = frames
    except Exception as exc:
        res["open_error"] = str(exc).splitlines()[0][:200]
    return res


def overlaps(a, b):
    return a["byte_offset"] < b["byte_offset"] + b["size"] and b["byte_offset"] < a["byte_offset"] + a["size"]


def drive(outdir, h5clear):
    report = {"h5py": h5py.version.version, "hdf5": h5py.version.hdf5_version, "runs": {}}
    for cfg, c in CONFIGS.items():
        swmr = c["swmr"]
        path = os.path.join(outdir, cfg + ".h5")
        sidecar = os.path.join(outdir, cfg + ".json")
        proc = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "write", cfg, path, sidecar],
                              capture_output=True, text=True)
        run = {"writer_rc": proc.returncode, "writer_stderr": proc.stderr[-400:]}
        if os.path.exists(sidecar):
            log = json.load(open(sidecar))
            flushed = log.get("flushed_chunk2", {})
            run["flushed_chunk2"] = flushed
            run["file_size_at_flush"] = log.get("flushed_file_size")
            run["file_size_at_crash"] = log.get("crash_file_size")
            run["fs_strategy_in_file"] = log.get("fs_strategy_in_file")
            run["pad_offset"] = log.get("pad_offset")
            reused = []
            if "byte_offset" in flushed:
                for ev in log["events"]:
                    for key in ("chunk2", "chunk3"):
                        loc = ev[key]
                        if "byte_offset" in loc and loc != flushed and overlaps(loc, flushed):
                            reused.append((ev["after_frame"], key, loc))
            run["post_flush_writes_overlapping_flushed_chunk2"] = reused
        run["read_only_open"] = inspect(path)
        if swmr:
            run["swmr_read_open"] = inspect(path, swmr=True)
        if "open_error" in run["read_only_open"]:
            copy = os.path.join(outdir, cfg + ".cleared-copy.h5")
            shutil.copyfile(path, copy)
            cp = subprocess.run([h5clear, "-s", copy], capture_output=True, text=True)
            run["h5clear_rc"] = cp.returncode
            run["after_h5clear_on_copy"] = inspect(copy)
        report["runs"][cfg] = run
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    if sys.argv[1] == "write":
        write(*sys.argv[2:5])
    else:
        drive(*sys.argv[2:4])
