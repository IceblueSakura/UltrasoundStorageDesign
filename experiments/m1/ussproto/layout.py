"""Test-only HDF5 encoding "uss-m1-test-only" version 0.

This is NOT the product format. Paths, record layouts and codes exist only so
that the M1 experiments can exercise DATA_SPEC 0.3-draft rules; the formal
encoding is still open (D-07). The layout is documented in ../README.md.
"""

import hashlib
import json
import zlib
from pathlib import Path

import numpy as np

FORMAT = "uss-m1-test-only"
FORMAT_VERSION = 0
LIBVER = ("v110", "v114")  # ADR-0005: files readable by HDF5 1.10-1.14

# lifecycle states (root /lifecycle record)
OPEN, SEALED, SEALED_WITH_FAILURE = 0, 1, 2
STATE_NAMES = {OPEN: "open", SEALED: "sealed", SEALED_WITH_FAILURE: "sealed_with_failure"}

# Scan states (commit record)
SCAN_ACTIVE, SCAN_COMPLETE = 0, 1

LIFECYCLE_DTYPE = np.dtype([
    ("state", "u1"),
    ("n_scans", "<u4"),
    ("failure_scan", "<i4"),
    ("failure_n_frames", "<u8"),
    ("failure_code", "<i4"),
    ("failure_message", "S200"),
    ("record_crc", "<u4"),
])

INTERPRETATIONS = {"channel_group": "single_element", "pa_beam_set": "array_pa", "txrx_matrix": "array_fmc"}


def commit_dtype(n_obj):
    return np.dtype([
        ("seq", "<u8"),
        ("scan_state", "u1"),
        ("n_frames", "<u8"),
        ("data_chunks", "<u8"),
        ("sums_chunks", "<u8"),
        ("sums_chain", "<u4"),
        ("tail_crc", "<u4", (n_obj,)),
        ("sums_tail_crc", "<u4"),
        ("record_crc", "<u4"),
    ])


def sums_dtype(n_obj):
    # one row per data chunk index c: checksums of chunk c of every frame-axis object
    return np.dtype([
        ("stored_len", "<u4", (n_obj,)),
        ("stored_crc", "<u4", (n_obj,)),
        ("decoded_crc", "<u4", (n_obj,)),
    ])


def record_crc(rec):
    """CRC32 over a packed record's bytes, excluding its trailing record_crc field."""
    raw = np.asarray(rec).tobytes()
    return zlib.crc32(raw[:-4]) & 0xFFFFFFFF


def scan_path(index):
    return f"scans/s{index:04d}"


def object_names(definition):
    """Frame-axis objects of a Scan, in the fixed order used by sums/commit records."""
    names = []
    for g in definition["groups"]:
        names += [f"g/{g['name']}/samples", f"g/{g['name']}/valid"]
    names.append("frames/records")
    return names


def record_fields_dtype(definition):
    return np.dtype([(f["name"], f["dtype"]) for f in definition["frame_records"]["fields"]])


def spec_revision(repo_root=None):
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[3]
    spec = root / "docs" / "DATA_SPEC.md"
    digest = hashlib.sha256(spec.read_bytes()).hexdigest() if spec.exists() else "unknown"
    return f"0.3-draft sha256:{digest}"


def dumps(obj):
    return np.frombuffer(json.dumps(obj, sort_keys=True).encode("utf-8"), np.uint8)


def loads(arr):
    return json.loads(np.asarray(arr, np.uint8).tobytes().decode("utf-8"))
