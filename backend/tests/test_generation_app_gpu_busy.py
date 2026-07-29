"""P4D 4D-1 — generation_app이 GpuBusyError를 503으로 매핑하는지 회귀 — 담당: 한의정."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

import app.generation_app as generation_app
from app.services import kontext_service


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(generation_app._STATE, "status", "ready")
    return TestClient(generation_app.app)


def _upload():
    return {"image": ("p.png", io.BytesIO(b"fake"), "image/png")}


def test_generate_maps_gpu_busy_to_503(client, monkeypatch):
    def _raise(*a, **kw):
        raise kontext_service.GpuBusyError("busy")

    monkeypatch.setattr(generation_app.generation_service, "run_from_upload_v2", _raise)

    resp = client.post(
        "/generate",
        data={"product_name": "테스트", "style": "editorial"},
        files=_upload(),
    )
    assert resp.status_code == 503
    assert "GPU busy" in resp.json()["detail"]


def test_generate_returns_503_when_worker_not_ready(client, monkeypatch):
    monkeypatch.setitem(generation_app._STATE, "status", "loading")

    resp = client.post(
        "/generate",
        data={"product_name": "테스트", "style": "editorial"},
        files=_upload(),
    )
    assert resp.status_code == 503
    assert "not ready" in resp.json()["detail"]


def test_health_busy_reflects_kontext_gpu_lock(client):
    kontext_service._GPU_LOCK.acquire()
    try:
        resp = client.get("/health")
        assert resp.json()["busy"] is True
    finally:
        kontext_service._GPU_LOCK.release()
