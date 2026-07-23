"""레이아웃 DSL 렌더 엔진 — 조판을 데이터(요소 리스트)로 해석한다. (DIRECTION_v6-1 L2/L3)

담당: 한의정. 목표: formats/*.py 의 하드코딩 조판을 데이터로 빼서 '생성된 광고(스타일·카피)'에
맞게 적응시키되, 값은 YAML/딕트로 정의하고 코드는 범용 해석기만 남긴다.

좌표 표현(표현식 문자열 대신 구조화 리스트 — 파싱 단순·안전):
  ["margin"]            → margin
  ["rmargin", off?]     → W - margin + off        (우측 정렬)
  ["fw", f, off?]       → int(W*f) + off
  ["fh", f, off?]       → int(H*f) + off
  ["restw"] / ["resth"] → W - base_x / H - base_y (이미지 size 전용: at 부터 끝까지)
  숫자                   → 절대값
색: "paper"|"paper_warm"|"ink"|"white" (named) | "accent"|"deep"|"tint" (palette) | [r,g,b]
바인딩: {"bind": "intro_headline"} | {"bind": "benefit_bullets.0"} | {"text": "STATIC"}, fallback 지원
조건: {"if": "product_name"} — copy 필드가 truthy 일 때만 그린다
폰트: {"font": 25, "bold": true} | {"font": {"fit": [start, min]}} (maxw = W - 2*margin)
텍스트 변형/줄바꿈: {"transform": "first_sentence"}, {"wrap": N, "line_h": H}
요소 타입: image | scrim | bar/panel(사각) | rule(선) | text
슬라이드: render_slide(size, spec, cuts, copy, pal, margin_ratio) — bg + images + elements
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

from .formats.detail_page import _scrim

_LAYOUT_DIR = Path(__file__).parent / "layouts"


@lru_cache(maxsize=8)
def load_layout(name: str) -> dict:
    """레이아웃 DSL 원장(layouts/{name}.yaml) 로드. 슬라이드/포맷명 → 스펙."""
    with open(_LAYOUT_DIR / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)

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


def _wrap(text: str, length: int) -> list[str]:
    """짧은 한글 광고 문구를 글자 수 기준으로 나눈다(formats.cardnews._wrap 과 동일)."""
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > length:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def _first_sentence(text: str) -> str:
    """본문 첫 문장만(formats.cardnews._first_sentence 와 동일)."""
    t = (text or "").strip()
    for sep in (". ", "! ", "? "):
        if sep in t:
            return t.split(sep)[0].strip()
    return t.rstrip(".!?").strip()


def _cover_img(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """cover 크롭(formats.cardnews._cover 와 동일 — round 사용)."""
    w, h = size
    scale = max(w / image.width, h / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _r(v, W: int, H: int, margin: int, base: int = 0) -> int:
    """좌표 표현 → 픽셀. base 는 restw/resth(이미지 size)용 기준점."""
    if isinstance(v, (int, float)):
        return int(v)
    kind = v[0]
    if kind == "margin":
        return margin + (v[1] if len(v) > 1 else 0)
    if kind == "rmargin":
        return W - margin + (v[1] if len(v) > 1 else 0)
    if kind == "fw":
        return int(W * v[1]) + (v[2] if len(v) > 2 else 0)
    if kind == "fh":
        return int(H * v[1]) + (v[2] if len(v) > 2 else 0)
    if kind == "fwm":  # int(W*f) + k*margin (colw-2margin 같은 폭 표현)
        return int(W * v[1]) + int(v[2] * margin)
    if kind == "restw":
        return W - base
    if kind == "resth":
        return H - base
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
    if not val:
        return el.get("fallback", "")
    if el.get("transform") == "first_sentence":
        return _first_sentence(val)
    return val


def _cond(el: dict, copy) -> bool:
    key = el.get("if")
    if not key:
        return True
    return bool(getattr(copy, key, None))


def _font_of(el: dict, text: str, W: int, H: int, margin: int) -> ImageFont.FreeTypeFont:
    f = el["font"]
    if isinstance(f, dict) and "fit" in f:
        mw = el.get("maxw")
        maxw = _r(mw, W, H, margin) if mw is not None else W - 2 * margin
        return _fit(text, maxw, f["fit"][0], f["fit"][1])
    return _font(f, el.get("bold", False))


def _paste_image(canvas: Image.Image, el: dict, cuts: dict, W: int, H: int, margin: int) -> None:
    at_x = _r(el["at"][0], W, H, margin)
    at_y = _r(el["at"][1], W, H, margin)
    sw = _r(el["size"][0], W, H, margin, base=at_x)
    sh = _r(el["size"][1], W, H, margin, base=at_y)
    img = _cover_img(Image.open(cuts[el["cut"]]).convert("RGB"), (sw, sh))
    canvas.paste(img, (at_x, at_y))


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
            box = [rr(c) for c in el["box"]]
            rgb = _color(el["color"], pal)
            draw.rectangle(box, fill=(*rgb, el["alpha"]) if "alpha" in el else rgb)
        elif t == "rule":
            box = [rr(c) for c in el["box"]]
            draw.line(box, fill=_color(el["color"], pal), width=el.get("width", 1))
        elif t == "text":
            s = _bind_text(el, copy)
            font = _font_of(el, s, W, H, margin)
            fill = _color(el["color"], pal)
            x, y0 = rr(el["at"][0]), rr(el["at"][1])
            if "wrap" in el:
                lh = el.get("line_h", 40)
                for i, line in enumerate(_wrap(s, el["wrap"])):
                    draw.text((x, y0 + i * lh), line, font=font, fill=fill, spacing=el.get("spacing", 4))
            else:
                draw.text((x, y0), s, font=font, fill=fill, spacing=el.get("spacing", 4))
        else:
            raise ValueError(f"알 수 없는 요소 타입: {t}")


def render_slide(size: tuple[int, int], spec: dict, cuts: dict, copy, pal,
                 margin_ratio: float) -> Image.Image:
    """슬라이드 스펙(bg + images + elements) → 완성 캔버스.

    bg: {"cut": "hero"}(컷 cover) | {"fill": "deep"}(단색). images: [{cut, at, size}].
    """
    W, H = size
    margin = int(W * margin_ratio)
    bg = spec.get("bg", {})
    if "cut" in bg:
        canvas = _cover_img(Image.open(cuts[bg["cut"]]).convert("RGB"), size)
    else:
        canvas = Image.new("RGB", size, _color(bg.get("fill", "white"), pal))
    for im in spec.get("images", []):
        _paste_image(canvas, im, cuts, W, H, margin)
    render_elements(canvas, spec.get("elements", []), copy, pal, W, H, margin)
    return canvas
