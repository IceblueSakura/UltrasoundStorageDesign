"""Independent check of a ussproto file against testdata/scan.h5.

    python -I experiments/m1/tools/check_independent.py FILE SRC [--limit N]

Does not import ussproto: it follows the test-only layout documented in
experiments/m1/README.md, decodes samples through HDF5's own filter pipeline,
recomputes every checksum and compares all values with the export. Run it under
different HDF5 versions to check readability (ADR-0005).
"""

import argparse
import json
import sys
import zlib
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.testdata_source import TestdataSource  # noqa: E402


def crc(b):
    return zlib.crc32(b) & 0xFFFFFFFF


def rec_ok(rec):
    raw = np.asarray(rec).tobytes()
    return crc(raw[:-4]) == int(rec["record_crc"])


def check_scan(sg, src, limit, out):
    definition = json.loads(sg["definition"][...].tobytes())
    F, Fs = definition["frames_per_chunk"], definition["sums_rows_per_chunk"]
    names = []
    for g in definition["groups"]:
        names += [f"g/{g['name']}/samples", f"g/{g['name']}/valid"]
    names.append("frames/records")
    commits = [r for r in sg["commit"][...] if int(r["seq"]) > 0 and rec_ok(r)]
    rec = max(commits, key=lambda r: int(r["seq"]))
    complete = int(rec["scan_state"]) == 1
    N, chunks = int(rec["n_frames"]), int(rec["data_chunks"])
    slot = int(rec["seq"]) % 2
    res = {"scan_id": sg.attrs["scan_id"], "commit_seq": int(rec["seq"]), "complete": complete,
           "n_frames": N, "data_chunks": chunks, "problems": []}

    # checksum table and its chain
    sums_main = chunks if complete else int(rec["sums_chunks"]) * Fs
    sums = sg["sums"][:sums_main]
    if not complete:
        tail = sg["journal/sums"][slot, :chunks - sums_main]
        if crc(np.ascontiguousarray(tail).tobytes()) != int(rec["sums_tail_crc"]):
            res["problems"].append("sums journal tail CRC")
        sums = np.concatenate([sums, tail])
    chain = 0
    for r in sums:
        chain = zlib.crc32(r.tobytes(), chain)
    if chain != int(rec["sums_chain"]):
        res["problems"].append("sums chain")

    # every stored chunk: stored-bytes CRC, and decoded CRC of the HDF5-decoded rows
    n_checked = 0
    for i, name in enumerate(names):
        d = sg[name]
        for c in range(chunks):
            _, raw = d.id.read_direct_chunk((c * F,) + (0,) * (d.ndim - 1))
            if len(raw) != int(sums[c]["stored_len"][i]) or crc(raw) != int(sums[c]["stored_crc"][i]):
                res["problems"].append(f"{name} chunk {c} stored CRC")
            rows = np.ascontiguousarray(d[c * F:(c + 1) * F])
            if crc(rows.tobytes()) != int(sums[c]["decoded_crc"][i]):
                res["problems"].append(f"{name} chunk {c} decoded CRC")
            n_checked += 1
    res["chunks_checked"] = n_checked

    # values against the export (single PA group as imported)
    g = definition["groups"][0]
    samples, valid_ds, records = sg[f"g/{g['name']}/samples"], sg[f"g/{g['name']}/valid"], sg["frames/records"]
    tails = {}
    if not complete:
        for i, name in enumerate(names):
            t = sg["journal/" + name.replace("/", "_")][slot, :N - chunks * F]
            if crc(np.ascontiguousarray(t).tobytes()) != int(rec["tail_crc"][i]):
                res["problems"].append(f"{name} journal tail CRC")
            tails[name] = t
    n_cmp = min(N, limit) if limit else N
    stats = {"frames": 0, "values": 0, "valid_slots": 0, "invalid_slots": 0, "sample_mismatch_frames": 0,
             "valid_mismatch_frames": 0, "record_mismatch_frames": 0, "nonzero_invalid_slots": 0}
    main_n = chunks * F if not complete else N
    for a in range(0, n_cmp, 128):
        b = min(a + 128, n_cmp)

        def take(name, ds):
            if b <= main_n:
                return ds[a:b]
            head = ds[a:main_n] if a < main_n else ds[0:0]
            return np.concatenate([head, tails[name][max(a, main_n) - main_n:b - main_n]])

        x = take(f"g/{g['name']}/samples", samples)
        v = np.unpackbits(take(f"g/{g['name']}/valid", valid_ds), axis=1, bitorder="little", count=g["K"]).astype(bool)
        r = take("frames/records", records)
        es, ev, er = src.frames(a, b)
        stats["sample_mismatch_frames"] += int((x != es).any(axis=(1, 2)).sum())
        stats["valid_mismatch_frames"] += int((v != ev).any(axis=1).sum())
        stats["record_mismatch_frames"] += int(sum(r[k].tolist() != er[k].tolist() for k in er.dtype.names))
        stats["nonzero_invalid_slots"] += int(x[~v].any(axis=-1).sum())
        stats["frames"] += b - a
        stats["values"] += x.size
        stats["valid_slots"] += int(v.sum())
        stats["invalid_slots"] += int((~v).sum())
    res["compare"] = stats
    out.append(res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("src")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    src = TestdataSource(a.src)
    report = {"hdf5": h5py.version.hdf5_version, "h5py": h5py.version.version, "file": a.file, "scans": []}
    with h5py.File(a.file, "r") as f:
        report["format"] = {k: (v.decode() if isinstance(v, bytes) else str(v)) for k, v in f.attrs.items()}
        life = f["lifecycle"][0]
        report["lifecycle"] = {"state": int(life["state"]), "crc_ok": rec_ok(life),
                               "failure_message": bytes(life["failure_message"]).decode()}
        n = 0
        while f"scans/s{n:04d}" in f:
            check_scan(f[f"scans/s{n:04d}"], src, a.limit, report["scans"])
            n += 1
    s = report["scans"]
    report["pass"] = bool(s) and all(not x["problems"] and x["compare"]["sample_mismatch_frames"] == 0
                                     and x["compare"]["valid_mismatch_frames"] == 0
                                     and x["compare"]["record_mismatch_frames"] == 0
                                     and x["compare"]["nonzero_invalid_slots"] == 0 for x in s)
    print(json.dumps(report, indent=1))
    sys.exit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
