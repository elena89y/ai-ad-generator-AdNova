"""음식 리터치 (A모드, 리터치형) — 담당: 한의정.

누끼+배경교체(B모드)와 달리 **원본 구도를 유지**하고 생성모델 img2img 로
음식을 '먹음직스럽게' 다시 그린다 — 광택·질감·플레이팅을 실제로 재생성
(색보정 수준이 아님. 육개장 레퍼런스급 변화). FR-08 정체성 보존 결.

핵심: SDXL base img2img (image_service.img2img) + 음식 뷰티파이 프롬프트.
  strength 로 변형 강도 조절 — 0.5 기본(정체성 유지+와우), 0.35 안전, 0.65 글램.
  용기에 담긴 음식은 하드 컷아웃 시 사각 잔재 → 잘라내지 않고 in-place 재생성.

⚠️ 없던 재료/가니시 창작은 허위광고 소지 → strength 상한을 0.65 로 두고
  프롬프트도 "존재하는 요소 강화"에 한정(새 토핑 지시 금지).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

# 강도 범위 — 프론트 슬라이더가 이 범위로 노출 (봄님 UI 연동).
#   하한 0.2 = 토핑이 정체성인 메뉴(눈꽃치즈 파우더 등) 보존용 — RealVis 는 강도 오르면
#   특징 토핑을 표준화(정리)해버림. 상한 0.65 = 없던 재료 창작(허위광고) 방지.
STRENGTH_MIN = 0.20
STRENGTH_MAX = 0.65
STRENGTH_DEFAULT = 0.50

# 음식 공통 스타일 (존재 요소 강화에 한정 — 새 토핑/가니시 지시 안 함).
#   ⚠️ 'food magazine quality' 등 과한 스타일어는 SDXL 을 3D 렌더/추상화로 밀어냄
#     (육개장·꽃등심 실측 붕괴). 사진 리얼리즘 앵커를 앞세우고 강도·guidance 를 낮춘다.
_FOOD_STYLE = (
    "realistic food photograph, natural sharp focus, appetizing, freshly served, "
    "glossy highlights, crisp texture, natural warm tones, soft natural lighting, "
    "shallow depth of field, high detail, true-to-life colors"
)
_FOOD_NEG = (
    "blurry, low quality, deformed, plastic, artificial, unappetizing, "
    "text, watermark, logo, cartoon, illustration, painting, oversaturated, burnt, "
    # 정직성: 구성 재료(프롬프트로 명시)는 허용하되 '외래 데코'만 차단 — 그 메뉴에
    #   원래 없는 장식·토핑을 만들어내는 허위광고 방지 ([[fr08-quality-direction]])
    "foreign garnish, unrelated decoration, random toppings not part of the dish, "
    "3d render, cgi, abstract, surreal, fractal, digital art, melting, warped, swirled, "
    # 음식 광고에 맨손이 음식에 닿으면 최악 → 손·손가락 차단 (젓가락은 프롬프트로 유지)
    "bare hand touching food, fingers touching food, hand gripping food, "
    "hand in bowl, human hand on food, unhygienic"
)

# 카테고리 힌트 — 메뉴 성격별 질감 강조어 + 영어 폴백 주어.
#   ⚠️ SDXL 의 CLIP 은 영어 학습 → 한글 메뉴명을 프롬프트에 넣으면 노이즈로 작용,
#     음식이 엉뚱하게 변형됨(치킨→조개 등). 반드시 영어 설명(food_en)만 사용.
CATEGORY_HINT = {
    "fried": ("crispy golden-brown crust, freshly fried", "fried food"),
    "soup": ("steaming hot, rich glossy broth, vibrant fresh ingredients", "Korean soup"),
    "bakery": ("golden baked crust, soft crumb, buttery sheen", "baked pastry"),
    "grill": ("charred grill marks, juicy, sizzling", "grilled dish"),
    # 생고기 계열 — 익히지 않고(_RAW_NEG 병행) 종류별 핵심을 강조:
    #   소고기=마블링(지방 결)이 생명 / 돼지고기=선명한 빨간 살코기
    "beef": ("premium beef, fine intramuscular marbling, well-marbled fat streaks, "
             "glistening fresh red meat", "fresh marbled beef"),
    "pork": ("fresh pork, vivid pink-red lean meat, juicy tender cut, clean fresh",
             "fresh pork cut"),
    "raw": ("glistening fresh cut, vivid natural color, juicy sheen", "fresh raw meat"),
    "default": ("", "delicious dish"),
}
_RAW_CATS = ("raw", "beef", "pork")
# 생고기 전용 추가 금지어 — img2img 가 고기를 익혀버리지 않도록.
_RAW_NEG = ", cooked, seared, grilled, browned, well-done, charred"


@dataclass
class RetouchResult:
    output_path: str
    strength: float
    seconds: float


def _build_prompt(food_en: str, category: str,
                  core_ingredients: Optional[list[str]] = None) -> tuple[str, str]:
    """SDXL img2img 프롬프트 — 영어 주어(food_en)만 사용(한글명 금지, CLIP 오염 방지).

    core_ingredients: 그 메뉴의 진짜 재료(예 육개장 beef,noodles) → 프롬프트에 명시해
      '정직한 생성'을 허용. 외래 데코는 negative 로 차단(정직성 경계).
    """
    hint, fallback = CATEGORY_HINT.get(category, CATEGORY_HINT["default"])
    subject = food_en.strip() or fallback
    ings = ", ".join(core_ingredients) if core_ingredients else ""
    parts = ", ".join(x for x in (subject, ings, hint) if x)
    negative = _FOOD_NEG + (_RAW_NEG if category in _RAW_CATS else "")
    return f"{parts}, {_FOOD_STYLE}", negative


def _upscale_to_1024(img: Image.Image) -> Image.Image:
    """SDXL(1024 학습) 품질 확보용. 롱사이드 1024, 8의 배수로 정렬."""
    w, h = img.size
    if max(w, h) <= 1024:
        return img
    s = 1024 / max(w, h)
    return img.resize((max(8, int(w * s) // 8 * 8), max(8, int(h * s) // 8 * 8)), Image.LANCZOS)


def enhance_food(
    image_path: str,
    food_en: str = "",
    category: str = "default",
    core_ingredients: Optional[list[str]] = None,
    strength: float = STRENGTH_DEFAULT,
    guidance: float = 5.0,
    seed: int = 7,
    output_dir: str = "backend/results/ai/food",
) -> RetouchResult:
    """음식 사진 생성형 리터치 (누끼·배경교체 없음, GPU 필요). — 생성 엔진.

    food_en: 영어 음식 설명(예 'Korean cheese fried chicken'). ⚠️ 한글명 금지(CLIP 오염).
      통합 시 gpt_service.analyze_menu 에서 공급. 비면 category 폴백 주어 사용.
    core_ingredients: 그 메뉴의 진짜 재료(정직한 생성 허용 경계).
    strength: 0.20~0.65 (기본 0.50). 프론트 슬라이더 연동 값. 범위 밖은 클램프.
    category: fried|soup|bakery|grill|beef|pork|default — 질감 강조어 선택.
    """
    import time

    from . import image_service

    t0 = time.time()
    strength = max(STRENGTH_MIN, min(STRENGTH_MAX, strength))
    src = Image.open(image_path).convert("RGB")
    up = _upscale_to_1024(src)
    positive, negative = _build_prompt(food_en, category, core_ingredients)

    out = image_service.img2img(up, positive, negative, strength=strength,
                                guidance=guidance, seed=seed, photoreal=True)
    if out.size != up.size:
        out = out.resize(up.size, Image.LANCZOS)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{Path(image_path).stem}_retouch.png"
    out.save(out_path)
    return RetouchResult(output_path=str(out_path), strength=strength,
                         seconds=round(time.time() - t0, 2))


# =============================================================================
# 보존 그레이드 엔진 (픽셀 보존, GPU 불필요) — 텍스처가 상품인 음식 전용.
#   생성(RealVis)은 마블링·파우더 같은 미세 텍스처를 표준화해 없앰(실측).
#   → 소고기 마블링·돼지 빨간육·눈꽃치즈 등은 원본 픽셀을 지키고 톤/광택/배경만 손봄.
#   핵심: 클래리티(국소대비)로 마블링을 '지우는' 게 아니라 '더 도드라지게'.
# =============================================================================
import numpy as np  # noqa: E402
from PIL import ImageFilter  # noqa: E402

# 카테고리별 그레이드 파라미터 (intensity 로 일괄 스케일).
#   warmth=웜밸런스, red=레드 채도, clarity=국소대비(마블링 강조), gloss=광택, focus=배경집중
_GRADE = {
    "beef": dict(warmth=0.0, red=0.28, clarity=0.65, gloss=0.26, focus=0.45),
    "pork": dict(warmth=0.02, red=0.42, clarity=0.32, gloss=0.24, focus=0.45),
    "default": dict(warmth=0.05, red=0.30, clarity=0.42, gloss=0.24, focus=0.50),
}


def _to_f(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0


def _to_img(a: np.ndarray) -> Image.Image:
    return Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


def _wb(rgb, warmth):
    if warmth <= 0:
        return rgb
    m = rgb.reshape(-1, 3).mean(0) + 1e-6
    g = m.mean()
    rgb = rgb * (1.0 + 0.4 * (g / m - 1.0))
    return rgb * np.array([1 + 0.28 * warmth, 1.0, 1 - 0.12 * warmth], np.float32)


def _red_sat(rgb, amount):
    """레드 계열 채도 강조 (고기 선홍빛). 순수 채도 부스트를 레드 마스크로 가중."""
    if amount <= 0:
        return rgb
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = (0.299 * r + 0.587 * g + 0.114 * b)[..., None]
    redness = np.clip((r - np.maximum(g, b)) / (r + 1e-6), 0, 1)[..., None]  # 레드일수록 1
    boosted = lum + (rgb - lum) * (1.0 + amount * (0.6 + 0.9 * redness))
    return boosted


def _clarity(rgb, amount):
    """국소 대비(언샤프, 큰 반경) — 마블링 지방결/엣지를 도드라지게(보존+강조)."""
    if amount <= 0:
        return rgb
    blur = _to_f(_to_img(rgb).filter(ImageFilter.GaussianBlur(radius=10)))
    return rgb + amount * (rgb - blur)


def _gloss(rgb, amount):
    """하이라이트 리프트 — 젖은 광택/신선한 윤기."""
    if amount <= 0:
        return rgb
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    hi = (np.clip((lum - 0.6) / 0.4, 0, 1) ** 2)[..., None]
    return rgb + amount * hi * (1.0 - rgb)


def _focus(rgb, amount):
    """중앙 타원 밖 블러+암부 → 음식 집중 (마스크 불필요)."""
    if amount <= 0:
        return rgb
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w * 0.5) / (w * 0.62)) ** 2 + ((yy - h * 0.52) / (h * 0.62)) ** 2)
    soft = np.clip(1.0 - r, 0, 1)[..., None]
    blur = _to_f(_to_img(rgb).filter(ImageFilter.GaussianBlur(radius=min(h, w) * 0.012)))
    return (rgb * soft + blur * (1 - soft)) * (1 - amount * 0.32 * (1 - soft))


def grade_food(
    image_path: str,
    category: str = "beef",
    intensity: float = 1.0,
    output_dir: str = "backend/results/ai/food",
) -> RetouchResult:
    """픽셀 보존 그레이드 — 텍스처(마블링·파우더) 100% 보존하며 톤·광택·배경만. GPU 불필요.

    intensity: 0~1.5 효과 배율(기본 1.0, 슬라이더 연동). category=beef/pork/default.
    """
    import time

    t0 = time.time()
    p = _GRADE.get(category, _GRADE["default"])
    k = max(0.0, min(1.5, intensity))
    rgb = _to_f(Image.open(image_path))
    rgb = _wb(rgb, p["warmth"] * k)
    rgb = _red_sat(rgb, p["red"] * k)
    rgb = _clarity(rgb, p["clarity"] * k)
    rgb = _gloss(rgb, p["gloss"] * k)
    rgb = _focus(rgb, p["focus"] * k)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{Path(image_path).stem}_retouch.png"
    _to_img(rgb).save(out_path)
    return RetouchResult(output_path=str(out_path), strength=round(k, 2),
                         seconds=round(time.time() - t0, 2))


# --- 라우터 -------------------------------------------------------------------
def retouch(
    image_path: str,
    analysis,  # gpt_service.MenuAnalysis
    knob: Optional[float] = None,
    output_dir: str = "backend/results/ai/food",
) -> RetouchResult:
    """메뉴 분석 → 엔진 자동 선택. texture_hero=True 면 보존 그레이드, 아니면 생성 리터치.

    knob: 공통 강도 슬라이더 값(0~1). None 이면 엔진별 기본값.
      - 그레이드: intensity = knob*1.5 (0~1.5), 기본 1.0
      - 생성   : strength  = knob (0.2~0.65), 기본 0.5
    """
    if getattr(analysis, "texture_hero", False):
        intensity = 1.0 if knob is None else max(0.0, min(1.5, knob * 1.5))
        return grade_food(image_path, category=analysis.category,
                          intensity=intensity, output_dir=output_dir)
    strength = STRENGTH_DEFAULT if knob is None else knob
    return enhance_food(image_path, food_en=analysis.food_en, category=analysis.category,
                        core_ingredients=analysis.core_ingredients,
                        strength=strength, output_dir=output_dir)
