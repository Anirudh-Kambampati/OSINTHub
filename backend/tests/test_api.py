async def _run(api, seed="anirudh123") -> dict:
    resp = await api.post("/api/investigations", json={"seed": seed})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    await api.app.state.runner.drain()
    return body


async def test_classify_endpoint(api):
    r = await api.post("/api/classify", json={"value": "john@example.com"})
    assert r.json() == {"valid": True, "type": "email", "normalized": "john@example.com", "alternatives": [], "error": None}
    r = await api.post("/api/classify", json={"value": "ftp://x"})
    assert r.json()["valid"] is False


async def test_create_returns_planned_sources_immediately(api):
    body = await _run(api)
    assert body["seed_type"] == "username"
    assert {r["connector"] for r in body["runs"]} == {"github", "devto", "gitlab", "broken", "crashy"}


async def test_investigation_lifecycle(api):
    created = await _run(api)
    iid = created["id"]

    detail = (await api.get(f"/api/investigations/{iid}")).json()
    assert detail["status"] == "partial"
    assert detail["stats"]["profiles"] == 2
    assert detail["stats"]["matched_profiles"] == 2
    assert detail["stats"]["confidence"] > 0.6

    profile = (await api.get(f"/api/investigations/{iid}/profile")).json()
    assert profile["subject"]["label"] == "Anirudh K"
    email = next(a for a in profile["attributes"] if a["attribute"] == "email")
    assert email["value"] == "anirudh@example.com"
    assert email["source_count"] == 2
    assert {e["source"]["connector"] for e in email["evidence"]} == {"github", "devto"}
    statuses = {p["connector"]: p["status"] for p in profile["presence"]}
    assert statuses["broken"] == "error" and statuses["gitlab"] == "not_found"

    graph = (await api.get(f"/api/investigations/{iid}/graph")).json()
    node_ids = {n["id"] for n in graph["nodes"]}
    assert all(e["source"] in node_ids and e["target"] in node_ids for e in graph["edges"])
    assert any(n["is_subject"] for n in graph["nodes"])
    assert any(e["inferred"] and e["type"] == "ASSOCIATED_WITH" for e in graph["edges"])

    gh = next(p for p in profile["profiles"] if p["key"] == "github:anirudh123")
    evidence = (await api.get(f"/api/entities/{gh['id']}/evidence")).json()
    assert evidence["entity"]["match"]["factors"]
    assert all(o["source"]["url"] for o in evidence["observations"])

    timeline = (await api.get(f"/api/investigations/{iid}/timeline")).json()
    assert isinstance(timeline, list)
    mentions = (await api.get(f"/api/investigations/{iid}/mentions?sort=confidence")).json()
    assert mentions["total"] == 0

    listed = (await api.get("/api/investigations")).json()
    assert listed[0]["id"] == iid

    assert (await api.delete(f"/api/investigations/{iid}")).status_code == 204
    assert (await api.get(f"/api/investigations/{iid}")).status_code == 404


async def test_invalid_seed_rejected(api):
    r = await api.post("/api/investigations", json={"seed": "javascript:alert(1)"})
    assert r.status_code == 422


async def test_unknown_ids_are_404(api):
    assert (await api.get("/api/investigations/nope")).status_code == 404
    assert (await api.get("/api/entities/nope/evidence")).status_code == 404
    assert (await api.get("/api/observations/nope/image")).status_code == 404


async def test_api_token_enforced(api, monkeypatch):
    from pydantic import SecretStr

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "api_token", SecretStr("s3cret"))
    assert (await api.get("/api/investigations")).status_code == 401
    ok = await api.get("/api/investigations", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
