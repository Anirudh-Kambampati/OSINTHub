"""Confidence vocabulary shared by the resolver, aggregations and API."""

from collections.abc import Iterable

LEVELS: list[tuple[float, str]] = [(0.85, "very_high"), (0.60, "high"), (0.30, "medium"), (0.0, "low")]

# Minimum match score for a profile to contribute to the subject's identity.
IDENTITY_THRESHOLD = 0.30
# Hard ceiling: an inference is never presented as certainty.
MAX_INFERRED = 0.97


def level(score: float) -> str:
    for threshold, name in LEVELS:
        if score >= threshold:
            return name
    return "low"


def noisy_or(values: Iterable[float]) -> float:
    """Combine independent pieces of evidence: P(at least one is right) = 1 - Π(1 - p_i)."""
    remaining = 1.0
    for v in values:
        remaining *= 1.0 - max(0.0, min(1.0, v))
    return 1.0 - remaining


def match_label(score: float, conflicting: bool) -> str:
    if conflicting and score < 0.60:
        return "Conflicting evidence"
    if score >= 0.85:
        return "High-confidence match"
    if score >= 0.60:
        return "Likely same entity"
    if score >= 0.30:
        return "Possible match"
    return "Unverified"
