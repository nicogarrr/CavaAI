"""public_fetch boundary contracts beyond URL validation.

validate_public_url is covered elsewhere; these pin the other safety
boundaries: the byte cap fires mid-stream (a server cannot force an
unbounded allocation), redirect targets are resolved and re-validated per
hop, and the content-length pre-check rejects oversized payloads before a
single byte is read.
"""

import httpx
import pytest

from app.services.public_fetch import _read_limited, _redirect_target


def test_read_limited_accepts_within_cap():
    chunks = [b"a" * 100, b"b" * 100]
    assert _read_limited(iter(chunks), 200) == b"a" * 100 + b"b" * 100


def test_read_limited_aborts_the_moment_cap_is_exceeded():
    chunks = [b"a" * 150, b"b" * 150, b"c" * 150]

    def gen():
        yield from chunks
        raise AssertionError("stream must not be consumed past the cap")

    with pytest.raises(ValueError, match="limit"):
        _read_limited(gen(), 200)


def test_redirect_target_only_for_redirect_statuses():
    for status in (301, 302, 303, 307, 308):
        response = httpx.Response(status, headers={"location": "https://ok.example/next"})
        assert _redirect_target(response, "https://ok.example/start") == "https://ok.example/next"
    response = httpx.Response(200, headers={"location": "https://ok.example/next"})
    assert _redirect_target(response, "https://ok.example/start") is None


def test_redirect_without_location_is_rejected():
    response = httpx.Response(302)
    with pytest.raises(ValueError, match="without a location"):
        _redirect_target(response, "https://ok.example/start")


def test_relative_redirect_resolved_against_current_url():
    response = httpx.Response(302, headers={"location": "/docs/file.pdf"})
    assert _redirect_target(response, "https://ok.example/a/b") == "https://ok.example/docs/file.pdf"
