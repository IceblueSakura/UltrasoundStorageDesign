"""Selection layer (ADR-0006): pure functions on Core I/O results, no file I/O.

Inputs are the arrays of one stream group: samples [B,K,S] and valid [B,K].
Ordered lists keep their order and repetitions (READ-02); bounds are checked
per stream group and never silently truncated.
"""

import numpy as np

from . import ValidationError


def _check(idx, size, what):
    idx = np.asarray(idx, dtype=np.int64)
    if idx.ndim != 1 or np.any(idx < 0) or np.any(idx >= size):
        raise ValidationError(f"{what} {idx.tolist()} outside [0,{size})")
    return idx


def streams(samples, valid, q_list):
    """Ordered stream/beam list, e.g. [2,0,2] -> [B,len,S] and [B,len]."""
    q = _check(q_list, samples.shape[1], "stream list")
    return samples[:, q], valid[:, q]


def sample_window(samples, lo, hi):
    if not 0 <= lo <= hi <= samples.shape[-1]:
        raise ValidationError(f"sample window [{lo},{hi}) outside [0,{samples.shape[-1]})")
    return samples[..., lo:hi]


def sample_list(samples, s_list):
    s = _check(s_list, samples.shape[-1], "sample list")
    return samples[..., s]


def ascan(samples, valid, b, q):
    """One A-scan (Frame b of the batch, stream q) and its validity bit."""
    _check([b], samples.shape[0], "frame")
    _check([q], samples.shape[1], "stream")
    return samples[b, q], bool(valid[b, q])
