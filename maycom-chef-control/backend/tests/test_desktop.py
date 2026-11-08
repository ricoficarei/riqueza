import json
import os

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.process_lock import acquire_worker_lock


@pytest.fixture(autouse=True)
def unavailable_test_only_local_engine(monkeypatch):
    async def inspect(config):
        return {"url": config.comfy_url, "ready": False, "configured": False,
                "issues": ["Motor local de teste indisponível."], "model": "Wan VACE 1.3B",
                "gpu": {"available": False, "name": None, "vram_gb": None}}

    monkeypatch.setattr("app.main.inspect_local", inspect)


def desktop_client(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", desktop_config_path=tmp_path / "settings.dat", desktop_mode=True, access_token="test-only-desktop-access", review_token="test-only-review", worker_enabled=False)
    app = create_app(settings)
    app.state.desktop_nonce = "test-only-launch-nonce"
    client = TestClient(app)
    response = client.get("/desktop/start/test-only-launch-nonce", follow_redirects=False)
    assert response.status_code == 303
    return client, settings


def test_desktop_bootstrap_is_single_use_and_configuration_is_private(tmp_path):
    client, settings = desktop_client(tmp_path)
    caps = client.get("/api/capabilities").json()
    assert caps["desktop_mode"] and caps["review"]["desktop_owner"]
    assert client.get("/desktop/start/test-only-launch-nonce", follow_redirects=False).status_code == 403
    assert client.get("/api/local/settings").json()["ready"] is False
    saved = client.put("/api/local/settings", json={"url": "http://localhost:8388/"})
    assert saved.status_code == 200
    assert saved.json()["url"] == "http://127.0.0.1:8388"
    # Saving an address does not claim that models or a GPU are available.
    assert saved.json()["ready"] is False
    settings_path = settings.data_dir / "local-engine.json"
    assert json.loads(settings_path.read_text()) == {"url": "http://127.0.0.1:8388"}
    assert "fal_key" not in client.get("/api/local/settings").text
    if os.name != "nt":
        assert settings_path.stat().st_mode & 0o777 == 0o600
    other = TestClient(create_app(settings))
    assert other.get("/api/local/settings").status_code == 401
    assert other.get("/api/local/settings", headers={"Authorization": "Bearer test-only-desktop-access"}).json()["url"] == "http://127.0.0.1:8388"
    for method in ("GET", "PUT", "DELETE"):
        assert client.request(method, "/api/desktop/settings").status_code == 410
    assert client.get("/api/capabilities").json()["provider"]["configured"] is False


def test_desktop_rejects_cross_port_origin_and_bad_hosts(tmp_path):
    client, _ = desktop_client(tmp_path)
    assert client.put("/api/local/settings", headers={"Origin": "http://localhost:5173"}, json={"url": "http://127.0.0.1:8188"}).status_code == 403
    assert client.get("/api/local/settings", headers={"Host": "attacker.example"}).status_code == 403


@pytest.mark.parametrize("url", ["https://127.0.0.1:8188", "http://example.com:8188", "http://127.0.0.1:80", "http://127.0.0.1:8188/path", "http://user:pass@127.0.0.1:8188", "http://127.0.0.1:8188/?key=value"])
def test_desktop_local_connection_rejects_nonlocal_addresses_and_credentials(tmp_path, url):
    client, settings = desktop_client(tmp_path)
    assert client.put("/api/local/settings", json={"url": url}).status_code == 422
    assert not (settings.data_dir / "local-engine.json").exists()


def test_desktop_needs_private_session_and_web_does_not_expose_settings(tmp_path):
    with pytest.raises(ValueError):
        create_app(Settings(data_dir=tmp_path / "bad", desktop_mode=True))
    app = create_app(Settings(data_dir=tmp_path / "web", worker_enabled=False, fal_key="", access_token="", review_token=""))
    client = TestClient(app)
    assert client.get("/api/local/settings").status_code == 404
    assert client.put("/api/local/settings", json={"url": "http://127.0.0.1:8188"}).status_code == 404


def test_process_lock_prevents_second_worker_and_releases_after_close(tmp_path):
    path = tmp_path / "worker.lock"
    first = acquire_worker_lock(path)
    try:
        with pytest.raises(RuntimeError):
            acquire_worker_lock(path)
    finally:
        first.close()
    second = acquire_worker_lock(path)
    second.close()
