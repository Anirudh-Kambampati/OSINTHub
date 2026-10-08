from tests.conftest import ADMIN

ANALYST = {"email": "analyst@example.com", "name": "Analyst", "password": "another-good-pass-2"}


async def test_unauthenticated_requests_are_rejected(anon_api):
    assert (await anon_api.get("/api/investigations")).status_code == 401
    status = (await anon_api.get("/api/auth/status")).json()
    assert status == {"user": None, "needs_setup": True, "allow_registration": False}


async def test_first_account_is_admin_then_registration_closes(anon_api):
    first = await anon_api.post("/api/auth/register", json=ADMIN)
    assert first.status_code == 201 and first.json()["role"] == "admin"
    anon_api.cookies.clear()
    second = await anon_api.post("/api/auth/register", json=ANALYST)
    assert second.status_code == 403


async def test_login_logout_and_bad_password(api):
    assert (await api.get("/api/auth/status")).json()["user"]["email"] == ADMIN["email"]
    assert (await api.post("/api/auth/logout")).status_code == 204
    assert (await api.get("/api/investigations")).status_code == 401
    bad = await api.post("/api/auth/login", json={"email": ADMIN["email"], "password": "wrong-password-123"})
    assert bad.status_code == 401
    ok = await api.post("/api/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]})
    assert ok.status_code == 200
    assert "httponly" in ok.headers["set-cookie"].lower()


async def test_weak_password_rejected(anon_api):
    r = await anon_api.post("/api/auth/register", json={**ADMIN, "password": "short"})
    assert r.status_code == 422


async def test_state_changes_require_csrf_header(api):
    r = await api.post("/api/investigations", json={"seed": "anirudh123"}, headers={"X-OSINT-CSRF": ""})
    assert r.status_code == 403


async def test_users_only_see_their_own_investigations(api):
    created = await api.post("/api/users", json=ANALYST)
    assert created.status_code == 201
    inv = (await api.post("/api/investigations", json={"seed": "anirudh123"})).json()

    await api.post("/api/auth/logout")
    await api.post("/api/auth/login", json={"email": ANALYST["email"], "password": ANALYST["password"]})
    assert (await api.get("/api/investigations")).json() == []
    assert (await api.get(f"/api/investigations/{inv['id']}")).status_code == 404
    assert (await api.get("/api/users")).status_code == 403


async def test_deactivated_user_cannot_sign_in(api):
    user = (await api.post("/api/users", json=ANALYST)).json()
    assert (await api.patch(f"/api/users/{user['id']}", json={"is_active": False})).status_code == 200
    await api.post("/api/auth/logout")
    r = await api.post("/api/auth/login", json={"email": ANALYST["email"], "password": ANALYST["password"]})
    assert r.status_code == 401


async def test_admin_cannot_lock_themselves_out(api):
    me = (await api.get("/api/auth/status")).json()["user"]
    r = await api.patch(f"/api/users/{me['id']}", json={"role": "analyst"})
    assert r.status_code == 409


async def test_audit_log_records_actions(api):
    await api.post("/api/investigations", json={"seed": "anirudh123"})
    actions = {e["action"] for e in (await api.get("/api/audit")).json()}
    assert {"user.register", "investigation.create"} <= actions
