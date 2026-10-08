"""Input classification: decide what kind of public identifier the user typed."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.core.enums import SeedType
from app.core.normalize import normalize_domain, normalize_url, public_suffix_known

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,253}\.[A-Za-z]{2,63}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._\-]{0,48}[A-Za-z0-9_])?$")
HOST_RE = re.compile(r"^(?=.{4,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-.][^\W\d_]+\.?)+$", re.UNICODE)

MAX_SEED_LENGTH = 256


class ClassificationError(ValueError):
    pass


@dataclass(frozen=True)
class Classification:
    type: SeedType
    normalized: str
    # Other plausible readings, e.g. "john.dev" is a domain but also a valid username.
    alternatives: list[SeedType] = field(default_factory=list)


def classify(raw: str) -> Classification:
    value = (raw or "").strip()
    if not value:
        raise ClassificationError("Enter a username, email, name, domain or URL.")
    if len(value) > MAX_SEED_LENGTH:
        raise ClassificationError(f"Input is longer than {MAX_SEED_LENGTH} characters.")
    if any(ord(c) < 32 for c in value):
        raise ClassificationError("Input contains control characters.")

    lowered = value.lower()
    if lowered.startswith(("http://", "https://")):
        parts = urlsplit(value)
        if not parts.hostname or not HOST_RE.match(parts.hostname):
            raise ClassificationError("URL must have a public hostname.")
        return Classification(SeedType.URL, normalize_url(value, keep_scheme=True))
    if "://" in value:
        raise ClassificationError("Only http and https URLs are supported.")

    if EMAIL_RE.match(value):
        return Classification(SeedType.EMAIL, lowered)

    if value.startswith("@") and USERNAME_RE.match(value[1:]):
        return Classification(SeedType.USERNAME, value[1:])

    if " " not in value and "/" in value:
        host = value.split("/", 1)[0]
        if HOST_RE.match(host) and public_suffix_known(host):
            return Classification(SeedType.URL, normalize_url("https://" + value, keep_scheme=True))

    if HOST_RE.match(value) and public_suffix_known(value):
        alternatives = [SeedType.USERNAME] if USERNAME_RE.match(value) else []
        return Classification(SeedType.DOMAIN, normalize_domain(value), alternatives)

    if " " in value:
        collapsed = " ".join(value.split())
        if NAME_RE.match(collapsed) and 2 <= len(collapsed.split()) <= 5:
            return Classification(SeedType.PERSON, collapsed)
        raise ClassificationError("Names may only contain letters, spaces, hyphens and apostrophes.")

    if USERNAME_RE.match(value):
        alternatives = [SeedType.PERSON] if value.isalpha() else []
        # Case is preserved: some platforms (e.g. Hacker News) have case-sensitive handles.
        return Classification(SeedType.USERNAME, value, alternatives)

    raise ClassificationError("Could not recognise this as a username, email, name, domain or URL.")


def classify_as(raw: str, forced: SeedType) -> Classification:
    """Honour an explicit user override, but only if the value is valid for that type."""
    detected = classify(raw)
    if forced == detected.type:
        return detected
    if forced not in detected.alternatives:
        raise ClassificationError(f"'{raw.strip()}' is not a valid {forced.value}.")
    value = raw.strip()
    if forced == SeedType.USERNAME:
        return Classification(SeedType.USERNAME, value.lstrip("@"))
    if forced == SeedType.PERSON:
        return Classification(SeedType.PERSON, " ".join(value.split()))
    raise ClassificationError(f"Cannot reinterpret input as {forced.value}.")
