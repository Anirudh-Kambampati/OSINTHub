"""Different sources, different formats -> the same canonical observations."""

from app.connectors.base import Findings, Pivot
from app.connectors.devto import DevToConnector
from app.connectors.github import GitHubConnector
from app.connectors.keybase import KeybaseConnector
from app.connectors.social import parse_social_url
from app.connectors.web import WebsiteConnector
from app.core.enums import EntityKind, RunStatus, SeedType
from app.core.normalize import normalize_value

GITHUB_RAW = {
    "mode": "username",
    "search_url": None,
    "users": [{
        "user": {
            "login": "Anirudh123", "html_url": "https://github.com/Anirudh123", "name": "Anirudh  Kumar",
            "company": "@ExampleCorp", "blog": "https://www.Anirudh.dev/", "location": "Bengaluru",
            "email": "Anirudh@Example.com", "bio": "Builder", "twitter_username": "anirudh_k",
            "avatar_url": "https://avatars.githubusercontent.com/u/1", "created_at": "2015-03-01T10:00:00Z",
            "updated_at": "2026-09-28T10:00:00Z", "public_repos": 3, "followers": 10, "following": 2,
        },
        "repos": [{"name": "tool", "full_name": "Anirudh123/tool", "fork": False, "html_url": "https://github.com/Anirudh123/tool",
                   "created_at": "2020-07-22T00:00:00Z", "language": "Python", "stargazers_count": 4, "description": "<b>A</b> tool"}],
    }],
}

DEVTO_RAW = {
    "user": {
        "username": "anirudh123", "name": "Anirudh Kumar", "summary": "Builder", "twitter_username": "anirudh_k",
        "github_username": "Anirudh123", "website_url": "anirudh.dev", "location": "Bengaluru",
        "joined_at": "Mar 4, 2019", "profile_image": "https://res.cloudinary.com/x.png",
    },
    "articles": [],
    "articles_url": "https://dev.to/api/articles?username=anirudh123",
}


def _obs(findings: Findings, attribute: str) -> set[str]:
    return {o.normalized_value for o in findings.observations if o.attribute == attribute}


def test_same_facts_from_different_formats_normalize_identically():
    gh = GitHubConnector().normalize(GITHUB_RAW, "Anirudh123", SeedType.USERNAME).findings
    dev = DevToConnector().normalize(DEVTO_RAW, "anirudh123", SeedType.USERNAME).findings
    assert _obs(gh, "website") == _obs(dev, "website") == {"anirudh.dev"}
    assert _obs(gh, "name") == _obs(dev, "name") == {"anirudh kumar"}
    assert _obs(gh, "location") == _obs(dev, "location") == {"bengaluru"}
    assert "x:anirudh_k" in _obs(gh, "linked_account") & _obs(dev, "linked_account")
    assert "github:anirudh123" in _obs(dev, "linked_account")


def test_github_normalization_creates_provenance_and_graph():
    result = GitHubConnector().normalize(GITHUB_RAW, "Anirudh123", SeedType.USERNAME)
    f = result.findings
    assert result.status == RunStatus.FOUND
    assert len(f.sources) == 1 and f.sources[0].url.startswith("https://api.github.com/users/")
    assert all(o.source == 0 for o in f.observations)
    kinds = {ref.kind for ref in f.entities}
    assert {EntityKind.PROFILE, EntityKind.EMAIL, EntityKind.WEBSITE, EntityKind.ORGANIZATION,
            EntityKind.REPOSITORY, EntityKind.USERNAME} <= kinds
    assert _obs(f, "email") == {"anirudh@example.com"}
    assert _obs(f, "organization") == {"examplecorp"}
    assert Pivot("website", "https://www.Anirudh.dev/") in result.pivots
    # External markup is stripped from stored text
    assert all("<" not in (e.detail or "") for e in f.events)
    assert {e.title for e in f.events} >= {"GitHub account created", "Repository tool created"}


def test_github_not_found():
    result = GitHubConnector().normalize({"users": []}, "nobody", SeedType.USERNAME)
    assert result.status == RunStatus.NOT_FOUND
    assert result.findings.is_empty


def test_keybase_proofs_are_high_confidence_links():
    raw = {
        "basics": {"username": "anirudh", "ctime": 1500000000},
        "profile": {"full_name": "Anirudh Kumar"},
        "proofs_summary": {"all": [
            {"proof_type": "github", "nametag": "Anirudh123"},
            {"proof_type": "twitter", "nametag": "anirudh_k"},
            {"proof_type": "generic_web_site", "nametag": "anirudh.dev"},
        ]},
    }
    f = KeybaseConnector().normalize(raw, "anirudh", SeedType.USERNAME).findings
    links = {o.normalized_value: o.confidence for o in f.observations if o.attribute == "linked_account"}
    assert links == {"github:anirudh123": 0.97, "x:anirudh_k": 0.97}


def test_website_extracts_rel_me_mailto_and_documents_only():
    html = """
    <html><head><title>Anirudh</title><meta name="description" content="Personal site">
    <link rel="me" href="https://github.com/Anirudh123"></head>
    <body><script>alert('x')</script>
      <a href="https://x.com/anirudh_k">X</a>
      <a href="mailto:hello@anirudh.dev?subject=hi">Email</a>
      <a href="/talks/slides.pdf">Slides</a>
      <a href="https://other.org/paper.pdf">Third-party paper</a>
      <a href="tel:+15555555555">call</a>
    </body></html>
    """
    result = WebsiteConnector().normalize({"url": "https://anirudh.dev/", "html": html}, "https://anirudh.dev/", SeedType.URL)
    f = result.findings
    links = {o.normalized_value: o.confidence for o in f.observations if o.attribute == "linked_account"}
    assert links["github:anirudh123"] == 0.9  # rel=me
    assert links["x:anirudh_k"] == 0.7
    assert _obs(f, "email") == {"hello@anirudh.dev"}
    assert "phone" not in {o.attribute for o in f.observations}
    assert result.pivots == [Pivot("document", "https://anirudh.dev/talks/slides.pdf")]


def test_parse_social_url():
    assert parse_social_url("https://twitter.com/Jack") == "x:jack"
    assert parse_social_url("https://www.linkedin.com/in/jane-doe/") == "linkedin:jane-doe"
    assert parse_social_url("https://news.ycombinator.com/user?id=pg") == "hackernews:pg"
    assert parse_social_url("https://bsky.app/profile/alice.bsky.social") == "bluesky:alice"
    assert parse_social_url("https://github.com/login") is None
    assert parse_social_url("https://example.com/github.com/x") is None


def test_value_normalization():
    assert normalize_value("email", "mailto:John@Example.COM") == "john@example.com"
    assert normalize_value("website", "HTTPS://www.Example.com/about/") == "example.com/about"
    assert normalize_value("organization", "@Acme, Inc.") == "acme"
    assert normalize_value("name", "José  Álvarez") == "jose alvarez"
