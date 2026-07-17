"""장면 합성 런타임 — 담당: 한의정. DIRECTION_v4 P4D.

실물 상품 픽셀을 배경(Tier1 코드 렌더 | Tier2 채택 사진)에 결정론적으로 배치하고
접지 그림자·색 조화·리플렉션을 더해 광고 장면을 만든다. Kontext(생성 모델) 대신
픽셀 합성이므로 브랜드 정체성 왜곡이 구조적으로 불가능하다 — 정직성 경계는 색
조화(⑥)를 ΔE≤6·L채널 불변으로 제한하는 것으로 지킨다.

GPU 락 없음: 이 모듈은 CPU만 쓴다(COMPOSE_REMBG_CUDA=1 게이트 통과 시 CUDA 누끼는
쓰되 Kontext GPU 락(kontext_service._GPU_LOCK)과는 별개 — D-10). 신규 의존성 금지
원칙(scene_render.py와 동일)을 지켜 PIL+NumPy만 사용한다(LAB 변환·연결성분도 직접
구현, scipy/scikit-image 미사용).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter

from . import scene_plans, scene_render

logger = logging.getLogger(__name__)

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "assets" / "scene_library_manifest.jsonl"
LIBRARY_DIR = Path(os.environ.get("SCENE_LIBRARY_DIR", "/opt/adnova/models/scene_library"))

# 누끼 신뢰도(2차 안전망 — 1차 판정은 Vision opacity, generation_service._compose_eligible)
_MIN_FG_RATIO = 0.05
_MAX_FG_RATIO = 0.70
_MIN_DOMINANT_COMPONENT_RATIO = 0.85  # 연결성분 1개 규칙 폐기(#4) — 분리 뚜껑·빨대 허용

_rembg_session = None
_manifest_cache: Optional[list[dict]] = None


# --- 누끼(cutout) --------------------------------------------------------------
def _get_compose_rembg_session():  # noqa: ANN202
    """합성 전용 rembg 세션. image_service의 GPU 세션과 분리(4D-2) — 워커 VRAM 영향 0이 기본값."""
    global _rembg_session
    if _rembg_session is not None:
        return _rembg_session
    try:
        import torch  # noqa: F401
    except Exception:
        pass

    providers = ["CPUExecutionProvider"]
    if os.environ.get("COMPOSE_REMBG_CUDA", "1") == "1":
        try:
            import onnxruntime

            if hasattr(onnxruntime, "preload_dlls"):
                onnxruntime.preload_dlls()
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        except Exception:
            pass  # CPU 전용 환경 — providers 는 CPU 유지

    from rembg import new_session

    _rembg_session = new_session("birefnet-general", providers=providers)
    logger.info("compose rembg 세션 초기화 (providers=%s)", providers)
    return _rembg_session


def _dominant_component_ratio(alpha: np.ndarray, threshold: int = 16, max_dim: int = 160) -> float:
    """전경 마스크의 최대 4-연결 성분 면적 / 전체 전경 면적. scipy 없이 다운샘플+BFS로 계산."""
    mask = alpha > threshold
    total = int(mask.sum())
    if total == 0:
        return 0.0
    h, w = mask.shape
    scale = max_dim / max(h, w)
    if scale < 1.0:
        small = np.asarray(
            Image.fromarray((mask.astype(np.uint8) * 255)).resize(
                (max(1, int(w * scale)), max(1, int(h * scale))), Image.NEAREST
            )
        ) > 127
    else:
        small = mask
    sh, sw = small.shape
    visited = np.zeros_like(small, dtype=bool)
    best = 0
    for sy in range(sh):
        for sx in range(sw):
            if small[sy, sx] and not visited[sy, sx]:
                stack = [(sy, sx)]
                visited[sy, sx] = True
                size = 0
                while stack:
                    y, x = stack.pop()
                    size += 1
                    for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                        if 0 <= ny < sh and 0 <= nx < sw and small[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            stack.append((ny, nx))
                best = max(best, size)
    denom = int(small.sum())
    return best / denom if denom else 0.0


def cutout(image_path: str) -> dict:
    """CPU(또는 게이트 통과 CUDA) rembg 누끼. 신뢰도 미달이면 ok=False(호출부 폴백)."""
    # ⚠️ 순서 고정: 세션 초기화(내부에서 torch 선로드)가 `from rembg import remove`보다
    #   먼저여야 한다 — 반대 순서면 onnxruntime이 CUDA 런타임 RPATH 없이 먼저 임포트되어
    #   libcudart.so.13 로드 실패로 CPU 백엔드까지 통째로 사라진다(image_service와 동일 함정).
    session = _get_compose_rembg_session()
    from rembg import remove

    img = Image.open(image_path).convert("RGB")
    try:
        rgba = remove(img, session=session)
    except Exception as exc:
        logger.warning("compose cutout 실패: %s", exc)
        return {"ok": False, "reason": "cutout_error"}

    alpha = np.asarray(rgba.split()[-1], dtype=np.uint8)
    fg_ratio = float((alpha > 16).sum()) / alpha.size
    if not (_MIN_FG_RATIO <= fg_ratio <= _MAX_FG_RATIO):
        return {"ok": False, "reason": "fg_ratio", "stats": {"fg_ratio": fg_ratio}}

    dominant_ratio = _dominant_component_ratio(alpha)
    if dominant_ratio < _MIN_DOMINANT_COMPONENT_RATIO:
        return {"ok": False, "reason": "fragmented", "stats": {"dominant_ratio": dominant_ratio}}

    edge = alpha[(alpha > 8) & (alpha < 247)]
    if edge.size == 0:
        return {"ok": False, "reason": "hard_edge", "stats": {"fg_ratio": fg_ratio}}

    return {
        "ok": True, "rgba": rgba,
        "stats": {"fg_ratio": round(fg_ratio, 4), "dominant_ratio": round(dominant_ratio, 4)},
    }


def _dominant_hue(rgba: Image.Image) -> float:
    """전경 픽셀 평균 색상(HSV hue, 0~360). monotone accent_hue 산출용(추가 비용 ~0)."""
    arr = np.asarray(rgba)
    alpha = arr[..., 3]
    mask = alpha > 32
    if not mask.any():
        return 0.0
    hsv = np.asarray(rgba.convert("RGB").convert("HSV"))
    return float(np.mean(hsv[..., 0][mask])) / 255.0 * 360.0


# --- 배경 소싱(D-1') -----------------------------------------------------------
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> list[dict]:
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    entries: list[dict] = []
    if MANIFEST_PATH.is_file():
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
    _manifest_cache = entries
    return entries


def _select_manifest_entry(plan: scene_plans.ScenePlan, allowed_props: set[str],
                           seed: int) -> Optional[dict]:
    """plan.key 매니페스트 항목 중 sha256 검증 통과 + props ⊆ allowed_props 인 것을 시드로 로테이션."""
    verified = []
    for entry in _load_manifest():
        if entry.get("plan") != plan.key:
            continue
        path = LIBRARY_DIR / str(entry.get("file", ""))
        if not path.is_file() or _sha256(path) != entry.get("sha256"):
            logger.warning("scene_library 항목 무효(파일 없음/sha256 불일치): %s", entry.get("file"))
            continue
        if set(entry.get("props") or []) <= allowed_props:
            verified.append(entry)
    if not verified:
        return None
    return verified[seed % len(verified)]


def acquire_background(plan: scene_plans.ScenePlan, allowed_props: set[str], seed: int,
                       accent_hue: float = 0.0) -> dict:
    """D-1'. code 플랜은 즉시 렌더, sdxl(Tier2) 플랜은 매니페스트에서 검증된 판을 로드."""
    if plan.render_mode == "code":
        bg = scene_render.render(plan, seed=seed, accent_hue=accent_hue)
        return {"ok": True, "image": bg, "surface_y": plan.surface_y}

    entry = _select_manifest_entry(plan, allowed_props, seed)
    if entry is None:
        return {"ok": False, "reason": "no_bg"}
    path = LIBRARY_DIR / str(entry["file"])
    bg = Image.open(path).convert("RGB")
    surface_y = float(entry.get("surface_y", plan.surface_y))  # 이미지별 실측 오버라이드 우선(S-0#4)
    return {"ok": True, "image": bg, "surface_y": surface_y}


# --- 합성 알고리즘 ④~⑦ ----------------------------------------------------------
def _place_product(bg_size: tuple[int, int], product_rgba: Image.Image,
                   plan: scene_plans.ScenePlan, surface_y: float) -> tuple[Image.Image, tuple[int, int]]:
    """④ 배치: 폭→subject_scale, bbox 하단→surface_y."""
    canvas_w, canvas_h = bg_size
    target_w = max(1, int(canvas_w * plan.subject_scale))
    scale = target_w / product_rgba.width
    target_h = max(1, int(round(product_rgba.height * scale)))
    resized = product_rgba.resize((target_w, target_h), Image.LANCZOS)
    cx = int(canvas_w * plan.subject_pos[0])
    surface_y_px = int(canvas_h * surface_y)
    left = cx - target_w // 2
    top = surface_y_px - target_h
    return resized, (left, top)


def _contact_shadow(product_rgba: Image.Image, plan: scene_plans.ScenePlan) -> Image.Image:
    """⑤ 접지 그림자: 실루엣 세로 12% 압축 + GaussianBlur(r=폭*0.05), 불투명도 shadow_strength."""
    w, h = product_rgba.size
    squashed_h = max(1, int(h * 0.12))
    alpha = product_rgba.split()[-1].resize((w, squashed_h), Image.LANCZOS)
    blur_radius = max(1, int(w * 0.05))
    alpha = alpha.filter(ImageFilter.GaussianBlur(blur_radius))
    arr = (np.asarray(alpha, dtype=np.float32) * plan.shadow_strength).clip(0, 255).astype(np.uint8)
    shadow = Image.new("RGBA", (w, squashed_h), (12, 10, 8, 0))
    shadow.putalpha(Image.fromarray(arr))
    return shadow


# --- LAB 변환 (신규 의존성 금지 — scikit-image 대신 numpy로 직접 구현) -----------------
_M_RGB2XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
], dtype=np.float64)
_M_XYZ2RGB = np.linalg.inv(_M_RGB2XYZ)
_D65_WHITE = np.array([0.95047, 1.0, 1.08883], dtype=np.float64)


def _srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * (c ** (1 / 2.4)) - 0.055)


def _rgb_to_lab(rgb_uint8: np.ndarray) -> np.ndarray:
    lin = _srgb_to_linear(rgb_uint8.astype(np.float64))
    xyz = lin @ _M_RGB2XYZ.T / _D65_WHITE
    delta = 6.0 / 29.0
    f = np.where(xyz > delta ** 3, np.cbrt(xyz), xyz / (3 * delta ** 2) + 4.0 / 29.0)
    fx, fy, fz = f[..., 0], f[..., 1], f[..., 2]
    lab = np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=-1)
    return lab


def _lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200
    delta = 6.0 / 29.0

    def _finv(t: np.ndarray) -> np.ndarray:
        return np.where(t > delta, t ** 3, 3 * delta ** 2 * (t - 4.0 / 29.0))

    xyz = np.stack([_finv(fx), _finv(fy), _finv(fz)], axis=-1) * _D65_WHITE
    lin = xyz @ _M_XYZ2RGB.T
    srgb = _linear_to_srgb(lin)
    return np.clip(srgb * 255.0, 0, 255)


def _harmonize_color(product_rgba: Image.Image, bg: Image.Image, place_xy: tuple[int, int],
                     delta_e_cap: float = 6.0) -> Image.Image:
    """⑥ 색 조화: 제품 LAB a·b 채널만 배경 색온도로 보정. L·디테일 불변. ΔE≤cap. 경계 2px feather."""
    w, h = product_rgba.size
    canvas_w, canvas_h = bg.size
    left, top = place_xy
    crop_box = (
        max(0, left), max(0, top),
        min(canvas_w, left + w), min(canvas_h, top + h),
    )
    if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
        return product_rgba
    bg_crop = bg.crop(crop_box).convert("RGB").resize((w, h))

    product_rgb = np.asarray(product_rgba.convert("RGB"))
    bg_rgb = np.asarray(bg_crop)

    product_lab = _rgb_to_lab(product_rgb)
    bg_lab = _rgb_to_lab(bg_rgb)

    shift_a = float(np.mean(bg_lab[..., 1]) - np.mean(product_lab[..., 1])) * 0.3
    shift_b = float(np.mean(bg_lab[..., 2]) - np.mean(product_lab[..., 2])) * 0.3
    delta_e = float(np.sqrt(shift_a ** 2 + shift_b ** 2))
    if delta_e > delta_e_cap:
        scale = delta_e_cap / delta_e
        shift_a *= scale
        shift_b *= scale

    out_lab = product_lab.copy()
    out_lab[..., 1] += shift_a
    out_lab[..., 2] += shift_b
    harmonized_rgb = _lab_to_rgb(out_lab).astype(np.uint8)

    alpha = np.asarray(product_rgba.split()[-1], dtype=np.float32) / 255.0
    # 경계 2px feather: 조화 강도를 alpha 자체로 가중(내부는 완전 적용, 경계는 원본과 블렌드)
    feathered = alpha
    blended = (
        product_rgb.astype(np.float32) * (1 - feathered[..., None])
        + harmonized_rgb.astype(np.float32) * feathered[..., None]
    ).clip(0, 255).astype(np.uint8)

    out = Image.fromarray(blended, "RGB").convert("RGBA")
    out.putalpha(Image.fromarray((alpha * 255).astype(np.uint8)))
    return out


def _reflection(product_rgba: Image.Image, strength: float) -> Image.Image:
    """⑦ 하단 15% 수직반전 리플렉션 — 아래로 갈수록 옅어지는 선형 감쇠(0~strength)."""
    w, h = product_rgba.size
    slice_h = max(1, int(h * 0.15))
    bottom = product_rgba.crop((0, h - slice_h, w, h)).transpose(Image.FLIP_TOP_BOTTOM)
    fade = np.linspace(strength, 0.0, slice_h, dtype=np.float32)[:, None]
    alpha = (np.asarray(bottom.split()[-1], dtype=np.float32) * fade).clip(0, 255).astype(np.uint8)
    bottom.putalpha(Image.fromarray(alpha))
    return bottom


def infer_effects(temperature: str) -> list[str]:
    """iced→["ice"] / hot→["steam"] / ambient→[]. 물리적으로 참인 효과만(정직성 경계)."""
    t = (temperature or "").strip().lower()
    if t == "iced":
        return ["ice"]
    if t == "hot":
        return ["steam"]
    return []


def _pick_plan(style: str, domain: str, seed: int, view_angle: str) -> Optional[scene_plans.ScenePlan]:
    """① view_angle 일치 플랜 우선(현재 전 플랜 view_angle="eye" 고정이라 사실상 항상 일치)."""
    cands = scene_plans.plans_for(style, domain)
    matching = [p for p in cands if p.view_angle == view_angle] or cands
    if not matching:
        return None
    return matching[seed % len(matching)]


def compose_scene(image_path: str, analysis, style_key: str, style_domain: str,
                  seed: int, output_dir: str) -> dict:
    """① 플랜 선택 ② 배경 획득 ③ 누끼 ④ 배치 ⑤ 그림자 ⑥ 색조화 ⑦ 리플렉션 ⑧ 반환.

    style_domain은 호출부(generation_service._resolve_style_domain)가 이미 계산한 "object"|"drink"
    값을 그대로 받는다 — 디저트/음료 판정 로직(2026-07-17 라이브 결함 수정분)을 이 함수 안에서
    다시 파생하면 두 곳이 어긋날 위험이 있어 의도적으로 중복 계산하지 않는다.
    """
    view_angle = getattr(analysis, "view_angle", "eye") or "eye"
    plan = _pick_plan(style_key, style_domain, seed, view_angle)
    if plan is None:
        return {"ok": False, "reason": "angle"}

    cut = cutout(image_path)
    if not cut["ok"]:
        return {"ok": False, "reason": cut.get("reason", "mask")}

    effects = infer_effects(getattr(analysis, "temperature", "") or "")
    allowed_props = scene_plans.map_props(getattr(analysis, "core_ingredients", None), effects)

    accent_hue = _dominant_hue(cut["rgba"]) if plan.style == "monotone" else 0.0
    acquired = acquire_background(plan, allowed_props, seed, accent_hue=accent_hue)
    if not acquired["ok"]:
        return {"ok": False, "reason": acquired.get("reason", "no_bg")}

    bg = acquired["image"].convert("RGB")
    product, place_xy = _place_product(bg.size, cut["rgba"], plan, acquired["surface_y"])

    canvas = bg.convert("RGBA")
    shadow = _contact_shadow(product, plan)
    offset_dir = 1 if plan.light_dir == "left" else -1  # 그림자는 광원 반대쪽(D-1' 계승)
    shadow_x = place_xy[0] + offset_dir * int(product.width * 0.06)
    shadow_y = place_xy[1] + product.height - shadow.height // 2
    canvas.alpha_composite(shadow, (shadow_x, shadow_y))

    harmonized = _harmonize_color(product, bg, place_xy)
    canvas.alpha_composite(harmonized, place_xy)

    if plan.reflection_strength > 0:
        reflection = _reflection(harmonized, plan.reflection_strength)
        canvas.alpha_composite(reflection, (place_xy[0], place_xy[1] + product.height))

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{Path(image_path).stem}_scene.png"
    canvas.convert("RGB").save(out_path, format="PNG")

    return {"ok": True, "path": str(out_path), "text_zone": plan.text_zone, "plan": plan.key}
