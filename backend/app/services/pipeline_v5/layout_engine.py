"""레이아웃 DSL 렌더 엔진 — 조판을 데이터(요소 리스트)로 해석한다. (DIRECTION_v6-1 L2)

담당: 한의정. 목표: formats/*.py 의 하드코딩 조판을 데이터로 빼서 '생성된 광고(스타일·카피)'에
맞게 적응시키되, 값은 YAML/딕트로 정의하고 코드는 범용 해석기만 남긴다.

좌표 표현(표현식 문자열 대신 구조화 리스트 — 파싱 단순·안전):
  ["margin"]            → margin
  ["rmargin", off?]     → W - margin + off        (우측 정렬)
  ["fw", f, off?]       → int(W*f) + off
  ["fh", f, off?]       → int(H*f) + off
  숫자                   → 절대값
색: "paper"|"paper_warm"|"ink"|"white" (named) | "accent"|"deep"|"tint" (palette) | [r,g,b]
바인딩: {"bind": "intro_headline"} | {"bind": "benefit_bullets.0"} | {"text": "STATIC"}, fallback 지원
조건: {"if": "product_name"} — copy 필드가 truthy 일 때만 그린다
폰트: {"font": 25, "bold": true} | {"font": {"fit": [start, min]}} (maxw = W - 2*margin)
요소 타입: scrim | bar(반투명 사각) | rule(선) | text | panel(불투명 사각) | bullet(원+번호+텍스트)
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .formats.detail_page import _scrim

_NAMED = {
    "paper": (248, 247, 243),
    "paper_warm": (245, 243, 238),
    "ink": (18, 18, 18),
    "white": (255, 255, 255),
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    root = Path(__file__).resolve().parents[3] / "assets" / "fonts"
    name = "Pretendard-Bold.otf" if bold else "Pretendard-Medium.otf"
    return ImageFont.truetype(str(root / name), size)


def _fit(text: str, max_width: int, start: int, minimum: int) -> ImageFont.FreeTypeFont:
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(start, minimum - 1, -2):
        font = _font(size, True)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return _font(minimum, True)


def _r(v, W: int, H: int, margin: int) -> int:
    """좌표 표현 → 픽셀."""
    if isinstance(v, (int, float)):
        return int(v)
    kind = v[0]
    off = v[-1] if (kind in ("rmargin", "fw", "fh") and len(v) > (2 if kind != "rmargin" else 1)) else 0
    if kind == "margin":
        return margin
    if kind == "rmargin":
        return W - margin + (v[1] if len(v) > 1 else 0)
    if kind == "fw":
        return int(W * v[1]) + off
    if kind == "fh":
        return int(H * v[1]) + off
    raise ValueError(f"알 수 없는 좌표 표현: {v}")


def _color(v, pal):
    if isinstance(v, (list, tuple)):
        return tuple(v)
    if v in _NAMED:
        return _NAMED[v]
    return pal[v]  # accent | deep | tint


def _bind_text(el: dict, copy) -> str:
    if "text" in el:
        return el["text"]
    ref = el["bind"]
    if "." in ref:  # benefit_bullets.0
        name, idx = ref.split(".")
        seq = getattr(copy, name, ()) or ()
        val = seq[int(idx)] if len(seq) > int(idx) else ""
    else:
        val = getattr(copy, ref, "") or ""
    return val or el.get("fallback", "")


def _cond(el: dict, copy) -> bool:
    key = el.get("if")
    if not key:
        return True
    val = getattr(copy, key, None)
    return bool(val)


def _font_of(el: dict, text: str, W: int, margin: int) -> ImageFont.FreeTypeFont:
    f = el["font"]
    if isinstance(f, dict) and "fit" in f:
        maxw = el.get("maxw", W - 2 * margin)
        return _fit(text, maxw, f["fit"][0], f["fit"][1])
    return _font(f, el.get("bold", False))


def render_elements(canvas: Image.Image, elements: list[dict], copy, pal,
                    W: int, H: int, margin: int) -> None:
    """요소 리스트를 canvas 에 순서대로 렌더. canvas 는 이미 배경(컷 등) 배치된 상태."""
    draw = ImageDraw.Draw(canvas, "RGBA")

    def rr(v):
        return _r(v, W, H, margin)

    for el in elements:
        if not _cond(el, copy):
            continue
        t = el["type"]
        if t == "scrim":
            _scrim(canvas, rr(el["frm"][1]), rr(el["to"][1]), W,
                   _color(el["color"], pal), el["amax"], rr(el["fade"]))
            draw = ImageDraw.Draw(canvas, "RGBA")  # scrim 이 canvas 를 갈아끼우므로 재바인딩
        elif t in ("bar", "panel"):
            box = [rr(el["box"][0]), rr(el["box"][1]), rr(el["box"][2]), rr(el["box"][3])]
            rgb = _color(el["color"], pal)
            fill = (*rgb, el["alpha"]) if "alpha" in el else rgb
            draw.rectangle(box, fill=fill)
        elif t == "rule":
            box = [rr(el["box"][0]), rr(el["box"][1]), rr(el["box"][2]), rr(el["box"][3])]
            draw.line(box, fill=_color(el["color"], pal), width=el.get("width", 1))
        elif t == "text":
            s = _bind_text(el, copy)
            font = _font_of(el, s, W, margin)
            draw.text((rr(el["at"][0]), rr(el["at"][1])), s, font=font,
                      fill=_color(el["color"], pal), spacing=el.get("spacing", 4))
        else:
            raise ValueError(f"알 수 없는 요소 타입: {t}")
