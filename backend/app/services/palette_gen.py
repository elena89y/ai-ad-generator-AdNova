"""제품 적응형 팝 팔레트 생성기 (PALETTE-ADAPT v1, PAL-001) — 담당: 한의정.

설계 단일 진실 원천: `~/ai-ad-generator-AdNova-rule/제품적응형_팔레트_설계_v1.md`.

배경: 기존 `reference_style_plans._POP_PALETTES` 는 상품과 무관한 보색 3종을 이름 해시로
고르는 고정 리스트였다(초코 케이크가 코발트+토마토레드를 받은 원인). 이 모듈은 그 고정
리스트를 대체해, **입력 제품 색에서 런타임으로** 팝 배경 팔레트 문구를 생성한다.

원칙(설계 §1~§4):
  - 2축: ①제품 색(이미지 추출) × ②제품군(SOFT/RICH/ZESTY/PUNCHY/OBJECT)
  - 제품군이 하모니 레시피 세트를 정하고, seed 로 로테이션(같은 상품도 재생성마다 다른 조합)
  - 부드러운 것(SOFT/RICH)=제품 색 조화 / 상큼·통통(ZESTY/PUNCHY)=보색을 다양하게
  - 60‑30‑10(배경 지배 + 계열/뉴트럴 보조), 식욕 게이트(고형 음식 뒤 파랑 큰 면 금지)
  - 소프트코딩: 고정 색 리스트 없음. config = 레시피 오프셋 + 제품군 envelope 뿐.

의존성 최소화(v1): PIL + colorsys + stdlib 만. (HSLuv 지각공간·WCAG 대비게이트·ΔE 는 v1.1 개선
항목 — 설계 §7. 지금은 colorsys HSV 로 근사하되 그 한계를 주석에 명시.)

출력: 기존 팔레트 문구와 같은 형태의 영어 절 —
  "a {qual} {hue} background and a clean {qual} {hue} table surface"
scene 프롬프트(영어)에 그대로 주입된다. 제품(음식) 색은 절대 안 건드린다(정직성 경계).
"""
from __future__ import annotations

import colorsys
import hashlib
import re
from pathlib import Path
from typing import Optional

# --- 제품군 분류 어휘 (subject_en 영문 기반, food_mode/domain 보조) --------------
# 우선순위: OBJECT → ZESTY → PUNCHY → RICH → SOFT(기본, 설계 "미분류=SOFT 안전측")
#   매칭은 _matches(토큰 정확 or 5자↑ 부분문자열) — raw `in` 부분문자열 오매칭 금지
#   ("cola" in "chocolate", "lime" in "sublime" 등 회귀). 짧은 힌트(cola/lime/soda/cake/
#   milk/roll/tart/chip/yuzu)는 정확 매칭만, 5자↑(lemon/chocolate…)은 복수·형용사형 흡수.
_ZESTY_HINTS = (
    "lemon", "lemonade", "citrus", "orange", "orangeade", "lime", "limeade", "grapefruit",
    "yuzu", "soda", "cola", "sparkling", "tonic", "mojito", "juice", "tangerine", "mandarin",
)
_PUNCHY_HINTS = (
    "fried", "chicken", "snack", "chip", "chips", "candy", "tteokbokki", "hotdog", "corndog",
    "nacho", "popcorn", "rainbow", "jelly", "gummy", "burger", "fries", "sausage",
)
_RICH_HINTS = (
    "chocolate", "choco", "cocoa", "coffee", "espresso", "americano", "cappuccino",
    "macchiato", "mocha", "caramel", "tiramisu", "brownie", "affogato",
)
_SOFT_HINTS = (
    "cake", "cream", "cheesecake", "cupcake", "pancake", "mousse", "pudding", "latte",
    "macaron", "custard", "milk", "yogurt", "panna", "whipped", "shortcake", "souffle",
    "roll", "vanilla", "pastry", "scone", "tart", "parfait", "bingsu",
)

# --- 제품군 → 하모니 레시피 세트 (설계 §3, config) ------------------------------
#   레시피명은 색채이론 영어명(스타일 "모노톤"과 층위 구분 — 설계 §2 용어표).
_RECIPES: dict[str, tuple[str, ...]] = {
    "SOFT": ("accented_neutral", "monochromatic", "analogous", "split_complementary_soft"),
    "RICH": ("monochromatic", "accented_neutral", "in_product_accent"),
    "ZESTY": ("split_complementary", "complementary", "triadic"),
    "PUNCHY": ("complementary", "split_complementary", "triadic", "tetradic"),
    "OBJECT": ("accented_neutral", "split_complementary"),
}

# --- 이름 기반 폴백 hue (이미지 추출 불가 시, 설계 §5 폴백) ----------------------
_SUBJECT_HUE = (  # (키워드, hue도) — 앞에서부터 첫 매치
    (("blueberry", "blue"), 245.0), (("grape", "violet", "purple", "taro", "ube"), 278.0),
    (("strawberry", "cherry", "tomato", "berry", "red"), 3.0), (("raspberry", "rose", "pink"), 335.0),
    (("lemon", "banana", "mango", "yellow", "honey"), 50.0), (("orange", "apricot", "peach", "carrot"), 28.0),
    (("lime", "matcha", "mint", "green", "basil", "avocado"), 110.0),
    (("chocolate", "choco", "cocoa", "coffee", "caramel", "espresso", "americano",
      "cappuccino", "macchiato", "mocha", "affogato", "latte"), 26.0),
    (("grapefruit", "watermelon"), 350.0),
)


def _subject_base_hue(subject_en: str) -> float:
    low = (subject_en or "").lower()
    for keys, hue in _SUBJECT_HUE:
        if any(k in low for k in keys):
            return hue
    return 35.0  # 미지 음식: 따뜻한 중립(베이지/브라운 계열)


def _tokens(subject_en: str) -> list[str]:
    return re.findall(r"[a-z]+", (subject_en or "").lower())


def _matches(tokens: list[str], hints: tuple[str, ...]) -> bool:
    """토큰 정확 매칭 또는 5자↑ 힌트의 부분문자열 매칭. 짧은 힌트는 정확 매칭만(오매칭 방지)."""
    for t in tokens:
        for h in hints:
            if t == h or (len(h) >= 5 and h in t):
                return True
    return False


def _classify(subject_en: str, domain: Optional[str],
              serving_type: Optional[str] = None) -> str:
    if domain == "object":
        return "OBJECT"
    # PAL-004(2026-07-24 라이브 원색 사고, historyId=213): serving_type=dessert|bakery 는
    #   LLM 의미 판정이 정본 — 무조건 SOFT(파스텔 네이밍). "딸기 초코 생크림 케이크"가
    #   '초코' 힌트로 RICH에 낚여 "a red background"(알몸 원색)를 받은 실측 재현 완료.
    if serving_type in ("dessert", "bakery"):
        return "SOFT"
    tokens = _tokens(subject_en)
    if _matches(tokens, _ZESTY_HINTS):
        return "ZESTY"
    if _matches(tokens, _PUNCHY_HINTS):
        return "PUNCHY"
    # SOFT(케이크·크림류)를 RICH(초코·커피)보다 먼저 — 초코 케이크는 케이크다(동일 사고의
    #   serving_type 미전달 경로 방어. 순수 초코·커피 단품만 RICH로).
    if _matches(tokens, _SOFT_HINTS):
        return "SOFT"
    if _matches(tokens, _RICH_HINTS):
        return "RICH"
    return "SOFT"


# --- 제품 색 추출 (마스크 없는 style_gen 경로 → 중앙가중 + 채도×면적 랭킹) -------
#   ⚠️ v1 한계: 누끼 마스크가 이 경로엔 없어 중앙 크롭으로 근사. 배경이 중앙까지 크면
#   오염 가능 — 마스크 기반 추출은 v1.1(설계 §5). 근-무채색 극단은 배경으로 보고 제외.
def _extract_colors(image_path: Optional[str]) -> Optional[tuple[tuple[float, float, float],
                                                                 tuple[float, float, float]]]:
    if not image_path or not Path(image_path).is_file():
        return None
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None
    try:
        im = Image.open(image_path).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    w, h = im.size
    crop = im.crop((int(w * 0.18), int(h * 0.14), int(w * 0.82), int(h * 0.86)))
    small = crop.resize((72, 72))
    counts: dict[tuple[int, int, int], int] = {}
    for r, g, b in small.getdata():
        key = (r // 24 * 24, g // 24 * 24, b // 24 * 24)
        counts[key] = counts.get(key, 0) + 1
    scored = []  # (score, hsv, area)
    for (r, g, b), n in counts.items():
        hh, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if v < 0.12 or (s < 0.12 and (v > 0.9 or v < 0.25)):  # 근-흰/근-검/무채 배경 제외
            continue
        scored.append((n * (0.35 + s), (hh * 360.0, s, v), n))
    if not scored:
        return None
    scored.sort(key=lambda t: t[0], reverse=True)
    field = scored[0][1]
    # accent = field 와 hue 가 충분히 다른(>40°) 가장 채도 높은 색, 없으면 field 재사용
    accent = max(
        (hsv for _, hsv, _ in scored if _hue_dist(hsv[0], field[0]) > 40.0),
        key=lambda hsv: hsv[1], default=field)
    return field, accent


def _hue_dist(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


# --- 색공간 유틸 --------------------------------------------------------------
def _rot(h: float, deg: float) -> float:
    return (h + deg) % 360.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# 제품군별 S/V 대역(설계 §3). (s_lo,s_hi, v_lo,v_hi)
_ENVELOPE = {
    "SOFT": (0.15, 0.42, 0.80, 0.93),
    "RICH": (0.35, 0.58, 0.22, 0.70),
    "ZESTY": (0.72, 0.95, 0.72, 0.94),
    "PUNCHY": (0.80, 1.00, 0.74, 0.95),
    "OBJECT": (0.10, 0.40, 0.72, 0.92),
}
_IVORY = (42.0, 0.10, 0.93)      # 따뜻한 크림/아이보리 뉴트럴
_CREAM = (38.0, 0.16, 0.90)
_NEAR_BLACK = (30.0, 0.20, 0.14)  # 볼드용 니어블랙 앵커
_SOFT_GREY = (40.0, 0.05, 0.86)


def _in_envelope(hsv: tuple[float, float, float], pclass: str,
                 v_bias: float = 0.0) -> tuple[float, float, float]:
    s_lo, s_hi, v_lo, v_hi = _ENVELOPE[pclass]
    h, s, v = hsv
    return (h, _clamp(s, s_lo, s_hi), _clamp(v + v_bias, v_lo, min(0.98, v_hi + abs(v_bias))))


def _appetite_gate(hsv: tuple[float, float, float], pclass: str,
                   domain: Optional[str]) -> tuple[float, float, float]:
    """고형 음식 배경 파랑(200–250°) 큰 면 금지(식욕 억제). 음료는 허용. 위반 시 탈채도로 완화."""
    if domain == "drink":
        return hsv
    h, s, v = hsv
    if 200.0 <= h <= 255.0 and s > 0.35 and pclass in ("ZESTY", "PUNCHY", "OBJECT"):
        return (h, min(s, 0.28), max(v, 0.82))  # 쨍한 코발트 → 소프트 파우더로 완화
    return hsv


# --- 레시피 → (배경, 테이블) 쌍 (설계 §5, 60‑30‑10: 배경 지배 + 보조) -----------
def _build_pair(field: tuple[float, float, float], accent: tuple[float, float, float],
                recipe: str, pclass: str, domain: Optional[str]):
    fh = field[0]
    if recipe == "monochromatic":
        bg = _in_envelope((fh, field[1], field[2]), pclass)
        plane = _in_envelope((fh, field[1] * 0.7, field[2] + 0.06), pclass, v_bias=0.08)
    elif recipe == "accented_neutral":
        bg = _in_envelope((fh, field[1], field[2]), pclass)
        plane = _IVORY if pclass in ("SOFT", "OBJECT") else _CREAM
    elif recipe == "analogous":
        bg = _in_envelope((_rot(fh, -28), field[1], field[2]), pclass)
        plane = _in_envelope((_rot(fh, 28), field[1] * 0.8, field[2] + 0.05), pclass)
    elif recipe in ("split_complementary", "split_complementary_soft"):
        soft = recipe.endswith("_soft")
        comp = _rot(fh, 158)  # 150–170° (설계: 순보색보다 부드러운 대비)
        bg = _in_envelope((comp, 0.85 if not soft else 0.4, 0.9), pclass)
        plane = _IVORY if soft else _in_envelope((_rot(fh, 202), 0.7, 0.9), pclass)
    elif recipe == "complementary":
        bg = _in_envelope((_rot(fh, 180), 0.9, 0.9), pclass)
        plane = _NEAR_BLACK if pclass == "PUNCHY" else _in_envelope((fh, 0.8, 0.88), pclass)
    elif recipe == "triadic":
        bg = _in_envelope((_rot(fh, 120), 0.85, 0.9), pclass)
        plane = _in_envelope((_rot(fh, 240), 0.8, 0.9), pclass)
    elif recipe == "tetradic":
        bg = _in_envelope((_rot(fh, 60), 0.85, 0.9), pclass)
        plane = _NEAR_BLACK
    elif recipe == "in_product_accent":
        bg = _in_envelope((fh, field[1], field[2]), pclass)  # 제품 계열 딥필드
        plane = _CREAM
    else:
        bg = _in_envelope(field, pclass)
        plane = _IVORY
    bg = _appetite_gate(bg, pclass, domain)
    plane = _appetite_gate(plane, pclass, domain)
    return bg, plane


# --- 색 → 영어 문구 (짧은 어휘 = t2i 렌더 안정, 설계 §5-9) -----------------------
_HUE_NAMES = (
    (12, "red"), (22, "coral"), (38, "orange"), (48, "amber"), (60, "golden-yellow"),
    (75, "yellow"), (95, "chartreuse"), (140, "green"), (165, "emerald"), (185, "teal"),
    (200, "cyan"), (215, "sky-blue"), (235, "cobalt-blue"), (255, "indigo"),
    (280, "violet"), (300, "purple"), (320, "magenta"), (340, "pink"), (352, "rose"),
    (360, "red"),
)


def _hue_name(h: float) -> str:
    for hi, name in _HUE_NAMES:
        if h < hi:
            return name
    return "red"


# SOFT 파스텔 변형명(PAL-002, 2026-07-23 아트디렉터 판정): "soft red" 같은 수식어+원색명은
#   렌더에서 수식어가 팝 플랜의 saturated 언어에 밀려 원색으로 나온다(라이브 실측 — 케이크가
#   시뻘건 배경). t2i 는 색 '이름'에 반응하므로 SOFT 계열은 이름 자체가 탈채도를 내장한
#   파스텔 변형명으로 강제한다. hue 경계는 _HUE_NAMES 와 동일.
_PASTEL_NAMES = (
    (12, "blush pink"), (22, "peach"), (38, "apricot"), (48, "butter yellow"),
    (60, "butter yellow"), (75, "lemon chiffon"), (95, "soft sage"), (140, "sage green"),
    (165, "soft sage"), (185, "powder mint"), (200, "powder mint"), (215, "powder blue"),
    (235, "powder blue"), (255, "lilac"), (280, "lilac"), (300, "lavender"),
    (320, "powder pink"), (340, "powder pink"), (352, "blush pink"), (360, "blush pink"),
)


def _pastel_name(h: float) -> str:
    for hi, name in _PASTEL_NAMES:
        if h < hi:
            return name
    return "blush pink"


def _phrase(hsv: tuple[float, float, float], pclass: Optional[str] = None) -> str:
    h, s, v = hsv
    if s < 0.14:  # 무채색 계열
        if v >= 0.85:
            return "warm ivory" if 20 <= h <= 60 else "soft off-white"
        if v <= 0.22:
            return "near-black charcoal"
        return "soft warm grey" if 20 <= h <= 60 else "soft grey"
    # PAL-002: SOFT(케이크·크림류)는 파스텔 변형명 — "pastel blush pink"는 렌더가 실제로
    #   탈채도됨(이름이 밝기를 내장). 타 제품군(ZESTY/PUNCHY 등)은 기존 대담 문구 유지.
    if pclass == "SOFT":
        return f"pastel {_pastel_name(h)}"
    name = _hue_name(h)
    if s >= 0.72 and v >= 0.6:
        # PAL-005(2026-07-24): "vivid saturated"(07-22 '강하게' 실험 잔재 — 아트디렉터가
        #   기각한 실험의 문구가 잔존해 원색 플랫 배경의 소스가 됨) 제거. 설계 v1 정본엔
        #   원색 단색 배경이 없음(ZESTY/PUNCHY도 '보색 조합+60-30-10+앵커') — 고채도
        #   의도는 "bright"로 유지하되 'saturated' 원색 소환 토큰은 금지.
        qual = "bright"
    elif s >= 0.5 and v < 0.45:
        qual = "rich deep"
    elif s < 0.45 and v >= 0.8:
        qual = "soft"
    elif s < 0.58:
        qual = "muted"
    else:
        # PAL-004: 무수식(알몸 색명, 예: "red") 금지 — 렌더가 원색으로 직행하는 구멍.
        #   vivid 문턱(s≥0.72·v≥0.6) 미달의 중채도는 "rich"로 한정.
        qual = "rich"
    return f"{qual} {name}".strip()


def _seed_int(subject_en: str, seed: Optional[int]) -> int:
    d = hashlib.sha256((subject_en or "").strip().lower().encode()).digest()[0]
    return d ^ (int(seed) & 0xFF if seed is not None else 0)


# --- PAL-003(2026-07-24): 파스텔·모노톤 롤아웃 — pop과 같은 "제품 무관 고정 팔레트" 원죄를
#   같은 추출 엔진으로 교정. 문구 '형태'는 기존 검증된 스타일 언어를 유지(파스텔="pale…low
#   muted table plane", 모노톤="strict … monochrome environment using … only")하고 색만
#   제품에서 도출한다. 제품 색 자체는 절대 안 건드림(배경·테이블만 — 기존 direction의
#   "Keep all food colors fully natural/true" 절이 이중 방어).
# 모노톤 딥 전용 hue 네이밍 — 일반 _HUE_NAMES(orange 등)는 저명도 모노크롬 환경명으로
#   부적합(커피가 "deep orange" 실측). 딥 모노톤은 어두운 관용색명이 렌더 언어.
_MONO_DEEP_NAMES = (
    (12, "burgundy"), (42, "espresso brown"), (75, "deep olive"), (140, "forest green"),
    (200, "deep teal"), (255, "midnight blue"), (320, "deep plum"), (352, "burgundy wine"),
    (360, "burgundy"),
)


def _mono_deep_name(h: float) -> str:
    for hi, name in _MONO_DEEP_NAMES:
        if h < hi:
            return name
    return "burgundy"


def _anchor_hue(subject_en: str, image_path: Optional[str]) -> tuple[float, bool]:
    """(hue, 유채확신) — 의미(키워드) 우선, 미매치 시 이미지 추출.

    pop은 하모니 회전이라 추출 오염(중앙 크롭 우드)이 완충되지만, 모노톤·파스텔은 단일
    hue가 전부라 오염이 직격(실측: 딸기케이크→orange 모노톤). 색 함의 키워드가 있으면
    그것이 정본, 없을 때만 이미지에서.
    """
    low = (subject_en or "").lower()
    for keys, hue in _SUBJECT_HUE:
        if any(k in low for k in keys):
            return hue, True
    extracted = _extract_colors(image_path)
    if extracted is not None:
        fh, fs, _ = extracted[0]
        return fh, fs >= 0.18
    return 35.0, True  # 웜 뉴트럴 — 무난한 브라운 계열


def _pastel_clause(subject_en: str, domain: Optional[str],
                   image_path: Optional[str], seed: Optional[int]) -> str:
    fh, _ = _anchor_hue(subject_en, image_path)
    # SOFT 하모니 로테이션: 톤온톤 / 유사색 / 소프트 보색 — 배경은 제품 조화, 플레인은 보조
    recipes = ((0.0, 28.0), (-28.0, 28.0), (158.0, 0.0))
    bg_off, plane_off = recipes[_seed_int(subject_en, seed) % len(recipes)]
    bg = _appetite_gate((_rot(fh, bg_off), 0.3, 0.9), "SOFT", domain)
    plane = _appetite_gate((_rot(fh, plane_off), 0.25, 0.86), "SOFT", domain)
    if domain == "object":
        return (f"a pale {_pastel_name(bg[0])} background and one low matte "
                f"{_pastel_name(plane[0])} pedestal behind the product")
    return (f"a pale {_pastel_name(bg[0])} background and a low muted "
            f"{_pastel_name(plane[0])} table plane")


def _monotone_clause(subject_en: str, domain: Optional[str],
                     image_path: Optional[str], seed: Optional[int]) -> str:
    fh, chromatic = _anchor_hue(subject_en, image_path)
    # 제품이 사실상 무채색이면 기존 도브그레이 유지(적응 근거 없음 — 안전측)
    if not chromatic:
        return ("a strict pale dove-gray monochrome environment using soft gray, "
                "warm white and pale taupe only")
    deep_name = _mono_deep_name(fh)
    pale_name = _pastel_name(fh)
    variants = (
        f"a strict deep {deep_name} monochrome environment using {deep_name}, "
        "charcoal and black only",
        f"a strict pale {pale_name} monochrome environment using soft {pale_name}, "
        "warm white and pale taupe only",
    )
    return variants[_seed_int(subject_en, seed) % len(variants)]


def style_palette_clause(style_key: str, subject_en: str, domain: Optional[str],
                         image_path: Optional[str] = None,
                         seed: Optional[int] = None,
                         serving_type: Optional[str] = None) -> Optional[str]:
    """스타일별 적응형 팔레트 통합 진입점(PAL-003). 미지원 스타일은 None(기존 고정 조회).

    serving_type(PAL-004): dessert|bakery 는 제품군 SOFT 강제 — 이름 힌트 오분류
    ('초코 케이크'→RICH→원색) 방어의 정본 신호.
    """
    if style_key == "pop":
        return pop_palette_clause(subject_en, domain, image_path, seed,
                                  serving_type=serving_type)
    if style_key == "pastel":
        return _pastel_clause(subject_en, domain, image_path, seed)
    if style_key == "monotone":
        return _monotone_clause(subject_en, domain, image_path, seed)
    return None


def pop_palette_clause(subject_en: str, domain: Optional[str],
                       image_path: Optional[str] = None,
                       seed: Optional[int] = None,
                       serving_type: Optional[str] = None) -> str:
    """제품 적응형 팝 배경 팔레트 문구. `_POP_PALETTES` 고정 조회의 드롭인 대체.

    image_path 로 제품 색을 추출(불가 시 subject_en 기반 hue 폴백) → 제품군 분류 →
    하모니 레시피 로테이션 → S/V 대역 clamp + 식욕 게이트 → 배경/테이블 2색 영어 문구.
    """
    pclass = _classify(subject_en, domain, serving_type)
    extracted = _extract_colors(image_path)
    if extracted is not None:
        field, accent = extracted
    else:
        bh = _subject_base_hue(subject_en)
        field = (bh, 0.6, 0.6)
        accent = (bh, 0.85, 0.7)
    recipes = _RECIPES.get(pclass, _RECIPES["SOFT"])
    recipe = recipes[_seed_int(subject_en, seed) % len(recipes)]
    bg, plane = _build_pair(field, accent, recipe, pclass, domain)
    return (f"a {_phrase(bg, pclass)} background and "
            f"a clean {_phrase(plane, pclass)} table surface")
