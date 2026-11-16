"""Deep verification of a Scan (VAL-01 depth layer, LIF-02 recovery prefix)."""

from . import layout as L
from .scan import IntegrityError, ScanState, commit_candidates


def verify_scan(sg, deep=True):
    """Return a report with the declared and verified Frame prefix of one Scan.

    The newest commit record whose journal tails and checksum chain verify is
    used; every chunk inside it is then checked (stored and decoded bytes). The
    verified prefix stops at the first failing chunk; nothing is guessed from
    extents (LIF-02).
    """
    rep = {"scan": sg.name, "scan_id": sg.attrs.get("scan_id"), "declared_n": 0, "verified_n": 0,
           "commit_seq": None, "scan_state": None, "failures": [], "unchecked": []}
    state = None
    for rec in commit_candidates(sg):
        try:
            st = ScanState(sg, rec)
            st.tails()
            st.sums()
            state = st
            break
        except (IntegrityError, OSError, ValueError) as exc:
            rep["failures"].append(f"commit seq {int(rec['seq'])} rejected: {exc}")
    if state is None:
        rep["failures"].append("no usable commit record")
        return rep, None
    rep["declared_n"], rep["commit_seq"] = state.n, state.seq
    rep["scan_state"] = "complete" if state.complete else "active"
    if not deep:
        rep["verified_n"] = state.n
        rep["unchecked"].append("chunk contents (deep=False)")
        return rep, state
    good = 0
    for c in range(state.data_chunks):
        try:
            for obj in range(len(state.names)):
                state.decode_chunk(obj, c, state.stored_chunk(obj, c))
        except Exception as exc:  # IntegrityError, zlib.error, h5py errors
            rep["failures"].append(f"chunk {c}: {type(exc).__name__}: {exc}")
            break
        good += 1
    if good == state.data_chunks:
        rep["verified_n"] = state.n
    else:
        rep["verified_n"] = min(state.n, good * state.F)
    return rep, state


def lifecycle(f):
    life = f["lifecycle"][0]
    ok = L.record_crc(life) == int(life["record_crc"])
    return {"state": L.STATE_NAMES.get(int(life["state"]), "unknown") if ok else "corrupt",
            "n_scans": int(life["n_scans"]), "failure_scan": int(life["failure_scan"]),
            "failure_n_frames": int(life["failure_n_frames"]),
            "failure_message": bytes(life["failure_message"]).decode("utf-8", "replace")}
