"""Exports: full JSON, per-dataset CSV and a self-contained printable HTML report.

Everything exported carries its provenance (source name + URL + collection time).
"""

import csv
import io
from datetime import UTC, datetime
from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.confidence import level
from app.models import ConnectorRun, Entity, Investigation, InvestigationNote, Observation, Relationship, Source
from app.services import views

CSV_DATASETS = ("attributes", "profiles", "mentions", "observations", "timeline", "sources")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value) -> str:
    """Neutralise spreadsheet formula injection from untrusted external text."""
    if value is None:
        return ""
    text = value.isoformat() if isinstance(value, datetime) else str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


async def export_json(s: AsyncSession, inv: Investigation) -> dict:
    profile = await views.build_profile(s, inv)
    detail = await views.investigation_out(s, inv, with_runs=True)
    entities = (await s.scalars(select(Entity).where(Entity.investigation_id == inv.id))).all()
    sources = {x.id: x for x in (await s.scalars(select(Source).where(Source.investigation_id == inv.id))).all()}
    observations = (await s.scalars(select(Observation).where(Observation.investigation_id == inv.id))).all()
    rels = (await s.scalars(select(Relationship).where(Relationship.investigation_id == inv.id))).all()
    notes = (await s.scalars(select(InvestigationNote).where(InvestigationNote.investigation_id == inv.id)
                             .order_by(InvestigationNote.created_at))).all()
    mentions = await views.list_mentions(s, inv.id, None, "newest", 10_000, 0)
    timeline = await views.timeline(s, inv.id, None)
    return {
        "format": "osint-console/v1",
        "exported_at": datetime.now(UTC).isoformat(),
        "investigation": detail.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json"),
        "entities": [
            {"id": e.id, "kind": e.kind, "key": e.key, "label": e.label, "confidence": e.confidence,
             "is_seed": e.is_seed, "data": e.data} for e in entities
        ],
        "observations": [
            {"id": o.id, "entity_id": o.entity_id, "attribute": o.attribute, "value": o.value,
             "normalized_value": o.normalized_value, "confidence": o.confidence,
             "observed_at": o.observed_at.isoformat(), "source_id": o.source_id} for o in observations
        ],
        "relationships": [
            {"id": r.id, "src": r.src_entity_id, "dst": r.dst_entity_id, "type": r.type,
             "confidence": r.confidence, "source_id": r.source_id, "inferred": r.source_id is None, "data": r.data}
            for r in rels
        ],
        "sources": [views.source_out(x).model_dump(mode="json") for x in sources.values()],
        "mentions": [m.model_dump(mode="json") for m in mentions.items],
        "timeline": [t.model_dump(mode="json") for t in timeline],
        "notes": [{"id": n.id, "body": n.body, "author_id": n.author_id, "created_at": n.created_at.isoformat()}
                  for n in notes],
    }


async def export_csv(s: AsyncSession, inv: Investigation, dataset: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    if dataset == "attributes":
        profile = await views.build_profile(s, inv)
        w.writerow(["attribute", "value", "confidence", "level", "independent_sources", "first_observed",
                    "last_observed", "source_urls"])
        for a in profile.attributes:
            w.writerow([_cell(x) for x in (a.attribute, a.value, a.confidence, a.level, a.source_count,
                                          a.first_observed, a.last_observed,
                                          " | ".join(sorted({e.source.url for e in a.evidence})))])
    elif dataset == "profiles":
        profile = await views.build_profile(s, inv)
        w.writerow(["platform", "handle", "url", "match_score", "match_label", "cluster", "analyst_decision",
                    "factors"])
        for p in profile.profiles:
            m = p.match
            w.writerow([_cell(x) for x in (
                p.data.get("platform"), p.label, p.data.get("url"), m.score if m else "", m.label if m else "",
                m.cluster if m else "", m.decision if m else "",
                "; ".join(f"{f.label} ({f.weight:+.2f})" for f in (m.factors if m else [])))])
    elif dataset == "mentions":
        page = await views.list_mentions(s, inv.id, None, "newest", 10_000, 0)
        w.writerow(["published_at", "observed_at", "title", "url", "category", "association", "confidence",
                    "source", "snippet"])
        for m in page.items:
            w.writerow([_cell(x) for x in (m.published_at, m.observed_at, m.title, m.url, m.category,
                                          m.association, m.confidence, m.source.name, m.snippet)])
    elif dataset == "observations":
        rows = (await s.execute(
            select(Observation, Source, Entity).join(Source, Source.id == Observation.source_id)
            .join(Entity, Entity.id == Observation.entity_id).where(Observation.investigation_id == inv.id)
            .order_by(Entity.label, Observation.attribute))).all()
        w.writerow(["entity_kind", "entity", "attribute", "value", "confidence", "observed_at", "source",
                    "source_url", "reliability"])
        for o, src, e in rows:
            w.writerow([_cell(x) for x in (e.kind, e.label, o.attribute, o.value, o.confidence, o.observed_at,
                                          src.name, src.url, src.reliability)])
    elif dataset == "timeline":
        w.writerow(["occurred_at", "kind", "title", "detail", "entity", "source", "source_url"])
        for t in await views.timeline(s, inv.id, None):
            w.writerow([_cell(x) for x in (t.occurred_at, t.kind, t.title, t.detail,
                                          t.entity.label if t.entity else "", t.source.name, t.source.url)])
    elif dataset == "sources":
        runs = (await s.scalars(select(ConnectorRun).where(ConnectorRun.investigation_id == inv.id)
                                .order_by(ConnectorRun.created_at))).all()
        w.writerow(["connector", "target", "phase", "status", "message", "results", "started_at", "finished_at"])
        for r in runs:
            w.writerow([_cell(x) for x in (r.connector, r.target, r.phase, r.status, r.message, r.result_count,
                                          r.started_at, r.finished_at)])
    else:
        raise ValueError(f"Unknown dataset {dataset!r}")
    return buf.getvalue()


def _fmt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "—"


def _link(url: str | None, text: str) -> str:
    """Anchor only for http(s) URLs; anything else is rendered as inert text."""
    if url and url.lower().startswith(("http://", "https://")):
        return f"<a href='{escape(url, quote=True)}' rel='noreferrer'>{escape(text)}</a>"
    return escape(text)


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{round(x * 100)}%"


REPORT_CSS = """
body{font:13px/1.5 -apple-system,Segoe UI,Inter,sans-serif;color:#16181d;max-width:960px;margin:32px auto;padding:0 24px}
h1{font-size:24px;margin:0}h2{font-size:15px;margin:28px 0 8px;border-bottom:1px solid #d9dde3;padding-bottom:4px}
.muted{color:#5f6772}.badge{display:inline-block;border:1px solid #c9ced6;border-radius:4px;padding:0 6px;font-size:11px}
table{width:100%;border-collapse:collapse;margin-top:6px}th,td{text-align:left;padding:5px 6px;border-bottom:1px solid #eceef1;vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#5f6772}td.num{text-align:right;font-variant-numeric:tabular-nums}
.stats{display:flex;flex-wrap:wrap;gap:16px;margin-top:12px}.stats div{border:1px solid #d9dde3;border-radius:6px;padding:6px 12px}
.stats b{display:block;font-size:18px}a{color:#2456c4;overflow-wrap:anywhere}td.src{min-width:180px}.note{white-space:pre-wrap;border-left:3px solid #c9ced6;padding-left:8px;margin:6px 0}
@media print{body{margin:0}a{color:inherit}}
"""


async def export_report_html(s: AsyncSession, inv: Investigation) -> str:
    profile = await views.build_profile(s, inv)
    detail = await views.investigation_out(s, inv, with_runs=True)
    mentions = await views.list_mentions(s, inv.id, None, "confidence", 50, 0)
    timeline = (await views.timeline(s, inv.id, None))[:100]
    notes = (await s.scalars(select(InvestigationNote).where(InvestigationNote.investigation_id == inv.id)
                             .order_by(InvestigationNote.created_at))).all()
    e = escape
    st = detail.stats
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        f"<title>Investigation report — {e(inv.title)}</title><style>{REPORT_CSS}</style></head><body>",
        f"<div class='muted'>OSINT Intelligence Console · investigation report · generated {_fmt(datetime.now(UTC))}</div>",
        f"<h1>{e(profile.subject.label)}</h1>",
        f"<div class='muted'>Seed <b>{e(inv.seed)}</b> ({e(inv.seed_type)}) · status {e(inv.status)} · "
        f"created {_fmt(inv.created_at)} · completed {_fmt(inv.completed_at)}</div>",
        f"<div>Overall confidence: <b>{_pct(profile.confidence)}</b> "
        f"({e(level(profile.confidence).replace('_', ' ')) if profile.confidence is not None else 'unscored'})</div>",
        "<div class='stats'>" + "".join(
            f"<div><b>{v}</b>{k}</div>" for k, v in [
                ("Profiles", st.profiles), ("Matched", st.matched_profiles), ("Mentions", st.mentions),
                ("Sources", st.sources), ("Relationships", st.relationships), ("Domains", st.domains),
                ("Documents", st.documents)]) + "</div>",
        "<h2>Identity attributes</h2><table><tr><th>Attribute</th><th>Value</th><th>Confidence</th>"
        "<th>Sources</th><th>Observed</th></tr>",
    ]
    for a in profile.attributes:
        srcs = ", ".join(_link(u, n) for n, u in sorted({(x.source.name, x.source.url) for x in a.evidence}))
        seen = a.first_observed.date().isoformat()
        if a.last_observed.date() != a.first_observed.date():
            seen += f" – {a.last_observed.date().isoformat()}"
        parts.append(f"<tr><td>{e(a.attribute)}</td><td>{e(a.value)}</td><td class='num'>{_pct(a.confidence)}</td>"
                     f"<td class='src'>{srcs}</td><td>{seen}</td></tr>")
    parts.append("</table><h2>Profiles</h2><table><tr><th>Platform</th><th>Handle</th><th>Match</th>"
                 "<th>Evidence</th></tr>")
    for p in profile.profiles:
        m = p.match
        factors = "<br>".join(f"{e(f.label)} ({f.weight:+.2f})" for f in (m.factors if m else []))
        parts.append(f"<tr><td>{e(str(p.data.get('platform_label') or p.data.get('platform') or ''))}</td>"
                     f"<td>{_link(str(p.data.get('url') or ''), p.label)}</td>"
                     f"<td>{e(m.label) if m else '—'} {_pct(m.score) if m else ''}</td><td>{factors}</td></tr>")
    parts.append("</table><h2>Source coverage</h2><table><tr><th>Source</th><th>Target</th><th>Status</th>"
                 "<th>Detail</th></tr>")
    for r in detail.runs:
        parts.append(f"<tr><td>{e(r.label)}</td><td>{e(r.target)}</td><td>{e(r.status.replace('_', ' '))}</td>"
                     f"<td>{e(r.message or '')}</td></tr>")
    parts.append("</table>")
    if mentions.items:
        parts.append("<h2>Top mentions</h2><table><tr><th>Date</th><th>Title</th><th>Association</th>"
                     "<th>Confidence</th></tr>")
        for m in mentions.items:
            parts.append(f"<tr><td>{_fmt(m.published_at or m.observed_at)}</td><td>{_link(m.url, m.title)}</td>"
                         f"<td>{e(m.association)}</td><td class='num'>{_pct(m.confidence)}</td></tr>")
        parts.append("</table>")
    if timeline:
        parts.append("<h2>Timeline</h2><table><tr><th>Date</th><th>Event</th><th>Source</th></tr>")
        for t in timeline:
            parts.append(f"<tr><td>{t.occurred_at.date().isoformat()}</td><td>{e(t.title)}</td>"
                         f"<td>{_link(t.source.url, t.source.name)}</td></tr>")
        parts.append("</table>")
    if notes:
        parts.append("<h2>Analyst notes</h2>")
        parts += [f"<div class='note'><span class='muted'>{_fmt(n.created_at)}</span><br>{e(n.body)}</div>"
                  for n in notes]
    parts.append(
        "<h2>Methodology</h2><p class='muted'>Only legitimately accessible public sources were queried. Every value "
        "above is an observation linked to the source that stated it. Match scores are evidence-based inferences, "
        "not facts; a matching username alone is never treated as the same person. Sources reported as not "
        "verified or requiring authentication were not queried, so absence of results is not evidence of absence."
        "</p></body></html>")
    return "".join(parts)
