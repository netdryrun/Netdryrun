"""Capture kit: record a driver's read-only commands on one containerlab lab node, sanitise the output, and write a
bundle (outputs plus manifest.json) someone can contribute without sharing an image.

  guard.py     the target must be a running containerlab node of the topology given; anything else is refused
  collect.py   the scenario menu, and the capture itself (the driver's own commands, recorded as they run)
  sanitize.py  deterministic, structure-preserving rewrite of addresses, AS numbers, hostnames and secrets
  bundle.py    manifest.json: write, replay through the driver, validate (the contributor CI gate)
"""
from __future__ import annotations

SCHEMA = "netdryrun.capture/v1"


class CaptureError(RuntimeError):
    """A capture or a bundle that can't be made or accepted. Never a partial result read as a good one."""
