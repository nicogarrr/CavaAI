import logging

from app.services.connectors.ibkr import _FlexTokenRedactor


def _record(message: str, args: tuple = ()) -> logging.LogRecord:
    return logging.LogRecord("httpx", logging.INFO, __file__, 1, message, args, None)


def test_redacts_flex_token_in_httpx_request_log() -> None:
    rec = _record(
        "HTTP Request: GET "
        "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
        "?v=3&t=TOPSECRET123&q=1614243 \"HTTP/1.1\" 200 OK"
    )
    assert _FlexTokenRedactor().filter(rec) is True
    out = rec.getMessage()
    assert "TOPSECRET123" not in out
    assert "t=***" in out
    assert "q=1614243" in out


def test_redacts_when_url_arrives_via_log_args() -> None:
    rec = _record("GET %s", ("https://ndcdyn.interactivebrokers.com/x?t=LEAKME&v=3",))
    _FlexTokenRedactor().filter(rec)
    out = rec.getMessage()
    assert "LEAKME" not in out
    assert "t=***" in out


def test_leaves_unrelated_urls_untouched() -> None:
    msg = "HTTP Request: GET https://example.com/api?t=public&x=1 \"HTTP/1.1\" 200 OK"
    rec = _record(msg)
    _FlexTokenRedactor().filter(rec)
    assert rec.getMessage() == msg


def test_filter_installed_on_httpx_logger() -> None:
    assert any(isinstance(f, _FlexTokenRedactor) for f in logging.getLogger("httpx").filters)
