"""Print a compact summary of all result files in a run directory."""

import json
import sys
from pathlib import Path


def main():
    d = Path(sys.argv[1])
    total_p = total_f = 0
    for p in sorted(d.glob("*.json")):
        if p.name == "crash-runs.json":
            continue
        doc = json.loads(p.read_text())
        if "checks" not in doc:
            continue
        total_p += doc["passed"]
        total_f += doc["failed"]
        print(f"{doc['test']}: {doc['passed']} passed, {doc['failed']} failed")
        for c in doc["checks"]:
            if c["result"] != "PASS":
                print("   FAIL", c["check"])
    print(f"TOTAL: {total_p} passed, {total_f} failed")


if __name__ == "__main__":
    main()
