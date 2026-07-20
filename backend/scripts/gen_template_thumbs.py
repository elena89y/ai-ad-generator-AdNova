"""템플릿 썸네일 정적 생성 (DIRECTION_v6 T4) — 담당: 한의정.

각 템플릿의 스타일 팔레트·무드로 480×600 카드 렌더 → backend/assets/templates/{id}.png.
사진 아님·코드 드로잉(비용 0, 재현 가능) — 실사 썸네일은 HYB-001 결과 중 선별로 교체 예정.
타이포는 코드(PIL) 원칙 그대로. 재실행 멱등(동일 입력 → 동일 출력, 덮어씀).

사용: cd backend && ../.venv/bin/python scripts/gen_template_thumbs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.template_service import load_templates  # noqa: E402

OUT_DIR = BACKEND / "assets" / "templates"
FONTS = BACKEND / "assets" / "fonts"
W, H = 480, 600


def _hex(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _luma(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def render_thumb(tid: str, title: str, palette: tuple[str, ...], mood: str) -> Path:
    cols = [_hex(p) for p in (palette or ("#EEEEEE", "#CCCCCC", "#333333"))]
    while len(cols) < 3:
        cols.append(cols[-1])
    bg, band, deep = cols[0], cols[1], cols[2]

    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    # 사선 컬러띠(브랜드 룩 계승) + 하단 딥톤 밴드
    d.polygon([(0, int(H * 0.58)), (W, int(H * 0.38)), (W, int(H * 0.52)),
               (0, int(H * 0.72))], fill=band)
    d.rectangle([0, int(H * 0.8), W, H], fill=deep)

    head = ImageFont.truetype(str(FONTS / "BlackHanSans-Regular.ttf"), 44)
    sub = ImageFont.truetype(str(FONTS / "DoHyeon-Regular.ttf"), 22)
    # 배경 명도에 따라 잉크 자동 선택(가독성)
    ink = (20, 20, 20) if _luma(bg) > 140 else (245, 245, 245)
    d.text((28, 36), title, font=head, fill=ink)
    # 무드 설명은 2줄까지, 하단 딥톤 밴드 위에 밝은 잉크
    band_ink = (245, 242, 235) if _luma(deep) <= 140 else (25, 25, 25)
    # "…"(U+2026)는 DoHyeon에 글리프가 없어 tofu 로 렌더(실측) — ASCII 마침표 3개 사용
    mood_line = mood if len(mood) <= 25 else mood[:25] + "..."
    d.text((28, int(H * 0.84)), mood_line, font=sub, fill=band_ink)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{tid}.png"
    im.save(out, "PNG")
    return out


def main() -> None:
    for tid, preset in load_templates().items():
        out = render_thumb(tid, preset.title, preset.palette, preset.mood)
        print(f"{tid}: {out.relative_to(BACKEND)}")


if __name__ == "__main__":
    main()
