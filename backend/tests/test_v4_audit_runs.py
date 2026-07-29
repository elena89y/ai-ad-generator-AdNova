"""P6A 오프라인 audit 배치 회귀 — 담당: 한의정. 무거운 지표 모델 없이 순수 로직만 검증."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from scripts import v4_audit_runs as audit


# --- OCR 보존율 --------------------------------------------------------------------
def test_ocr_preservation_none_when_input_has_no_text():
    assert audit.ocr_preservation([], ["anything"]) is None
    assert audit.ocr_preservation(["x"], []) is None  # 1글자 노이즈는 채점 대상 아님


def test_ocr_preservation_normalizes_case_space_punct():
    assert audit.ocr_preservation(["Coca-Cola"], ["COCA COLA zero"]) == 1.0
    assert audit.ocr_preservation(["말차 라떼"], ["말차라떼 500ml"]) == 1.0


def test_ocr_preservation_partial_loss():
    got = audit.ocr_preservation(["BrandName", "Vitamin C"], ["brandname only"])
    assert got == 0.5


# --- ΔE ------------------------------------------------------------------------
def test_product_delta_e_zero_for_identical_and_positive_for_shifted():
    base = Image.fromarray(
        np.full((64, 64, 3), (180, 120, 90), dtype=np.uint8), "RGB")
    shifted = Image.fromarray(
        np.full((64, 64, 3), (150, 140, 120), dtype=np.uint8), "RGB")
    assert audit.product_delta_e(base, base) == pytest.approx(0.0, abs=0.01)
    assert audit.product_delta_e(base, shifted) > 5.0


# --- runs.jsonl 선별 ------------------------------------------------------------
def test_select_runs_filters_existing_files_and_phase(tmp_path):
    img = tmp_path / "a.png"
    Image.new("RGB", (4, 4)).save(img)
    rows = [
        {"run_id": "old", "phase": "V3P1", "input": str(img), "output": str(img)},
        {"run_id": "missing", "phase": "V4P4A", "input": str(img),
         "output": str(tmp_path / "nope.png")},
        {"run_id": "no_output", "phase": "V4P4A", "input": str(img), "output": None},
        {"run_id": "good", "phase": "V4P4A", "input": str(img), "output": str(img)},
    ]
    runs = tmp_path / "runs.jsonl"
    runs.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\ngarbage-line\n", encoding="utf-8")

    picked = audit._select_runs(runs, limit=10, phase_prefix="V4")
    assert [r["run_id"] for r in picked] == ["good"]

    picked_all = audit._select_runs(runs, limit=10)
    assert [r["run_id"] for r in picked_all] == ["good", "old"]  # 최신부터

    assert audit._select_runs(tmp_path / "absent.jsonl", limit=5) == []


def test_select_runs_respects_limit(tmp_path):
    img = tmp_path / "a.png"
    Image.new("RGB", (4, 4)).save(img)
    rows = [{"run_id": f"r{i}", "phase": "V4", "input": str(img), "output": str(img)}
            for i in range(10)]
    runs = tmp_path / "runs.jsonl"
    runs.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    picked = audit._select_runs(runs, limit=3)
    assert [r["run_id"] for r in picked] == ["r9", "r8", "r7"]


# --- audit_run 실패 격리 -----------------------------------------------------------
def test_audit_run_isolates_metric_failures(tmp_path, monkeypatch):
    """지표 하나가 죽어도 나머지는 기록된다(metrics.py None 규약)."""
    img = tmp_path / "img.png"
    Image.new("RGB", (32, 32), (200, 100, 50)).save(img)
    row = {"run_id": "r1", "phase": "V4P4D", "engine": "scene:pop/object/color_block",
           "input": str(img), "output": str(img)}

    crop = Image.new("RGB", (16, 16), (200, 100, 50))
    monkeypatch.setattr(audit, "_subject_crop", lambda path: crop)
    monkeypatch.setattr(
        audit, "_ocr_texts",
        lambda path: (_ for _ in ()).throw(RuntimeError("easyocr not installed")),
    )
    fake_metrics = SimpleNamespace(
        identity_dino=lambda a, b: 0.97, identity_lpips=lambda a, b: 0.05)
    # `from app.harness import metrics`는 이미 임포트된 패키지 속성을 우선 반환하므로
    # sys.modules와 패키지 속성 둘 다 패치해야 실제 DINO 로드(다운로드)를 확실히 차단한다.
    import app.harness as harness_pkg
    monkeypatch.setitem(sys.modules, "app.harness.metrics", fake_metrics)
    monkeypatch.setattr(harness_pkg, "metrics", fake_metrics, raising=False)

    entry = audit.audit_run(row, tmp_path)

    assert entry["run_id"] == "r1"
    assert entry["identity_dino"] == 0.97
    assert entry["identity_lpips"] == 0.05
    assert entry["product_delta_e"] == pytest.approx(0.0, abs=0.01)
    assert entry["ocr_preservation"] is None       # OCR 실패 → None, 크래시 없음
    assert entry["style_stats"] is not None        # style_stats는 정상 기록


def test_audit_run_survives_crop_failure(tmp_path, monkeypatch):
    img = tmp_path / "img.png"
    Image.new("RGB", (32, 32)).save(img)
    row = {"run_id": "r2", "input": str(img), "output": str(img)}
    monkeypatch.setattr(
        audit, "_subject_crop",
        lambda path: (_ for _ in ()).throw(RuntimeError("rembg down")),
    )
    monkeypatch.setattr(audit, "_ocr_texts", lambda path: [])

    entry = audit.audit_run(row, tmp_path)
    assert entry["identity_dino"] is None
    assert entry["product_delta_e"] is None
    assert entry["ocr_preservation"] is None


# --- CPU reader 헬퍼 (D-7) ----------------------------------------------------------
def test_get_reader_cpu_is_separate_singleton_with_gpu_false(monkeypatch):
    from app.harness import text_clean

    created = []

    class FakeReader:
        def __init__(self, langs, gpu, verbose):
            created.append({"langs": langs, "gpu": gpu})

    monkeypatch.setitem(sys.modules, "easyocr", SimpleNamespace(Reader=FakeReader))
    monkeypatch.setattr(text_clean, "_reader", None)
    monkeypatch.setattr(text_clean, "_reader_cpu", None)

    r1 = text_clean.get_reader_cpu()
    r2 = text_clean.get_reader_cpu()
    assert r1 is r2                                  # 싱글턴
    assert created == [{"langs": ["ko", "en"], "gpu": False}]
    assert text_clean._reader is None                # 원본 GPU reader는 건드리지 않는다


def test_reader_cpu_module_forces_cpu_env():
    """스크립트 import 만으로 CPU 강제 env가 걸린다(워커 밖 CPU 계약)."""
    import os
    assert os.environ.get("COMPOSE_REMBG_CUDA") == "0"


# --- summary 백분위 ----------------------------------------------------------------
def test_percentile_basic():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert audit._percentile(vals, 0.0) == 1.0
    assert audit._percentile(vals, 0.5) == 3.0
    assert audit._percentile(vals, 1.0) == 5.0
