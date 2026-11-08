"""Real media fixtures for tests only; never connected to app inference."""

import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(scope="session")
def media_files(tmp_path_factory):
    root = tmp_path_factory.mktemp("media-test-fixtures")
    image = root / "personagem fictícia.png"
    canvas = Image.new("RGB", (320, 240), "#242038")
    ImageDraw.Draw(canvas).rectangle((90, 30, 230, 220), fill="#7860b8")
    canvas.save(image)
    video = root / "movimento referência.mp4"
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=5",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=5",
        "-c:v", "libx264", "-threads", "2", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video),
    ], check=True, timeout=30)
    return {"image": image, "video": video}


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    clients = []
    local_states = {}

    async def test_only_inspect_local(config):
        # Readiness is controlled per test app, without a running ComfyUI or
        # an inference fallback. Actual loopback contracts have their own tests.
        ready, issues = local_states[id(config)]
        return {"url": config.comfy_url, "ready": ready, "configured": ready,
                "issues": issues, "model": "Wan VACE 1.3B",
                "gpu": {"available": ready, "name": "test-only-device" if ready else None,
                        "vram_gb": 8 if ready else None}}

    monkeypatch.setattr("app.main.inspect_local", test_only_inspect_local)

    def factory(**overrides):
        ready = overrides.pop("local_ready", True)
        issues = overrides.pop("local_issues", [] if ready else ["Motor local indisponível."])
        config = Settings(
            data_dir=tmp_path / f"store-{len(clients)}",
            fal_key=overrides.pop("fal_key", ""),
            review_token=overrides.pop("review_token", "test-only-review-key"),
            access_token=overrides.pop("access_token", ""),
            worker_enabled=False,
            **overrides,
        )
        local_states[id(config)] = ready, issues
        app = create_app(config)
        client = TestClient(app)
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.close()


def upload(client, path: Path, role: str, filename=None, content_type="application/octet-stream"):
    with path.open("rb") as stream:
        response = client.post("/api/assets", data={"role": role}, files={"file": (filename or path.name, stream, content_type)})
    assert response.status_code == 201, response.text
    return response.json()


def approve(client, asset, token="test-only-review-key"):
    response = client.post(
        f"/api/assets/{asset['id']}/review",
        headers={"X-Review-Token": token},
        json={"decision": "approved", "fictional_adult_confirmed": True, "non_intimate_confirmed": True},
    )
    assert response.status_code == 200, response.text
    return response.json()


def job_body(character, reference, **settings):
    return {
        "character_id": character["id"],
        "reference_id": reference["id"],
        "rights_confirmed": True,
        "fictional_adult_confirmed": True,
        "non_intimate_confirmed": True,
        "settings": {"duration": 3, **settings},
    }


@pytest.fixture
def approved_assets(make_client, media_files):
    client = make_client()
    character = approve(client, upload(client, media_files["image"], "character"))
    reference = approve(client, upload(client, media_files["video"], "reference"))
    return client, character, reference
