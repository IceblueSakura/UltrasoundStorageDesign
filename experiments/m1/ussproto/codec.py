"""Chunk codecs for the test-only prototype.

Every codec is a standard HDF5 filter pipeline, so chunks the prototype encodes
itself and writes with H5Dwrite_chunk stay decodable by any HDF5 reader.
"""

import zlib

import numpy as np

# name -> ordered HDF5 filter pipeline applied on write
PIPELINES = {
    "none": (),
    "deflate1": (("deflate", 1),),
    "shuffle-deflate1": (("shuffle",), ("deflate", 1)),
}


def dataset_filter_kwargs(codec):
    """h5py create_dataset() keywords that declare the codec's filter pipeline."""
    kw = {}
    for step in PIPELINES[codec]:
        if step[0] == "shuffle":
            kw["shuffle"] = True
        elif step[0] == "deflate":
            kw["compression"] = "gzip"
            kw["compression_opts"] = step[1]
    return kw


def _shuffle(raw, itemsize):
    if itemsize == 1:
        return raw
    return np.frombuffer(raw, np.uint8).reshape(-1, itemsize).T.tobytes()


def _unshuffle(raw, itemsize):
    if itemsize == 1:
        return raw
    return np.frombuffer(raw, np.uint8).reshape(itemsize, -1).T.tobytes()


def encode(codec, chunk):
    """Encode one whole chunk (a C-contiguous array) into its stored bytes."""
    data = np.ascontiguousarray(chunk).tobytes()
    for step in PIPELINES[codec]:
        if step[0] == "shuffle":
            data = _shuffle(data, chunk.dtype.itemsize)
        elif step[0] == "deflate":
            data = zlib.compress(data, step[1])
    return data


def decode(codec, stored, dtype, shape):
    """Decode stored chunk bytes into a new array of the given dtype/shape."""
    data = stored
    for step in reversed(PIPELINES[codec]):
        if step[0] == "deflate":
            data = zlib.decompress(data)
        elif step[0] == "shuffle":
            data = _unshuffle(data, np.dtype(dtype).itemsize)
    return np.frombuffer(data, dtype=dtype).reshape(shape).copy()


def crc(data):
    return zlib.crc32(data) & 0xFFFFFFFF
