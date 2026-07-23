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


def _cover_img(image: Image.Image, size: tuple[int, int], mode: str = "round") -> Image.Image:
    """cover 크롭. mode='round'=카드뉴스/배너, 'int'=상세페이지(원본 _cover 반올림 차이)."""
    w, h = size
    scale = max(w / image.width, h / image.height)
    r = round if mode == "round" else int
    resized = image.resize((r(image.width * scale), r(image.height * scale)), Image.LANCZOS)
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
    if kind == "wsub":  # W - int(W*f) + k*margin (split 우측 텍스트 폭)
        return W - int(W * v[1]) + int(v[2] * margin)
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
    if isinstance(f, dict):
        mw = el.get("maxw")
        maxw = _r(mw, W, H, margin) if mw is not None else W - 2 * margin
        if "fit" in f:  # 단일 라인 축소(카드뉴스)
            return _fit(text, maxw, f["fit"][0], f["fit"][1])
        if "fit_headline" in f:  # 1~2줄 허용 크기의 폰트만 취함(배너 catalog 단일 draw)
            return _fit_headline(text, maxw, f["fit_headline"][0], f["fit_headline"][1])[1]
    return _font(f, el.get("bold", False))


def _paste_image(canvas: Image.Image, el: dict, cuts: dict, W: int, H: int, margin: int,
                 mode: str = "round") -> None:
    at_x = _r(el["at"][0], W, H, margin)
    at_y = _r(el["at"][1], W, H, margin)
    sw = _r(el["size"][0], W, H, margin, base=at_x)
    sh = _r(el["size"][1], W, H, margin, base=at_y)
    img = _cover_img(Image.open(cuts[el["cut"]]).convert("RGB"), (sw, sh), mode)
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
            if "wrap" in el:  # 글자 수 기준(카드뉴스)
                lh = el.get("line_h", 40)
                for i, line in enumerate(_wrap(s, el["wrap"])):
                    draw.text((x, y0 + i * lh), line, font=font, fill=fill, spacing=el.get("spacing", 4))
            elif "wrap_px" in el:  # 픽셀 폭 기준(상세페이지 본문)
                maxw = _r(el["maxw"], W, H, margin) if isinstance(el.get("maxw"), list) else (W - 2 * margin)
                lines = _wrap_px(s, font, maxw)
                if "max_lines" in el:
                    lines = lines[:el["max_lines"]]
                lh = el.get("line_h", 40)
                for i, line in enumerate(lines):
                    draw.text((x, y0 + i * lh), line, font=font, fill=fill, spacing=el.get("spacing", 4))
            else:
                draw.text((x, y0), s, font=font, fill=fill, spacing=el.get("spacing", 4))
        elif t == "text_lines":  # 커머스 배너 헤드라인 — 1~2줄 자동 맞춤(fit_headline)
            s = _bind_text(el, copy)
            mw = el["maxw"]
            maxw = _r(mw, W, H, margin) if isinstance(mw, list) else mw
            lines, font = _fit_headline(s, maxw, el["fit_lines"][0], el["fit_lines"][1])
            x, y0 = rr(el["at"][0]), rr(el["at"][1])
            lh = _line_height(font)
            for i, line in enumerate(lines):
                draw.text((x, y0 + i * lh), line, font=font, fill=_color(el["color"], pal))
        elif t == "cta_pill":
            s = _bind_text(el, copy)
            _cta_pill(canvas, s, _font(el["font"], True), (rr(el["at"][0]), rr(el["at"][1])),
                      fill=_color(el["fill"], pal), fg=_color(el["fg"], pal))
        elif t == "bullets":  # 상세페이지 혜택 불릿(원+번호+텍스트) — 섹션 로컬 좌표
            items = list(getattr(copy, el["bind"], ()) or ())
            y0, row_h, fsize = el.get("y0", 96), el.get("row_h", 72), el.get("font", 27)
            for i, b in enumerate(items):
                row = y0 + i * row_h
                draw.ellipse((margin, row + 8, margin + 34, row + 42), fill=_color(el["dot"], pal))
                draw.text((margin + 9, row + 13), str(i + 1), font=_font(19, True), fill=_color(el["num"], pal))
                label = _fit_line(b, W - 2 * margin - 56, fsize)
                draw.text((margin + 56, row + 8), label, font=_font(fsize, True), fill=_color(el["color"], pal))
        elif t == "section_label":  # 상세페이지 섹션 라벨 바(번호 제거·텍스트 폭 맞춤)
            title = _bind_text(el, copy)
            light = el.get("light", False)
            box_fill = (*_NAMED["paper"], 232) if light else (*_NAMED["ink"], 205)
            tcol = (24, 24, 24) if light else (255, 255, 255)
            label = _fit_line(title, 520 - 68 - 24, 27)
            lf = _font(27, True)
            right = max(240, min(520, 68 + draw.textbbox((0, 0), label, font=lf)[2] + 36))
            draw.rectangle((44, 42, right, 145), fill=box_fill)
            draw.text((68, 68), label, font=lf, fill=tcol)
        else:
            raise ValueError(f"알 수 없는 요소 타입: {t}")


# --- 커머스 배너용 헬퍼(formats.banner 와 동일 — 정적 규격 DSL 이 재사용) ---------
def _split_two_lines(text: str) -> list[str]:
    words = text.split()
    if len(words) < 2:
        return [text]
    best = min(range(1, len(words)),
               key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def _ellipsize(text: str, font, max_width: int, draw) -> str:
    suffix = "…"
    value = text
    while value and draw.textbbox((0, 0), value + suffix, font=font)[2] > max_width:
        value = value[:-1]
    return (value.rstrip() + suffix) if value else suffix


def _fit_headline(text: str, max_width: int, max_size: int, min_size: int):
    clean = " ".join((text or "광고 이미지").split())
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(max_size, min_size - 1, -2):
        font = _font(size, True)
        if probe.textbbox((0, 0), clean, font=font)[2] <= max_width:
            return [clean], font
        lines = _split_two_lines(clean)
        if len(lines) == 2 and all(
            probe.textbbox((0, 0), line, font=font)[2] <= max_width for line in lines
        ):
            return lines, font
    font = _font(min_size, True)
    return [_ellipsize(clean, font, max_width, probe)], font


def _line_height(font) -> int:
    box = font.getbbox("가Ag")
    return int((box[3] - box[1]) * 1.28)


def _cta_pill(img: Image.Image, text: str, font, xy, pad: int = 20,
              fill=(255, 255, 255), fg=(20, 20, 20)) -> None:
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    tw, th = right - left, bottom - top
    x, y = xy
    box = [x, y, x + tw + 2 * pad, y + th + int(pad * 1.2)]
    radius = (box[3] - box[1]) // 2
    draw.rounded_rectangle(box, radius=radius, fill=fill)
    draw.text((x + pad, y + int(pad * 0.6)), text, font=font, fill=fg)


def render_slide(size: tuple[int, int], spec: dict, cuts: dict, copy, pal,
                 margin_ratio: float, cover_mode: str = "round") -> Image.Image:
    """슬라이드 스펙(bg + images + elements) → 완성 캔버스.

    bg: {"cut": "hero"}(컷 cover) | {"fill": "deep"}(단색). images: [{cut, at, size}].
    cover_mode: 컷 리사이즈 반올림('round'=카드뉴스/배너, 'int'=상세페이지).
    """
    W, H = size
    margin = int(W * margin_ratio)
    bg = spec.get("bg", {})
    if "cut" in bg:
        canvas = _cover_img(Image.open(cuts[bg["cut"]]).convert("RGB"), size, cover_mode)
    else:
        canvas = Image.new("RGB", size, _color(bg.get("fill", "white"), pal))
    for im in spec.get("images", []):
        _paste_image(canvas, im, cuts, W, H, margin, cover_mode)
    render_elements(canvas, spec.get("elements", []), copy, pal, W, H, margin)
    return canvas


# --- 세로 스택 페이지(상세페이지) — 섹션별 가변 높이 계산 후 미니 슬라이드로 스택 ------
def _fit_line(text: str, max_width: int, size: int) -> str:
    """폭 초과 한 줄 라벨을 말줄임(formats.detail_page._fit_line 과 동일)."""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    font = _font(size, True)
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    while text and draw.textbbox((0, 0), text + "…", font=font)[2] > max_width:
        text = text[:-1]
    return text + "…"


def _wrap_px(text: str, font, max_width: int) -> list[str]:
    """픽셀 폭 기준 어절 줄바꿈(formats.detail_page._wrap_px 과 동일)."""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines, current = [], ""
    for word in (text or "").split():
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _h_story(copy, width: int, margin: int) -> int:
    lines = _wrap_px(copy.story_body, _font(22), width - 2 * margin) if copy.story_body else []
    return max(390, 295 + max(len(lines), 1) * 38 + 90)


def _h_benefits(copy, width: int, margin: int) -> int:
    return 0 if not copy.benefit_bullets else 96 + len(copy.benefit_bullets) * 72 + 48


_HEIGHT_CALC = {"story": _h_story, "benefits": _h_benefits}


def _section_height(s: dict, copy, width: int, margin: int) -> int:
    h = s["height"]
    if isinstance(h, dict) and "calc" in h:
        return _HEIGHT_CALC[h["calc"]](copy, width, margin)
    return int(h)


def render_page(width: int, page: dict, cuts: dict, copy, pal, margin_ratio: float) -> Image.Image:
    """섹션들을 세로로 스택(상세페이지 롱스크롤). 각 섹션 = (width, 계산된 높이) 미니 슬라이드.

    가변 높이(story/benefits)는 카피 길이로 결정(_HEIGHT_CALC). 높이 0 섹션은 생략.
    """
    margin = int(width * margin_ratio)
    cm = page.get("cover_mode", "round")
    sections = page["sections"]
    heights = [_section_height(s, copy, width, margin) for s in sections]
    canvas = Image.new("RGB", (width, sum(heights)), _color(page.get("bg_fill", "white"), pal))
    y = 0
    for s, h in zip(sections, heights):
        if h <= 0:
            continue
        # 섹션별 margin override(예: hero 0.07) — 나머지는 page margin_ratio.
        sec = render_slide((width, h), s, cuts, copy, pal, s.get("margin_ratio", margin_ratio), cover_mode=cm)
        canvas.paste(sec, (0, y))
        y += h
    return canvas
