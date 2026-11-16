"""Write I/O failure: failure state, sealing with a failure marker, recovery (WRT-01, IO-01, LIF-01/02).

A child writer hits EFBIG through RLIMIT_FSIZE in the middle of a Scan.
transient : the limit is lifted, seal_with_failure() must succeed and a normal
            Reader must see the failure marker and every committed Frame.
persistent: sealing fails; recovery must still return every flushed Frame.
"""

import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import H5CLEAR, M1, PY, SRC, Results, run_dir  # noqa: E402
from test_crash import prepare  # noqa: E402

from ussproto.reader import Reader  # noqa: E402


def frames_equal(rd, idx, n, s, v, r):
    for a in range(0, n, 64):
        b = min(a + 64, n)
        x = rd.read(idx, a, b - a)
        if not (np.array_equal(x.samples("pa0"), np.where(v[a:b, :, None], s[a:b], 0))
                and np.array_equal(x.valid("pa0"), v[a:b]) and np.array_equal(x.records(), r[a:b])):
            return False
    return True


def main():
    out = run_dir()
    R = Results("io_failure")
    src_dir, s, v, r = prepare(out)
    here = os.path.dirname(os.path.abspath(__file__))
    for mode in ("transient", "persistent"):
        h5 = out / f"iofail-{mode}.h5"
        if h5.exists():
            h5.unlink()
        p = subprocess.run([PY, "-I", os.path.join(here, "io_failure_writer.py"), mode, str(h5), str(src_dir)],
                           capture_output=True, text=True)
        try:
            log = json.loads(p.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            R.check(f"{mode}: child ran", False, rc=p.returncode, stderr=p.stderr[-1500:])
            continue
        R.note(f"{mode}: child log", log)
        R.check(f"{mode}: the write call failed with an I/O error", "write_error" in log, error=log.get("write_error"))
        R.check(f"{mode}: Writer is in the failure state", log["writer_state"] == "failed")
        R.check(f"{mode}: write/flush/seal are refused in the failure state",
                all(str(log[k]).startswith("StateError") for k in ("write_after_failure", "flush_after_failure",
                                                                    "seal_after_failure")))
        if mode == "transient":
            ok = log["seal_with_failure"] == "ok"
            R.check("transient: seal_with_failure succeeds after verifying committed data", ok,
                    result=log["seal_with_failure"])
            if not ok:
                continue
            rd = Reader.open(h5)
            life = rd.lifecycle()
            sc = rd.scans()[0]
            R.check("transient: normal Reader sees the failure marker", life["state"] == "sealed_with_failure"
                    and life["failure_n_frames"] == log["committed_n"], lifecycle=life)
            R.check("transient: every committed Frame (incl. unflushed ones) is readable",
                    sc["n_frames"] == log["committed_n"] > log["flushed_n"], n=sc["n_frames"],
                    committed=log["committed_n"], flushed=log["flushed_n"])
            R.check("transient: committed Frames equal the source", frames_equal(rd, 0, sc["n_frames"], s, v, r))
            rd.close()
            chk = subprocess.run([PY, "-I", str(M1 / "tools" / "check_independent.py"), str(h5), str(SRC)],
                                 capture_output=True, text=True)
            rep = json.loads(chk.stdout)
            R.check("transient: independent check passes (journal tail included)", rep["pass"],
                    problems=[x["problems"] for x in rep["scans"]])
        else:
            R.check("persistent: seal_with_failure fails while the disk stays full",
                    log["seal_with_failure"] != "ok", result=log["seal_with_failure"])
            rd = Reader.open_recovery(h5, h5clear=H5CLEAR, workdir=out)
            rep = rd.recovery_reports["scans"][0]
            R.check("persistent: recovery returns at least every flushed Frame",
                    rep["verified_n"] >= log["flushed_n"] and rep["verified_n"] == rep["declared_n"],
                    verified=rep["verified_n"], declared=rep["declared_n"], flushed=log["flushed_n"],
                    committed=log["committed_n"], open_method=rd.recovery_reports["open_method"])
            R.check("persistent: recovered Frames equal the source", frames_equal(rd, 0, rep["verified_n"], s, v, r))
            rd.close()
    return R.finish(out)


if __name__ == "__main__":
    sys.exit(main())
