"""Read the temporary PA export in testdata/scan.h5 as complete Frames.

Independent of ussproto, so it can serve both as the import source and as the
expected values of the independent checks. The export is a test payload only;
nothing here is a design reference for the SDK.

Mapping used by the M1 experiments (test-only):
- Scan Frame n  <- absolute frame n+1 of the export (frames 1..2995).
- one PA beam-set stream group, K=125 beams, S=1000 samples, <u2.
- valid[n, b]   <- index/record_index[n+1, b] >= 0 (6 slots are missing).
- frame records: encoder_a/encoder_b (raw frame position, encoder counts) and
  source_frame (the export's absolute frame number, a device-side source ID).
"""

import h5py
import numpy as np

RECORD_DTYPE = np.dtype([("encoder_a", "<i8"), ("encoder_b", "<i8"), ("source_frame", "<i8")])
K, S, DTYPE = 125, 1000, np.dtype("<u2")


class TestdataSource:
    def __init__(self, path):
        self.f = h5py.File(path, "r")
        ri = self.f["index/record_index"][...]
        self.abs_frames = np.nonzero((ri >= 0).any(axis=1))[0]
        self.rec_index = ri[self.abs_frames]
        self.enc_a = self.f["encoder/a_by_frame"][...][self.abs_frames]
        self.enc_b = self.f["encoder/b_by_frame"][...][self.abs_frames]
        self.ascan = self.f["raw/ascan"]
        self.n = len(self.abs_frames)

    def frames(self, n0, n1):
        """Frames [n0, n1): samples [B,K,S] (zero where invalid), valid [B,K], records [B]."""
        idx = self.rec_index[n0:n1]
        valid = idx >= 0
        r = idx[valid]
        samples = np.zeros((n1 - n0, K, S), DTYPE)
        if r.size:
            block = self.ascan[int(r.min()):int(r.max()) + 1]
            samples[valid] = block[r - r.min()]
        rec = np.zeros(n1 - n0, RECORD_DTYPE)
        rec["encoder_a"], rec["encoder_b"] = self.enc_a[n0:n1], self.enc_b[n0:n1]
        rec["source_frame"] = self.abs_frames[n0:n1]
        return samples, valid, rec

    def config_bytes(self):
        return self.f["source/config_json"][...].tobytes()

    def close(self):
        self.f.close()


def scan_definition(codec="shuffle-deflate1"):
    """(groups, frame_record_fields) for ussproto.Writer.begin_scan."""
    groups = [{
        "name": "pa0", "interpretation": "pa_beam_set", "K": K, "S": S, "dtype": "<u2", "codec": codec,
        # The export does not identify events, receive outputs or focal laws.
        "stream_table": [{"q": q, "k": q, "beam_index": q, "event": None, "rx_output": None}
                         for q in range(K)],
    }]
    fields = [
        {"name": "encoder_a", "dtype": "<i8", "unit": "encoder_count", "description": "raw frame position, axis A"},
        {"name": "encoder_b", "dtype": "<i8", "unit": "encoder_count", "description": "raw frame position, axis B"},
        {"name": "source_frame", "dtype": "<i8", "unit": "", "description": "device absolute frame number"},
    ]
    return groups, fields
