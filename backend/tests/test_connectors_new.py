"""Fixture-based normalization tests for the second wave of connectors (no network)."""

from app.connectors.base import Pivot
from app.connectors.domain import DnsConnector
from app.connectors.infra import EmailIntelConnector, IpIntelConnector, SecurityTxtConnector
from app.connectors.people import OrcidConnector, StackExchangeConnector, WikidataConnector
from app.connectors.platforms import (
    CodebergConnector, CratesIoConnector, LichessConnector, MastodonConnector, NpmConnector,
)
from app.core.enums import RunStatus, SeedType


def obs(result, attribute):
    return {o.normalized_value: o.confidence for o in result.findings.observations if o.attribute == attribute}


def test_mastodon_verified_fields_become_verified_links():
    raw = [("fosstodon.org", {
        "username": "alice", "display_name": "Alice", "note": "<p>Hi</p>", "url": "https://fosstodon.org/@alice",
        "created_at": "2022-01-01T00:00:00Z", "fields": [
            {"name": "GitHub", "value": '<a href="https://github.com/alice">github.com/alice</a>',
             "verified_at": "2022-02-01T00:00:00Z"},
            {"name": "Site", "value": '<a href="https://alice.dev">alice.dev</a>', "verified_at": None},
        ]})]
    result = MastodonConnector().normalize(raw, "alice", SeedType.USERNAME)
    assert result.status == RunStatus.FOUND
    assert obs(result, "linked_account") == {"github:alice": 0.97}
    assert "alice.dev" in obs(result, "website")
    assert {r.key for r in result.findings.entities} >= {"mastodon:alice@fosstodon.org"}
    assert result.pivots == [Pivot("website", "https://alice.dev")]


def test_mastodon_not_found_on_any_instance():
    assert MastodonConnector().normalize([], "nobody", SeedType.USERNAME).status == RunStatus.NOT_FOUND


def test_codeberg_ignores_noreply_email():
    raw = {"login": "bob", "full_name": "Bob", "email": "bob@noreply.codeberg.org", "website": "https://bob.example",
           "created": "2021-01-01T00:00:00Z"}
    result = CodebergConnector().normalize(raw, "bob", SeedType.USERNAME)
    assert obs(result, "email") == {}
    assert "bob.example" in obs(result, "website")


def test_crates_io_login_is_a_verified_github_link():
    raw = {"user": {"login": "dtolnay", "name": "David Tolnay", "url": "https://github.com/dtolnay"}}
    result = CratesIoConnector().normalize(raw, "dtolnay", SeedType.USERNAME)
    assert obs(result, "linked_account") == {"github:dtolnay": 0.97}


def test_lichess_closed_accounts_are_not_found():
    assert LichessConnector().normalize({"username": "x", "disabled": True}, "x", SeedType.USERNAME).status \
        == RunStatus.NOT_FOUND


def test_npm_only_counts_packages_the_user_maintains():
    raw = {"url": "https://registry.npmjs.org/-/v1/search?text=maintainer:carol", "objects": [
        {"package": {"name": "pkg-a", "date": "2024-01-01T00:00:00Z", "maintainers": [
            {"username": "carol", "email": "carol@example.com"}], "links": {"repository": "https://github.com/carol/pkg-a"}}},
        {"package": {"name": "pkg-b", "maintainers": [{"username": "someone-else"}]}},
    ]}
    result = NpmConnector().normalize(raw, "carol", SeedType.USERNAME)
    repos = {r.key for r in result.findings.entities if r.kind == "repository"}
    assert repos == {"npm:pkg-a"}
    assert obs(result, "email") == {"carol@example.com": 0.85}
    assert "github:carol" in obs(result, "linked_account")


def test_stack_overflow_requires_exact_display_name():
    raw = {"items": [{"user_id": 1, "display_name": "Jon Skeet", "link": "https://stackoverflow.com/users/1"},
                     {"user_id": 2, "display_name": "Jon Skeeter", "link": "https://stackoverflow.com/users/2"}]}
    result = StackExchangeConnector().normalize(raw, "jon skeet", SeedType.PERSON)
    assert {r.key for r in result.findings.entities if r.kind == "profile"} == {"stackoverflow:1"}


def test_orcid_candidates_are_separate_profiles():
    raw = {"url": "x", "results": [
        {"orcid-id": "0000-0002-1825-0097", "given-names": "Josiah", "family-names": "Carberry",
         "institution-name": ["Brown University"], "email": []},
        {"orcid-id": "0000-0002-1028-6941", "given-names": "Josiah", "family-names": "Carberry", "email": []},
    ]}
    result = OrcidConnector().normalize(raw, "Josiah Carberry", SeedType.PERSON)
    assert len([r for r in result.findings.entities if r.kind == "profile"]) == 2
    assert "brown university" in obs(result, "organization")


def test_wikidata_keeps_only_humans():
    raw = {"order": ["Q1", "Q2"], "entities": {
        "Q1": {"labels": {"en": {"value": "Ada Lovelace"}}, "descriptions": {"en": {"value": "mathematician"}},
               "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}],
                          "P856": [{"mainsnak": {"datavalue": {"value": "https://ada.example"}}}]}},
        "Q2": {"labels": {"en": {"value": "Ada Lovelace (ship)"}},
               "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11446"}}}}]}},
    }}
    result = WikidataConnector().normalize(raw, "Ada Lovelace", SeedType.PERSON)
    assert {r.key for r in result.findings.entities if r.kind == "profile"} == {"wikidata:q1"}


def test_email_intel_classifies_provider_without_probing_mailbox():
    raw = {"domain": "gmail.com", "MX:gmail.com": {"Answer": [{"type": 15, "data": "5 gmail-smtp-in.l.google.com."}]},
           "TXT:gmail.com": {}, "TXT:_dmarc.gmail.com": {}}
    result = EmailIntelConnector().normalize(raw, "someone@gmail.com", SeedType.EMAIL)
    assert obs(result, "email_provider") == {"free webmail": 0.95}
    assert obs(result, "domain_accepts_mail") == {"yes": 0.95}


def test_dns_emits_ip_pivots():
    a = {"Status": 0, "Answer": [{"type": 1, "data": "93.184.215.14"}]}
    raw = {"A:example.com": a, "AAAA:example.com": {}, "MX:example.com": {}, "NS:example.com": {},
           "TXT:example.com": {}, "TXT:_dmarc.example.com": {}}
    result = DnsConnector().normalize(raw, "example.com", SeedType.DOMAIN)
    assert result.pivots == [Pivot("ip", "93.184.215.14")]


def test_ip_intel_combines_rdap_and_internetdb():
    raw = {"ip": "1.1.1.1", "rdap_url": "https://rdap.org/ip/1.1.1.1",
           "rdap": {"name": "APNIC-LABS", "country": "AU", "startAddress": "1.1.1.0", "endAddress": "1.1.1.255",
                    "entities": [{"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "APNIC"]]]}]},
           "internetdb": {"ports": [53, 443], "hostnames": ["one.one.one.one"], "cpes": [], "tags": [], "vulns": []}}
    result = IpIntelConnector().normalize(raw, "1.1.1.1", SeedType.URL)
    assert set(obs(result, "open_port")) == {"53", "443"}
    assert obs(result, "network_owner") == {"apnic": 0.9}


def test_security_txt_parses_contacts():
    raw = {"url": "https://example.com/.well-known/security.txt",
           "text": "# comment\nContact: mailto:security@example.com\nPolicy: https://example.com/p\nExpires: 2027-01-01"}
    result = SecurityTxtConnector().normalize(raw, "example.com", SeedType.DOMAIN)
    assert "security@example.com" in obs(result, "email")
    assert "https://example.com/p" in obs(result, "security_policy")
