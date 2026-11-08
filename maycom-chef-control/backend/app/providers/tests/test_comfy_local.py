"""Comfy HTTP contract tests only; no model inference is simulated in runtime."""
import json
import re

import httpx
import pytest

from app.providers.comfy_local import (
    ComfyLocalProvider, ENCODER, MODEL, REQUIRED_NODES, VAE, local_url,
)
from app.providers.fal_motion import ProviderError


def object_info():
    info = {node: {"input": {"required": {}}} for node in REQUIRED_NODES}
    for node, field, value in (("UNETLoader", "unet_name", MODEL),
                               ("CLIPLoader", "clip_name", ENCODER),
                               ("VAELoader", "vae_name", VAE)):
        info[node]["input"]["required"][field] = [["installed/" + value], {}]
    return info


def gpu_stats():
    return {"devices": [{"name": "test-only AMD DirectML device", "type": "privateuseone", "vram_total": 8 * 1024**3}]}


@pytest.mark.parametrize("value", [
    "https://127.0.0.1:8188", "http://example.com:8188", "http://127.0.0.2:8188",
    "http://127.0.0.1.attacker.example:8188", "http://127.0.0.1:8188@evil.example:8188",
    "http://user:secret@127.0.0.1:8188", "http://127.0.0.1:8188/path",
    "http://127.0.0.1:8188/?redirect=evil", "http://127.0.0.1:8188#evil",
    "http://127.0.0.1", "http://127.0.0.1:80", "http://[::1]:8188", "file:///tmp/test",
])
def test_rejects_remote_or_credentialed_urls(value):
    with pytest.raises(ValueError):
        local_url(value)


def test_localhost_is_normalized_without_external_name_resolution():
    assert local_url(" http://localhost:8188/ ") == "http://127.0.0.1:8188"
    assert local_url("http://127.0.0.1:12345") == "http://127.0.0.1:12345"


def test_fixed_workflow_uses_character_and_actual_pose_motion():
    graph = ComfyLocalProvider.workflow("character.png", "reference.mp4", {
        "duration": 3, "quality": "standard", "prompt": "walking", "local_width": 832, "local_height": 480,
    }, object_info(), "maycom/test")
    assert set(n["class_type"] for n in graph.values()) <= set(REQUIRED_NODES)
    assert graph["7"]["inputs"]["file"] == "reference.mp4"
    assert graph["8"]["inputs"]["video"] == ["7", 0]
    assert graph["9"]["inputs"]["image"] == ["8", 0]
    assert graph["9"]["inputs"]["pose_estimator"].endswith(".onnx")
    assert graph["10"]["inputs"]["reference_image"] == ["6", 0]
    assert graph["10"]["inputs"]["control_video"] == ["9", 0]
    assert graph["10"]["inputs"]["length"] == 49
    assert graph["2"]["inputs"]["device"] == "cpu"
    assert graph["2"]["inputs"]["clip_name"] == "installed/" + ENCODER
    assert graph["1"]["inputs"]["weight_dtype"] == "default"
    assert graph["13"]["inputs"] == {"samples": ["12", 0], "trim_amount": ["10", 3]}
    assert graph["14"]["class_type"] == "VAEDecodeTiled"
    assert graph["15"]["inputs"]["fps"] == 16
    assert graph["12"]["inputs"]["steps"] == 20
    assert graph["16"]["inputs"]["format"] == "mp4"
    assert "walking" in graph["4"]["inputs"]["text"]


@pytest.mark.asyncio
async def test_inspection_reports_missing_components_without_claiming_generation():
    info = object_info()
    del info["DWPreprocessor"]
    info["UNETLoader"]["input"]["required"]["unet_name"] = [[], {}]

    def handler(request):
        return httpx.Response(200, json={"devices": [{"name": "cpu", "type": "cpu"}]} if request.url.path == "/system_stats" else info)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ComfyLocalProvider("http://localhost:8188", http_client=client).inspect()
    assert result["configured"] is True and result["ready"] is False
    assert result["gpu"]["available"] is False
    assert any("CPU" in issue for issue in result["issues"])
    assert any("DWPreprocessor" in issue for issue in result["issues"])
    assert any(MODEL in issue for issue in result["issues"])


@pytest.mark.asyncio
async def test_unavailable_local_server_never_falls_back_to_paid_service(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "test-only-must-not-leave-process")
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "127.0.0.1"
        assert "authorization" not in request.headers
        assert "test-only-must-not-leave-process" not in str(request.headers)
        raise httpx.ConnectError("test-only unavailable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ComfyLocalProvider("http://127.0.0.1:8188", http_client=client).inspect()
    assert result["ready"] is False and result["configured"] is False
    assert requests
    assert set(r.url.path for r in requests) <= {"/system_stats", "/object_info"}


@pytest.mark.asyncio
async def test_submit_poll_and_download_use_only_loopback_and_real_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "test-only-paid-key-never-used")
    character, reference = tmp_path / "character.png", tmp_path / "reference.mp4"
    character.write_bytes(b"test-only-image-fixture")
    reference.write_bytes(b"test-only-video-fixture")
    prompt_id = "test-only-local-prompt"
    submitted = []
    request_paths = []
    # Explicit binary HTTP fixture for contract validation, not model output.
    mp4 = b"\x00\x00\x00\x18ftypmp42test-only-contract-fixture"

    def handler(request):
        assert request.url.host == "127.0.0.1" and request.url.port == 8188
        assert "authorization" not in request.headers
        assert b"test-only-paid-key-never-used" not in request.content
        request_paths.append(request.url.path)
        if request.url.path == "/system_stats":
            return httpx.Response(200, json=gpu_stats())
        if request.url.path == "/object_info":
            return httpx.Response(200, json=object_info())
        if request.url.path == "/upload/image":
            match = re.search(rb'filename="([^\"]+)"', request.content)
            assert match
            return httpx.Response(200, json={"name": match.group(1).decode(), "subfolder": "", "type": "input"})
        if request.url.path == "/prompt":
            payload = json.loads(request.content)
            submitted.append(payload)
            return httpx.Response(200, json={"prompt_id": prompt_id})
        if request.url.path == "/history/" + prompt_id:
            return httpx.Response(200, json={prompt_id: {"status": {"completed": True, "status_str": "success"}, "outputs": {"16": {"images": [{"filename": "fixture.mp4", "subfolder": "maycom", "type": "output"}]}}}})
        if request.url.path == "/view":
            assert dict(request.url.params) == {"filename": "fixture.mp4", "subfolder": "maycom", "type": "output"}
            return httpx.Response(200, content=mp4)
        raise AssertionError("Unexpected local request: " + str(request.url))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ComfyLocalProvider("http://127.0.0.1:8188", http_client=client)
        ident = await provider.submit(character, reference, {"duration": 3, "quality": "pro", "local_width": 480, "local_height": 832})
        assert ident == prompt_id
        assert await provider.status(ident) == {"status": "COMPLETED"}
        result = await provider.result(ident)
        output = tmp_path / "received.mp4"
        await provider.download_result(result["video_url"], output)
        await provider.aclose()
        assert not client.is_closed  # caller retains ownership of injected client
    assert len(submitted) == 1
    assert submitted[0]["prompt"]["12"]["inputs"]["steps"] == 30
    assert submitted[0]["prompt"]["10"]["inputs"]["height"] == 832
    assert output.read_bytes() == mp4
    assert not output.with_suffix(".part").exists()
    assert request_paths.count("/upload/image") == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("file", [
    {"filename": "../../secret.mp4", "subfolder": "maycom", "type": "output"},
    {"filename": "secret.mp4", "subfolder": "maycom/../../private", "type": "output"},
    {"filename": "secret.mp4", "subfolder": "/maycom", "type": "output"},
    {"filename": "secret\\name.mp4", "subfolder": "maycom", "type": "output"},
    {"filename": "secret.mp4", "subfolder": "maycom", "type": "input"},
    {"filename": "https://paid.example/video.mp4", "subfolder": "maycom", "type": "output"},
])
async def test_result_rejects_unexpected_output_paths(file):
    def handler(request):
        assert request.url.path == "/history/test-local"
        return httpx.Response(200, json={"test-local": {"outputs": {"16": {"images": [file]}}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match="inválido"):
            await ComfyLocalProvider("http://127.0.0.1:8188", http_client=client).result("test-local")


@pytest.mark.asyncio
@pytest.mark.parametrize("body,status", [(b"not an MP4", 200), (b"", 302)])
async def test_download_rejects_invalid_media_and_redirects_and_cleans_partial(tmp_path, body, status):
    paths = []

    def handler(request):
        paths.append(str(request.url))
        return httpx.Response(status, content=body, headers={"Location": "https://paid.example/result.mp4"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        provider = ComfyLocalProvider("http://127.0.0.1:8188", http_client=client)
        output = tmp_path / "result.mp4"
        with pytest.raises(ProviderError):
            await provider.download_result(json.dumps({"filename": "test.mp4", "subfolder": "maycom", "type": "output"}), output)
    assert len(paths) == 1 and paths[0].startswith("http://127.0.0.1:8188/view?")
    assert not output.exists() and not output.with_suffix(".part").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("running,interrupt", [([], False), ([[0, "another-job", {}]], False), ([[0, "ours", {}]], True), ([[0, "ours", {}], [1, "another-job", {}]], False)])
async def test_cancel_deletes_own_pending_job_and_never_interrupts_other_active_job(running, interrupt):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/queue" and request.method == "POST":
            assert json.loads(request.content) == {"delete": ["ours"]}
            # Official ComfyUI v0.3.40 returns an empty HTTP 200 here.
            return httpx.Response(200)
        if request.url.path == "/queue":
            return httpx.Response(200, json={"queue_running": running})
        assert request.url.path == "/interrupt"
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await ComfyLocalProvider("http://127.0.0.1:8188", http_client=client).cancel("ours")
    assert (("POST", "/interrupt") in calls) is interrupt


@pytest.mark.asyncio
async def test_inference_error_is_reported_without_echoing_private_console_message():
    secret = "test-only-private-path-and-token"

    def handler(request):
        return httpx.Response(200, json={"ours": {"status": {"status_str": "error", "messages": [secret]}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as failure:
            await ComfyLocalProvider("http://127.0.0.1:8188", http_client=client).status("ours")
    assert failure.value.code == "local_inference_failed"
    assert secret not in str(failure.value)
