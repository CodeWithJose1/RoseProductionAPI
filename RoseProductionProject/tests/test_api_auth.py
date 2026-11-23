"""Authentication and access control (NFR-06)."""

import pytest

import auth

PROTECTED = ["/farms", "/lots", "/varieties", "/crops", "/seasons",
             "/harvests", "/forecasts", "/stats/dashboard",
             "/forecasts/status", "/forecasts/summary"]
GUI = {"X-Requested-With": "RoseProductionGUI"}


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    auth._failed_logins.clear()
    yield
    auth._failed_logins.clear()


def test_home_is_public(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_json()
    assert body["message"] == "Rose Production API is running"
    assert body["database"] == "RoseProductionDB"
    assert body["version"] == "1.2.0"


@pytest.mark.parametrize("path", PROTECTED)
def test_missing_key_is_401(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.get_json() == {"error": "Unauthorized"}


@pytest.mark.parametrize("path", PROTECTED)
def test_wrong_key_is_401(client, path):
    response = client.get(path, headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


@pytest.mark.parametrize("path", PROTECTED)
def test_valid_key_is_200(client, h, path):
    assert client.get(path, headers=h).status_code == 200


def test_non_ascii_key_does_not_crash(client):
    response = client.get("/farms", headers={"X-API-Key": "clé-ñ"})
    assert response.status_code == 401


def test_write_without_key_is_401(client):
    response = client.post("/varieties", json={"name": "x", "color": "y"})
    assert response.status_code == 401


def test_unknown_route_requires_auth_then_404(client, h):
    assert client.get("/does-not-exist").status_code == 401
    response = client.get("/does-not-exist", headers=h)
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_method_not_allowed_is_json_405(client, h):
    response = client.patch("/farms", headers=h)
    assert response.status_code == 405
    assert response.get_json()["error"] == "Method not allowed"


# ---------------------------------------------------------------- session

def test_auth_status_anonymous(client):
    body = client.get("/auth/status").get_json()
    assert body == {"authenticated": False, "auth_configured": True}


def test_login_with_wrong_key_is_401(client):
    response = client.post("/auth/login", json={"api_key": "nope"},
                           headers=GUI)
    assert response.status_code == 401
    assert response.get_json()["code"] == "INVALID_CREDENTIALS"
    assert client.get("/farms").status_code == 401


def test_login_requires_key_field(client):
    response = client.post("/auth/login", json={}, headers=GUI)
    assert response.status_code == 400
    assert client.post("/auth/login", data="not json",
                       headers=GUI).status_code == 400


def test_session_login_read_write_logout(client, api_key, tracker):
    response = client.post("/auth/login", json={"api_key": api_key},
                           headers=GUI)
    assert response.status_code == 200
    cookie = response.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert api_key not in cookie

    assert client.get("/auth/status").get_json()["authenticated"] is True
    assert client.get("/farms").status_code == 200

    created = client.post("/varieties", headers=GUI,
                          json={"name": "TEST_session", "color": "Red"})
    assert created.status_code == 201
    tracker.add("RoseVariety", created.get_json()["variety"]["variety_id"])

    assert client.post("/auth/logout", headers=GUI).status_code == 200
    assert client.get("/farms").status_code == 401


def test_session_write_without_gui_header_is_403(client, api_key):
    client.post("/auth/login", json={"api_key": api_key}, headers=GUI)
    response = client.post("/varieties",
                           json={"name": "TEST_csrf", "color": "Red"})
    assert response.status_code == 403
    assert response.get_json()["code"] == "CSRF_CHECK_FAILED"
    # Reads do not need the header.
    assert client.get("/varieties").status_code == 200


def test_session_cookie_cannot_be_forged(client):
    client.set_cookie("rose_session", "forged-value")
    assert client.get("/farms").status_code == 401


def test_login_is_throttled_after_repeated_failures(client, app):
    limit = app.config["LOGIN_MAX_FAILURES"]
    for _ in range(limit):
        assert client.post("/auth/login", json={"api_key": "bad"},
                           headers=GUI).status_code == 401
    blocked = client.post("/auth/login", json={"api_key": "bad"},
                          headers=GUI)
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")


def test_security_headers_present(client, h):
    response = client.get("/farms", headers=h)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in response.headers


def test_request_body_too_large_is_413(client, h):
    response = client.post("/varieties", headers=h,
                           data=b'{"name": "' + b"x" * (1024 * 1024 + 10)
                           + b'", "color": "Red"}',
                           content_type="application/json")
    assert response.status_code == 413
    assert response.get_json()["error"] == "Request body too large"
