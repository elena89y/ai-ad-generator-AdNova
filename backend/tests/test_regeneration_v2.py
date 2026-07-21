"""v2 재생성 seed와 결과 파일 고유성 회귀 테스트."""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

from PIL import Image

from app.schemas.ads import ProductInfo, StylePreset
from app.services import generation_service, image_service


def test_style_seeds_use_requested_seed_for_single_generation() -> None:
    assert generation_service._style_seeds(None, 1) == [42]
    assert generation_service._style_seeds(1234, 1) == [1234]
    assert generation_service._style_seeds(123, 3) == [123, 7, 42]


def test_next_seed_retries_when_random_value_matches_previous(monkeypatch) -> None:
    values = iter((42, 99))
    monkeypatch.setattr(generation_service.random, "randint", lambda *_args: next(values))

    assert generation_service._next_seed(42) == 99


def test_seed_tag_keeps_best_of_candidates_separate(tmp_path) -> None:
    base = tmp_path / "input_kontext.png"
    base.write_bytes(b"seed-7")
    first = generation_service._tag_seed_output(str(base), 7)

    base.write_bytes(b"seed-42")
    second = generation_service._tag_seed_output(str(base), 42)

    assert first != second
    assert (tmp_path / "input_kontext_s7.png").read_bytes() == b"seed-7"
    assert (tmp_path / "input_kontext_s42.png").read_bytes() == b"seed-42"


def test_rerun_uses_new_seed_and_unique_output(monkeypatch, tmp_path) -> None:
    processed_dir = tmp_path / "processed"
    results_dir = tmp_path / "results"
    processed_dir.mkdir()
    results_dir.mkdir()
    source = processed_dir / "abc123def456_v2input.png"
    source.write_bytes(b"original")

    monkeypatch.setattr(image_service, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(image_service, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(generation_service, "_next_seed", lambda _prev: 987654)
    monkeypatch.setattr(generation_service, "_platform_copies_safe", lambda *_args: {})

    captured = {}

    def fake_process_ad(image_path, _name, **kwargs):
        captured["input"] = image_path
        captured["seed"] = kwargs["seed"]
        output = results_dir / f"{generation_service.Path(image_path).stem}_kontext.png"
        Image.new("RGB", (64, 64), "white").save(output)
        return SimpleNamespace(
            final_image_path=str(output), seed=kwargs["seed"], copy_text="copy", seconds=1.0
        )

    monkeypatch.setattr(generation_service, "process_ad", fake_process_ad)

    result = generation_service.rerun_v2(
        "abc123def456",
        ProductInfo(name="카페 라떼"),
        StylePreset.MONOTONE,
        prev_seed=42,
    )

    assert result.seed == 987654
    assert captured["seed"] == 987654
    assert "_rerun_" in result.final_image_path
    assert result.final_image_path != str(results_dir / "abc123def456_v2input_kontext.png")
    assert source.is_file()
    assert not generation_service.Path(captured["input"]).exists()


def test_initial_v2_generation_reports_seed_used_by_pipeline(monkeypatch, tmp_path) -> None:
    processed_dir = tmp_path / "processed"
    results_dir = tmp_path / "results"
    processed_dir.mkdir()
    results_dir.mkdir()
    uploaded = tmp_path / "upload.png"
    uploaded.write_bytes(b"input")

    monkeypatch.setattr(image_service, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(image_service, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(
        generation_service.gpt_service,
        "verify_photo_subject",
        lambda *_args: {"match": True, "seen": ""},
    )
    monkeypatch.setattr(generation_service, "_platform_copies_safe", lambda *_args: {})

    captured = {}

    def fake_process_ad(image_path, _name, **kwargs):
        captured["seed"] = kwargs["seed"]
        output = results_dir / "initial.png"
        Image.new("RGB", (64, 64), "white").save(output)
        return SimpleNamespace(
            final_image_path=str(output), seed=kwargs["seed"], copy_text="copy", seconds=1.0
        )

    monkeypatch.setattr(generation_service, "process_ad", fake_process_ad)

    result = generation_service.run_from_upload_v2(
        str(uploaded), ProductInfo(name="카페 라떼"), StylePreset.MONOTONE
    )

    assert captured["seed"] == 42
    assert result.seed == 42


def test_expired_regeneration_input_is_removed(monkeypatch, tmp_path) -> None:
    source = tmp_path / "abc123def456_v2input.png"
    source.write_bytes(b"temporary input")
    expired_at = time.time() - 2
    os.utime(source, (expired_at, expired_at))

    monkeypatch.setattr(image_service, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(generation_service, "TEMP_REGENERATE_TTL_SECONDS", 1)

    generation_service._purge_expired_regeneration_inputs()

    assert not source.exists()
