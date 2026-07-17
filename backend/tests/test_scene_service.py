"""P4D 합성 런타임 회귀 — 담당: 한의정. 실제 rembg/GPU 없이 순수 로직만 검증한다."""
from __future__ import annotations

import json
from types import SimpleNamespace

try:
    # onnxruntime-gpu(CU13) 환경에서는 `import rembg`가 첫 호출 시 모듈 레벨에서 provider를
    # 검사해 torch가 먼저 로드되지 않으면 SystemExit(1)로 죽는다(image_service._get_rembg_session
    # 주석과 동일 함정). 이 테스트 파일이 pytest 세션에서 rembg를 처음 임포트하는 파일일 수
    # 있으므로 여기서도 torch를 먼저 시도해 순서를 보장한다.
    import torch  # noqa: F401
except Exception:
    pass

import numpy as np
import pytest
from PIL import Image

from app.services import scene_plans, scene_service


def _solid_rgba(w=200, h=300, fg_box=(40, 40, 160, 260), rgb=(200, 60, 60)) -> Image.Image:
    """직사각형 하나짜리 합성 전경 — 연결성분 신뢰도 테스트용 단순 픽스처."""
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    x0, y0, x1, y1 = fg_box
    arr[y0:y1, x0:x1] = (*rgb, 255)
    return Image.fromarray(arr, "RGBA")


def test_infer_effects_only_physically_true():
    assert scene_service.infer_effects("iced") == ["ice"]
    assert scene_service.infer_effects("hot") == ["steam"]
    assert scene_service.infer_effects("ambient") == []
    assert scene_service.infer_effects("") == []
    assert scene_service.infer_effects(None) == []


def test_lab_roundtrip_is_near_identity():
    rgb = np.random.default_rng(0).integers(0, 256, size=(16, 16, 3)).astype(np.uint8)
    lab = scene_service._rgb_to_lab(rgb)
    back = scene_service._lab_to_rgb(lab)
    assert np.abs(back - rgb.astype(np.float64)).max() < 1.5  # 부동소수 왕복 오차만 허용


def test_dominant_component_ratio_single_blob_is_high():
    rgba = _solid_rgba()
    alpha = np.asarray(rgba.split()[-1], dtype=np.uint8)
    ratio = scene_service._dominant_component_ratio(alpha)
    assert ratio > 0.95  # 사각형 하나 = 사실상 100% 단일 연결성분


def test_dominant_component_ratio_fragmented_mask_is_low():
    w, h = 200, 200
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    # 서로 떨어진 4개의 작은 블록 — 어느 것도 전체 전경의 85%를 못 채움
    for (x, y) in [(10, 10), (10, 150), (150, 10), (150, 150)]:
        arr[y:y + 30, x:x + 30] = (200, 60, 60, 255)
    rgba = Image.fromarray(arr, "RGBA")
    alpha = np.asarray(rgba.split()[-1], dtype=np.uint8)
    ratio = scene_service._dominant_component_ratio(alpha)
    assert ratio == pytest.approx(0.25, abs=0.05)


def test_cutout_rejects_fragmented_mask(tmp_path, monkeypatch):
    fragmented = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    arr = np.asarray(fragmented).copy()
    for (x, y) in [(10, 10), (10, 150), (150, 10), (150, 150)]:
        arr[y:y + 30, x:x + 30] = (200, 60, 60, 255)
    fragmented = Image.fromarray(arr, "RGBA")

    src = tmp_path / "input.png"
    Image.new("RGB", (200, 200), (5, 5, 5)).save(src)

    # 실제 onnxruntime/rembg 세션 생성을 건너뛴다 — 신뢰도 판정 로직만 검증 대상이고,
    # 운영 환경(onnxruntime-gpu)의 torch 선로드 요구사항에 테스트가 얽매이면 안 된다.
    monkeypatch.setattr(scene_service, "_get_compose_rembg_session", lambda: object())
    import rembg
    monkeypatch.setattr(rembg, "remove", lambda img, session=None: fragmented, raising=False)

    result = scene_service.cutout(str(src))
    assert result["ok"] is False
    assert result["reason"] == "fragmented"


def test_acquire_background_code_mode_uses_scene_render(monkeypatch):
    plan = next(p for p in scene_plans.PLANS if p.render_mode == "code")
    sentinel = Image.new("RGB", (8, 8), (1, 2, 3))
    monkeypatch.setattr(scene_service.scene_render, "render", lambda plan, seed, accent_hue: sentinel)

    result = scene_service.acquire_background(plan, allowed_props=set(), seed=0)
    assert result["ok"] is True
    assert result["image"] is sentinel
    assert result["surface_y"] == plan.surface_y


def test_acquire_background_sdxl_mode_prefers_manifest_surface_y(tmp_path, monkeypatch):
    plan = next(p for p in scene_plans.PLANS
                if p.render_mode != "code" and not p.requires_recompose)
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    img_path = library_dir / "bg.png"
    Image.new("RGB", (8, 8), (9, 9, 9)).save(img_path)

    manifest = tmp_path / "manifest.jsonl"
    entry = {
        "plan": plan.key, "file": "bg.png", "sha256": scene_service._sha256(img_path),
        "version": 1, "props": [], "curated_by": "tester", "surface_y": 0.42,
    }
    manifest.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    monkeypatch.setattr(scene_service, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(scene_service, "LIBRARY_DIR", library_dir)
    monkeypatch.setattr(scene_service, "_manifest_cache", None)

    result = scene_service.acquire_background(plan, allowed_props=set(), seed=0)
    assert result["ok"] is True
    assert result["surface_y"] == 0.42  # 이미지별 오버라이드가 플랜 기본값(surface_y)보다 우선


def test_acquire_background_rejects_sha256_mismatch(tmp_path, monkeypatch):
    plan = next(p for p in scene_plans.PLANS
                if p.render_mode != "code" and not p.requires_recompose)
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    img_path = library_dir / "bg.png"
    Image.new("RGB", (8, 8), (9, 9, 9)).save(img_path)

    manifest = tmp_path / "manifest.jsonl"
    entry = {
        "plan": plan.key, "file": "bg.png", "sha256": "0" * 64,  # 의도적 불일치
        "version": 1, "props": [], "curated_by": "tester", "surface_y": 0.42,
    }
    manifest.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    monkeypatch.setattr(scene_service, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(scene_service, "LIBRARY_DIR", library_dir)
    monkeypatch.setattr(scene_service, "_manifest_cache", None)

    result = scene_service.acquire_background(plan, allowed_props=set(), seed=0)
    assert result == {"ok": False, "reason": "no_bg"}


def test_place_product_bottom_touches_surface_y():
    plan = next(p for p in scene_plans.PLANS if p.render_mode == "code")
    product = Image.new("RGBA", (100, 150), (255, 0, 0, 255))
    canvas_size = (1024, 1024)
    resized, (left, top) = scene_service._place_product(canvas_size, product, plan, surface_y=0.7)
    assert top + resized.height == int(1024 * 0.7)
    assert resized.width == int(1024 * plan.subject_scale)


def test_contact_shadow_fades_to_zero_at_borders():
    """접지 그림자 사각형 버그 회귀(V4P4D-EXP-001 재검증 발견 ③).

    트림된 누끼는 실루엣이 항상 캔버스 가장자리에 닿는다 — 알파가 가득 찬 최악 케이스에서
    블러 여백이 없으면 그림자 네 변이 직선으로 잘려 회색 사각형이 된다. 수정 후에는
    가장자리 알파가 0으로 페이드해야 한다."""
    plan = next(p for p in scene_plans.PLANS if p.render_mode == "code")
    product = Image.new("RGBA", (200, 300), (255, 255, 255, 255))  # 알파 100% = 최악 케이스
    shadow = scene_service._contact_shadow(product, plan)
    assert shadow.width > product.width  # 블러 여백(pad)이 실제로 확보됨
    a = np.asarray(shadow.split()[-1])
    assert a.max() > 0  # 그림자 자체는 존재
    border = np.concatenate([a[0, :], a[-1, :], a[:, 0], a[:, -1]])
    assert border.max() <= 2  # 네 변 모두 사실상 0으로 페이드 (하드엣지 없음)


def test_trim_to_alpha_bbox_removes_rembg_padding():
    """rembg 결과는 원본 사진 크기 그대로라 전경 아래에 투명 여백이 남는다 — 잘라내지
    않으면 배치 시 상품이 접지선 위로 '뜬다'(2026-07-17 VM 실측 재현: 아이스 라떼가 공중부양)."""
    padded = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    arr = np.asarray(padded).copy()
    arr[40:120, 100:200] = (0, 200, 0, 255)  # 전경은 위쪽에만, 아래 180px는 투명 여백
    padded = Image.fromarray(arr, "RGBA")

    trimmed = scene_service._trim_to_alpha_bbox(padded)
    assert trimmed.size == (100, 80)  # (200-100, 120-40)

    plan = next(p for p in scene_plans.PLANS if p.render_mode == "code")
    _, (_, top_padded) = scene_service._place_product((1024, 1024), padded, plan, surface_y=0.7)
    _, (_, top_trimmed) = scene_service._place_product((1024, 1024), trimmed, plan, surface_y=0.7)
    assert top_trimmed > top_padded  # 트림 후에는 상품이 접지선에 더 가깝게(아래로) 내려온다


def test_harmonize_color_preserves_alpha_and_caps_delta_e():
    product = Image.new("RGBA", (40, 40), (220, 40, 40, 255))
    bg = Image.new("RGB", (200, 200), (20, 60, 120))  # 강한 색온도 차이
    harmonized, applied_delta_e = scene_service._harmonize_color(product, bg, (10, 10))
    assert 0.0 < applied_delta_e <= 6.0  # 반환 ΔE도 상한 준수(P6B 게이트 입력)
    orig_alpha = np.asarray(product.split()[-1])
    new_alpha = np.asarray(harmonized.split()[-1])
    assert np.array_equal(orig_alpha, new_alpha)  # 알파(형태)는 절대 불변

    prod_lab = scene_service._rgb_to_lab(np.asarray(product.convert("RGB")))
    harm_lab = scene_service._rgb_to_lab(np.asarray(harmonized.convert("RGB")))
    da = float(np.mean(harm_lab[..., 1]) - np.mean(prod_lab[..., 1]))
    db = float(np.mean(harm_lab[..., 2]) - np.mean(prod_lab[..., 2]))
    assert (da ** 2 + db ** 2) ** 0.5 <= 6.05  # ΔE 상한(부동소수 여유)
    # L(밝기) 채널은 손대지 않는다
    dl = float(np.mean(harm_lab[..., 0]) - np.mean(prod_lab[..., 0]))
    assert abs(dl) < 0.5


def test_compose_scene_end_to_end_with_code_plan(tmp_path, monkeypatch):
    """cutout만 모킹하고 나머지(배경 획득~합성~저장)는 실제 코드를 그대로 통과시킨다."""
    plan = next(p for p in scene_plans.PLANS
                if p.render_mode == "code" and p.style != "monotone")
    cutout_rgba = Image.new("RGBA", (120, 160), (255, 255, 255, 0))
    arr = np.asarray(cutout_rgba).copy()
    arr[20:140, 20:100] = (200, 80, 40, 255)
    cutout_rgba = Image.fromarray(arr, "RGBA")

    monkeypatch.setattr(scene_service, "cutout",
                        lambda path: {"ok": True, "rgba": cutout_rgba, "stats": {}})

    analysis = SimpleNamespace(
        view_angle="eye", temperature="ambient", core_ingredients=[], material="matte",
    )
    src = tmp_path / "input.png"
    Image.new("RGB", (100, 100), (10, 10, 10)).save(src)

    result = scene_service.compose_scene(
        str(src), analysis, plan.style, plan.domain, seed=0, output_dir=str(tmp_path / "out"),
    )
    assert result["ok"] is True
    assert result["plan"] == plan.key
    assert result["text_zone"] == plan.text_zone
    from pathlib import Path
    assert Path(result["path"]).is_file()
