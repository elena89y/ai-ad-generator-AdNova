"""STY-001: 경로1 Vision 스타일 추천 실제 호출 테스트 — 담당: 한의정.

⚠️ 실행 1회 = OpenAI Vision 호출 1회 = 비용 발생 ($30 팀 한도).
   반복 실행 금지. CI 등 자동 실행 경로에 포함하지 말 것.

실행:  python backend/scripts/sty001_vision_style.py [이미지경로]
       (이미지 미지정 시 합성 상품 이미지 생성 후 사용)
필요:  backend/.env 에 OPENAI_API_KEY
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

from app.schemas.ads import StyleRequest
from app.services.style_service import decide_style


def _make_test_image(path: Path) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1024, 768), (245, 240, 230))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([380, 250, 640, 620], radius=30, fill=(140, 90, 50))   # 병 몸통
    d.rectangle([470, 170, 550, 260], fill=(90, 60, 35))                        # 병목
    d.ellipse([420, 330, 600, 480], fill=(230, 220, 200))                       # 라벨
    img.save(path, format="JPEG", quality=90)


def main() -> None:
    # 경로2 (자유 텍스트, 비용 없음) 먼저 확인
    r2 = decide_style(StyleRequest(free_text="따뜻하고 빈티지한 느낌으로"))
    print(f"[경로2] resolved={r2.resolved.value}, reason={r2.candidates[0].reason}")

    # 경로1 (Vision, 비용 발생 — 1회만)
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        _run_path1(image_path)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            image_path = str(Path(tmp) / "product.jpg")
            _make_test_image(Path(image_path))
            _run_path1(image_path)


def _run_path1(image_path: str) -> None:
    print(f"[경로1] Vision 호출 시작: {image_path}")
    started = time.perf_counter()
    r1 = decide_style(StyleRequest(image_path=image_path))
    elapsed = time.perf_counter() - started

    print(f"[경로1] 응답 {elapsed:.2f}s, 후보 {len(r1.candidates)}개 (resolved={r1.resolved})")
    for i, c in enumerate(r1.candidates, 1):
        print(f"  {i}. {c.preset.value}: {c.reason}")


if __name__ == "__main__":
    main()
