"""Recognise links to public profiles on known platforms -> "platform:handle"."""

import re
from urllib.parse import parse_qs, urlsplit

PLATFORM_LABELS = {
    "github": "GitHub",
    "gitlab": "GitLab",
    "hackernews": "Hacker News",
    "devto": "DEV",
    "keybase": "Keybase",
    "bluesky": "Bluesky",
    "medium": "Medium",
    "reddit": "Reddit",
    "youtube": "YouTube",
    "x": "X",
    "instagram": "Instagram",
    "linkedin": "LinkedIn",
    "gravatar": "Gravatar",
    "mastodon": "Mastodon",
    "stackoverflow": "Stack Overflow",
}

_HANDLE = r"([A-Za-z0-9_.\-]{1,64})"
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("github", re.compile(rf"^(?:www\.)?github\.com/{_HANDLE}/?$")),
    ("gitlab", re.compile(rf"^(?:www\.)?gitlab\.com/{_HANDLE}/?$")),
    ("x", re.compile(rf"^(?:www\.|mobile\.)?(?:twitter|x)\.com/{_HANDLE}/?$")),
    ("instagram", re.compile(rf"^(?:www\.)?instagram\.com/{_HANDLE}/?$")),
    ("linkedin", re.compile(rf"^(?:[a-z]{{2,3}}\.)?linkedin\.com/in/{_HANDLE}/?$")),
    ("youtube", re.compile(rf"^(?:www\.|m\.)?youtube\.com/@{_HANDLE}/?$")),
    ("reddit", re.compile(rf"^(?:www\.|old\.)?reddit\.com/u(?:ser)?/{_HANDLE}/?$")),
    ("medium", re.compile(rf"^(?:www\.)?medium\.com/@{_HANDLE}/?$")),
    ("devto", re.compile(rf"^(?:www\.)?dev\.to/{_HANDLE}/?$")),
    ("keybase", re.compile(rf"^(?:www\.)?keybase\.io/{_HANDLE}/?$")),
    ("bluesky", re.compile(rf"^bsky\.app/profile/{_HANDLE}/?$")),
    ("gravatar", re.compile(rf"^(?:[a-z]{{2}}\.)?gravatar\.com/{_HANDLE}/?$")),
]
_RESERVED = {"about", "login", "signup", "explore", "settings", "home", "search", "share", "intent", "orgs", "features"}


def parse_social_url(url: str) -> str | None:
    """Return 'platform:handle' (handle lowercased) for a recognised public profile URL."""
    try:
        parts = urlsplit(url if "://" in url else "https://" + url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    path = parts.path.rstrip("/")
    if host == "news.ycombinator.com" and path == "/user":
        handle = parse_qs(parts.query).get("id", [None])[0]
        return f"hackernews:{handle.lower()}" if handle else None
    candidate = f"{host}{path}"
    for platform, pattern in _PATTERNS:
        m = pattern.match(candidate)
        if m and m.group(1).lower() not in _RESERVED:
            handle = m.group(1).lower()
            if platform == "bluesky" and handle.endswith(".bsky.social"):
                handle = handle.removesuffix(".bsky.social")
            return f"{platform}:{handle}"
    return None
