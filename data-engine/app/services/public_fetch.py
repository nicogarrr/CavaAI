"""Bounded HTTP fetching for user-supplied public URLs.

This module deliberately does not follow redirects automatically. Every hop is
validated to prevent SSRF through private, loopback, link-local, or metadata
addresses. Responses are streamed with a hard byte limit so a remote server
cannot force an unbounded allocation.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urljoin, urlparse

import httpx

MAX_REDIRECTS = 3
DEFAULT_MAX_BYTES = 15 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0
USER_AGENT = "CavaAI Public Document Fetcher/1.0"


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http(s) URLs can be fetched")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not allowed")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must include a hostname")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("URL contains an invalid port") from exc

    try:
        addresses = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError("URL hostname could not be resolved") from exc
    if not addresses:
        raise ValueError("URL hostname has no usable address")

    for address in {str(item[4][0]) for item in addresses}:
        try:
            parsed_ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError as exc:
            raise ValueError("URL resolved to an invalid address") from exc
        if not parsed_ip.is_global:
            raise ValueError("Private, loopback, link-local, or reserved URLs are not allowed")
    return url


def _read_limited(chunks: Iterable[bytes], max_bytes: int) -> bytes:
    content = bytearray()
    for chunk in chunks:
        content.extend(chunk)
        if len(content) > max_bytes:
            raise ValueError(f"Remote document exceeds {max_bytes // (1024 * 1024)}MB limit")
    return bytes(content)


def _redirect_target(response: httpx.Response, current_url: str) -> str | None:
    if response.status_code not in {301, 302, 303, 307, 308}:
        return None
    location = response.headers.get("location")
    if not location:
        raise ValueError("Remote server returned a redirect without a location")
    return urljoin(current_url, location)


def fetch_public_url(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[bytes, str | None, str]:
    current_url = validate_public_url(url)
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            validate_public_url(current_url)
            with client.stream("GET", current_url) as response:
                target = _redirect_target(response, current_url)
                if target is not None:
                    current_url = target
                    continue
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    raise ValueError(
                        f"Remote document exceeds {max_bytes // (1024 * 1024)}MB limit"
                    )
                content = _read_limited(response.iter_bytes(), max_bytes)
                return content, response.headers.get("content-type"), current_url
    raise ValueError(f"Too many redirects (maximum {MAX_REDIRECTS})")


async def fetch_public_url_async(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[bytes, str | None, str]:
    current_url = validate_public_url(url)
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers=headers,
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            validate_public_url(current_url)
            async with client.stream("GET", current_url) as response:
                target = _redirect_target(response, current_url)
                if target is not None:
                    current_url = target
                    continue
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    raise ValueError(
                        f"Remote document exceeds {max_bytes // (1024 * 1024)}MB limit"
                    )
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise ValueError(
                            f"Remote document exceeds {max_bytes // (1024 * 1024)}MB limit"
                        )
                return bytes(content), response.headers.get("content-type"), current_url
    raise ValueError(f"Too many redirects (maximum {MAX_REDIRECTS})")
