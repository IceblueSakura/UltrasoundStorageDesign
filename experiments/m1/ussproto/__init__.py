"""Test-only prototype for the M1 experiments of Spec 0.3-draft (not the SDK)."""

import threading

# ADR-0004: every HDF5 call in the process is serialised through one lock;
# codec work runs outside it.
HDF5_LOCK = threading.RLock()


class UssError(Exception):
    """Base class of prototype errors."""


class ValidationError(UssError):
    """A call was rejected before touching the file (WRT-01, READ-02)."""


class StateError(UssError):
    """The object's lifecycle state does not allow the call (LIF-01, failure state)."""


class WriteIOError(UssError):
    """An I/O error during a write/Flush/finish/seal; the Writer is now failed (WRT-01)."""


class ReadIOError(UssError):
    """An I/O or integrity error during a data read; nothing was delivered (IO-01)."""


class InternalDecodeError(ReadIOError):
    """Stored bytes verified but decoding disagreed with the decoded checksum (MAP-02 item 5)."""


class BorrowExpired(UssError):
    """A poll view was used after its borrow ended (BUF-01)."""
