"""Analyst workflow: decisions, notes, tags, monitoring settings, exports."""

from app.services.export import _cell


async def _investigation(api) -> tuple[str, dict]:
    inv = (await api.post("/api/investigations", json={"seed": "anirudh123"})).json()
    await api.app.state.worker.run_until_idle()
    profile = (await api.get(f"/api/investigations/{inv['id']}/profile")).json()
    return inv["id"], profile


async def test_analyst_decisions_override_the_resolver(api):
    iid, profile = await _investigation(api)
    devto = next(p for p in profile["profiles"] if p["key"] == "devto:anirudh123")

    rejected = (await api.put(f"/api/entities/{devto['id']}/decision", json={"decision": "rejected"})).json()
    assert rejected["entity"]["match"]["score"] == 0
    assert rejected["entity"]["match"]["decision"] == "rejected"
    profile = (await api.get(f"/api/investigations/{iid}/profile")).json()
    email = next(a for a in profile["attributes"] if a["attribute"] == "email")
    assert {e["source"]["connector"] for e in email["evidence"]} == {"github"}

    confirmed = (await api.put(f"/api/entities/{devto['id']}/decision",
                               json={"decision": "confirmed", "note": "same avatar and bio"})).json()
    assert confirmed["entity"]["match"]["label"] == "Analyst confirmed"
    assert confirmed["entity"]["match"]["decision_note"] == "same avatar and bio"

    cleared = (await api.delete(f"/api/entities/{devto['id']}/decision")).json()
    assert cleared["entity"]["match"]["decision"] is None


async def test_corroborated_profiles_share_a_cluster(api):
    _, profile = await _investigation(api)
    clusters = {p["key"]: p["match"]["cluster"] for p in profile["profiles"]}
    assert clusters["github:anirudh123"] == clusters["devto:anirudh123"] == 0


async def test_notes_tags_and_monitoring(api):
    iid, _ = await _investigation(api)
    note = (await api.post(f"/api/investigations/{iid}/notes", json={"body": "Follow up on DEV posts"})).json()
    assert note["author_name"] == "Admin"
    assert len((await api.get(f"/api/investigations/{iid}/notes")).json()) == 1
    assert (await api.delete(f"/api/investigations/{iid}/notes/{note['id']}")).status_code == 204

    updated = (await api.patch(f"/api/investigations/{iid}", json={"tags": ["case-42", "priority"],
                                                                   "monitor_interval_hours": 24})).json()
    assert updated["tags"] == ["case-42", "priority"]
    assert updated["next_run_at"] is not None
    off = (await api.patch(f"/api/investigations/{iid}", json={"monitor_interval_hours": None})).json()
    assert off["monitor_interval_hours"] is None and off["next_run_at"] is None
    bad = await api.patch(f"/api/investigations/{iid}", json={"tags": ["<script>"]})
    assert bad.status_code == 422


async def test_rerun_marks_new_entities(api):
    iid, _ = await _investigation(api)
    await api.post(f"/api/investigations/{iid}/search")
    await api.app.state.worker.run_until_idle()
    detail = (await api.get(f"/api/investigations/{iid}")).json()
    assert detail["run_count"] == 2 and detail["previous_completed_at"]
    assert detail["stats"]["new_entities"] == 0  # same data both runs: nothing new


async def test_exports(api):
    iid, _ = await _investigation(api)
    full = (await api.get(f"/api/investigations/{iid}/export.json")).json()
    assert full["format"] == "osint-console/v1"
    assert full["observations"] and full["sources"]
    assert all(o["source_id"] for o in full["observations"])

    for dataset in ("attributes", "profiles", "mentions", "observations", "timeline", "sources"):
        csv = await api.get(f"/api/investigations/{iid}/export.csv?dataset={dataset}")
        assert csv.status_code == 200, dataset
        assert "attachment" in csv.headers["content-disposition"]
    attrs = await api.get(f"/api/investigations/{iid}/export.csv?dataset=attributes")
    assert "anirudh@example.com" in attrs.text

    report = await api.get(f"/api/investigations/{iid}/report.html")
    assert "default-src 'none'" in report.headers["content-security-policy"]
    assert "Anirudh K" in report.text and "<script" not in report.text


def test_csv_cells_neutralise_formulas():
    assert _cell('=HYPERLINK("http://evil")').startswith("'")
    assert _cell("@SUM(A1)") == "'@SUM(A1)"
    assert _cell("normal") == "normal"
