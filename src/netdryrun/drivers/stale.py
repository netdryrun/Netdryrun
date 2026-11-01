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
