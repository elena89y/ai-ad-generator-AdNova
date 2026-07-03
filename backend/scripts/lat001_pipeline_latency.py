"""LAT-001: 3단계 파이프라인 합산 지연시간 측정 — 담당: 한의정.

측정 대상 (서버 상시 기동 = 모델 warm 상태 전제):
  ① 스타일 결정 (경로1 Vision 추천)      — OpenAI Vision 1회
  ② 광고 이미지 생성 (SDXL Inpainting)   — steps 30 / 20 비교
  ③ 광고 문구 생성                        — BLIP 경로 + (--vision 시) Vision 경로

전처리(FR-06)는 3단계 정의 밖이지만 참고용으로 별도 측정.
warm-up(모델 로드·첫 추론)은 측정에서 제외 — 사전 실행 후 계측.

⚠️ 비용: 실행 1회 = Vision 1회(①) + 텍스트 1회(③BLIP) [+ Vision 1회(③ --vision)]
결과는 backend/results/ai/lat001_<타임스탬프>.md 로 저장.

실행:  .venv/bin/python backend/scripts/lat001_pipeline_latency.py <상품사진> [--vision]
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

from app.schemas.ads import ProductInfo, StyleRequest
from app.services import gpt_service, image_service, style_service
from app.services.prompt_service import build_image_prompt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", help="상품 사진 경로")
    parser.add_argument("--vision", action="store_true", help="③ Vision 경로도 측정 (비용 추가)")
    parser.add_argument("--name", default="말차 라즈베리 쿠키")
    args = parser.parse_args()

    lines: list[str] = [
        f"# LAT-001 결과 — {datetime.now().isoformat(timespec='seconds')}",
        f"- 입력: {args.image}",
        "- 전제: 모델 warm 상태 (로드·첫 추론 제외), seed=42, steps 30/20 비교",
        "",
    ]

    def record(text: str) -> None:
        print(text)
        lines.append(text)

    product = ProductInfo(name=args.name)

    # --- warm-up (측정 제외): rembg + SDXL + BLIP 로드 및 1회 추론 -------------
    print("--- warm-up (측정 제외) ---")
    t0 = time.perf_counter()
    processed = image_service.preprocess(args.image)  # rembg warm + 전처리 산출
    preprocess_cold = time.perf_counter() - t0
    prompt_warm = build_image_prompt(product, list(style_service.StylePreset)[1])
    image_service.generate_ad_image(processed, prompt_warm, seed=1)  # SDXL warm
    gpt_service._caption_image(processed.processed_image_path)  # BLIP warm

    # 전처리 warm 재측정 (참고용, 3단계 정의 밖)
    t0 = time.perf_counter()
    processed = image_service.preprocess(args.image)
    preprocess_warm = time.perf_counter() - t0
    record(f"[참고] 전처리 FR-06: cold {preprocess_cold:.2f}s / warm {preprocess_warm:.2f}s")

    # --- ① 스타일 결정 (경로1 Vision) ------------------------------------------
    t0 = time.perf_counter()
    style_resp = style_service.decide_style(StyleRequest(image_path=args.image))
    t_style = time.perf_counter() - t0
    chosen = style_resp.candidates[0].preset  # 유저 선택 대신 1순위 후보 사용
    record(f"① 스타일 결정 (Vision 추천): {t_style:.2f}s → 후보 {[c.preset.value for c in style_resp.candidates]}, 선택={chosen.value}")

    # --- ② 이미지 생성 (steps 30 vs 20) ----------------------------------------
    prompt = build_image_prompt(product, chosen)

    result30 = image_service.generate_ad_image(processed, prompt, seed=42)
    record(f"② 이미지 생성 steps=30: {result30.infer_seconds:.2f}s → {result30.final_image_path}")

    # 동일 seed 라 파일명이 겹침 → steps20 은 하위 폴더로 분리 (steps30 결과 보존)
    orig_steps = image_service.DEFAULT_STEPS
    image_service.DEFAULT_STEPS = 20
    try:
        result20 = image_service.generate_ad_image(
            processed, prompt, seed=42,
            output_dir=str(BACKEND_DIR / "results" / "ai" / "lat001_steps20"),
        )
    finally:
        image_service.DEFAULT_STEPS = orig_steps
    record(f"② 이미지 생성 steps=20: {result20.infer_seconds:.2f}s → {result20.final_image_path}")

    # --- ③ 문구 생성 -------------------------------------------------------------
    t0 = time.perf_counter()
    copy_blip = gpt_service.generate_copy(result30.final_image_path, product, chosen)
    t_copy_blip = time.perf_counter() - t0
    record(f"③ 문구 생성 (BLIP 경로): {t_copy_blip:.2f}s")
    record(f"   {copy_blip.copy_text!r}")

    t_copy_vision = None
    if args.vision:
        t0 = time.perf_counter()
        copy_vision = gpt_service.generate_copy(
            result30.final_image_path, product, chosen, use_vision=True
        )
        t_copy_vision = time.perf_counter() - t0
        record(f"③ 문구 생성 (Vision 경로): {t_copy_vision:.2f}s")
        record(f"   {copy_vision.copy_text!r}")

    # --- 합산 --------------------------------------------------------------------
    record("")
    record("## 합산 (목표 20s)")
    for steps_label, t_img in (("steps30", result30.infer_seconds), ("steps20", result20.infer_seconds)):
        total_blip = t_style + t_img + t_copy_blip
        mark = "✅" if total_blip <= 20 else "⚠️ 초과"
        record(f"- ①+②({steps_label})+③(BLIP) = {t_style:.2f}+{t_img:.2f}+{t_copy_blip:.2f} = {total_blip:.2f}s {mark}")
        if t_copy_vision is not None:
            total_v = t_style + t_img + t_copy_vision
            mark = "✅" if total_v <= 20 else "⚠️ 초과"
            record(f"- ①+②({steps_label})+③(Vision) = {t_style:.2f}+{t_img:.2f}+{t_copy_vision:.2f} = {total_v:.2f}s {mark}")

    out_dir = BACKEND_DIR / "results" / "ai"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"lat001_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    main()
