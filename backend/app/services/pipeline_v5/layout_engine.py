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
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

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


# 폰트 패밀리 — DSL font_family 로 선택(단조로움 해소·세련). 기본 sans=Pretendard.
_FONTS = {
    "sans": "Pretendard-Medium.otf",
    "sans_bold": "Pretendard-Bold.otf",
    "serif": "MaruBuri-Bold.ttf",          # 한글 명조(헤드라인 세련)
    "display": "PlayfairDisplay.ttf",      # 영문 매거진 세리프(키커)
    "grotesk": "SpaceGrotesk-Medium.ttf",  # 영문 모던
    "condensed": "BebasNeue-Regular.ttf",  # 임팩트 대문자 키커
}


# 스타일 원장 head_font/sub_font(kind) → 폰트 파일. '생성된 광고 스타일에 맞는 폰트'
# 자동 선택용(font_role: head/sub). styles/specs.yaml 의 kind 값과 1:1.
_KIND_FONTS = {
    "serif_elegant": "MaruBuri-Bold.ttf",      # 매거진 명조(editorial/realism/warm_vintage)
    "gothic": "Pretendard-Medium.otf",
    "gothic_bold": "Pretendard-Bold.otf",
    "display_heavy": "BlackHanSans-Regular.ttf",  # 볼드 임팩트(pop/monotone/object_studio)
    "display_round": "Jua-Regular.ttf",           # 둥근(pastel_float)
    "condensed": "Paperlogy-8ExtraBold.ttf",      # 콘덴스트 임팩트(pop_split/object_splash)
}


def _font(size: int, bold: bool = False, family: str | None = None,
          font_file: str | None = None) -> ImageFont.FreeTypeFont:
    root = Path(__file__).resolve().parents[3] / "assets" / "fonts"
    if font_file:
        name = font_file
    elif family:
        name = _FONTS.get(family, _FONTS["sans"])
    else:
        name = _FONTS["sans_bold"] if bold else _FONTS["sans"]
    return ImageFont.truetype(str(root / name), size)


def _style_font_file(ctx: dict | None, role: str) -> str | None:
    """ctx 의 style → styles/specs.yaml head_font/sub_font(kind) → 폰트 파일."""
    if not ctx or not ctx.get("style"):
        return None
    from ..style_specs import get_spec
    spec = get_spec(ctx["style"])
    kind = spec.head_font if role == "head" else spec.sub_font
    return _KIND_FONTS.get(kind)


def _fit(text: str, max_width: int, start: int, minimum: int,
         family: str | None = None, font_file: str | None = None) -> ImageFont.FreeTypeFont:
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(start, minimum - 1, -2):
        font = _font(size, True, family, font_file)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return _font(minimum, True, family, font_file)


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
    tf = el.get("transform")
    if tf == "first_sentence":
        return _first_sentence(val)
    if tf == "upper":
        return val.upper()
    return val


def _cond(el: dict, copy, ctx: dict | None = None) -> bool:
    """요소 표시 조건. if(copy 필드 truthy) + 콘텐츠 적응(L5): if_domain/unless_domain/if_density.

    ctx = {"domain": food|drink|object|cafe, "density": minimal|medium|dense}.
    조건을 안 붙인 요소는 항상 표시 → 기존 렌더 불변(픽셀 동등 유지).
    """
    ctx = ctx or {}
    key = el.get("if")
    if key and not getattr(copy, key, None):
        return False
    dom = ctx.get("domain")
    if "if_domain" in el and dom not in el["if_domain"]:
        return False
    if "unless_domain" in el and dom in el["unless_domain"]:
        return False
    if "if_density" in el and ctx.get("density") not in el["if_density"]:
        return False
    return True


def _font_of(el: dict, text: str, W: int, H: int, margin: int,
             ctx: dict | None = None) -> ImageFont.FreeTypeFont:
    fam = el.get("font_family")  # 고정 패밀리(serif/display/grotesk/condensed…)
    # font_role: head/sub → 스타일(ctx)에 맞는 폰트 자동 선택(스타일 원장 head_font/sub_font).
    ff = _style_font_file(ctx, el["font_role"]) if el.get("font_role") else None
    f = el["font"]
    if isinstance(f, dict):
        mw = el.get("maxw")
        maxw = _r(mw, W, H, margin) if mw is not None else W - 2 * margin
        if "fit" in f:  # 단일 라인 축소(카드뉴스)
            return _fit(text, maxw, f["fit"][0], f["fit"][1], fam, ff)
        if "fit_headline" in f:  # 1~2줄 허용 크기의 폰트만 취함(배너 catalog 단일 draw)
            return _fit_headline(text, maxw, f["fit_headline"][0], f["fit_headline"][1], font_file=ff)[1]
    return _font(f, el.get("bold", False), fam, ff)


def _paste_image(canvas: Image.Image, el: dict, cuts: dict, W: int, H: int, margin: int,
                 mode: str = "round") -> None:
    at_x = _r(el["at"][0], W, H, margin)
    at_y = _r(el["at"][1], W, H, margin)
    sw = _r(el["size"][0], W, H, margin, base=at_x)
    sh = _r(el["size"][1], W, H, margin, base=at_y)
    img = _cover_img(Image.open(cuts[el["cut"]]).convert("RGB"), (sw, sh), mode)
    canvas.paste(img, (at_x, at_y))


def render_elements(canvas: Image.Image, elements: list[dict], copy, pal,
                    W: int, H: int, margin: int, ctx: dict | None = None) -> None:
    """요소 리스트를 canvas 에 순서대로 렌더. canvas 는 이미 배경(컷 등) 배치된 상태.

    ctx = 콘텐츠 적응 컨텍스트(domain/density) — _cond 의 if_domain/if_density 판정용(L5).
    """
    draw = ImageDraw.Draw(canvas, "RGBA")

    def rr(v):
        return _r(v, W, H, margin)

    for el in elements:
        if not _cond(el, copy, ctx):
            continue
        t = el["type"]
        if t == "scrim":
            if "box" in el:  # 방향성 그라디언트(배너 솔리드 패널·바 대체) — box+anchor
                _grad_scrim(canvas, [rr(c) for c in el["box"]], _color(el["color"], pal),
                            el["amax"], el.get("anchor", "bottom"), el.get("fade_frac", 1.0))
            else:  # 기존 세로 밴드(frm/to+fade)
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
            font = _font_of(el, s, W, H, margin, ctx)
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
            ff = _style_font_file(ctx, el["font_role"]) if el.get("font_role") else None
            lines, font = _fit_headline(s, maxw, el["fit_lines"][0], el["fit_lines"][1], font_file=ff)
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


def _fit_headline(text: str, max_width: int, max_size: int, min_size: int,
                  font_file: str | None = None):
    clean = " ".join((text or "광고 이미지").split())
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(max_size, min_size - 1, -2):
        font = _font(size, True, font_file=font_file)
        if probe.textbbox((0, 0), clean, font=font)[2] <= max_width:
            return [clean], font
        lines = _split_two_lines(clean)
        if len(lines) == 2 and all(
            probe.textbbox((0, 0), line, font=font)[2] <= max_width for line in lines
        ):
            return lines, font
    font = _font(min_size, True, font_file=font_file)
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


# --- 이미지 인식 오버레이 배치(B) + 스타일 아키타입(A) ---------------------------
# 구도를 한 틀로 고정하지 않는다. bg-컷 섹션의 타이포는 (A) 스타일 원장 head_font(kind)로
# 정렬·라이트스크림 성향을 고르고, (B) 컷 이미지의 위/아래 밴드 중 '덜 복잡한(여백) 쪽'을
# 골라 스크림+글자를 얹는다. 같은 레이아웃이라도 광고 이미지마다 글자 위치·명암이 달라진다.
_OVERLAY_TRACE = None  # 진단용 훅: 리스트를 주입하면 _draw_overlay 가 배치 결정을 append(기본 무부하)
_ARCHETYPES = {
    # kind(head_font) → {정렬, 밝은영역에 검정글자 허용(에디토리얼 미니멀)}
    "serif_elegant": {"align": "left", "allow_light": True},    # editorial/warm_vintage/realism
    "display_heavy": {"align": "left", "allow_light": False},   # pop/monotone — 강한 임팩트
    "display_round": {"align": "center", "allow_light": True},  # pastel — 둥근·중앙
    "condensed": {"align": "left", "allow_light": False},       # pop_split/object_splash
    "gothic": {"align": "left", "allow_light": True},
    "gothic_bold": {"align": "left", "allow_light": True},
}


def _archetype(ctx: dict | None) -> dict:
    """ctx.style → 스타일 원장 head_font(kind) → 구도 아키타입(정렬·명암 성향)."""
    if ctx and ctx.get("style"):
        from ..style_specs import get_spec
        kind = get_spec(ctx["style"]).head_font
        return _ARCHETYPES.get(kind, _ARCHETYPES["gothic"])
    return _ARCHETYPES["gothic"]


def _band_stats(canvas: Image.Image, box: tuple) -> tuple[float, float]:
    """밴드의 (평균 밝기, 복잡도). 복잡도=엣지 강도 평균(높을수록 디테일 많음=글자 얹기 나쁨)."""
    region = canvas.crop(box).convert("L")
    lum = ImageStat.Stat(region).mean[0]
    busy = ImageStat.Stat(region.filter(ImageFilter.FIND_EDGES)).mean[0]
    return lum, busy


# 상단 밴드 선택 기준: (상대) 25%↑ 더 깔끔 AND (절대) 최소차↑. 근소차는 하단 우선(커머스 관습).
# 실측 튜닝(2026-07-24): 실사진 edge busy 스케일이 1~18로 압축돼 절대 bias 6은 과보수적(거의 항상
# 하단=단조) → 스케일 불변 상대 규칙 + 노이즈 방지 절대 하한. 실컷 3도메인 A/B 로 검증.
_BAND_REL = 0.75
_BAND_MIN = 2.0
_MASK_MIN = 13.0     # 마스크 점유 최소차(0~255, ≈5%p) — 제품이 뚜렷하게 적은 밴드만 상단 채택
_SIDE_SECTION = 115.0  # 좌우정렬은 컷 전체 점유율이 이 미만(≈45%, 여백 있는 컷)일 때만 — 꽉 찬 클로즈업 제외
_SIDE_EMPTY = 64.0    # 그리고 우측 점유율이 이 미만(≈25%, 진짜 여백)일 때만 우측 정렬(이중 안전)


def _choose_band(canvas: Image.Image, W: int, H: int, block_h: int, margin: int,
                 mask: Image.Image | None = None) -> tuple[str, float, float, float]:
    """텍스트 블록을 얹을 밴드(top/bottom) 선택. (band, 밝기, top_score, bot_score).

    mask(전경 누끼, L) 있으면 '제품 점유율'로 판정(정확) — 제품이 없는 밴드 우선.
    없으면 edge busy 휴리스틱(폴백). 둘 다 근소차는 하단 우선(커머스 관습).
    """
    span = max(1, min(H, block_h + 2 * margin))
    top_box, bot_box = (0, 0, W, span), (0, H - span, W, H)
    if mask is not None:  # 제품 점유율(마스크 평균, 0~255)이 뚜렷이 적은 밴드
        top_occ = ImageStat.Stat(mask.crop(top_box)).mean[0]
        bot_occ = ImageStat.Stat(mask.crop(bot_box)).mean[0]
        top_lum = _band_stats(canvas, top_box)[0]
        bot_lum = _band_stats(canvas, bot_box)[0]
        if top_occ < bot_occ * _BAND_REL and (bot_occ - top_occ) >= _MASK_MIN:
            return "top", top_lum, top_occ, bot_occ
        return "bottom", bot_lum, top_occ, bot_occ
    top_lum, top_busy = _band_stats(canvas, top_box)
    bot_lum, bot_busy = _band_stats(canvas, bot_box)
    if top_busy < bot_busy * _BAND_REL and (bot_busy - top_busy) >= _BAND_MIN:
        return "top", top_lum, top_busy, bot_busy
    return "bottom", bot_lum, top_busy, bot_busy


def _scrim_band(canvas: Image.Image, y0: int, y1: int, W: int, rgb: tuple,
                amax: int, fade: int, anchor: str) -> None:
    """방향 있는 페이드 스크림. anchor='bottom'=하단 불투명→위로 소멸, 'top'=상단 불투명→아래로 소멸."""
    h = int(y1 - y0)
    if h <= 0:
        return
    ramp = Image.new("L", (1, h))
    px = ramp.load()
    for i in range(h):
        dist = i if anchor == "top" else (h - 1 - i)  # 불투명 모서리로부터의 거리
        px[0, i] = int(amax * max(0.0, 1.0 - dist / max(1, fade)))
    overlay = Image.new("RGBA", (W, h), (rgb[0], rgb[1], rgb[2], 0))
    overlay.putalpha(ramp.resize((W, h)))
    region = canvas.crop((0, int(y0), W, int(y0) + h)).convert("RGBA")
    canvas.paste(Image.alpha_composite(region, overlay).convert("RGB"), (0, int(y0)))


def _grad_scrim(canvas: Image.Image, box: list, rgb: tuple, amax: int,
                anchor: str, fade_frac: float = 1.0) -> None:
    """박스 영역에 방향성 페이드 스크림(솔리드 블록 대체). anchor=top/bottom/left/right 모서리 불투명."""
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    if anchor in ("left", "right"):
        ramp = Image.new("L", (w, 1))
        px = ramp.load()
        span = max(1, int(w * fade_frac))
        for i in range(w):
            dist = i if anchor == "left" else (w - 1 - i)
            px[i, 0] = int(amax * max(0.0, 1.0 - dist / span))
    else:
        ramp = Image.new("L", (1, h))
        px = ramp.load()
        span = max(1, int(h * fade_frac))
        for i in range(h):
            dist = i if anchor == "top" else (h - 1 - i)
            px[0, i] = int(amax * max(0.0, 1.0 - dist / span))
    overlay = Image.new("RGBA", (w, h), (rgb[0], rgb[1], rgb[2], 0))
    overlay.putalpha(ramp.resize((w, h)))
    region = canvas.crop((x0, y0, x1, y1)).convert("RGBA")
    canvas.paste(Image.alpha_composite(region, overlay).convert("RGB"), (x0, y0))


def _overlay_lines(el: dict, copy, font, W: int, margin: int) -> list[str]:
    """헤드라인 줄 구성. font.fit(단일 축소)면 1줄, 아니면 픽셀 폭 줄바꿈."""
    text = _bind_text(el, copy)
    if isinstance(el.get("font"), dict):  # fit → 이미 폭에 맞춘 단일 라인
        return [text]
    return _wrap_px(text, font, W - 2 * margin)[: el.get("max_lines", 2)]


def _draw_overlay(canvas: Image.Image, ov: dict, copy, pal, W: int, H: int,
                  margin: int, ctx: dict | None, mask: Image.Image | None = None) -> None:
    """bg-컷 섹션 타이포를 이미지 인식(B)+아키타입(A)으로 얹는다. ov={kicker?, headline}.

    mask(전경 누끼, L·컷과 동일 cover): 있으면 밴드·좌우 정렬을 제품 점유율로 결정(제품 회피)."""
    arch = _archetype(ctx)
    align = arch["align"]
    head_el = ov["headline"]
    head_text = _bind_text(head_el, copy)
    if not head_text:
        return
    head_font = _font_of(head_el, head_text, W, H, margin, ctx)
    head_lines = _overlay_lines(head_el, copy, head_font, W, margin)
    lh = _line_height(head_font)

    kick_el = ov.get("kicker")
    kick_text = _bind_text(kick_el, copy) if kick_el else ""
    kick_font = _font_of(kick_el, kick_text, W, H, margin, ctx) if kick_el else None
    kh = _line_height(kick_font) if kick_text else 0
    gap = int(kh * 0.45)
    block_h = (kh + gap if kick_text else 0) + lh * len(head_lines)

    band, lum, top_score, bot_score = _choose_band(canvas, W, H, block_h, margin, mask)
    dark_on_light = arch["allow_light"] and lum > 178      # 밝고 깔끔한 영역엔 검정 글자(미니멀)
    text_col = _NAMED["ink"] if dark_on_light else _NAMED["white"]
    scrim_rgb = _NAMED["paper"] if dark_on_light else _NAMED["ink"]
    # 스크림 세기: 검정글자=약하게, 흰글자는 배경이 밝을수록 강하게.
    amax = 120 if dark_on_light else (215 if lum > 135 else 185)

    frac = 0.52
    if band == "top":
        y0, y1, anchor = 0, int(H * frac), "top"
        block_top = margin
    else:
        y0, y1, anchor = int(H * (1 - frac)), H, "bottom"
        block_top = H - margin - block_h

    # 좌우 정렬(마스크 전용): 좌측(기본)이 제품에 가리고 우측이 '진짜 비었을' 때만 우측 정렬.
    # 절대 여백 게이트(_SIDE_EMPTY)로 프레임 꽉 찬 클로즈업 오발동 방지.
    side = "left"
    if mask is not None and align != "center" and ImageStat.Stat(mask).mean[0] < _SIDE_SECTION:
        by0, by1 = block_top, min(H, block_top + block_h)
        left_occ = ImageStat.Stat(mask.crop((0, by0, W // 2, by1))).mean[0]
        right_occ = ImageStat.Stat(mask.crop((W // 2, by0, W, by1))).mean[0]
        if right_occ < _SIDE_EMPTY and right_occ + _MASK_MIN < left_occ:
            side = "right"
    if _OVERLAY_TRACE is not None:  # 진단용(기본 None·무부하): 배치 결정 기록
        _OVERLAY_TRACE.append({"head": head_text[:24], "band": band, "align": align, "side": side,
                               "lum": round(lum, 1), "top_score": round(top_score, 1),
                               "bot_score": round(bot_score, 1), "dark_on_light": dark_on_light,
                               "amax": amax, "lines": len(head_lines), "mask": mask is not None})

    _scrim_band(canvas, y0, y1, W, scrim_rgb, amax, int((y1 - y0) * 0.6), anchor)
    draw = ImageDraw.Draw(canvas, "RGBA")

    def _x(text: str, font) -> int:
        tw = draw.textbbox((0, 0), text, font=font)[2]
        if align == "center":
            return (W - tw) // 2
        if side == "right":
            return W - margin - tw
        return margin

    y = block_top
    if kick_text:
        kcol = pal["accent"] if dark_on_light else pal.get("tint", text_col)
        draw.text((_x(kick_text, kick_font), y), kick_text, font=kick_font, fill=kcol)
        y += kh + gap
    for line in head_lines:
        draw.text((_x(line, head_font), y), line, font=head_font,
                  fill=text_col, spacing=head_el.get("spacing", 4))
        y += lh


def render_slide(size: tuple[int, int], spec: dict, cuts: dict, copy, pal,
                 margin_ratio: float, cover_mode: str = "round", ctx: dict | None = None,
                 masks: dict | None = None) -> Image.Image:
    """슬라이드 스펙(bg + images + elements) → 완성 캔버스.

    bg: {"cut": "hero"}(컷 cover) | {"fill": "deep"}(단색). images: [{cut, at, size}].
    cover_mode: 컷 리사이즈 반올림('round'=카드뉴스/배너, 'int'=상세페이지). ctx: 콘텐츠 적응(L5).
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
    render_elements(canvas, spec.get("elements", []), copy, pal, W, H, margin, ctx)
    if spec.get("overlay"):  # bg-컷 타이포 — 이미지 인식 배치(B)+아키타입(A)
        cut = spec.get("bg", {}).get("cut")
        mimg = None
        if masks and cut and cut in masks:  # 전경 마스크 있으면 제품 회피 배치
            mimg = _cover_img(Image.open(masks[cut]).convert("L"), size, cover_mode)
        _draw_overlay(canvas, spec["overlay"], copy, pal, W, H, margin, ctx, mimg)
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


def render_page(width: int, page: dict, cuts: dict, copy, pal, margin_ratio: float,
                ctx: dict | None = None, masks: dict | None = None) -> Image.Image:
    """섹션들을 세로로 스택(상세페이지 롱스크롤). 각 섹션 = (width, 계산된 높이) 미니 슬라이드.

    가변 높이(story/benefits)는 카피 길이로 결정(_HEIGHT_CALC). 높이 0 섹션은 생략.
    ctx: 콘텐츠 적응(domain/density) — 요소 조건(if_domain 등)에 전달(L5).
    masks: {컷명: 전경 누끼 경로} — 있으면 오버레이 배치가 제품을 회피(정확).
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
        sec = render_slide((width, h), s, cuts, copy, pal, s.get("margin_ratio", margin_ratio),
                           cover_mode=cm, ctx=ctx, masks=masks)
        canvas.paste(sec, (0, y))
        y += h
    return canvas
