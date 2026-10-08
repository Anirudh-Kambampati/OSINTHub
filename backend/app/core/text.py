"""Sanitization of untrusted external text. Everything leaves here as plain text."""

import html
import re
from datetime import UTC, datetime
from html.parser import HTMLParser

_WS = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag in ("p", "br", "div", "li"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    return _WS.sub(" ", html.unescape("".join(parser.parts))).strip()


def clean_text(value: str | None, max_len: int = 280) -> str | None:
    """Strip markup/control chars and cap length (we keep short snippets, never full content)."""
    if value is None:
        return None
    text = html_to_text(str(value)) if "<" in str(value) else str(value)
    text = "".join(c for c in text if c.isprintable() or c == " ")
    text = _WS.sub(" ", text).strip()
    if not text:
        return None
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def parse_datetime(value) -> datetime | None:
    """Best-effort parse of ISO strings / unix timestamps into aware UTC datetimes."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, int | float):
            return datetime.fromtimestamp(float(value), UTC)
        s = str(value).strip()
        if s.isdigit():
            return datetime.fromtimestamp(int(s), UTC)
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (ValueError, OverflowError, OSError):
        pass
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None
