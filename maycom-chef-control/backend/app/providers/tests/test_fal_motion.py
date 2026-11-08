"""Provider protocol tests. HTTP and upload are mocked; no inference is claimed."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.providers import FalMotionProvider, ProviderError


def run(coroutine):
    return asyncio.run(coroutine)


def test_submit_uses_verified_schema_and_forces_provider_safety(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"request_id": "request-123"})

    uploads = []

    async def upload(path):
        uploads.append(path)
        return f"https://v3.fal.media/{path.name}"

    character = tmp_path / "adult-fictional.png"
    reference = tmp_path / "movement.mp4"
    character.write_bytes(b"test image input; real decoding belongs to the media layer")
    reference.write_bytes(b"test video input; real decoding belongs to the media layer")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = FalMotionProvider("test-key", http_client=client, uploader=upload)
            result = await provider.submit(character, reference, {
                "model_version": "v3", "quality": "pro", "character_orientation": "video",
                "prompt": "  Fashion dance  ", "keep_original_sound": False,
            })
            assert result == "request-123"

    run(scenario())
    assert uploads == [character, reference]
    assert str(requests[0].url) == "https://queue.fal.run/fal-ai/kling-video/v3/pro/motion-control"
    assert requests[0].headers["authorization"] == "Key test-key"
    assert json.loads(requests[0].content) == {
        "image_url": "https://v3.fal.media/adult-fictional.png",
        "video_url": "https://v3.fal.media/movement.mp4",
        "character_orientation": "video", "keep_original_sound": False,
        "prompt": "Fashion dance", "enable_safety_checker": True,
    }


def test_unsupported_controls_rejected_before_upload(tmp_path):
    async def scenario():
        provider = FalMotionProvider("test-key")
        with pytest.raises(ProviderError) as error:
            await provider.submit(tmp_path / "a.png", tmp_path / "r.mp4", {"intensity": 0.9})
        assert error.value.code == "unsupported_settings"
        await provider.aclose()

    run(scenario())


def test_status_result_cancel_use_fixed_queue_route_and_no_fake_percent():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "PUT":
            return httpx.Response(204)
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "IN_PROGRESS", "progress": 99, "logs": [{"message": "discard"}]})
        return httpx.Response(200, json={"video": {"url": "https://v3.fal.media/output.mp4", "file_size": 4096}})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = FalMotionProvider("test-key", http_client=client)
            assert await provider.status("request-1") == {"status": "IN_PROGRESS", "logs": []}
            result = await provider.result("request-1")
            assert result["video_url"] == "https://v3.fal.media/output.mp4"
            await provider.cancel("request-1")

    run(scenario())
    assert [r.url.path for r in requests] == [
        "/fal-ai/kling-video/requests/request-1/status",
        "/fal-ai/kling-video/requests/request-1",
        "/fal-ai/kling-video/requests/request-1/cancel",
    ]


@pytest.mark.parametrize("url", [
    "http://v3.fal.media/output.mp4", "https://127.0.0.1/private",
    "https://fal.media.evil.example/video.mp4", "https://v3.fal.media:8443/video.mp4",
    "https://user:password@v3.fal.media/video.mp4", "https://v3.fal.media/output.mp4#fragment",
])
def test_rejects_untrusted_result_urls_without_network(url, tmp_path):
    async def scenario():
        provider = FalMotionProvider("test-key")
        with pytest.raises(ProviderError) as error:
            await provider.download_result(url, tmp_path / "result.mp4")
        assert error.value.code == "unsafe_result_url"
        assert not (tmp_path / "result.mp4").exists()
        await provider.aclose()

    run(scenario())


def test_redirect_checked_before_request_and_never_sends_fal_auth(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            provider = FalMotionProvider("must-never-leak", download_client=client)
            with pytest.raises(ProviderError) as error:
                await provider.download_result("https://v3.fal.media/result.mp4", tmp_path / "result.mp4")
            assert error.value.code == "unsafe_result_url"

    run(scenario())
    assert len(requests) == 1
    assert "authorization" not in requests[0].headers


def test_streams_verified_mp4_atomically(tmp_path):
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 50

    def handler(request):
        assert "authorization" not in request.headers
        return httpx.Response(200, content=mp4, headers={"content-type": "video/mp4"})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = FalMotionProvider("test-key", download_client=client)
            await provider.download_result("https://v3.fal.media/output.mp4?signature=secret", tmp_path / "result.mp4")

    run(scenario())
    assert (tmp_path / "result.mp4").read_bytes() == mp4
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("content,limit,code", [(b"not an mp4", 1024, "invalid_result"), (b"x" * 1025, 1024, "result_too_large")])
def test_invalid_download_cleans_partial_files(tmp_path, content, limit, code):
    async def scenario():
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=content)))
        async with client:
            provider = FalMotionProvider("test-key", download_client=client, max_result_bytes=limit)
            with pytest.raises(ProviderError) as error:
                await provider.download_result("https://v3.fal.media/video.mp4", tmp_path / "result.mp4")
            assert error.value.code == code

    run(scenario())
    assert not (tmp_path / "result.mp4").exists()
    assert not list(tmp_path.glob(".maycom-result-*.part"))


def test_provider_error_redacts_payload_and_does_not_retry_submit(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503, json={"detail": "Authorization: Key secret-key; signed-url=secret"})

    async def upload(path):
        return f"https://v3.fal.media/{path.name}"

    (tmp_path / "i.png").touch()
    (tmp_path / "r.mp4").touch()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = FalMotionProvider("secret-key", http_client=client, uploader=upload)
            with pytest.raises(ProviderError) as error:
                await provider.submit(tmp_path / "i.png", tmp_path / "r.mp4", {})
            assert error.value.retryable
            assert "secret" not in str(error.value)

    run(scenario())
    assert len(requests) == 1
