import asyncio
import io
import threading

import pytest
from fastapi import HTTPException, UploadFile

from app import generation_app
from app.schemas.ads import StylePreset
from app.services import generation_client


@pytest.fixture(autouse=True)
def reset_worker_state(monkeypatch):
    monkeypatch.setattr(generation_app, "_GPU_LOCK", threading.Lock())
    generation_app._STATE.update(status="starting", error=None)


def test_preload_marks_worker_ready(monkeypatch):
    called = []
    monkeypatch.setattr(generation_app.kontext_service, "preload", lambda: called.append(True))

    generation_app._preload()

    assert called == [True]
    assert generation_app._STATE == {"status": "ready", "error": None}


def test_preload_records_error_and_reraises(monkeypatch):
    def fail():
        raise RuntimeError("load failed")

    monkeypatch.setattr(generation_app.kontext_service, "preload", fail)

    with pytest.raises(RuntimeError, match="load failed"):
        generation_app._preload()

    assert generation_app._STATE == {"status": "error", "error": "RuntimeError"}


def test_lifespan_can_skip_preload(monkeypatch):
    monkeypatch.setenv("PRELOAD_KONTEXT", "0")
    monkeypatch.setattr(generation_app, "shutdown_langfuse", lambda: None)

    async def exercise():
        async with generation_app.lifespan(generation_app.app):
            assert generation_app._STATE["status"] == "ready"

    asyncio.run(exercise())


def test_gpu_slot_rejects_unready_worker():
    generation_app._STATE["status"] = "loading"

    with pytest.raises(HTTPException) as exc_info:
        with generation_app._gpu_slot():
            pass

    assert exc_info.value.status_code == 503


def test_gpu_slot_times_out_when_busy(monkeypatch):
    generation_app._STATE["status"] = "ready"
    monkeypatch.setenv("GPU_QUEUE_TIMEOUT", "0")
    generation_app._GPU_LOCK.acquire()
    try:
        with pytest.raises(HTTPException) as exc_info:
            with generation_app._gpu_slot():
                pass
    finally:
        generation_app._GPU_LOCK.release()

    assert exc_info.value.status_code == 503
    assert "GPU busy" in exc_info.value.detail


def test_generate_releases_gpu_lock_after_failure(tmp_path, monkeypatch):
    generation_app._STATE["status"] = "ready"
    monkeypatch.setattr(generation_app, "UPLOAD_DIR", tmp_path)

    def fail(*_args, **_kwargs):
        raise RuntimeError("generation failed")

    monkeypatch.setattr(generation_app.generation_service, "run_from_upload_v2", fail)
    upload = UploadFile(filename="latte.png", file=io.BytesIO(b"image"))

    with pytest.raises(HTTPException) as exc_info:
        generation_app.generate(
            upload, "카페라떼", "", StylePreset.MONOTONE, False, False, 42,
        )

    assert exc_info.value.status_code == 500
    assert generation_app._GPU_LOCK.locked() is False


def test_health_reports_ready_and_busy():
    generation_app._STATE["status"] = "ready"
    generation_app._GPU_LOCK.acquire()
    try:
        body = generation_app.health()
    finally:
        generation_app._GPU_LOCK.release()

    assert body["status"] == "ok"
    assert body["worker"] == "ready"
    assert body["busy"] is True


def test_generation_client_enforces_300_second_minimum(monkeypatch):
    monkeypatch.setattr(generation_client.settings, "GENERATION_TIMEOUT_S", 180)
    assert generation_client._request_timeout() == 300

    monkeypatch.setattr(generation_client.settings, "GENERATION_TIMEOUT_S", 420)
    assert generation_client._request_timeout() == 420
