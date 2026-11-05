"""Graceful-restart stale paths, read the same way on every driver whose output marks them.

While a peer restarts gracefully the router keeps the peer's paths, marked stale, until the peer re-sends them or the stale
timer ends. Such a path is neither present nor gone yet, so no check can pass or fail on it: the read is refused (a
`DriverError`, "not settled"), and the check samples again until the mark clears. A stale field of an unexpected type is
an error too, never "not stale".
"""
from __future__ import annotations

from .base import DriverError, unexpected


def strict_bool(command: str, value: object) -> bool:
    """A stale mark that is a real boolean; anything else (a string, a number, null) is unexpected output."""
    if value is True or value is False:
        return value
    raise unexpected(command, f"stale mark is not a boolean: {str(value)[:60]!r}")


def refuse_if_stale(prefix: str, peer: object, stale: bool) -> None:
    if stale:
        raise DriverError(f"{prefix}: BGP path from {peer or '?'} is stale (graceful restart in progress): not settled")


# RFC 9494: a path a long-lived graceful restart keeps past the restart time carries LLGR_STALE. Read from the
# communities of every driver that reads them (stated as untested live: the night labs' LLGR phase saw the stale marks,
# not the community, on the NOSes that print one)
LLGR_STALE = "65535:6"


def refuse_llgr_stale(prefix: str, paths) -> None:
    for p in paths or []:
        if LLGR_STALE in p.communities:
            raise DriverError(f"{prefix}: BGP path from {getattr(p, 'neighbor', None) or '?'} carries LLGR_STALE "
                              "(65535:6): long-lived graceful restart in progress, not settled")
