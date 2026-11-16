"""Import the whole export, seal, reopen and check it independently.

Covers: write -> seal -> reopen -> independent check (T-02, T-22 partial),
Reader values equal to the export, deep verification, HDF5 1.14 readability
(ADR-0005) and the SWMR variant of the writer.
"""

import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import M1, PY, SRC, Results, TestdataSource, run_dir  # noqa: E402

from ussproto.reader import Reader  # noqa: E402
from ussproto.verify import verify_scan  # noqa: E402


def import_file(dst, *extra):
    p = subprocess.run([PY, "-I", str(M1 / "tools" / "import_testdata.py"), str(SRC), str(dst), *extra],
                       capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])
    return json.loads(p.stdout)


def independent(py, path):
    p = subprocess.run([py, "-I", str(M1 / "tools" / "check_independent.py"), str(path), str(SRC)],
                       capture_output=True, text=True)
    try:
        rep = json.loads(p.stdout)
    except ValueError:
        rep = {"pass": False, "stderr": p.stderr[-2000:]}
    return rep


def main():
    out = run_dir()
    R = Results("roundtrip")
    py114 = os.environ.get("USS_PY_HDF5_114")
    src = TestdataSource(SRC)
    files = {}
    for codec, swmr in (("shuffle-deflate1", False), ("shuffle-deflate1", True), ("deflate1", False), ("none", False)):
        name = f"full-{codec}{'-swmr' if swmr else ''}.h5"
        dst = out / name
        if dst.exists():
            dst.unlink()
        info = import_file(dst, "--codec", codec, *(["--swmr"] if swmr else []))
        files[name] = info
        rep = independent(PY, dst)
        R.check(f"{name}: independent check (HDF5 {rep.get('hdf5')})", rep.get("pass", False),
                compare=[s.get("compare") for s in rep.get("scans", [])],
                problems=[s.get("problems") for s in rep.get("scans", [])])
        if py114:
            rep = independent(py114, dst)
            R.check(f"{name}: independent check (HDF5 {rep.get('hdf5')})", rep.get("pass", False),
                    problems=[s.get("problems") for s in rep.get("scans", [])], stderr=rep.get("stderr"))
    R.note("imports", files)

    main_file = out / "full-shuffle-deflate1.h5"
    r = Reader.open(main_file)
    sc = r.scans()[0]
    R.check("one complete Scan with all Frames", sc["state"] == "complete" and sc["n_frames"] == src.n,
            n_frames=sc["n_frames"], expected=src.n)
    mism = 0
    for a in range(0, src.n, 100):
        b = min(a + 100, src.n)
        v = r.read(0, a, b - a)
        es, ev, er = src.frames(a, b)
        mism += int(not (np.array_equal(v.samples("pa0"), es) and np.array_equal(v.valid("pa0"), ev)
                         and np.array_equal(v.records(), er)))
    R.check("Reader (poll, B=100) equals the export for every Frame", mism == 0, mismatching_batches=mism)
    ctype, cver, content = r.metadata(0, "source-config")
    R.check("metadata content returned byte-exact with type/version", content == src.config_bytes(),
            content_type=ctype, content_version=cver)
    rep, _ = verify_scan(r.f["scans/s0000"])
    R.check("deep verification covers the whole declared prefix", rep["verified_n"] == rep["declared_n"] == src.n
            and not rep["failures"], report=rep)
    invalid = np.argwhere(src.rec_index < 0)
    v = r.read(0, int(invalid[0][0]), 1)
    R.check("missing export slot stored as valid=0 with zero fill",
            not v.valid("pa0")[0, invalid[0][1]] and not v.samples("pa0")[0, invalid[0][1]].any(),
            frame=int(invalid[0][0]), beam=int(invalid[0][1]), invalid_slots_total=len(invalid))
    r.close()
    return R.finish(out)


if __name__ == "__main__":
    sys.exit(main())
