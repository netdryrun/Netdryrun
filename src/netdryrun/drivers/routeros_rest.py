"""RouterOS 7 REST answers: what each one means before any parser looks inside. No I/O.

REST returns a real HTTP status, so an error is never a quiet empty answer. Rules:
- a non-2xx answer is a failed collection (RouterOS error bodies have `error`, `message`, `detail`);
- a 2xx with an empty list is an observed empty answer for that exact query only; the caller decides what it means
  (and for a VRF/table query must confirm the table exists first);
- a body that is not JSON, empty on a 2xx, or of an unexpected top-level shape is an error;
- RouterOS returns every value as a string: `as_int` and `as_bool` convert explicitly and raise on anything else.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from .base import DriverError, unexpected


@dataclass(frozen=True)
class Reply:
    kind: str                      # rows | empty_list | object | http_error | not_json | no_body | no_answer | unexpected_shape
    status: int = 0
    detail: str = ""
    rows: tuple = ()
    obj: dict | None = None
    request: str = ""

    @property
    def ok(self) -> bool:
        return self.kind in ("rows", "empty_list", "object")

    def require_ok(self) -> Reply:
        """The reply itself if it is a readable answer; DriverError for every failure kind."""
        if not self.ok:
            raise unexpected(self.request, f"{self.kind} (HTTP {self.status}): {self.detail}" if self.detail else self.kind)
        return self


def classify_reply(request: str, status: int, body: str) -> Reply:
    """Classify one REST answer. `request` is e.g. "GET /ip/route" (kept for messages), `status` 0 when curl got no
    HTTP answer at all."""
    if not status:
        return Reply("no_answer", 0, "no HTTP answer", request=request)
    text = body if isinstance(body, str) else ""
    if not 200 <= status < 300:
        detail = ""
        try:
            d = json.loads(text)
            if isinstance(d, dict):
                detail = " ".join(str(d.get(k)) for k in ("message", "detail") if d.get(k))
        except ValueError:
            detail = " ".join(text.split())[:120]
        return Reply("http_error", status, detail or f"HTTP {status}", request=request)
    if not text.strip():
        return Reply("no_body", status, "2xx with an empty body", request=request)
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return Reply("not_json", status, " ".join(text.split())[:120], request=request)
    if isinstance(data, list):
        if not data:
            return Reply("empty_list", status, request=request)
        if all(isinstance(r, dict) for r in data):
            return Reply("rows", status, rows=tuple(data), request=request)
        return Reply("unexpected_shape", status, "list with non-object rows", request=request)
    if isinstance(data, dict):
        return Reply("object", status, obj=data, request=request)
    return Reply("unexpected_shape", status, f"top-level {type(data).__name__}", request=request)


def as_int(request: str, value: object) -> int:
    """An integer from a RouterOS string value (digits only)."""
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    raise unexpected(request, f"not a number: {str(value)[:60]!r}")


def as_bool(request: str, value: object) -> bool:
    """A boolean from RouterOS's `"true"`/`"false"` strings (anything else raises)."""
    if value == "true":
        return True
    if value == "false":
        return False
    raise unexpected(request, f"not a boolean: {str(value)[:60]!r}")


# The request, run inside the router's container (the host cannot reach the router's management address: live capture,
# 2026-10-30). Prints the HTTP status (000 when there was no HTTP answer), then the body. Python 3 standard library only.
HELPER = r"""import base64
import os
import sys
import urllib.error
import urllib.request

method, path, cred = sys.argv[1], sys.argv[2], sys.argv[3]
body = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None
target = os.environ.get("MT_TARGET", "http://172.31.255.30")
headers = {"Accept": "application/json", "Authorization": "Basic " + base64.b64encode(cred.encode()).decode()}
data = None
if body is not None:
    data = body.encode()
    headers["Content-Type"] = "application/json"
req = urllib.request.Request(target + "/rest" + path, data=data, method=method, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=45) as r:
        status, payload = r.status, r.read()
except urllib.error.HTTPError as e:
    status, payload = e.code, e.read()
except Exception as exc:
    sys.stderr.write("rest_helper: %r" % (exc,) + chr(10))
    status, payload = 0, b""
sys.stdout.write("%03d\n" % status)
sys.stdout.flush()
sys.stdout.buffer.write(payload)
sys.stdout.buffer.flush()
"""


__all__ = ["DriverError", "HELPER", "Reply", "as_bool", "as_int", "classify_reply"]
