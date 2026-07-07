"""사물 제품컷 (C모드) — 담당: 한의정.

하드굿즈(마우스·거울·컵·괄사 등) 광고: 누끼 + 클린 보정 + 스튜디오 배경.
음식(A)과 달리 '먹음직'이 아니라 '정확·깔끔'이 목표 → 중립 보정.
⚠️ 사물은 SKU(손님이 받는 그 물건)라 정직도가 음식보다 엄격 → 형태·색 왜곡 금지,
  톤·크리스프·광택만 보수적으로. 재질(무광/반사/투명)별 강도 차등.

흐름: preprocess(누끼) → clean_object(중립 그레이드) → 스튜디오 배경 합성.
순수 PIL(GPU 불필요). image_service 의 studio 배경·접촉그림자 재사용.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# 재질별 클린 보정 강도 (intensity 로 일괄 스케일).
#   wb=캐스트제거, sat=중립채도, clarity=크리스프, gloss=광택.
#   반사(금속·거울)=광택·대비↑ / 무광=중간 / 투명(유리)=최소(왜곡 위험).
_OBJ_GRADE = {
    "matte": dict(wb=0.5, sat=0.14, clarity=0.34, gloss=0.14),
    "reflective": dict(wb=0.5, sat=0.12, clarity=0.44, gloss=0.30),
    "transparent": dict(wb=0.4, sat=0.10, clarity=0.24, gloss=0.10),
    "default": dict(wb=0.5, sat=0.14, clarity=0.34, gloss=0.18),
}


@dataclass
class ObjectAdResult:
    output_path: str
    material: str
    seconds: float


def _to_f(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0


def _to_img(a: np.ndarray) -> Image.Image:
    return Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


def _neutral_wb(rgb, mask, amount):
    """그레이월드로 컬러 캐스트만 제거 (웜 푸시 없음 — 색 정확). 통계는 제품 픽셀만."""
    if amount <= 0:
        return rgb
    px = rgb[mask]
    if len(px) < 20:
        return rgb
    m = px.mean(0) + 1e-6
    gain = 1.0 + amount * (m.mean() / m - 1.0)
    return rgb * gain


def _sat(rgb, amount):
    """중립 채도 (루미넌스 기준 확장 — 특정 색 편향 없이). 과하지 않게."""
    if amount <= 0:
        return rgb
    lum = (rgb @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
    return lum + (rgb - lum) * (1.0 + amount)


def _clarity(rgb, amount):
    if amount <= 0:
        return rgb
    blur = _to_f(_to_img(rgb).filter(ImageFilter.GaussianBlur(radius=8)))
    return rgb + amount * (rgb - blur)


def _gloss(rgb, amount):
    if amount <= 0:
        return rgb
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    hi = (np.clip((lum - 0.62) / 0.38, 0, 1) ** 2)[..., None]
    return rgb + amount * hi * (1.0 - rgb)


def clean_object(product_rgba: Image.Image, material: str = "default",
                 intensity: float = 1.0) -> Image.Image:
    """누끼 딴 사물(RGBA)에 중립 클린 보정 — 형태·색 유지, 톤·크리스프·광택만. 알파 보존."""
    p = _OBJ_GRADE.get(material, _OBJ_GRADE["default"])
    k = max(0.0, min(1.5, intensity))
    alpha = np.asarray(product_rgba.split()[-1], dtype=np.uint8)
    mask = alpha > 20
    rgb = _to_f(product_rgba)
    rgb = _neutral_wb(rgb, mask, p["wb"] * k)
    rgb = _sat(rgb, p["sat"] * k)
    rgb = _clarity(rgb, p["clarity"] * k)
    rgb = _gloss(rgb, p["gloss"] * k)
    out = _to_img(rgb).convert("RGBA")
    out.putalpha(product_rgba.split()[-1])
    return out


def generate_object_ad(
    image_path: str,
    material: str = "default",
    intensity: float = 1.0,
    output_dir: str = "backend/results/ai/object",
) -> ObjectAdResult:
    """C모드 사물 제품컷: 누끼 → 클린 보정 → 스튜디오 배경 합성. GPU 불필요.

    material: matte|reflective|transparent|default (재질별 보정 강도).
      통합 시 analyze_menu(사물)에서 재질 공급 예정.
    """
    import time

    from . import image_service

    t0 = time.time()
    proc = image_service.preprocess(image_path, output_dir=output_dir)
    prgba = Image.open(proc.processed_image_path).convert("RGBA")
    pmask = Image.open(proc.mask_path).convert("L")

    cleaned = clean_object(prgba, material=material, intensity=intensity)
    studio = image_service._flat_color_background(cleaned, pmask, mode="studio")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{Path(image_path).stem}_objectcut.png"
    studio.convert("RGB").save(out_path)
    return ObjectAdResult(output_path=str(out_path), material=material,
                          seconds=round(time.time() - t0, 2))
