"""RouterOS 7 REST answers: what each one means before any parser looks inside.

REST gives a real HTTP status, which is stronger evidence than IOS-style text errors. The rules under test:

- A non-2xx answer is a failed collection, never an empty result (RouterOS error bodies carry error, message and
  detail).
- A 2xx whose body is an empty list is an observed empty answer for that exact query; it proves nothing about a
  different table, a different filter or a menu that doesn't exist (the caller decides what an empty list means).
- A body that is not JSON, or JSON of an unexpected top-level shape, is an error.
- Every value RouterOS returns is a string: numbers and booleans are converted explicitly, and anything else raises.
"""
from __future__ import annotations

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.drivers.routeros_rest import Reply, as_bool, as_int, classify_reply


def test_list_body_is_ok_with_rows():
    r = classify_reply("GET /ip/route", 200, '[{".id": "*1", "dst-address": "10.0.0.0/8"}]')
    assert r.kind == "rows" and len(r.rows) == 1 and r.ok


def test_empty_list_is_an_observed_empty_answer_not_an_error():
    r = classify_reply("GET /routing/bgp/session", 200, "[]")
    assert r.kind == "empty_list" and r.rows == () and r.ok


def test_object_body_is_ok():
    r = classify_reply("GET /system/resource", 200, '{"version": "7.23.8 (long-term)"}')
    assert r.kind == "object" and r.obj["version"].startswith("7.23.8")


def test_http_error_is_a_failed_collection_with_the_detail_kept():
    body = '{"error": 400, "message": "Bad Request", "detail": "no such command or directory (bogus)"}'
    r = classify_reply("GET /routing/bogus", 400, body)
    assert r.kind == "http_error" and not r.ok
    assert r.status == 400 and "no such command" in r.detail


@pytest.mark.parametrize("status", [301, 401, 403, 404, 409, 500, 503])
def test_every_non_2xx_is_an_error(status):
    r = classify_reply("GET /x", status, '{"error": %d, "message": "m"}' % status)
    assert r.kind == "http_error" and not r.ok and r.status == status


def test_http_error_with_an_unreadable_body_is_still_an_error():
    r = classify_reply("GET /x", 500, "<html>boom</html>")
    assert r.kind == "http_error" and not r.ok


def test_success_with_a_body_that_is_not_json_is_an_error():
    r = classify_reply("GET /x", 200, "<html>not json</html>")
    assert r.kind == "not_json" and not r.ok


def test_success_with_nothing_is_an_error_not_an_empty_list():
    # a 2xx with an empty body is unusual for a read; it must not be read as "[]"
    r = classify_reply("GET /x", 200, "")
    assert r.kind == "no_body" and not r.ok


def test_no_http_answer_at_all_is_an_error():
    r = classify_reply("GET /x", 0, "")
    assert r.kind == "no_answer" and not r.ok


def test_json_scalar_or_null_body_is_an_error():
    for body in ("null", "42", '"text"', "true"):
        assert classify_reply("GET /x", 200, body).kind == "unexpected_shape"


def test_list_of_non_objects_is_an_error():
    assert classify_reply("GET /x", 200, "[1, 2]").kind == "unexpected_shape"
    assert classify_reply("GET /x", 200, '[{"a": "1"}, "x"]').kind == "unexpected_shape"


def test_reply_is_immutable():
    r = classify_reply("GET /x", 200, "[]")
    with pytest.raises(AttributeError):
        r.kind = "rows"  # type: ignore[misc]


def test_require_ok_raises_for_every_failure_kind():
    for status, body in [(400, "{}"), (200, "x"), (200, ""), (0, ""), (200, "null")]:
        with pytest.raises(DriverError):
            classify_reply("GET /x", status, body).require_ok()


def test_require_ok_returns_the_reply_when_fine():
    r = classify_reply("GET /x", 200, "[]")
    assert r.require_ok() is r


# ---- values are strings ---------------------------------------------------------------------------------------
def test_as_int_accepts_digit_strings_only():
    assert as_int("x", "42") == 42
    for bad in ("", "4x", "1.5", None, 5, True, "1e3", " 7", "-5", "+5", "٣"):
        with pytest.raises(DriverError):
            as_int("x", bad)


def test_as_bool_accepts_only_true_and_false_strings():
    assert as_bool("x", "true") is True
    assert as_bool("x", "false") is False
    for bad in ("yes", "no", "1", "0", "", None, True, False, "True", "FALSE"):
        with pytest.raises(DriverError):
            as_bool("x", bad)


def test_reply_type_exported():
    assert Reply is not None
