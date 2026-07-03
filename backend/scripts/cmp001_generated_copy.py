"""CMP-G01: 생성이미지 기반 문구 생성 정합성 검증 — 담당: 한의정.

배경: 기존 CMP 실험(B-1/B-2)은 원본 상품사진 기준 검증. 확정 파이프라인은
  FR-08 '생성된 광고 이미지'를 문구 생성 입력으로 사용 → 별도 검증 필요 항목.

실행 내용:
  1. FR-08 산출 이미지에 대해 BLIP 캡션 경로(generate_copy, 저비용)로 카피 생성
  2. --vision 지정 시 Vision 직접 입력 경로도 실행해 비교 (비용 ↑, 1회만)
  3. generate_sns_copy(용도별)도 1건 생성
정합성(카피가 이미지 분위기·소품과 일치하는지) 판정은 육안으로 실험로그에 기록.

⚠️ 실행 1회 = 텍스트 API 2회(+ --vision 시 Vision 1회). 반복 실행 주의.

결과는 stdout 출력과 동시에 backend/results/ai/cmp001_<타임스탬프>.md 로 저장된다.

실행:  .venv/bin/python backend/scripts/cmp001_generated_copy.py <생성이미지경로> [--vision]
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

from app.schemas.ads import AdPurpose, ProductInfo, StylePreset
from app.services.gpt_service import _caption_image, generate_copy, generate_sns_copy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", help="FR-08 생성 광고 이미지 경로")
    parser.add_argument("--vision", action="store_true", help="Vision 직접 입력 경로도 실행 (비용 발생)")
    parser.add_argument("--name", default="말차 라즈베리 쿠키")
    parser.add_argument("--desc", default="수제 쌀가루 쿠키")
    args = parser.parse_args()

    product = ProductInfo(name=args.name, description=args.desc)
    style = StylePreset.WARM_VINTAGE
    lines: list[str] = [
        f"# CMP-G01 결과 — {datetime.now().isoformat(timespec='seconds')}",
        f"- 입력 이미지: {args.image}",
        f"- 상품: {args.name} — {args.desc} / 스타일: {style.value}",
        "",
    ]

    def record(text: str) -> None:
        print(text)
        lines.append(text)

    # 0) BLIP 캡션 자체 확인 (비용 없음)
    t0 = time.perf_counter()
    caption = _caption_image(args.image)
    record(f"[BLIP 캡션] ({time.perf_counter() - t0:.2f}s) {caption}")

    # 1) 저비용 경로 (BLIP 캡션 → 텍스트 API)
    t0 = time.perf_counter()
    r1 = generate_copy(args.image, product, style, use_vision=False)
    record(f"\n[경로 B-0 저비용: BLIP→텍스트] ({time.perf_counter() - t0:.2f}s)")
    record(r1.copy_text)

    # 2) Vision 직접 입력 경로 (옵션)
    if args.vision:
        t0 = time.perf_counter()
        r2 = generate_copy(args.image, product, style, use_vision=True)
        record(f"\n[경로 Vision 직접] ({time.perf_counter() - t0:.2f}s)")
        record(r2.copy_text)

    # 3) SNS 문구 (FR-23, 텍스트 전용)
    t0 = time.perf_counter()
    sns = generate_sns_copy(product, style, AdPurpose.SNS)
    record(f"\n[SNS 문구 (FR-23)] ({time.perf_counter() - t0:.2f}s)")
    record(sns.caption)
    record(" ".join(sns.hashtags))

    results_dir = BACKEND_DIR / "results" / "ai"
    results_dir.mkdir(parents=True, exist_ok=True)
    out_path = results_dir / f"cmp001_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    main()
