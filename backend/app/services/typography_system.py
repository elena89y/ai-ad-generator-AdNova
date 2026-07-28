"""타이포 시스템 v0 조판기 — 코퍼스 파생 레지스트리(TS-1~3b) + 구도 자동 분기.

근거: ~/Desktop/AdNova/템플릿_프롬프트/11_타이포_시스템_v0.md (2026-07-21 아트디렉터 판정:
전 스타일 채택 + 구도별 자동 분기). overlay_service 기본 룩(키커+명조 오버레이)은
템플릿·홈페이지 사용 금지 판정이라 이 모듈이 그 자리를 대체한다.

역할 분리 원칙 유지: 여기는 전부 코드(PIL) 조판 — 생성 모델은 관여하지 않는다.
z-order 가림(TS-1)은 v0에서 배경 균일색 거리 마스크로 근사한다. 스튜디오/단색 배경에서
잘 동작하고, 마스크 신뢰도가 낮은 복잡 배경은 분기 단계에서 TS-1이 선택되지 않으므로
rembg 왕복 비용 없이 안전하다 (busy 배경 → bg fraction 낮음 → TS-3b 폴백).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

# 레지스트리 키 (schema typography.layers[].font_class 와 일치)
TS1_BG_LETTERING = "ts1_bg_lettering"
# TS-1_2 = TS-1과 동일한 배경 레터링 구조(투명 z-order·중앙 배치·배경적응 색)이되
#   입력 상품명을 **언어 그대로** 렌더한다(한글→BlackHanSans, 영문→Anton). 음식·사물 전용.
#   기존 TS-1(베이커리·음료=영문 subject_en)은 건드리지 않기 위한 별도 구조 (2026-07-26 지시).
TS1_2_BG_LETTERING = "ts1_2_bg_lettering"
TS2_EDITORIAL_SERIF = "ts2_editorial_serif"
TS3_KOREAN_BLOCK = "ts3_korean_block"
TS3B_PANEL = "ts3b_panel"
# TS-DISH = 음식점 savory 접시 전용 캡션 밴드 조판. 배경 레터링(TS-1_2)이 접시 매몰·마스크
#   의존·데드존으로 취약해, dish는 피사체와 겹치지 않는 고정 밴드로 간다 (2026-07-26 지시).
TS_DISH_BAND = "ts_dish_band"

# 배경 레터링 가독 하한 — 이 아래면 더 열린 띠로 이동(긴 라벨이 히어로에 조각나는 것 방지).
_BAND_MIN_VIS = 0.55

# TS-1_2 배경 레터링 알파(0~255) — 불투명 솔리드가 아니라 배경에 스며드는 반투명.
#   접시(마스크 밖)에 걸쳐도 하드 블록이 아닌 은은한 오버레이로 읽히게 한다 (2026-07-26 지시).
_BG_LETTER_ALPHA = 150


@dataclass(frozen=True)
class TypoPlan:
    """분기 결과 — 어떤 스타일로, 어떤 텍스트를 조판할지."""

    style: str
    head: str
    sub: str


@dataclass(frozen=True)
class MoodTypo:
    """무드별 타이포 파인튜닝 단위 (2026-07-26 지시: 무드별로 쪼개 앞으로 개별 설정).

    **역할 분리**: 위치/레이아웃(밴드 상하·배경레터링 중앙 등)은 *도메인*이 정하고, 여기서는
    무드 고유의 '타이포 표정' — 글씨체·자간 — 만 설정한다. 무드마다 이 한 줄만 바꾸면 튜닝 끝.
    - head_ko/head_en : 대형 헤드라인(TS-1·TS-1_2·TS-DISH·TS-3·TS-3b) 한글/영문 폰트
    - sig_en          : TS-2 우하단 시그니처 폰트(에디토리얼 세리프 자리)
    - tracking        : 대형 헤드라인 추가 자간(비율)
    """

    head_ko: str = "BlackHanSans-Regular.ttf"
    head_en: str = "Anton-Regular.ttf"
    sig_en: str = "PlayfairDisplay.ttf"
    tracking: float = 0.0


_MOOD_TYPO_DEFAULT = MoodTypo()

# 무드별 타이포 레지스트리 — 앞으로 각 무드 줄만 수정해 파인튜닝. 미등록/불명 무드는 기본값.
_MOOD_TYPO: dict[str, MoodTypo] = {
    # 에디토리얼 = 세련된 필기체 (2026-07-26 아트디렉터 확정):
    #   영문 = Dancing Script(세련+가독+바운시), 한글 = Diphylleia(가늘고 섬세한 명조 흘림).
    #   둘 다 OFL. Dancing Script는 라틴 전용이라 한글은 Diphylleia가 받는다.
    "editorial": MoodTypo(head_ko="Diphylleia-Regular.ttf",
                          head_en="DancingScript.ttf",
                          sig_en="DancingScript.ttf"),
    # 아래 5무드는 현재 기본(BlackHanSans/Anton/Playfair) — 추후 무드별 글씨체 지정 예정
    "pop": MoodTypo(),
    "monotone": MoodTypo(),
    "pastel": MoodTypo(),
    "realism": MoodTypo(),
    "warm_organic": MoodTypo(),
}


def mood_typo(mood: str) -> MoodTypo:
    """무드 키 → MoodTypo (불명/결측은 기본값). 대소문자 무시."""
    return _MOOD_TYPO.get((mood or "").strip().lower(), _MOOD_TYPO_DEFAULT)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_DIR / name), max(12, int(size)))


def _fit_width(draw: ImageDraw.ImageDraw, text: str, fname: str,
               target_w: float, spacing: float = 0.0) -> ImageFont.FreeTypeFont:
    """target_w 이하로 들어가는 최대 폰트 크기 탐색 (자간 비율 포함)."""
    size = 400
    while size > 16:
        f = _font(fname, size)
        w = draw.textlength(text, font=f) + spacing * size * max(0, len(text) - 1)
        if w <= target_w:
            return f
        size -= 6
    return _font(fname, 16)


def _spaced_text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
                 f: ImageFont.FreeTypeFont, fill, spacing_frac: float) -> None:
    x, y = xy
    sp = f.size * spacing_frac
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f) + sp


def _bg_color(img: Image.Image) -> tuple[int, int, int]:
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    corners = np.concatenate([a[:40, :40].reshape(-1, 3), a[:40, -40:].reshape(-1, 3)])
    return tuple(int(c) for c in corners.mean(axis=0))


def _subject_mask(img: Image.Image) -> np.ndarray:
    """배경 균일색 거리 마스크 (True=피사체). 단색·스튜디오 배경 전용 근사.

    소프트 그라데이션 배경(FLUX/Kontext 씬)에서 과민해지지 않도록, 테두리 링의
    거리 분포 90퍼센타일을 노이즈 플로어로 삼는 적응형 임계값을 쓴다 (07-21 실측:
    고정 30은 아메리카노 씬의 배경 비네팅을 피사체로 오인 → TS-1 분기 실패).
    """
    a = np.asarray(img.convert("RGB"), dtype=np.int16)
    h, w = a.shape[:2]
    corners = np.concatenate([a[:40, :40].reshape(-1, 3), a[:40, -40:].reshape(-1, 3),
                              a[-40:, :40].reshape(-1, 3), a[-40:, -40:].reshape(-1, 3)])
    bg = corners.mean(axis=0)
    dist = np.abs(a - bg).sum(axis=2)
    m = max(8, int(min(h, w) * 0.06))
    ring = np.concatenate([dist[:m].ravel(), dist[-m:].ravel(),
                           dist[:, :m].ravel(), dist[:, -m:].ravel()])
    thresh = float(np.percentile(ring, 90)) + 22.0
    return dist > thresh


def _subject_mask_precise(img: Image.Image) -> np.ndarray:
    """TS-1 z-order 가림용 정밀 마스크 — 스펙(렌더→누끼 재합성)대로 rembg 우선.

    워커에는 birefnet 세션이 상주하므로 추가 로드 비용이 거의 없다. rembg 미설치/
    가중치 없는 로컬 환경에서는 색거리 근사로 폴백 (시안·테스트 용도로 충분).
    """
    try:
        from rembg import remove

        from .image_service import _get_rembg_session

        alpha = remove(img.convert("RGB"), session=_get_rembg_session(), only_mask=True)
        return np.asarray(alpha.convert("L")) > 96
    except Exception:
        return _subject_mask(img)


# Z-ORDER 히어로 한정(2026-07-28 아트디렉터: "소품은 피사체로 잡지 말고 배경으로 볼 것").
#   rembg 는 전경 전체를 분할해 금색 오브제·소품까지 피사체로 잡는다 → 배경 레터링이 소품 뒤로
#   숨어 글자가 잘린 것처럼 보였다(말차베리쿠키 "MATCHA BERRY COO" 실측). 가장 큰 덩어리를
#   히어로로 보고, 그에 견줘 작은 덩어리(소품)는 배경으로 돌린다.
#   임계 0.60: 실측 소품은 히어로의 3~26%(금색 오브제 26%가 0.25를 아슬하게 통과해 글자를
#   먹었다) — 반면 접시 위 여러 개 히어로(쿠키 무더기)는 서로 비슷한 크기라 0.60 위로 남는다.
_HERO_MIN_RATIO = 0.60


def _hero_only(mask: np.ndarray) -> np.ndarray:
    """마스크에서 히어로 덩어리만 남긴다(소품=배경). scipy 없으면 원본 유지(무해 폴백)."""
    try:
        from scipy import ndimage
    except Exception:
        return mask
    lab, n = ndimage.label(mask)
    if n <= 1:
        return mask
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    biggest = float(sizes.max())
    if biggest <= 0:
        return mask
    keep = {i + 1 for i, sz in enumerate(sizes) if sz >= _HERO_MIN_RATIO * biggest}
    return np.isin(lab, list(keep))


def _is_light(color: tuple[int, int, int]) -> bool:
    r, g, b = color
    return (0.299 * r + 0.587 * g + 0.114 * b) > 140


def _ink_for(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """배경 밝기에 따른 잉크색 — 밝으면 웜 차콜, 어두우면 크림."""
    return (30, 27, 24) if _is_light(bg) else (248, 244, 236)


def select_style(img: Image.Image, has_english: bool, domain: str = "food") -> str:
    """구도 분석으로 스타일 자동 분기 (v0 휴리스틱, 판정 07-21).

    상단 1/3에 배경이 넉넉하면 TS-1(배경 레터링), 우하단 코너가 비면 TS-2(에디토리얼),
    그 외(탑뷰 풀플레이트 등)는 캔버스 확장 패널 TS-3b — 겹침 제로라 항상 안전.

    음식점 dish(domain=="food")는 배경 레터링이 접시 매몰·마스크 취약으로 부적합 → 전용
    캡션 밴드 TS-DISH 로 간다. 사물(object)은 스튜디오 단품이라 배경 레터링 TS-1_2 유지.
    (bakery/dessert/drink 는 _typography_domain 이 별도 값으로 빼 아래 geometry 분기를 탄다.)
    2026-07-26 지시.
    """
    if domain == "food":            # 음식점 savory 접시 → 견고 밴드
        return TS_DISH_BAND
    if domain == "object":          # 사물 → 배경 레터링(입력명 그대로)
        return TS1_2_BG_LETTERING
    mask = _subject_mask(img)
    h, w = mask.shape
    top_bg = 1.0 - float(mask[: int(h * 0.32)].mean())
    # TS-1 판별은 레터링 라인(y 0.20~0.40) 높이의 피사체 '폭' — 탑뷰 접시(~85%)는
    # 글자가 다 가려지고, 측면 음료(~40%)는 글자가 양옆으로 살아난다 (07-21 실측)
    band_subject = float(mask[int(h * 0.20): int(h * 0.40)].mean())
    corner = mask[int(h * 0.78):, int(w * 0.62):]
    corner_bg = 1.0 - float(corner.mean())
    if has_english and band_subject < 0.45:
        return TS1_BG_LETTERING
    if has_english and corner_bg > 0.85:
        return TS2_EDITORIAL_SERIF
    if top_bg > 0.88:
        return TS3_KOREAN_BLOCK
    return TS3B_PANEL


def render_ts1(img: Image.Image, head_en: str,
               typo: MoodTypo = _MOOD_TYPO_DEFAULT) -> Image.Image:
    """TS-1 대형 배경 레터링 — 한 줄, 피사체가 글자를 가린다(z-order).

    글씨체는 무드 레지스트리(typo)에서 온다: 영문=typo.head_en, 한글=typo.head_ko.
    """
    im = img.convert("RGB")
    w, h = im.size
    layer = im.copy()
    d = ImageDraw.Draw(layer)
    fname = typo.head_en if head_en.isascii() else typo.head_ko
    f = _fit_width(d, head_en, fname, w * 0.86)
    tw = d.textlength(head_en, font=f)
    bg = _bg_color(im)
    # 스펙: 크림·아이보리·베이지 (순백 금지). 밝은 배경에선 대비 위해 소프트 베이지 딥톤.
    fill = (196, 168, 138) if _is_light(bg) else (240, 233, 220)
    # READABLE-BAND(2026-07-28): 18자 캡 제거(#332) 후 긴 영문 라벨이 히어로에 가운데를 먹혀
    #   "BLUE___M CAKE"처럼 조각났다(실측). 짧은 라벨은 기존대로 두고, 기본 띠(y0.30)의 배경
    #   가시율이 낮을 때만 더 열린 띠로 옮긴다 — TS-1_2 에서 검증된 적응형 배치와 동일 원리.
    mask_arr = _hero_only(_subject_mask_precise(im))
    bb = d.textbbox((0, 0), head_en, font=f)
    ink_top, ink_h = bb[1], max(1, bb[3] - bb[1])
    x0, x1 = max(0, int((w - tw) / 2)), min(w, int((w + tw) / 2))

    def _band_vis(center_frac: float) -> tuple[float, int]:
        top = int(h * center_frac) - (ink_top + ink_h // 2)
        top = max(0, min(h - ink_h - ink_top, top))
        strip = mask_arr[top + ink_top: top + ink_top + ink_h, x0:x1]
        return (1.0 - float(strip.mean()) if strip.size else 1.0), top

    vis, draw_top = _band_vis(0.30)
    if vis < _BAND_MIN_VIS:
        cands = [(round(v, 2), -fr, t) for fr in (0.30, 0.12, 0.16, 0.20, 0.80, 0.86)
                 for v, t in [_band_vis(fr)]]
        draw_top = max(cands)[2]
    d.text(((w - tw) / 2, draw_top), head_en, font=f, fill=fill)
    mask_img = Image.fromarray((mask_arr * 255).astype(np.uint8))
    layer.paste(im, (0, 0), mask_img)
    return layer


def render_ts1_2(img: Image.Image, head: str,
                 typo: MoodTypo = _MOOD_TYPO_DEFAULT) -> Image.Image:
    """TS-1_2 — TS-1과 **동일 구조**(투명 z-order 가림·중앙 배치·배경적응 크림/베이지색)를
    쓰되, 입력 상품명을 언어 그대로 렌더한다(글씨체는 무드 typo: 한글 head_ko / 영문 head_en).

    사물 전용(음식 dish는 TS-DISH 밴드로 분리됨). 기존 TS-1(음료·베이커리)은 손대지 않는다.

    **탑뷰 적응 배치**(2026-07-26 지시, TS-3b 폴백 대신): 기본 위치(y≈0.30)를 피사체가
    크게 가리면 레터링을 **배경이 열린 세로 위치로 이동**해 헤드라인이 묻히지 않게 한다.
    """
    im = img.convert("RGB")
    w, h = im.size
    layer = im.copy()
    d = ImageDraw.Draw(layer)
    fname = typo.head_en if head.isascii() else typo.head_ko
    f = _fit_width(d, head, fname, w * 0.86)
    bb = d.textbbox((0, 0), head, font=f)
    tw = bb[2] - bb[0]
    ink_top, ink_h = bb[1], max(1, bb[3] - bb[1])
    bg = _bg_color(im)
    # 스펙: 크림·아이보리·베이지 (순백 금지). 밝은 배경엔 소프트 베이지 딥톤.
    fill = (196, 168, 138) if _is_light(bg) else (240, 233, 220)
    mask = _hero_only(_subject_mask_precise(im))
    x = (w - tw) / 2
    x0, x1 = max(0, int(x)), min(w, int(x + tw))

    def _place(center_frac: float) -> tuple[float, int]:
        """잉크 세로 중심을 center_frac 에 두는 draw-top 과 그 위치의 배경 가시율."""
        top = int(h * center_frac) - (ink_top + ink_h // 2)
        top = max(0, min(h - ink_h - ink_top, top))
        strip = mask[top + ink_top: top + ink_top + ink_h, x0:x1]
        vis = 1.0 - float(strip.mean()) if strip.size else 1.0
        return vis, top

    vis_default, top_default = _place(0.30)
    if vis_default >= 0.45:
        draw_top = top_default          # 3/4뷰: 스펙 기본 위치(부분 가림이 오히려 자연)
    else:
        # 탑뷰: 배경이 가장 열린 위치로 이동, 근소차면 위쪽(헤드라인) 우선
        cands = [0.30, 0.12, 0.16, 0.20, 0.24, 0.76, 0.82, 0.88]
        scored = []
        for fr in cands:
            vis, top = _place(fr)
            scored.append((round(vis, 2), -fr, top))
        draw_top = max(scored)[2]
    # 반투명 배경 레터링(알파 블렌드) — 불투명 솔리드가 아니라 배경에 스며든다.
    #   접시(마스크 밖)에 걸쳐도 하드 블록이 아닌 은은한 오버레이로 읽힌다.
    txt = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(txt).text((x, draw_top), head, font=f, fill=(*fill, _BG_LETTER_ALPHA))
    out = Image.alpha_composite(im.convert("RGBA"), txt).convert("RGB")
    # z-order: 피사체(음식)를 글자 위로 완전 복원
    out.paste(im, (0, 0), Image.fromarray((mask * 255).astype(np.uint8)))
    return out


def render_ts_dish_band(img: Image.Image, head: str, sub: str,
                        typo: MoodTypo = _MOOD_TYPO_DEFAULT) -> Image.Image:
    """TS-DISH — 음식점 savory 접시 전용 캡션 밴드 (2026-07-26 지시, 배경 레터링 대체).

    배경 레터링은 접시 탑뷰/오프센터에서 헤드라인이 매몰되고 마스크(음식만 누끼)에 의존해
    취약하다. dish는 대신 **음식이 적은 쪽(상/하 자동 선택)** 에 소프트 그라데이션 스크림
    밴드를 깔고 상품명 헤드라인을 얹는다 — 어떤 구도에서도 피사체와 안 겹치고 항상 읽힌다.

    헤드라인은 **폭 72%(크기 M)**로 채우고, 밴드 높이는 그 헤드라인에 맞춰 늘어난다
    (짧은 이름 세로 길어짐 해결 07-26 → 07-27 "음식이 돋보이게" 판정으로 92%→72% 축소).
    서브카피는 렌더하지 않는다.
    """
    im = img.convert("RGB")
    w, h = im.size
    # 음식이 적은 쪽에 밴드 배치(히어로를 안 가리게). 마스크 실패 시 하단 기본.
    try:
        mask = _hero_only(_subject_mask_precise(im))
        at_top = float(mask[:int(h * 0.26)].mean()) <= float(mask[int(h * 0.74):].mean())
    except Exception:
        at_top = False
    # 헤드라인 크기 M: 폭 72% + 높이 18% 상한(짧은 이름 과대 방지).
    #   글씨체는 무드 typo(한글 head_ko / 영문 head_en).
    dish_font = typo.head_en if head.isascii() else typo.head_ko
    d0 = ImageDraw.Draw(im)
    # 크기 M(2026-07-27 아트디렉터 확정): 폭 72%·높이 18% — 음식이 주인공, 헤드라인은 캡션.
    #   (구 92%/28%는 헤드라인이 화면을 지배 — "글자 너무 크다, 음식이 돋보이게" 판정)
    f = _fit_width(d0, head, dish_font, w * 0.72, spacing=-0.02)
    while f.size > 16:
        bb = d0.textbbox((0, 0), head, font=f)
        if bb[3] - bb[1] <= int(h * 0.18):
            break
        f = _font(dish_font, f.size - 6)
    bb = d0.textbbox((0, 0), head, font=f)
    tw, ih, itop = bb[2] - bb[0], bb[3] - bb[1], bb[1]
    # 밴드 높이 = 헤드라인 + 상하 여백 (헤드라인에 맞춰 적응)
    pad = int(ih * 0.44)
    bh = ih + pad * 2
    scr = np.zeros((bh, w, 4), np.uint8)
    scr[..., :3] = (18, 16, 14)
    ramp = np.linspace(0, 205, bh).astype(np.uint8)   # 밴드 안쪽 진함→이미지쪽 페이드
    scr[..., 3] = (ramp[::-1] if at_top else ramp)[:, None]
    out = im.convert("RGBA")
    out.alpha_composite(Image.fromarray(scr, "RGBA"), (0, 0 if at_top else h - bh))
    d = ImageDraw.Draw(out)
    band_top = 0 if at_top else h - bh
    _spaced_text(d, ((w - tw) / 2, band_top + pad - itop), head, f, (245, 240, 230), -0.02)
    return out.convert("RGB")


def render_ts2(img: Image.Image, head_en: str, sub_kr: str,
               typo: MoodTypo = _MOOD_TYPO_DEFAULT) -> Image.Image:
    """TS-2 에디토리얼 시그니처 — 우하단 대문자(자간 9%). 글씨체는 무드 typo.sig_en
    (기본 Playfair 세리프, editorial 무드는 NanumPen 필기체)."""
    im = img.convert("RGB")
    d = ImageDraw.Draw(im)
    w, h = im.size
    ink = _ink_for(_bg_color(im))
    f = _fit_width(d, head_en, typo.sig_en, w * 0.30, spacing=0.09)
    tw = d.textlength(head_en, font=f) + 0.09 * f.size * (len(head_en) - 1)
    x, y = w - tw - int(w * 0.035), int(h * 0.905)
    _spaced_text(d, (x, y), head_en, f, ink, 0.09)
    if sub_kr:
        sf = _font("NanumPenScript-Regular.ttf", int(f.size * 1.15))
        sw = d.textlength(sub_kr, font=sf)
        d.text((w - sw - int(w * 0.035), y - sf.size - 4), sub_kr, font=sf, fill=ink)
    return im


def render_ts3(img: Image.Image, head_kr: str, sub_kr: str,
               typo: MoodTypo = _MOOD_TYPO_DEFAULT) -> Image.Image:
    """TS-3 한글 블록 — 초대형 상단(글씨체 무드 typo.head_ko) + 좌하단 룰·소카피."""
    im = img.convert("RGB")
    d = ImageDraw.Draw(im)
    w, h = im.size
    ink = _ink_for(_bg_color(im))
    f = _fit_width(d, head_kr, typo.head_ko, w * 0.90, spacing=-0.02)
    _spaced_text(d, (int(w * 0.05), int(h * 0.012)), head_kr, f, ink, -0.02)
    if sub_kr:
        sf = _font("Pretendard-Medium.otf", int(h * 0.028))
        sx, sy = int(w * 0.05), int(h * 0.935)
        d.line([(sx, sy + sf.size // 2), (sx + int(w * 0.10), sy + sf.size // 2)],
               fill=ink, width=3)
        d.text((sx + int(w * 0.12), sy), sub_kr, font=sf, fill=ink)
    return im


def render_ts3b(img: Image.Image, head_kr: str, sub_kr: str,
                typo: MoodTypo = _MOOD_TYPO_DEFAULT) -> Image.Image:
    """TS-3b 패널 확장 — 캔버스를 위로 늘려 단색 패널에 블록 타이포 (글씨체 무드 typo.head_ko)."""
    im = img.convert("RGB")
    w, h = im.size
    bg = _bg_color(im)
    ink = _ink_for(bg)
    # 패널 높이는 내용(헤드+서브) 실측으로 계산 — 고정 비율은 서브가 밀려나옴 (07-21 실측)
    probe = ImageDraw.Draw(im)
    f = _fit_width(probe, head_kr, typo.head_ko, w * 0.88, spacing=-0.02)
    sub_h = int(f.size * 0.62) if sub_kr else 0
    panel_h = int(f.size * 0.34 + f.size * 1.22 + sub_h + f.size * 0.30)
    canvas = Image.new("RGB", (w, h + panel_h), bg)
    canvas.paste(im, (0, panel_h))
    d = ImageDraw.Draw(canvas)
    tw = d.textlength(head_kr, font=f) - 0.02 * f.size * max(0, len(head_kr) - 1)
    ty = int(f.size * 0.34)
    _spaced_text(d, ((w - tw) / 2, ty), head_kr, f, ink, -0.02)
    if sub_kr:
        kf = _font("Pretendard-Medium.otf", int(f.size * 0.30))
        kw = d.textlength(sub_kr, font=kf)
        ky = ty + int(f.size * 1.22)
        lw, gap = int(w * 0.07), int(w * 0.02)
        cx = (w - kw) / 2
        mid = ky + kf.size // 2
        d.line([(cx - gap - lw, mid), (cx - gap, mid)], fill=ink, width=2)
        d.text((cx, ky), sub_kr, font=kf, fill=ink)
        d.line([(cx + kw + gap, mid), (cx + kw + gap + lw, mid)], fill=ink, width=2)
    return canvas


def plan_typography(img: Image.Image, product_name: str, copy_headline: str,
                    subject_en: str, domain: str = "food") -> TypoPlan:
    """텍스트 소스·스타일 분기 — 도메인별 (2026-07-26 아트디렉터 지시).

    **서브카피는 넣지 않는다 — 오직 상품명(헤드라인)만** ('한 그릇의 깊은 품격' 류 카피 제거 지시).
    - **음식점 dish(food)**: 입력 상품명(언어 그대로) → 캡션 밴드 TS-DISH.
    - **사물(object)**: 입력 상품명(언어 그대로) → 배경 레터링 TS-1_2.
    - **음료/베이커리(원래대로)**: 영문 라벨(subject_en) 헤드라인 + 기존 geometry 분기.
    """
    if domain in ("food", "object"):
        # 입력명 그대로. subject_en(영문 번역) 치환 없음. 없을 때만 라벨→카피 폴백.
        head = (product_name or "").strip() or (subject_en or "").strip() \
            or (copy_headline or "").strip()
        style = select_style(img, has_english=head.isascii(), domain=domain)
        if head.isascii():          # 영문 입력명만 올캡스(배경 레터링 스펙), 한글은 그대로
            head = head.upper()
        return TypoPlan(style=style, head=head, sub="")

    # ---- 원래대로 (음료/베이커리): 영문 라벨 헤드라인 + geometry 분기 ----
    head_en = (subject_en or "").strip().upper()
    # ENG-LABEL-NO-CAP(2026-07-28): 규약 "음료·디저트=영문 통일"에 맞춰 영문 라벨이 있으면 항상
    #   영문. 기존 <=18자 캡은 2~3단어 디저트명(BLUEBERRY CREAM CAKE=20·MATCHA BERRY COOKIE=19)을
    #   탈락시켜 한글로 폴백하던 버그. render_ts1 이 _fit_width 로 폭에 맞춰 축소하므로 길이 무해.
    #   subject_en 은 analyze_menu 계약상 2~6단어라 초장문도 아님.
    has_english = len(head_en) > 0
    style = select_style(img, has_english, domain)
    head_kr = (product_name or "").strip() or (copy_headline or "").strip()
    if style == TS2_EDITORIAL_SERIF:
        return TypoPlan(style=style, head=head_en, sub="")
    # 베이커리·음료는 **영문으로 통일**(2026-07-27: 홀초코케이크 pop이 TS-3b로 새 한글로
    #   나오던 영/한 혼재 제거). 영문 라벨이 있으면 geometry가 한글 블록(TS-3/3b)을 골라도
    #   TS-1 영문 배경 레터링으로 강제한다. 라벨이 없을 때만 한글 폴백.
    if has_english:
        return TypoPlan(style=TS1_BG_LETTERING, head=head_en, sub="")
    return TypoPlan(style=style, head=head_kr, sub="")


def render_typography(image_path: str, out_path: str, product_name: str,
                      copy_headline: str, subject_en: str = "",
                      domain: str = "food", mood: str = "") -> str:
    """조판기 v0 진입점 — 스타일 자동 분기 후 렌더, 실패 시 TS-3b 폴백.

    레이아웃/위치는 도메인이(plan_typography), 글씨체는 무드가(mood_typo) 정한다.
    반환: 사용한 스타일 키 (로그·실험 기록용).
    """
    img = Image.open(image_path)
    plan = plan_typography(img, product_name, copy_headline, subject_en, domain)
    typo = mood_typo(mood)          # 무드별 글씨체 파인튜닝 레지스트리
    try:
        if plan.style == TS1_BG_LETTERING:
            out = render_ts1(img, plan.head, typo)
        elif plan.style == TS1_2_BG_LETTERING:
            out = render_ts1_2(img, plan.head, typo)
        elif plan.style == TS_DISH_BAND:
            out = render_ts_dish_band(img, plan.head, plan.sub, typo)
        elif plan.style == TS2_EDITORIAL_SERIF:
            out = render_ts2(img, plan.head, plan.sub, typo)
        elif plan.style == TS3_KOREAN_BLOCK:
            out = render_ts3(img, plan.head, plan.sub, typo)
        else:
            out = render_ts3b(img, plan.head, plan.sub, typo)
        used = plan.style
    except Exception:
        # 어떤 입력에서도 죽지 않는다 — 패널은 소스와 무관하게 항상 성립
        out = render_ts3b(img, (product_name or copy_headline or "").strip() or " ",
                          "", typo)
        used = TS3B_PANEL
    out.save(out_path)
    return used
