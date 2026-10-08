"""Entity resolution: how likely is each discovered profile to belong to the investigated subject?

The resolver is a pure function over `Candidate`s so it can be tuned and tested in
isolation. A score is built from explicit, explainable factors:

  1. Seed factors    — how the candidate relates to what the user searched for.
  2. Corroboration   — independent agreement with *other* anchored candidates
                       (shared email, cross-links, shared website/name/org...).
  3. Contradictions  — conflicting public information lowers the score.

Each corroboration code counts once (its strongest instance), so ten weak signals
can't masquerade as one strong one. Matching usernames alone never exceed "Possible match".
"""

import re
from dataclasses import dataclass, field

from app.core.confidence import MAX_INFERRED, match_label
from app.core.enums import SeedType
from app.core.normalize import normalize_name, normalize_username, registrable_domain

WEIGHTS: dict[str, float] = {
    # seed factors
    "seed_username_exact": 0.35,
    "seed_username_variant": 0.25,
    "seed_username_similar": 0.12,
    "seed_email": 0.60,
    "seed_email_local_part": 0.12,
    "seed_name_exact": 0.25,
    "seed_name_partial": 0.10,
    "seed_domain": 0.50,
    # corroboration
    "verified_link": 0.45,
    "mutual_link": 0.40,
    "shared_email": 0.40,
    "profile_link": 0.25,
    "shared_website": 0.25,
    "shared_name": 0.10,
    "similar_name": 0.05,
    "shared_organization": 0.10,
    "shared_location": 0.05,
    # contradictions
    "name_conflict": -0.20,
}
MAX_CORROBORATION = 0.60
SELF_SITE_CODES = {"mutual_link", "shared_email"}

_SEP = re.compile(r"[._\-]")


@dataclass
class Candidate:
    """Everything the resolver may know about a profile (or website) from its observations."""

    entity_id: str
    identity: str                # "github:octocat" / "site:example.com"
    label: str
    is_profile: bool = True
    username: str | None = None
    names: set[str] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    websites: set[str] = field(default_factory=set)            # normalized URLs
    linked_accounts: dict[str, float] = field(default_factory=dict)  # "platform:handle" -> confidence
    organizations: set[str] = field(default_factory=set)
    locations: set[str] = field(default_factory=set)

    @property
    def claims(self) -> dict[str, float]:
        out = dict(self.linked_accounts)
        for w in self.websites:
            out.setdefault(f"site:{w}", 0.8)
        return out

    @property
    def domains(self) -> set[str]:
        return {registrable_domain(w.split("/", 1)[0]) for w in self.websites}


@dataclass
class Factor:
    code: str
    label: str
    weight: float
    related_entity_id: str | None = None

    def as_dict(self) -> dict:
        return {"code": self.code, "label": self.label, "weight": round(self.weight, 3),
                "related_entity_id": self.related_entity_id}


@dataclass
class MatchResult:
    score: float
    label: str
    factors: list[Factor]

    @property
    def conflicting(self) -> bool:
        return any(f.weight < 0 for f in self.factors)


def _levenshtein_le1(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 1 or a == b:
        return a == b
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def _name_tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[\s.\-']+", name) if len(t) > 1}


def seed_factors(c: Candidate, seed_type: SeedType, seed: str) -> list[Factor]:
    out: list[Factor] = []
    s = seed.lower()
    if seed_type == SeedType.USERNAME and c.username:
        u = normalize_username(c.username)
        if u == s:
            out.append(Factor("seed_username_exact", f"Exact username match (@{c.username})", WEIGHTS["seed_username_exact"]))
        elif _SEP.sub("", u) == _SEP.sub("", s):
            out.append(Factor("seed_username_variant", f"Username variant (@{c.username})", WEIGHTS["seed_username_variant"]))
        elif len(s) >= 5 and _levenshtein_le1(u, s):
            out.append(Factor("seed_username_similar", f"Similar username (@{c.username})", WEIGHTS["seed_username_similar"]))
    if seed_type == SeedType.EMAIL:
        if s in c.emails:
            out.append(Factor("seed_email", "Profile publicly lists the searched email", WEIGHTS["seed_email"]))
        elif c.username and normalize_username(c.username) == s.split("@", 1)[0]:
            out.append(Factor("seed_email_local_part", "Username equals the email's local part",
                              WEIGHTS["seed_email_local_part"]))
    if seed_type == SeedType.PERSON:
        target = normalize_name(seed)
        if target in c.names:
            out.append(Factor("seed_name_exact", "Public name matches the searched name", WEIGHTS["seed_name_exact"]))
        elif any(_name_tokens(target) <= _name_tokens(n) or _name_tokens(n) <= _name_tokens(target)
                 for n in c.names if _name_tokens(n)):
            out.append(Factor("seed_name_partial", "Public name partially matches", WEIGHTS["seed_name_partial"]))
    if seed_type in (SeedType.DOMAIN, SeedType.URL):
        seed_domain = registrable_domain(s.split("://", 1)[-1].split("/", 1)[0])
        if seed_domain in c.domains:
            out.append(Factor("seed_domain", f"Links to {seed_domain}", WEIGHTS["seed_domain"]))
    return out


def pair_factors(a: Candidate, b: Candidate) -> list[Factor]:
    """Evidence that `a` and `b` belong to the same public entity (from a's perspective)."""
    out: list[Factor] = []
    a_to_b = a.claims.get(b.identity)
    b_to_a = b.claims.get(a.identity)
    if a_to_b and b_to_a:
        out.append(Factor("mutual_link", f"{a.label} and {b.label} link to each other", WEIGHTS["mutual_link"], b.entity_id))
    elif (a_to_b or 0) >= 0.95 or (b_to_a or 0) >= 0.95:
        out.append(Factor("verified_link", f"Verified link between {a.label} and {b.label}", WEIGHTS["verified_link"], b.entity_id))
    elif a_to_b or b_to_a:
        src, dst = (a, b) if a_to_b else (b, a)
        out.append(Factor("profile_link", f"{src.label} links to {dst.label}", WEIGHTS["profile_link"], b.entity_id))

    if shared := a.emails & b.emails:
        out.append(Factor("shared_email", f"Same public email as {b.label} ({sorted(shared)[0]})", WEIGHTS["shared_email"], b.entity_id))
    if a.is_profile and b.is_profile and (shared := a.websites & b.websites):
        out.append(Factor("shared_website", f"Same website as {b.label} ({sorted(shared)[0]})", WEIGHTS["shared_website"], b.entity_id))
    if a.organizations & b.organizations:
        out.append(Factor("shared_organization", f"Same organization as {b.label}", WEIGHTS["shared_organization"], b.entity_id))
    if a.locations & b.locations:
        out.append(Factor("shared_location", f"Same location as {b.label}", WEIGHTS["shared_location"], b.entity_id))

    if a.names and b.names:
        if a.names & b.names:
            out.append(Factor("shared_name", f"Same public name as {b.label}", WEIGHTS["shared_name"], b.entity_id))
        else:
            a_tok = set().union(*(_name_tokens(n) for n in a.names))
            b_tok = set().union(*(_name_tokens(n) for n in b.names))
            if a_tok & b_tok:
                out.append(Factor("similar_name", f"Similar public name to {b.label}", WEIGHTS["similar_name"], b.entity_id))
            elif a_tok and b_tok and not (a_to_b or b_to_a):
                out.append(Factor("name_conflict", f"Different public name from {b.label}", WEIGHTS["name_conflict"], b.entity_id))
    return out


def resolve(candidates: list[Candidate], seed_type: SeedType, seed: str) -> dict[str, MatchResult]:
    """Score every profile candidate. Websites act only as corroborating evidence."""
    seeds = {c.entity_id: seed_factors(c, seed_type, seed) for c in candidates}
    # A candidate is "anchored" if it relates to the seed directly, or (websites) is claimed by an anchored profile.
    anchored = {cid for cid, fs in seeds.items() if fs}
    site_anchors: dict[str, set[str]] = {}
    for c in candidates:
        if c.is_profile:
            continue
        site_anchors[c.entity_id] = {
            o.entity_id for o in candidates if o.is_profile and o.entity_id in anchored and c.identity in o.claims
        }
        if site_anchors[c.entity_id] or seeds[c.entity_id]:
            anchored.add(c.entity_id)

    results: dict[str, MatchResult] = {}
    for c in candidates:
        if not c.is_profile:
            continue
        best: dict[str, Factor] = {}
        penalties: list[Factor] = []
        for other in candidates:
            if other.entity_id == c.entity_id or other.entity_id not in anchored:
                continue
            # A website reached only through c's own link is not independent of c: only a
            # link back to c, or the site separately publishing the same email, corroborates.
            self_anchored = not other.is_profile and not seeds[other.entity_id] \
                and site_anchors[other.entity_id] <= {c.entity_id}
            for factor in pair_factors(c, other):
                if self_anchored and factor.code not in SELF_SITE_CODES:
                    continue
                if factor.weight < 0:
                    penalties.append(factor)
                elif factor.code not in best or factor.weight > best[factor.code].weight:
                    best[factor.code] = factor
        corroboration = sorted(best.values(), key=lambda f: -f.weight)
        corr_total = min(MAX_CORROBORATION, sum(f.weight for f in corroboration))
        penalty = penalties[:1]  # one contradiction is meaningful; repeats of the same name are not new evidence
        base = sum(f.weight for f in seeds[c.entity_id])
        score = max(0.0, min(MAX_INFERRED, base + corr_total + sum(f.weight for f in penalty)))
        factors = [*seeds[c.entity_id], *corroboration, *penalty]
        results[c.entity_id] = MatchResult(round(score, 4), match_label(score, bool(penalty)), factors)
    return results
