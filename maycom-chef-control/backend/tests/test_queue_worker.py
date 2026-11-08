"""The only inference double lives in tests; it is never a runtime fallback."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
import shutil
import subprocess
import uuid

import pytest

from app.database import Database, now
from app.media import _probe
from app.providers import ProviderError
from app.worker import Worker
from conftest import job_body


def record(status="queued", request_id=None):
    stamp = now()
    return {"id": uuid.uuid4().hex, "status": status, "stage": "test", "created_at": stamp, "updated_at": stamp,
            "provider_request_id": request_id, "logs": [], "settings": {"model_version": "v3", "quality": "pro"}}


def test_concurrent_claim_is_exclusive_and_queue_limit_is_atomic(tmp_path):
    db = Database(tmp_path / "queue.db")
    jobs = [record() for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        def enqueue(job):
            try:
                db.enqueue(job, 3)
                return True
            except ValueError:
                return False
        assert sum(pool.map(enqueue, jobs)) == 3
        claimed = list(pool.map(lambda _: db.claim(), range(8)))
    ids = [j["id"] for j in claimed if j]
    assert len(ids) == len(set(ids)) == 3
    assert db.claim() is None


def test_restart_keeps_remote_id_and_never_blindly_resubmits(tmp_path):
    db = Database(tmp_path / "queue.db")
    running = record("running", "remote-job-one")
    uncertain = record("submitting")
    queued = record()
    cancelled = record("cancelled", "do-not-resume")
    for job in (running, uncertain, queued, cancelled):
        db.enqueue(job, 10)
    reopened = Database(db.path)
    reopened.recover()
    assert reopened.job(running["id"])["status"] == "queued"
    assert reopened.job(running["id"])["provider_request_id"] == "remote-job-one"
    assert reopened.job(uncertain["id"])["status"] == "failed"
    assert "cobrança" in reopened.job(uncertain["id"])["error"]
    assert reopened.job(queued["id"])["status"] == "queued"
    assert reopened.job(cancelled["id"])["status"] == "cancelled"


class TestOnlyProvider:
    __test__ = False

    def __init__(self, fixture, failure=None):
        self.fixture, self.failure = fixture, failure
        self.submissions = []
        self.polls = 0
        self.closed = 0
        self.cancelled = []

    async def submit(self, character, reference, settings):
        assert character.is_file() and reference.is_file()
        self.submissions.append(settings)
        if self.failure:
            raise self.failure
        return "test-remote-request"

    async def status(self, request_id):
        assert request_id == "test-remote-request"
        self.polls += 1
        return {"status": "IN_PROGRESS" if self.polls == 1 else "COMPLETED"}

    async def result(self, request_id):
        return {"video_url": "https://test-only.invalid/synthetic-fixture.mp4"}

    async def download_result(self, url, path):
        assert url.startswith("https://test-only.invalid/")
        shutil.copyfile(self.fixture, path)

    async def cancel(self, request_id):
        self.cancelled.append(request_id)

    async def aclose(self):
        self.closed += 1


@pytest.mark.asyncio
async def test_worker_real_media_pipeline_with_explicit_test_provider(approved_assets, media_files):
    client, character, reference = approved_assets
    job = client.post("/api/jobs", json=job_body(character, reference, output_fps=30)).json()
    db, config = client.app.state.db, client.app.state.settings
    config.poll_interval = 0.01
    provider = TestOnlyProvider(media_files["video"])
    worker = Worker(db, config, lambda options: provider)
    await worker.process(db.claim())
    stored = db.job(job["id"])
    assert stored["status"] == "completed"
    assert provider.submissions == [{"model_version": "v3", "quality": "standard", "character_orientation": "video", "keep_original_sound": True, "prompt": ""}]
    assert provider.polls == 2 and provider.closed == 1
    assert stored["progress"] is None
    assert stored["quality_report"]["metrics"]["available"] is True
    assert stored["quality_report"]["status"] == "review_required"
    assert _probe(stored["output_path"])["fps"] == 30
    assert _probe(stored["output_path"])["has_audio"] is True
    response = client.get(stored["output_url"] + "?download=true")
    assert response.status_code == 200 and response.content
    assert "attachment" in response.headers["content-disposition"]
    assert len(list((config.data_dir / "jobs" / job["id"]).iterdir())) == 1
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert not (config.data_dir / "jobs" / job["id"]).exists()


@pytest.mark.asyncio
async def test_local_worker_normalizes_motion_restores_audio_and_cleans_workfiles(approved_assets, media_files, tmp_path):
    """Exercise local FFmpeg branches with a labelled inference double only."""
    client, character, reference = approved_assets
    response = client.post("/api/jobs", json=job_body(character, reference, trim_start=1, duration=3, output_fps=24))
    assert response.status_code == 202
    job = response.json()
    assert job["settings"]["engine"] == "comfy-local"
    db, config = client.app.state.db, client.app.state.settings
    config.poll_interval = 0.01

    # A deliberately silent synthetic test result proves the local worker adds
    # authorized reference audio, rather than preserving audio from this double.
    silent_result = tmp_path / "test-only-silent-result.mp4"
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(media_files["video"]),
        "-t", "3", "-an", "-c:v", "copy", str(silent_result),
    ], check=True, timeout=30)
    assert _probe(silent_result)["has_audio"] is False

    class InspectingTestOnlyProvider(TestOnlyProvider):
        async def submit(self, character_path, reference_path, settings):
            assert reference_path.name == "motion16.mp4"
            prepared = _probe(reference_path)
            assert prepared["fps"] == 16
            assert (prepared["width"], prepared["height"]) == (832, 480)
            assert prepared["duration"] == pytest.approx(3, abs=0.1)
            assert prepared["has_audio"] is False
            assert settings["duration"] == 3
            assert (settings["local_width"], settings["local_height"]) == (832, 480)
            return await super().submit(character_path, reference_path, settings)

    provider = InspectingTestOnlyProvider(silent_result)
    worker = Worker(db, config, lambda options: provider)
    # Controlled provider output is confined to this test; production's default
    # constructor uses the real ComfyUI client with this local branch enabled.
    worker.local = True
    await worker.process(db.claim())
    stored = db.job(job["id"])
    assert stored["status"] == "completed"
    assert len(provider.submissions) == 1
    assert provider.closed == 1
    exported = _probe(stored["output_path"])
    assert exported["fps"] == 24
    assert exported["duration"] == pytest.approx(3, abs=0.15)
    assert exported["has_audio"] is True
    assert stored["quality_report"]["status"] == "review_required"
    assert {path.name for path in (config.data_dir / "jobs" / job["id"]).iterdir()} == {"output.mp4"}


@pytest.mark.asyncio
async def test_worker_records_failure_and_does_not_create_fake_output(approved_assets, media_files):
    client, character, reference = approved_assets
    job = client.post("/api/jobs", json=job_body(character, reference)).json()
    db, config = client.app.state.db, client.app.state.settings
    provider = TestOnlyProvider(media_files["video"], failure=ProviderError("Test-only remote denial"))
    worker = Worker(db, config, lambda options: provider)
    task = asyncio.create_task(worker.run())
    try:
        for _ in range(150):
            if db.job(job["id"])["status"] == "failed":
                break
            await asyncio.sleep(0.05)
        failed = db.job(job["id"])
        assert failed["status"] == "failed"
        assert failed["error"].startswith("Test-only remote denial")
        assert "cobrança" in failed["error"]
        assert failed["output_url"] is None
        assert not (config.data_dir / "jobs" / job["id"]).exists()
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_recovered_local_job_fails_without_resubmission(approved_assets, media_files):
    client, character, reference = approved_assets
    job = client.post("/api/jobs", json=job_body(character, reference)).json()
    db, config = client.app.state.db, client.app.state.settings
    db.update_job(job["id"], status="running", provider_request_id="test-remote-request")
    db.recover()
    provider = TestOnlyProvider(media_files["video"])
    assert db.claim() is None
    assert provider.submissions == []
    assert provider.polls == 0
    recovered = db.job(job["id"])
    assert recovered["status"] == "failed"
    assert "local" in recovered["error"]
    assert "cobrança" not in recovered["error"]
    assert recovered["provider_request_id"] == "test-remote-request"


def test_local_only_recovery_blocks_legacy_jobs_and_preserves_queued_local(tmp_path):
    db = Database(tmp_path / "queue.db")
    legacy_queued = record()
    legacy_running = record("running", "legacy-fal-request")
    local_queued = record()
    local_queued["settings"]["engine"] = "comfy-local"
    for job in (legacy_queued, legacy_running, local_queued):
        db.enqueue(job, 10)
    db.recover(local_only=True)
    assert db.job(legacy_queued["id"])["status"] == "failed"
    assert db.job(legacy_running["id"])["status"] == "failed"
    assert db.job(local_queued["id"])["status"] == "queued"
    assert db.claim()["id"] == local_queued["id"]
