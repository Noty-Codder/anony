"""Spotify / Apple Music / Resso / SoundCloud links.

These services cannot be streamed directly, so the link is turned into a
"title - artist" text and the track is then searched on YouTube.
"""

import html
import re

import aiohttp

_PLATFORMS = re.compile(
    r"^https?://(?:[\w-]+\.)*(?:open\.spotify\.com|spotify\.link|music\.apple\.com"
    r"|resso\.(?:app|me|com)|soundcloud\.com|on\.soundcloud\.com|snd\.sc)/",
    re.I,
)
_OG = re.compile(
    r'<meta[^>]+property=["\']og:(title|description)["\'][^>]+content=["\']([^"\']*)["\']',
    re.I,
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36"}


def is_platform(url: str | None) -> bool:
    return bool(url and _PLATFORMS.match(url))


def _clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\s*[|\-–—]\s*(Spotify|Apple Music|Resso|SoundCloud|Listen.*)$", "", text, flags=re.I)
    text = re.sub(r"\b(on|by)\s+(Apple Music|Spotify|SoundCloud)\b", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" -|·")


async def resolve(url: str) -> str | None:
    """Return a YouTube search query for a platform link (or None)."""
    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as s:
            # oEmbed first: clean title, no scraping
            api = None
            if "spotify" in url:
                api = "https://open.spotify.com/oembed?url="
            elif "soundcloud" in url or "snd.sc" in url:
                api = "https://soundcloud.com/oembed?format=json&url="
            if api:
                try:
                    async with s.get(api + url) as r:
                        if r.status == 200:
                            data = await r.json(content_type=None)
                            title = _clean(data.get("title", ""))
                            author = _clean(data.get("author_name", ""))
                            if title:
                                if author and author.lower() not in title.lower():
                                    return f"{title} {author}"
                                return title
                except Exception:
                    pass
            # fallback: Open Graph tags of the page
            async with s.get(url, allow_redirects=True) as r:
                if r.status != 200:
                    return None
                page = await r.text()
        og = {k.lower(): v for k, v in _OG.findall(page)}
        title = _clean(og.get("title", ""))
        desc = og.get("description", "")
        artist = ""
        m = re.search(r"(?:by|·|-)\s*([^·|]+?)(?:\s*[·|]|$)", html.unescape(desc))
        if m and m.group(1).lower() not in title.lower():
            artist = _clean(m.group(1))
        return f"{title} {artist}".strip() or None
    except Exception:
        return None
