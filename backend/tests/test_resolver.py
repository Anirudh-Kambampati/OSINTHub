from app.core.confidence import level, noisy_or
from app.core.enums import SeedType
from app.services.resolver import Candidate, resolve


def profile(eid, platform, username, **kw) -> Candidate:
    return Candidate(entity_id=eid, identity=f"{platform}:{username.lower()}", label=f"{platform} @{username}",
                     username=username, **kw)


def test_same_username_only_is_a_possible_match_not_a_merge():
    results = resolve([profile("a", "github", "anirudh123"), profile("b", "devto", "anirudh123")],
                      SeedType.USERNAME, "anirudh123")
    for r in results.values():
        assert 0.30 <= r.score < 0.60
        assert r.label == "Possible match"
        assert [f.code for f in r.factors] == ["seed_username_exact"]


def test_same_email_and_username_is_high_confidence():
    a = profile("a", "github", "anirudh123", emails={"a@example.com"})
    b = profile("b", "devto", "anirudh123", emails={"a@example.com"})
    results = resolve([a, b], SeedType.USERNAME, "anirudh123")
    assert results["a"].score >= 0.60
    assert level(results["a"].score) in ("high", "very_high")
    assert "shared_email" in {f.code for f in results["a"].factors}


def test_contradictory_information_reduces_confidence():
    a = profile("a", "github", "anirudh123", names={"anirudh kumar"})
    b = profile("b", "devto", "anirudh123", names={"maria lopez"})
    baseline = resolve([profile("a", "github", "anirudh123"), profile("b", "devto", "anirudh123")],
                       SeedType.USERNAME, "anirudh123")
    results = resolve([a, b], SeedType.USERNAME, "anirudh123")
    assert results["a"].score < baseline["a"].score
    assert results["a"].label == "Conflicting evidence"


def test_mutual_links_and_verified_proofs_are_strong_evidence():
    a = profile("a", "github", "anirudh123", websites={"anirudh.dev"})
    site = Candidate(entity_id="s", identity="site:anirudh.dev", label="anirudh.dev", is_profile=False,
                     linked_accounts={"github:anirudh123": 0.9})
    kb = profile("k", "keybase", "anirudh123", linked_accounts={"github:anirudh123": 0.97})
    results = resolve([a, site, kb], SeedType.USERNAME, "anirudh123")
    assert "s" not in results  # websites corroborate; they are not scored as profiles
    codes = {f.code for f in results["a"].factors}
    assert {"mutual_link", "verified_link"} <= codes
    assert results["a"].score >= 0.85


def test_scores_never_reach_certainty():
    a = profile("a", "github", "x1", emails={"e@x.io"}, names={"n"}, organizations={"o"},
                linked_accounts={"devto:x1": 0.97})
    b = profile("b", "devto", "x1", emails={"e@x.io"}, names={"n"}, organizations={"o"},
                linked_accounts={"github:x1": 0.97})
    assert all(r.score <= 0.97 for r in resolve([a, b], SeedType.USERNAME, "x1").values())


def test_unanchored_candidates_do_not_corroborate():
    a = profile("a", "github", "anirudh123", emails={"a@example.com"})
    stranger = profile("z", "gitlab", "someone_else", emails={"a@example.com"})
    results = resolve([a, stranger], SeedType.USERNAME, "anirudh123")
    assert results["a"].score == 0.35
    assert results["z"].score >= 0.30  # it is corroborated by an anchored profile...
    assert {f.code for f in results["z"].factors} == {"shared_email"}  # ...but only through evidence


def test_email_seed():
    a = profile("a", "gravatar", "anirudh", emails={"a@example.com"})
    assert resolve([a], SeedType.EMAIL, "a@example.com")["a"].score >= 0.60


def test_noisy_or_combines_independent_evidence():
    assert noisy_or([]) == 0
    assert round(noisy_or([0.5, 0.5]), 2) == 0.75
    assert noisy_or([0.9, 0.2]) > 0.9


def test_profile_own_website_is_not_independent_corroboration():
    a = profile("a", "github", "octocat", websites={"blog.example"})
    site_one_way = Candidate(entity_id="s", identity="site:blog.example", label="blog.example", is_profile=False)
    assert resolve([a, site_one_way], SeedType.USERNAME, "octocat")["a"].score == 0.35
    site_links_back = Candidate(entity_id="s", identity="site:blog.example", label="blog.example",
                                is_profile=False, linked_accounts={"github:octocat": 0.9})
    assert "mutual_link" in {f.code for f in resolve([a, site_links_back], SeedType.USERNAME, "octocat")["a"].factors}


def test_website_anchored_by_another_profile_corroborates():
    a = profile("a", "github", "octocat", websites={"blog.example"})
    b = profile("b", "devto", "octocat")
    site = Candidate(entity_id="s", identity="site:blog.example", label="blog.example", is_profile=False,
                     linked_accounts={"devto:octocat": 0.7})
    assert "profile_link" in {f.code for f in resolve([a, b, site], SeedType.USERNAME, "octocat")["b"].factors}
