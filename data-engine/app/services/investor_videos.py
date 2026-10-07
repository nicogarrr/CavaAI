"""Videos publicos de un canal identificado, nunca cartera ni canal personal inferido."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from threading import Lock

import httpx

_CHANNEL = re.compile(r"UC[A-Za-z0-9_-]{22}\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)\Z")
_VIDEO = re.compile(r"[A-Za-z0-9_-]{11}\Z")
_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"
# Canal de archivo de referencia de channels.ts, no canal personal de Buffett.
# El nombre sale del RSS; no se atribuye su propiedad a CNBC sin prueba.
CHANNELS: dict[str, tuple[str, str]] = {
    "buffett": ("UCyMGOTSE13Uf9Big_Ppj8Wg", "archive"),
}
_CACHE: dict[str, tuple[float, list[dict[str, str]]]] = {}
_LOCK = Lock()
TTL_SECONDS = 3600
MAX_BYTES = 256_000


def parse_feed(content: bytes, channel_id: str, channel_kind: str) -> list[dict[str, str]]:
    if not _CHANNEL.fullmatch(channel_id) or channel_kind not in ("personal_confirmed", "archive"):
        return []
    if len(content) > MAX_BYTES:
        return []
    # Solo UTF-8: ET no recibe bytes que puedan reinterpretarse como UTF-16.
    # Rechaza NUL y una declaracion de encoding distinta, no repara el XML.
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        return []
    encoding = re.search(r"<\?xml\s[^?]*encoding\s*=\s*['\"]([^'\"]+)['\"]", text, re.IGNORECASE)
    if "\x00" in text or (encoding and encoding.group(1).lower() not in ("utf-8", "utf8")):
        return []
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    if root.tag != _ATOM + "feed" or root.findtext(_YT + "channelId") != channel_id:
        return []
    name = (root.findtext(_ATOM + "title") or "").strip()
    if not name:
        return []
    result = []
    seen = set()
    for entry in root.findall(_ATOM + "entry"):
        vid = entry.findtext(_YT + "videoId") or ""
        title = (entry.findtext(_ATOM + "title") or "").strip()
        published = entry.findtext(_ATOM + "published") or ""
        if not _VIDEO.fullmatch(vid) or not title or vid in seen or not _DATE.fullmatch(published):
            continue
        if entry.findtext(_YT + "channelId") != channel_id:
            continue
        try:
            at = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            continue
        if at.tzinfo is None:
            continue
        seen.add(vid)
        result.append({
            "video_id": vid,
            "title": title[:500],
            "published_at": at.isoformat(),
            "channel_name": name[:200],
            "channel_url": f"https://www.youtube.com/channel/{channel_id}",
            "channel_kind": channel_kind,
        })
    return sorted(result, key=lambda row: datetime.fromisoformat(row["published_at"]), reverse=True)[:6]


def investor_videos(slug: str) -> list[dict[str, str]]:
    channel = CHANNELS.get(slug)
    if channel is None:
        return []
    channel_id, kind = channel
    if not _CHANNEL.fullmatch(channel_id):
        return []
    with _LOCK:
        cached = _CACHE.get(slug)
        if cached is not None and time.monotonic() < cached[0]:
            return [dict(row) for row in cached[1]]
        videos: list[dict[str, str]] = []
        try:
            # Destino fijo validado; sin redirects, cookies, auth ni API key.
            with (
                httpx.Client(timeout=5.0, follow_redirects=False) as client,
                client.stream("GET", "https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id}) as response,
            ):
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_BYTES:
                        break
                videos = parse_feed(bytes(content), channel_id, kind)
        except httpx.HTTPError:
            pass
        _CACHE[slug] = (time.monotonic() + TTL_SECONDS, videos)
        return [dict(row) for row in videos]
