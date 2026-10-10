# How conclusions are reached

A discussion of what the numbers mean — and what they deliberately do not.

## Observations, not truth

Entities (profile, email, website, domain, repository, IP…) are anchors. Everything *believed*
about them is stored as an observation:

```
Observation(entity, attribute, value, source, confidence, observed_at)
```

Every source is itself a stored retrieval with URL, fetch time and reliability. Re-runs **append**
observations rather than replacing them, so first-seen/last-seen accumulate and a value that
disappears can still be explained. The evidence drawer in the UI is this model surfaced: any
attribute can answer *"why does the system believe this?"* by listing the observations behind it.

This is why the product word is **observation**, not fact: the console records what sources said,
when, and how reliably — never an unattributed claim.

## Entity resolution

`backend/app/services/resolver.py` scores each discovered profile against the seed from
explainable factors:

| Factor | Score |
|---|---|
| Exact username match | +0.35 |
| Seed email listed on the profile | +0.60 |
| Verified link (Keybase proof, Mastodon-verified field, crates.io login) | +0.45 |
| Mutual link (each references the other) | +0.40 |
| Shared email | +0.40 |
| One-way link | +0.25 |
| Shared website | +0.25 |
| Shared name / organization / location | positive, small |
| Different public name on same handle | −0.20 |

Structural rules that keep the score honest:

- **Each factor counts once** — repetition in one profile cannot stack.
- **Corroboration is capped** — many weak signals cannot sum into certainty.
- **Scores never exceed 97%** — absolute certainty is not offered.
- **A profile's own website corroborates it only if the site links back** — claiming a domain is
  free; being claimed *by* it is evidence.

## Identity clusters

Strong pairwise evidence groups profiles into **clusters** so several people using one handle
appear as separate identities instead of one blended profile. A person and a project sharing a
username should not merge — the cluster structure, not a single global score, is what prevents it.

## Analyst decisions override

An analyst can **confirm** or **reject** any profile. The verdict:

1. overrides the numeric score,
2. re-runs resolution with the decision pinned,
3. is written to the audit log.

The score informs the analyst; it never overrules one.

## Attribute confidence

Per-attribute confidence is a **noisy-OR across independent connectors** of:

```
observation confidence × profile match × source reliability
```

capped at 97%. Noisy-OR means two independent corroborating sources lift confidence substantially,
while the same source repeating itself does not. Mention confidence is further scaled by the match
of the profile it belongs to — a pure text match with no identity backing stays low. Weak values
display rounded (`~35%`) as a reminder they are leads, not findings.

## Limits worth internalizing

- Resolution runs on **public signals only** — an unlinked but genuine account will score low until
  corroborating evidence appears (re-runs are cheap; monitoring automates them).
- Confidence is **not** a probability of truth; it is a consistency measure across sources with
  known reliability.
- Sources restricted from legitimate querying (Instagram, LinkedIn) contribute **no** signals at
  all — they are reported, never scraped, so their absence is visible rather than silently missing.
