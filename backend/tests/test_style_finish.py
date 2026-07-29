"""Phase 3 결정론적 스타일 마감 테스트."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from app.services import style_finish


def _fixture(path: Path) -> str:
    width = height = 160
    yy, xx = np.mgrid[0:height, 0:width]
    hue = xx / width
    sat = np.full_like(hue, 0.55)
    val = 0.35 + 0.6 * (yy / height)
    hsv = np.stack((hue, sat, val), axis=-1)
    rgb = style_finish._hsv_to_rgb(hsv)

    # 중앙 상품 영역은 색 통계와 보호 효과를 구분할 수 있도록 녹색 사각형으로 둔다.
    rgb[48:112, 52:108] = np.array([0.12, 0.64, 0.28], dtype=np.float32)
    Image.fromarray((rgb * 255).astype(np.uint8), mode="RGB").save(path)
    return str(path)


def test_six_styles_create_outputs_and_expected_statistics(tmp_path: Path) -> None:
    source = _fixture(tmp_path / "source.png")
    original = style_finish.style_stats(source)
    results = {}

    for style in (
        "editorial", "pop", "realism", "pastel_float", "monotone", "warm_vintage",
    ):
        output = style_finish.apply(source, style, strength=0.6)
        assert output != source
        assert Path(output).exists()
        renamed = tmp_path / f"{style}.png"
        Path(output).replace(renamed)
        results[style] = style_finish.style_stats(str(renamed))

    assert results["monotone"]["hue_concentration"] > original["hue_concentration"]
    assert results["pop"]["mean_sat"] > original["mean_sat"]
    assert results["warm_vintage"]["warmth"] > original["warmth"]


def test_zero_strength_is_pixel_identical(tmp_path: Path) -> None:
    source = _fixture(tmp_path / "source.png")
    output = style_finish.apply(source, "pop", strength=0)

    assert output == source
    assert np.array_equal(np.asarray(Image.open(source)), np.asarray(Image.open(output)))


def test_central_product_changes_less_than_background(tmp_path: Path) -> None:
    source = _fixture(tmp_path / "source.png")
    output = style_finish.apply(source, "monotone", strength=0.8)
    before = np.asarray(Image.open(source), dtype=np.float32)
    after = np.asarray(Image.open(output), dtype=np.float32)
    delta = np.abs(after - before).mean(axis=2)

    center_delta = float(delta[60:100, 64:96].mean())
    border = np.concatenate((delta[:30].ravel(), delta[-30:].ravel()))
    assert center_delta < float(border.mean()) * 0.55


def test_explicit_mask_protects_product_more_than_fallback(tmp_path: Path) -> None:
    source = _fixture(tmp_path / "source.png")
    mask = np.zeros((160, 160), dtype=np.uint8)
    mask[48:112, 52:108] = 255
    mask_path = tmp_path / "mask.png"
    Image.fromarray(mask, mode="L").save(mask_path)

    fallback = style_finish.apply(source, "pop", strength=0.8)
    fallback_pixels = np.asarray(Image.open(fallback), dtype=np.float32).copy()
    Path(fallback).unlink()
    masked = style_finish.apply(source, "pop", mask_path=str(mask_path), strength=0.8)
    source_pixels = np.asarray(Image.open(source), dtype=np.float32)
    masked_pixels = np.asarray(Image.open(masked), dtype=np.float32)

    region = np.s_[48:112, 52:108]
    fallback_delta = np.abs(fallback_pixels[region] - source_pixels[region]).mean()
    masked_delta = np.abs(masked_pixels[region] - source_pixels[region]).mean()
    assert masked_delta < fallback_delta


def test_unknown_style_is_noop(tmp_path: Path) -> None:
    source = _fixture(tmp_path / "source.png")
    assert style_finish.apply(source, "cross_section") == source


def test_process_ad_applies_finish_between_select_and_copy(tmp_path: Path, monkeypatch) -> None:
    from app.services import generation_service, gpt_service, style_gen

    events = []

    class FakeRun:
        @contextmanager
        def stage(self, name):
            events.append(name)
            yield

    source = _fixture(tmp_path / "source.png")
    generated = _fixture(tmp_path / "generated.png")
    finished = tmp_path / "generated_finish.png"

    monkeypatch.setenv("STYLE_FINISH", "1")
    monkeypatch.setenv("STYLE_FINISH_STRENGTH", "0.45")
    monkeypatch.setattr(
        gpt_service, "analyze_menu",
        lambda _name: SimpleNamespace(subject_en="cafe latte", domain="food", food_mode="cafe"),
    )
    monkeypatch.setattr(style_gen, "generate_scene", lambda *_args, **_kwargs: generated)

    def fake_finish(path, style_key, strength):
        assert path.endswith("_s42.png")
        assert style_key == "monotone"
        assert strength == 0.45
        finished.write_bytes(Path(path).read_bytes())
        return str(finished)

    monkeypatch.setattr(style_finish, "apply", fake_finish)
    monkeypatch.setattr(
        generation_service, "_generate_copy",
        lambda path, *_args, **_kwargs: (
            events.append(f"copy:{Path(path).name}")
            or SimpleNamespace(copy_text="headline\nsubcopy")
        ),
    )

    result = generation_service.process_ad(
        source, "카페라떼", style="monotone", poster=False,
        output_dir=str(tmp_path), seed=42, log=False, _run=FakeRun(),
    )

    assert result.final_image_path == str(finished)
    assert events == [
        "analysis", "generate", "select", "style_finish", "copy", "copy:generated_finish.png",
    ]
