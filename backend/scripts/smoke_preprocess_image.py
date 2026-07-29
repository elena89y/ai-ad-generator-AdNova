"""FR-06 전처리 스모크 테스트 — 담당: 한의정.

합성 상품 이미지를 생성해 preprocess_image / preprocess 를 검증한다.
외부 의존(실제 상품 사진) 없이 실행 가능. GPU 없으면 CPU 로 폴백(느림).

실행:  python backend/scripts/smoke_preprocess_image.py
"""
from __future__ import annotations

import io
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

from app.services.image_service import (
    DEFAULT_OUTPUT_SIZE,
    preprocess,
    preprocess_image,
)


def _make_test_image(size: tuple[int, int] = (1600, 1200)) -> bytes:
    """단색 배경 위 상품(도형) 합성 이미지 생성."""
    img = Image.new("RGB", size, (200, 220, 240))
    d = ImageDraw.Draw(img)
    d.ellipse([500, 300, 1100, 900], fill=(180, 60, 40))
    d.rectangle([740, 200, 860, 320], fill=(120, 40, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def main() -> None:
    raw = _make_test_image()

    # 1) bytes API
    started = time.perf_counter()
    out_bytes = preprocess_image(raw)
    elapsed = time.perf_counter() - started

    out_img = Image.open(io.BytesIO(out_bytes))
    assert out_img.size == DEFAULT_OUTPUT_SIZE, f"크기 불일치: {out_img.size}"
    assert out_img.mode == "RGBA", f"RGBA 아님: {out_img.mode}"

    alpha_hist = out_img.split()[-1].histogram()
    total = out_img.size[0] * out_img.size[1]
    transparent_ratio = sum(alpha_hist[:10]) / total
    assert transparent_ratio > 0.5, f"배경 제거 미흡 (투명 비율 {transparent_ratio:.1%})"
    print(f"[OK] bytes API — {elapsed:.2f}s, 투명 비율 {transparent_ratio:.1%}")

    # 2) 경로 API (processed + mask 산출)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "product.jpg"
        src.write_bytes(raw)

        result = preprocess(str(src), output_dir=tmp)
        assert Path(result.processed_image_path).is_file()
        assert result.mask_path and Path(result.mask_path).is_file()

        mask = Image.open(result.mask_path)
        assert mask.mode == "L", f"마스크 모드 불일치: {mask.mode}"
        assert mask.size == DEFAULT_OUTPUT_SIZE
        print(f"[OK] 경로 API — processed/mask 저장 및 규격 검증 통과")

    print("스모크 테스트 전체 통과")


if __name__ == "__main__":
    main()
