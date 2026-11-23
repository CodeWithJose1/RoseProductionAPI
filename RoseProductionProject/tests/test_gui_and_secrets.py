"""The GUI is served by Flask and contains no credential."""

import os
import subprocess

import pytest

from conftest import ROOT

DIST = os.path.join(ROOT, "frontend", "dist")


def _dist_files():
    for folder, _, files in os.walk(DIST):
        for name in files:
            yield os.path.join(folder, name)


def test_gui_build_exists():
    assert os.path.isfile(os.path.join(DIST, "index.html")), \
        "Run 'npm run build' in frontend/"


def test_gui_index_is_public(client):
    response = client.get("/app/")
    assert response.status_code == 200
    assert b'<div id="root">' in response.data
    assert response.headers["Cache-Control"] == "no-cache"


def test_gui_redirect_and_spa_fallback(client):
    assert client.get("/app").status_code == 302
    for route in ("farms", "harvests", "forecasts", "analytics"):
        response = client.get(f"/app/{route}")
        assert response.status_code == 200
        assert b'<div id="root">' in response.data


def test_gui_assets_are_served_with_long_cache(client):
    assets = [p for p in _dist_files() if "/assets/" in p.replace("\\", "/")]
    assert assets
    name = os.path.relpath(assets[0], DIST).replace("\\", "/")
    response = client.get(f"/app/{name}")
    assert response.status_code == 200
    assert "immutable" in response.headers["Cache-Control"]


@pytest.mark.parametrize("path", ["/app/../app.py", "/app/..%2Fapp.py",
                                  "/app/%2e%2e/.env", "/app/../../.env"])
def test_gui_path_traversal_is_blocked(client, path):
    response = client.get(path)
    assert b"API_KEY" not in response.data
    assert b"DB_PASSWORD" not in response.data
    assert b"import" not in response.data[:200]


def test_api_key_not_in_any_frontend_asset(api_key):
    for path in _dist_files():
        with open(path, "rb") as handle:
            assert api_key.encode() not in handle.read(), path


def test_api_key_not_in_frontend_sources(api_key):
    src = os.path.join(ROOT, "frontend")
    for folder, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist")]
        for name in files:
            path = os.path.join(folder, name)
            with open(path, "rb") as handle:
                assert api_key.encode() not in handle.read(), path


def test_no_vite_env_files_expose_secrets():
    frontend = os.path.join(ROOT, "frontend")
    for name in os.listdir(frontend):
        if name.startswith(".env"):
            with open(os.path.join(frontend, name), encoding="utf-8") as fh:
                assert "API_KEY" not in fh.read()


def test_env_file_is_git_ignored():
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        ignored = fh.read().split()
    assert ".env" in ignored


def test_env_example_has_no_real_values(api_key):
    with open(os.path.join(ROOT, ".env.example"), encoding="utf-8") as fh:
        content = fh.read()
    assert api_key not in content
    assert "API_KEY=" in content


def test_env_not_tracked_by_git():
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".env"], cwd=ROOT,
            capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("git not available")
    if "not a git repository" in (result.stderr or "").lower():
        pytest.skip("project folder is not a git repository")
    assert result.returncode != 0, ".env is tracked by git!"
