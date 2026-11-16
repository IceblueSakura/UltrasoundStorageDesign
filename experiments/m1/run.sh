#!/usr/bin/env bash
# Run the M1 experiments. Usage: experiments/m1/run.sh [test ...]
# Outputs go to experiments/runs/m1-<timestamp>/ (or $USS_RUN_DIR).
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=${USS_PY:-$(nix build --no-link --print-out-paths '.#python3WithHdf5')/bin/python3}
export USS_H5CLEAR=${USS_H5CLEAR:-$(nix build --no-link --print-out-paths '.#hdf5^bin')/bin/h5clear}
# h5py linked against nixpkgs' default HDF5 1.14, for the readability check (ADR-0005)
export USS_PY_HDF5_114=${USS_PY_HDF5_114:-$(nix build --no-link --print-out-paths --impure --expr \
  'let f = builtins.getFlake "path:'"$PWD"'"; pkgs = import f.inputs.nixpkgs { system = builtins.currentSystem; };
   in pkgs.python313.withPackages (p: [ p.h5py p.numpy ])')/bin/python3}
export USS_RUN_DIR=${USS_RUN_DIR:-$PWD/experiments/runs/m1-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$USS_RUN_DIR"

tests=("$@")
if [ ${#tests[@]} -eq 0 ]; then
  tests=(test_roundtrip test_semantics test_validation test_read_failure test_io_failure
         test_crash test_concurrency bench_push_read bench_flush bench_pool_stream)
fi
status=0
for t in "${tests[@]}"; do
  echo "== $t"
  "$PY" -I "experiments/m1/tests/$t.py" || status=1
done
"$PY" -I experiments/m1/tests/summarize.py "$USS_RUN_DIR" | tee "$USS_RUN_DIR/summary.txt"
exit $status
