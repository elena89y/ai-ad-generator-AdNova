"""P4D 4D-1 GPU 락 재설계 회귀 — 담당: 한의정.

락이 kontext_service 모듈 전역으로 이동했는지(엔드포인트 래핑 제거)와 직렬화·타임아웃
동작을 확인한다. 실제 Kontext 파이프라인(torch/diffusers)은 로드하지 않는다.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.services import kontext_service


@pytest.fixture(autouse=True)
def _fresh_lock(monkeypatch):
    """테스트 간 락 상태 격리."""
    monkeypatch.setattr(kontext_service, "_GPU_LOCK", threading.Lock())


def test_acquire_gpu_serializes_concurrent_callers():
    order = []

    def worker(tag):
        with kontext_service.acquire_gpu(timeout=5):
            order.append(f"{tag}-start")
            time.sleep(0.05)
            order.append(f"{tag}-end")

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    time.sleep(0.01)  # a가 먼저 락을 잡도록
    t2.start()
    t1.join()
    t2.join()

    # 두 작업이 겹치지 않는다 — a의 end가 b의 start보다 먼저 와야 함
    assert order == ["a-start", "a-end", "b-start", "b-end"]


def test_acquire_gpu_raises_gpu_busy_on_timeout():
    kontext_service._GPU_LOCK.acquire()
    try:
        with pytest.raises(kontext_service.GpuBusyError):
            with kontext_service.acquire_gpu(timeout=0.05):
                pass  # pragma: no cover
    finally:
        kontext_service._GPU_LOCK.release()


def test_acquire_gpu_releases_lock_on_exception():
    with pytest.raises(RuntimeError):
        with kontext_service.acquire_gpu(timeout=1):
            raise RuntimeError("boom")
    assert not kontext_service._GPU_LOCK.locked()


def test_generation_app_no_longer_owns_the_lock():
    """4D-1: 락이 엔드포인트 래핑(_gpu_slot)에서 kontext_service로 이동했다."""
    import app.generation_app as generation_app

    assert not hasattr(generation_app, "_gpu_slot")
    assert not hasattr(generation_app, "_GPU_LOCK")
    assert generation_app.kontext_service._GPU_LOCK is kontext_service._GPU_LOCK
