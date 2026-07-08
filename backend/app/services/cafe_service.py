"""카페 제품 광고 (B모드) — 담당: 한의정.

카페 음료·디저트: 누끼 + 제품 생성리터치 + FLUX 씬 배경.
A(음식점 dish, in-place)·C(사물, 스튜디오)와 달리, 이산(discrete) 제품을 잘라
먹음직스럽게 리터치한 뒤 FLUX 로 프리미엄 씬 배경을 만든다.

⚠️ VRAM: RealVis(리터치)와 FLUX(배경)는 동시 상주 시 OOM(L4 22GB) →
  리터치 후 image_service.unload_pipelines() 로 비우고 FLUX 로드 (피크 ~13GB).
  FLUX cpu_offload 금지(T5 CPU 낙하=행).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image


@dataclass
class CafeAdResult:
    output_path: str
    retouch_strength: float
    seconds: float


def _scene_prompt(subject_en: str) -> str:
    """FLUX 씬 프롬프트 (T5 — 서술형). 'no text' 필수, 제품은 마스크 보존."""
    return (
        f"{subject_en} on a soft cream cafe table, warm golden window light, "
        "cozy premium cafe atmosphere, subtle props, shallow depth of field, "
        "editorial food photography, no text, no letters"
    )


def generate_cafe_ad(
    image_path: str,
    subject_en: str,
    retouch_strength: float = 0.4,
    scene_prompt: Optional[str] = None,
    seed: Optional[int] = None,
    output_dir: str = "backend/results/ai/cafe",
) -> CafeAdResult:
    """B모드: 누끼 → 제품 생성리터치(RealVis) → VRAM 확보 → FLUX 씬 배경. GPU 필요.

    subject_en: 영어 제품 설명(analyze_menu.subject_en). retouch_strength 0.2~0.65.
    """
    import time

    from . import flux_service, image_service

    t0 = time.time()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. 누끼
    proc = image_service.preprocess(image_path, output_dir=output_dir)
    prgba = Image.open(proc.processed_image_path).convert("RGBA")
    mask = Image.open(proc.mask_path).convert("L")

    # 2. 제품만 생성리터치 (흰 배경 위에서 RealVis → 원본 마스크로 재적용)
    white = Image.new("RGBA", prgba.size, (255, 255, 255, 255))
    white.alpha_composite(prgba)
    positive = (f"{subject_en}, realistic food photograph, appetizing, glossy highlights, "
                "fresh, natural sharp focus, high detail, true-to-life colors")
    negative = ("blurry, deformed, plastic, artificial, text, watermark, cartoon, "
                "3d render, cgi, extra items, foreign garnish")
    strength = max(0.2, min(0.65, retouch_strength))
    retouched = image_service.img2img(white.convert("RGB"), positive, negative,
                                      strength=strength, guidance=5.0, photoreal=True)
    retouched_rgba = retouched.convert("RGBA")
    retouched_rgba.putalpha(mask)
    ret_path = out_dir / f"{Path(image_path).stem}_retouched.png"
    retouched_rgba.save(ret_path)

    # 3. VRAM 확보 — RealVis/SDXL 언로드 후 FLUX
    image_service.unload_pipelines()

    # 4. FLUX 씬 배경 (제품 마스크 보존)
    proc_ret = image_service.PreprocessResult(
        processed_image_path=str(ret_path), mask_path=proc.mask_path)
    fr = flux_service.generate_with_flux(
        proc_ret, scene_prompt or _scene_prompt(subject_en), seed=seed,
        output_dir=str(out_dir))

    return CafeAdResult(output_path=fr.final_image_path,
                        retouch_strength=strength, seconds=round(time.time() - t0, 2))
