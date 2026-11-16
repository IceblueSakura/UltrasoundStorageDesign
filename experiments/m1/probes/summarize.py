import json, sys
r = json.load(open(sys.argv[1]))
print("h5py", r["h5py"], "hdf5", r["hdf5"])
for cfg, run in r["runs"].items():
    print("==", cfg, "writer_rc", run["writer_rc"], (run["writer_stderr"] or "").strip()[-160:])
    print("   fs_strategy", run.get("fs_strategy_in_file"), "pad@", run.get("pad_offset"), "flushed chunk2:", run.get("flushed_chunk2"), "size@flush", run.get("file_size_at_flush"), "size@crash", run.get("file_size_at_crash"))
    print("   post-flush allocations overlapping flushed chunk2:", run.get("post_flush_writes_overlapping_flushed_chunk2"))
    for key in ("read_only_open", "swmr_read_open", "after_h5clear_on_copy"):
        if key in run:
            v = run[key]
            if "open_error" in v:
                print("  ", key, "OPEN_ERROR:", v["open_error"])
            else:
                bad = {k: s for k, s in v["frames"].items() if s != "ok"}
                print("  ", key, "shape", v["shape"], "bad frames:", bad if bad else "none")
    if "h5clear_rc" in run: print("   h5clear rc", run["h5clear_rc"])
