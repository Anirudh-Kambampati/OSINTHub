import pytest

from app.core.classify import ClassificationError, classify, classify_as
from app.core.enums import SeedType


@pytest.mark.parametrize(
    ("raw", "expected", "normalized"),
    [
        ("john@example.com", SeedType.EMAIL, "john@example.com"),
        ("  John.Doe@Example.COM ", SeedType.EMAIL, "john.doe@example.com"),
        ("john_doe", SeedType.USERNAME, "john_doe"),
        ("anirudh123", SeedType.USERNAME, "anirudh123"),
        ("@octocat", SeedType.USERNAME, "octocat"),
        ("John Doe", SeedType.PERSON, "John Doe"),
        ("Jean-Luc   Picard", SeedType.PERSON, "Jean-Luc Picard"),
        ("example.com", SeedType.DOMAIN, "example.com"),
        ("www.Example.co.uk", SeedType.DOMAIN, "example.co.uk"),
        ("https://example.com/about", SeedType.URL, "https://example.com/about"),
        ("example.com/about", SeedType.URL, "https://example.com/about"),
    ],
)
def test_classifies_input_types(raw, expected, normalized):
    c = classify(raw)
    assert c.type == expected
    assert c.normalized == normalized


def test_username_case_is_preserved_for_case_sensitive_platforms():
    assert classify("PG").normalized == "PG"


def test_dotted_username_that_is_not_a_domain():
    assert classify("john.doe").type == SeedType.USERNAME


def test_ambiguous_domain_offers_username_alternative():
    c = classify("john.dev")
    assert c.type == SeedType.DOMAIN
    assert SeedType.USERNAME in c.alternatives
    assert classify_as("john.dev", SeedType.USERNAME).type == SeedType.USERNAME


def test_override_rejects_invalid_reinterpretation():
    with pytest.raises(ClassificationError):
        classify_as("john@example.com", SeedType.DOMAIN)


@pytest.mark.parametrize("raw", ["", "   ", "ftp://example.com", "javascript:alert(1)", "a" * 300, "bad\x00input",
                                 "<script>", "John 123 Doe"])
def test_rejects_invalid_input(raw):
    with pytest.raises(ClassificationError):
        classify(raw)
