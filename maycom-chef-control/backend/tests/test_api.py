import hashlib
import hmac
import time
import subprocess

import pytest

from conftest import approve, job_body, upload


def test_local_unavailable_blocks_generation_even_with_legacy_paid_key(make_client):
    client = make_client(local_ready=False, fal_key="test-only-legacy-key-never-used", review_token="")
    data = client.get("/api/capabilities").json()
    assert data["app_name"] == "MAYCOM CHEF CONTROL"
    assert data["provider"]["configured"] is False
    assert data["provider"]["id"] == "comfy-local"
    assert "test-only-legacy-key" not in str(data)
    assert data["features"]["identity_verification"] is False
    assert data["features"]["pose_estimation"] is False
    assert data["review"] == {"required": True, "configured": False, "desktop_owner": False}
    assert data["desktop_mode"] is False
    response = client.post("/api/jobs", json={
        "character_id": "a" * 32, "reference_id": "b" * 32,
        "rights_confirmed": True, "fictional_adult_confirmed": True, "non_intimate_confirmed": True,
    })
    assert response.status_code == 503
    assert client.get("/api/jobs").json() == []


def test_missing_model_diagnostic_prevents_queueing(make_client):
    issue = "Modelo ausente: wan2.1_vace_1.3B_fp16.safetensors"
    client = make_client(local_ready=False, local_issues=[issue])
    caps = client.get("/api/capabilities").json()
    assert caps["local"]["issues"] == [issue]
    response = client.post("/api/jobs", json={
        "character_id": "a" * 32, "reference_id": "b" * 32,
        "rights_confirmed": True, "fictional_adult_confirmed": True,
        "non_intimate_confirmed": True,
    })
    assert response.status_code == 503
    assert issue in response.json()["detail"]
    assert client.get("/api/jobs").json() == []


def test_upload_detects_content_and_deletes_private_file(make_client, media_files):
    client = make_client()
    data = upload(client, media_files["image"], "character", filename="C:\\fake\\portrait.exe", content_type="text/html")
    assert data["kind"] == "image"
    assert data["filename"] == "portrait.exe"
    assert data["content_type"] == "image/png"
    assert (data["width"], data["height"]) == (320, 240)
    assert data["review_status"] == "pending"
    assert "path" not in data
    result = client.get(data["file_url"])
    assert result.content == media_files["image"].read_bytes()
    assert result.headers["x-content-type-options"] == "nosniff"
    assert client.delete(f"/api/assets/{data['id']}").status_code == 204
    assert client.get(data["file_url"]).status_code == 404
    assert list((client.app.state.settings.data_dir / "assets").iterdir()) == []


def test_video_upload_runs_real_metadata_and_optical_flow(make_client, media_files):
    client = make_client()
    data = upload(client, media_files["video"], "reference")
    assert data["kind"] == "video"
    assert data["duration"] == pytest.approx(5, abs=0.1)
    assert data["fps"] == 24
    assert data["has_audio"] is True
    assert data["analysis"]["available"] is True
    assert data["analysis"]["sampled_frames"] > 1
    assert data["analysis"]["motion_magnitude"] > 0
    assert data["analysis"]["pose_estimation_available"] is False


@pytest.mark.parametrize("payload,role", [(b"not a video", "reference"), (b"<svg></svg>", "character"), (b"", "character")])
def test_invalid_payload_cleanup(make_client, payload, role):
    client = make_client()
    response = client.post("/api/assets", data={"role": role}, files={"file": ("legit.mp4", payload, "video/mp4")})
    assert response.status_code == 422
    assert client.get("/api/assets").json() == []
    assert list((client.app.state.settings.data_dir / "assets").iterdir()) == []


def test_image_cannot_be_movement_reference(make_client, media_files):
    client = make_client()
    response = client.post("/api/assets", data={"role": "reference"}, files={"file": ("fake.mp4", media_files["image"].read_bytes(), "video/mp4")})
    assert response.status_code == 422


def test_too_short_reference_rejected(make_client, tmp_path, media_files):
    client = make_client()
    short = tmp_path / "two-seconds.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(media_files["video"]), "-t", "2", "-c", "copy", str(short)], check=True, timeout=20)
    response = client.post("/api/assets", data={"role": "reference"}, files={"file": (short.name, short.read_bytes(), "video/mp4")})
    assert response.status_code == 422
    assert client.get("/api/assets").json() == []


def test_oversized_upload_is_cleaned(make_client):
    client = make_client(max_upload_bytes=8)
    response = client.post("/api/assets", data={"role": "character"}, files={"file": ("p.png", b"123456789", "image/png")})
    assert response.status_code == 413
    assert not list((client.app.state.settings.data_dir / "assets").iterdir())


def test_safety_review_fails_closed_and_requires_explicit_confirmation(make_client, media_files):
    unavailable = make_client(review_token="")
    item = upload(unavailable, media_files["image"], "character")
    assert unavailable.post(f"/api/assets/{item['id']}/review", json={"decision": "approved"}).status_code == 503
    client = make_client()
    item = upload(client, media_files["image"], "character")
    route = f"/api/assets/{item['id']}/review"
    assert client.post(route, json={"decision": "approved"}).status_code == 403
    assert client.post(route, headers={"X-Review-Token": "test-only-review-key"}, json={"decision": "approved"}).status_code == 422
    assert approve(client, item)["review_status"] == "approved"
    assert client.post(route, headers={"X-Review-Token": "test-only-review-key"}, json={"decision": "rejected"}).json()["review_status"] == "rejected"


def test_unreviewed_media_cannot_generate(make_client, media_files):
    client = make_client()
    character = upload(client, media_files["image"], "character")
    reference = upload(client, media_files["video"], "reference")
    assert client.post("/api/jobs", json=job_body(character, reference)).status_code == 409
    assert client.get("/api/jobs").json() == []


@pytest.mark.parametrize("change", [
    {"rights_confirmed": False},
    {"fictional_adult_confirmed": False},
    {"non_intimate_confirmed": False},
    {"settings": {"duration": 11, "character_orientation": "image"}},
    {"settings": {"duration": 2}},
    {"settings": {"duration": 4, "trim_start": 2}},
    {"settings": {"motion_intensity": 0.8}},
    {"settings": {"prompt": "nude dance"}},
])
def test_unsupported_or_unsafe_jobs_rejected(approved_assets, change):
    client, character, reference = approved_assets
    body = job_body(character, reference)
    body.update(change)
    assert client.post("/api/jobs", json=body).status_code == 422
    assert client.get("/api/jobs").json() == []


def test_queue_cancel_and_delete_lifecycle(approved_assets):
    client, character, reference = approved_assets
    response = client.post("/api/jobs", json=job_body(character, reference))
    assert response.status_code == 202
    job = response.json()
    assert job["settings"]["engine"] == "comfy-local"
    assert job["settings"]["quality"] == "standard"
    assert job["status"] == "queued" and job["progress"] is None
    assert "provider_request_id" not in job and "output_path" not in job
    assert client.get(f"/api/jobs/{job['id']}/output").status_code == 404
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 409
    assert client.delete(f"/api/assets/{character['id']}").status_code == 409
    assert client.post(f"/api/assets/{character['id']}/review", headers={"X-Review-Token": "test-only-review-key"}, json={"decision": "rejected"}).status_code == 409
    cancelled = client.post(f"/api/jobs/{job['id']}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 409
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.delete(f"/api/assets/{character['id']}").status_code == 204
    assert client.get("/api/jobs").json() == []


def test_cookie_authenticates_media_and_logout_revokes_browser_session(make_client, media_files):
    client = make_client(access_token="test-only-access-key")
    assert client.get("/api/assets").status_code == 401
    assert client.get("/api/capabilities").status_code == 200
    assert client.post("/api/session", headers={"Authorization": "Bearer incorrect"}).status_code == 401
    login = client.post("/api/session", headers={"Authorization": "Bearer test-only-access-key"})
    assert login.status_code == 200
    assert "HttpOnly" in login.headers["set-cookie"]
    assert "SameSite=strict" in login.headers["set-cookie"]
    data = upload(client, media_files["image"], "character")
    assert client.get(data["file_url"]).status_code == 200
    assert client.post("/api/session/logout").status_code == 200
    assert client.get(data["file_url"]).status_code == 401
    assert client.get(data["file_url"], headers={"Authorization": "Bearer test-only-access-key"}).status_code == 200


def test_session_rejects_expired_forged_and_future_signatures(make_client):
    client = make_client(access_token="test-only-access-key")
    for stamp, secret in [(str(int(time.time()) - 9 * 3600), "test-only-access-key"), (str(int(time.time()) + 3600), "test-only-access-key"), (str(int(time.time())), "wrong")]:
        signature = hmac.new(secret.encode(), stamp.encode(), hashlib.sha256).hexdigest()
        client.cookies.set("maycom_session", f"{stamp}.{signature}", path="/api")
        assert client.get("/api/jobs").status_code == 401


def test_foreign_origin_cannot_access_or_mutate_studio(make_client):
    client = make_client()
    for method, route in [("GET", "/api/jobs"), ("POST", "/api/session")]:
        assert client.request(method, route, headers={"Origin": "https://attacker.example"}).status_code == 403
