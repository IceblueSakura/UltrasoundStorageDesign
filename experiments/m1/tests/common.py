"""Shared helpers for the M1 experiment scripts."""

import json
import os
import sys
import time
from pathlib import Path

M1 = Path(__file__).resolve().parents[1]
REPO = M1.parents[1]
sys.path.insert(0, str(M1))

from tools.testdata_source import RECORD_DTYPE, TestdataSource, scan_definition  # noqa: E402,F401

PY = sys.executable
SRC = Path(os.environ.get("USS_TESTDATA", REPO / "testdata" / "scan.h5"))
H5CLEAR = os.environ.get("USS_H5CLEAR", "h5clear")


def run_dir():
    """Output directory under experiments/runs/ (ignored by Git)."""
    d = Path(os.environ.get("USS_RUN_DIR") or REPO / "experiments" / "runs" / time.strftime("m1-%Y%m%d-%H%M%S"))
    d.mkdir(parents=True, exist_ok=True)
    return d


class Results:
    """Collects named checks; PASS only for checks that ran and held."""

    def __init__(self, name):
        self.name, self.checks, self.info = name, [], {}

    def check(self, label, ok, **detail):
        self.checks.append({"check": label, "result": "PASS" if ok else "FAIL", "detail": detail})
        return ok

    def note(self, key, value):
        self.info[key] = value

    def finish(self, out_dir):
        failed = [c for c in self.checks if c["result"] != "PASS"]
        doc = {"test": self.name, "passed": len(self.checks) - len(failed), "failed": len(failed),
               "checks": self.checks, "info": self.info}
        (Path(out_dir) / f"{self.name}.json").write_text(json.dumps(doc, indent=1, default=str))
        print(json.dumps({"test": self.name, "passed": doc["passed"], "failed": doc["failed"]}))
        for c in failed:
            print("  FAIL:", json.dumps(c, default=str)[:400])
        return 1 if failed else 0
