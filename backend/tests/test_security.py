import httpx
import pytest
import respx

from app.config import get_settings
from app.core import net
from app.core.net import UnsafeURLError, redact_url, validate_public_url
from app.core.text import clean_text


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "http://localhost/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://0.0.0.0/",
    "file:///etc/passwd",
    "gopher://example.com/",
    "http://example.com:8080/",
    "http://user:pass@example.com/",
    "http://printer.local/",
])
async def test_ssrf_guard_rejects_internal_destinations(url):
    with pytest.raises(UnsafeURLError):
        await validate_public_url(url)


async def test_ssrf_guard_allows_public_ip_literal():
    await validate_public_url("https://1.1.1.1/")


def test_secrets_are_redacted_from_logged_urls():
    url = redact_url("https://www.googleapis.com/youtube/v3/channels?part=snippet&key=AIzaSECRET")
    assert "AIzaSECRET" not in url
    assert "part=snippet" in url


def test_external_text_is_sanitized():
    assert clean_text("<img src=x onerror=alert(1)>hello <b>world</b>") == "hello world"
    assert len(clean_text("x" * 1000, 280)) == 280


async def test_credentials_not_forwarded_across_hosts(monkeypatch):
    async def allow(_url):
        return None

    monkeypatch.setattr(net, "validate_public_url", allow)
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.example.com/x").respond(302, headers={"Location": "https://other.example.org/y"})
        final = mock.get("https://other.example.org/y").respond(200, text="ok")
        async with httpx.AsyncClient() as client:
            http = net.SourceHttp(client, get_settings(), net.HostLimiter(), "test", [])
            resp = await http.get("https://api.example.com/x", headers={"Authorization": "Bearer secret"})
        assert resp.status_code == 200
        assert "authorization" not in final.calls.last.request.headers


async def test_transient_errors_retried_once_but_429_is_not(monkeypatch):
    async def allow(_url):
        return None

    monkeypatch.setattr(net, "validate_public_url", allow)
    monkeypatch.setattr(net, "RETRY_DELAY", 0)
    with respx.mock() as mock:
        flaky = mock.get("https://a.example.com/").mock(side_effect=[httpx.Response(503), httpx.Response(200)])
        limited = mock.get("https://b.example.com/").respond(429)
        async with httpx.AsyncClient() as client:
            http = net.SourceHttp(client, get_settings(), net.HostLimiter(), "test", [])
            assert (await http.get("https://a.example.com/")).status_code == 200
            assert (await http.get("https://b.example.com/")).status_code == 429
        assert flaky.call_count == 2
        assert limited.call_count == 1
