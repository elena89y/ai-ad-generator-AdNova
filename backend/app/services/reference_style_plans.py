"""레퍼런스 실험(STY-003~005)에서 검증한 도메인별 6무드 StylePlan.

무드 이름만 공유하고 실제 연출 지시는 음식·음료·사물별로 분리한다. Kontext에는
레퍼런스 이미지를 직접 넣지 않으므로 reference_ids는 추적·평가용이며, 생성 지시는
해당 레퍼런스에서 추출한 배경·조명·구도 규칙만 사용한다.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
import os

from . import prompt_registry as _prompts

_NS = "reference_style_plans"


@dataclass(frozen=True)
class ReferenceStylePlan:
    style_key: str
    domain: str
    archetype: str
    reference_ids: tuple[str, ...]
    direction: str
    # REAL-001: 사진적 사실감 finish 프로파일. 기본 "none"(무주입) → 모든 기존 지시는
    #   바이트 동일(스냅샷·회귀 가드). 실험 arm이 build_*_instruction(finish_profile=...)로
    #   덮어써 리얼리즘 절을 켠다. 루브릭 근거 = 픽바이트 레퍼런스 관찰(자연광 논리·재질
    #   사실감·절제색·공간 그라운딩). 모드 불가지 — food/object/drink 전부 동일 절 적용.
    finish_profile: str = "none"


# REAL-001 리얼리즘 finish 절 (생성 프롬프트 → 영어. 함정 #1: 한글 금지).
#   trailing space 포함 = direction과 금지꼬리 사이에 자연 삽입, "none"은 빈 문자열이라
#   기존 조립과 바이트 동일.
_FINISH_CLAUSES: dict[str, str] = {
    "none": "",
    "photographic": (
        "Strongly regrade this into a true-to-life photograph: pronounced soft directional window "
        "light with clear contact shadows and bright natural highlight rolloff, crisp accurate "
        "material texture with visible fine surface detail, and a rich warm natural color grade — "
        "deeper, punchier tones that still read as a real photograph, never plastic, CGI or "
        "oversaturated. Keep the subject firmly grounded in a real physical setting with a softly "
        "defined background, never a flat studio void or a blurred bokeh blur. "
    ),
}


def _finish_clause(profile: str | None) -> str:
    """finish_profile → 삽입 절. 미지정·미등록은 무주입("")으로 안전 폴백."""
    return _FINISH_CLAUSES.get((profile or "none"), "")


# --- DIV-2: 사진-톤 매칭 표면·배경 풀 ------------------------------------------
# 설계메모 §3 DIV-2: "스타일당 1문장 → 템플릿+슬롯, 무드별 표면/배경 풀에서 사진 톤 매칭".
#   다양성의 원천을 프리셋 6개가 아니라 유저 입력 사진으로 옮긴다 — image_service.
#   classify_scene_tone(픽셀 통계, API 0)이 warm/cool/neutral 을 주면 조화되는 버킷에서 고른다.
#
# 방식(BYTE-IDENTITY): scene_tone 미지정(OFF/기본)이면 direction 문자열을 건드리지 않는다 →
#   기존 스냅샷·회귀와 완전 동일(무위험). 지정 시에만 v0 스팬을 톤-매칭 후보로 str.replace.
#   후보는 관사·명사(table/wall/surface/tabletop/sweep)까지 포함한 완결 구로 문법 파손 없음.
# 적용 대상 = 표면/배경이 고정된 editorial·realism·warm_organic (pop/pastel/monotone 은 이미
#   {palette}로 subject별 변동). object/editorial 배경은 구조적 프롭이라 표면만 슬롯.
_SCENE_SPANS: dict[tuple[str, str], dict[str, str]] = {
    ("food", "editorial"): {"surface": "a muted cream stone table",
                            "background": "a pale warm-gray background"},
    ("food", "realism"): {"surface": "a dark charcoal stone table",
                         "background": "a softly blurred neutral dining background"},
    ("food", "warm_organic"): {"surface": "a pale travertine table",
                              "background": "a softly textured beige wall"},
    ("drink", "editorial"): {"surface": "a pale cream stone table",
                            "background": "a very light cool-gray background"},
    ("drink", "realism"): {"surface": "a clean warm-gray stone tabletop",
                          "background": "a softly sunlit neutral wall"},
    ("drink", "warm_organic"): {"surface": "a pale travertine table",
                               "background": "a softly textured beige wall"},
    ("object", "editorial"): {"surface": "a cool off-white studio sweep"},
    ("object", "realism"): {"surface": "a light gray limestone surface",
                           "background": "a softly sunlit neutral wall"},
    ("object", "warm_organic"): {"surface": "a pale travertine surface",
                                "background": "a softly textured beige wall"},
}

# 각 (domain, mood, slot) → {warm/cool/neutral: [후보...]}. v0(현행 스팬)은 자기 톤 버킷 선두.
#   trailing 명사는 스팬과 일치(문법 유지). 빈 버킷은 neutral→v0 순으로 폴백.
_SCENE_POOLS: dict[tuple[str, str], dict[str, dict[str, list[str]]]] = {
    ("food", "editorial"): {
        "surface": {"neutral": ["a muted cream stone table", "a soft greige microcement table"],
                    "warm": ["a warm oak wood table", "a honey travertine table"],
                    "cool": ["a cool pale concrete table", "a light grey terrazzo table"]},
        "background": {"neutral": ["a pale warm-gray background", "a soft stone-white background"],
                       "warm": ["a soft ecru background", "a warm sand-beige background"],
                       "cool": ["a very light cool-gray background", "a pale slate-gray background"]},
    },
    ("food", "realism"): {
        "surface": {"neutral": ["a dark charcoal stone table", "a honed slate table"],
                    "warm": ["a weathered walnut wood table", "a warm terracotta tiled table"],
                    "cool": ["a cool grey concrete table"]},
        "background": {"neutral": ["a softly blurred neutral dining background"],
                       "warm": ["a softly blurred warm restaurant background",
                                "a blurred amber-lit dining background"],
                       "cool": ["a softly blurred cool grey dining background"]},
    },
    ("food", "warm_organic"): {
        "surface": {"warm": ["a pale travertine table", "a raw oak table"],
                    "neutral": ["a limewash concrete table"], "cool": []},
        "background": {"warm": ["a softly textured beige wall", "a warm clay-plaster wall"],
                       "neutral": ["a soft sand-toned wall"], "cool": []},
    },
    ("drink", "editorial"): {
        "surface": {"neutral": ["a pale cream stone table", "a soft greige microcement table"],
                    "warm": ["a warm oak wood table"], "cool": ["a cool pale concrete table"]},
        "background": {"cool": ["a very light cool-gray background", "a pale slate-gray background"],
                       "neutral": ["a soft stone-white background"], "warm": ["a soft ecru background"]},
    },
    ("drink", "realism"): {
        "surface": {"neutral": ["a clean warm-gray stone tabletop", "a honed pale concrete tabletop"],
                    "warm": ["a warm oak wood tabletop"], "cool": ["a cool grey stone tabletop"]},
        "background": {"warm": ["a softly sunlit neutral wall", "a soft warm plaster wall"],
                       "neutral": ["a soft pale grey wall"], "cool": ["a cool morning-lit wall"]},
    },
    ("drink", "warm_organic"): {
        "surface": {"warm": ["a pale travertine table", "a raw oak table"],
                    "neutral": ["a limewash concrete table"], "cool": []},
        "background": {"warm": ["a softly textured beige wall", "a warm clay-plaster wall"],
                       "neutral": ["a soft sand-toned wall"], "cool": []},
    },
    ("object", "editorial"): {
        "surface": {"neutral": ["a cool off-white studio sweep", "a soft warm-white studio sweep"],
                    "warm": ["a soft sand studio sweep"], "cool": ["a cool light-grey studio sweep"]},
    },
    ("object", "realism"): {
        "surface": {"neutral": ["a light gray limestone surface", "a honed pale concrete surface"],
                    "warm": ["a pale oak plank surface"], "cool": ["a cool grey stone surface"]},
        "background": {"warm": ["a softly sunlit neutral wall", "a soft warm plaster wall"],
                       "neutral": ["a soft pale grey wall"], "cool": ["a cool morning-lit wall"]},
    },
    ("object", "warm_organic"): {
        "surface": {"warm": ["a pale travertine surface", "a raw oak surface"],
                    "neutral": ["an unglazed stoneware surface"], "cool": []},
        "background": {"warm": ["a softly textured beige wall", "a warm clay-plaster wall"],
                       "neutral": ["a soft sand-toned wall"], "cool": []},
    },
}


def _scene_pick(pool_slot: dict[str, list[str]], tone: str, subject: str, seed: int) -> str | None:
    """톤 버킷에서 결정론적 선택. 매칭 톤 → neutral 순 폴백. subject·seed 로 가게별·재생성별 변동.

    seed 를 선형 가산이 아니라 해시에 접는다 — subject 에 slot salt(_apply_scene_tone)가 이미
    붙어 있어 "subject:slot:seed" 해시가 되므로 surface·background 가 slot·seed 양축으로 독립
    선택된다(동조 방지, 무대 조합↑). 파이썬 내장 hash()는 프로세스마다 달라 결정론 깨짐 → hashlib.
    """
    import hashlib

    base = int(hashlib.md5(f"{subject}:{seed}".encode("utf-8")).hexdigest()[:8], 16)
    for t in (tone, "neutral"):
        cands = pool_slot.get(t) or []
        if cands:
            return cands[base % len(cands)]
    return None


def _apply_scene_tone(domain: str, mood: str, direction: str, tone: str,
                      subject: str, seed: int) -> str:
    """direction 의 표면/배경 스팬을 입력 톤에 맞춰 교체(DIV-2). 스팬 미발견·후보 없음은 무변경."""
    spans = _SCENE_SPANS.get((domain, mood))
    pools = _SCENE_POOLS.get((domain, mood))
    if not spans or not pools:
        return direction
    for slot in ("surface", "background"):
        span = spans.get(slot)
        pool = pools.get(slot)
        if not span or not pool or span not in direction:
            continue
        # slot 별로 subject 를 salt → surface·background 가 독립 선택(동조 방지, 무대 조합↑).
        pick = _scene_pick(pool, tone, f"{subject}:{slot}", seed)
        if pick and pick != span:
            direction = direction.replace(span, pick, 1)
    return direction


_STYLE_ALIASES = {
    "editorial": "editorial",
    "pop": "pop",
    "realism": "realism",
    "pastel": "pastel",
    "pastel_float": "pastel",
    "monotone": "monotone",
    "warm_organic": "warm_organic",
    "warm_vintage": "warm_organic",
}

_CLIP_STYLE_ANCHORS = {
    "editorial": "airy premium editorial, soft natural light, clean copy space",
    "pop": "bold pop advertising, saturated color-block set, crisp hard light",
    "realism": "true-to-life commercial photography, natural texture and light",
    "pastel": "soft pastel advertising set, high-key diffused light",
    "monotone": "minimal tone-on-tone campaign, graphic shadow",
    "warm_organic": "warm organic editorial, travertine, gentle golden light",
}

# PALETTE-001(2026-07-20): "pop" 스타일이 상품과 무관하게 도메인당 색조합 딱 1개로 고정돼
#   있었다("항상 저 색깔로만 출력"). reference_recipe_data.PALETTE_VARIANTS에 이미 pop용
#   후보(cobalt_duo/teal_duo/coral_duo)가 있지만, 그건 "전부 후보 — 시각 몽타주 승인 전
#   조립부 사용 금지"로 명시된 미승인 레지스트리라 여기서 그대로 끌어쓰지 않는다. 대신
#   기존 색(원래 프로덕션에서 쓰던 값)을 variant 0으로 유지하고, 같은 미감을 유지하는 새
#   조합을 추가해 상품명(subject_en) 해시로 결정론적 선택한다 — 같은 상품은 항상 같은 색,
#   다른 상품은 다른 색. PALETTE-002(같은 날): pastel·monotone(food/drink)도 같은 문제라
#   같은 방식으로 확장 — object monotone은 원래 색 미지정("one restrained color family")이라
#   해당 없음.
_POP_PALETTES: dict[str, tuple[str, ...]] = {
    "food": (
        "a saturated cobalt-blue background and a clean tomato-red table surface",
        "a saturated magenta-pink background and a clean lime-green table surface",
        "a saturated golden-yellow background and a clean deep-violet table surface",
    ),
    "drink": (
        "a saturated cobalt-blue background and a clean vivid orange table surface",
        "a saturated teal background and a clean coral table surface",
        "a saturated violet background and a clean chartreuse table surface",
    ),
    "object": (
        "a saturated electric-blue surface against a vivid coral background",
        "a saturated emerald-green surface against a vivid magenta background",
        "a saturated amber-yellow surface against a vivid indigo background",
    ),
}

_PASTEL_PALETTES: dict[str, tuple[str, ...]] = {
    "food": (
        "a pale blush background and a low muted lavender table plane",
        "a pale powder-blue background and a low muted blush-pink table plane",
        "a pale mint-green background and a low muted lilac table plane",
    ),
    "drink": (
        "a pale blush background and a muted lavender table plane",
        "a pale powder-blue background and a muted blush-pink table plane",
        "a pale mint-green background and a muted lilac table plane",
    ),
    "object": (
        "a pale blush background and one low matte lavender pedestal behind the product",
        "a pale powder-blue background and one low matte blush-pink pedestal behind the product",
        "a pale mint-green background and one low matte lilac pedestal behind the product",
    ),
}

_MONOTONE_PALETTES: dict[str, tuple[str, ...]] = {
    "food": (
        "a strict deep burgundy monochrome environment using wine-red, charcoal and black only",
        "a strict pale dove-gray monochrome environment using soft gray, warm white and pale taupe only",
    ),
    "drink": (
        "a strict espresso-brown monochrome environment using coffee brown, dark cocoa and warm cream only",
        "a strict pale dove-gray monochrome environment using soft gray, warm white and pale taupe only",
    ),
}


def _palette_clause(palettes: dict[str, tuple[str, ...]], domain: str, subject_en: str) -> str:
    """상품명 기준 결정론적 팔레트 선택. 같은 상품은 재생성해도 항상 같은 색."""
    variants = palettes.get(domain, palettes.get("food", next(iter(palettes.values()))))
    digest = hashlib.sha256((subject_en or "").strip().lower().encode()).digest()
    return variants[digest[0] % len(variants)]


_STYLE_PALETTES: dict[str, dict[str, tuple[str, ...]]] = {
    "pop": _POP_PALETTES,
    "pastel": _PASTEL_PALETTES,
    "monotone": _MONOTONE_PALETTES,
}


def _style_palette_clause(style_key: str, domain: str, subject_en: str) -> str:
    palettes = _STYLE_PALETTES.get(style_key)
    if palettes is None:
        return ""
    return _palette_clause(palettes, domain, subject_en)


# CONTAINER-001(2026-07-21): food 프리앰블의 "no cup/tumbler"(BUG-KTX-001·PLATING-001 대응)와
#   (food,realism)의 "plate resting flat on dark charcoal"(BUG-KTX-001-2 대응)이 굽 유리볼
#   빙수 같은 장식 용기를 밋밋한 식당 접시로 강제 변환(운영 historyId=107). 실측 버그 대응
#   문구라 삭제 불가 — analyze_photo(Vision)가 본 용기 묘사로 분기해 장식 용기(vessel)일 때만
#   긍정 단언 프리앰블로 치환한다. 문구·분류 키워드는 prompts/reference_style_plans.yaml(T1).
def classify_container(container_desc: str | None,
                       container_opacity: str | None = None) -> str:
    """Vision 용기 묘사 → 'vessel'(내용물 보이는 유리 디저트 용기) | 'default'(접시 경로).

    실측(2026-07-21): analyze_photo가 굽·스템을 단어로 안 주고 kind는 'glass'/'plate' 수준.
    대신 opacity가 유리 용기(transparent)와 불투명 접시(opaque)를 확실히 가른다. 판정 3층위:
      1) vessel_keywords(고블릿·파르페 등 명시 형태) → opacity 무관 vessel.
      2) flat_kinds(plate·board 등) → 투명이어도 default(PLATING-001 가드).
      3) glass_vessel_kinds(glass·bowl·cup 등 깊은 용기) + opacity∈{transparent,translucent}
         → 내용물 비치는 쇼피스 vessel.
    근거 없음(None·빈값)·미분류는 전부 'default' — 컵 변환·프로핑 대응 문구 유지 안전측 폴백.
    이름 추정 금지(개정 #2): 입력은 analyze_photo 산출만.
    """
    desc = (container_desc or "").strip().lower()
    if not desc or desc == "none":
        return "default"
    if any(kw in desc for kw in _prompts.get(_NS, "container.vessel_keywords")):
        return "vessel"
    if any(fw in desc for fw in _prompts.get(_NS, "container.flat_kinds")):
        return "default"
    opacity = (container_opacity or "").strip().lower()
    if opacity in ("transparent", "translucent") and any(
            dk in desc for dk in _prompts.get(_NS, "container.glass_vessel_kinds")):
        return "vessel"
    return "default"

# RETOUCH-003: tpl_47(identity_grade=loose) 정본 이상화 절 — 디저트 전용.
#   "같은 제품으로 인식 + 무발명" 경계 안에서 최상의 광고 버전으로 끌어올린다.
#   ⚠️ 길이 예산(RETOUCH-003-2 실측): 잠금이 씬 지시보다 앞이라 T5 512토큰 초과 시 씬이
#   잘림 — 이상화 3/3에서 팔레트·소품 소실, 우드 테이블 폴백. append 금지, 절제형 리터치
#   절(_RETOUCH_RESTRAINED)과 맞교환할 것. 'warm light'도 우드 프라이어를 당겨 제거.
# RETOUCH-004: 질감 절을 제품별 상수로 분리 — 초코 디저트는 generic(스펀지·과일 일반론)이
#   약해 크럼블리하게 남는다(2차 시안 아트디렉터 관찰) → 초코 전용 어휘로 **등길이 맞교환**
#   (append 금지는 여기도 동일). 'ganache'는 기존 크림의 렌더 수사(simile)로만 — 무발명 유지.
_IDEALIZE_TEX_GENERIC = (
    "moist airy sponge with visible pores, silky luscious cream with a dewy sheen, glossy juicy fruit"
)
_IDEALIZE_TEX_CHOCO = (
    "moist fudgy chocolate sponge, its cream silky and glossy like soft ganache, deep cocoa "
    "color, glossy juicy fruit"
)
_DESSERT_IDEALIZE = (
    "Do NOT paste the original photo as-is. Idealize this dessert into its most appetizing premium "
    "advertising version — the same dessert, clearly recognizable, with the same layers, ingredients "
    "and decoration. Rich appetizing light, deep natural color, " + _IDEALIZE_TEX_GENERIC + ", "
    "a real photograph, never plastic or "
    "over-smoothed, and never add ingredients, layers or decoration beyond the original. "
    "Remove any screenshot UI elements, icons, buttons or watermarks. "
)


_IDENTITY_LOCKS = {
    "food": (
        # BUG-KTX-001-2(2026-07-20): "realism" 스타일에서 컵 변환이 재발(negative 문구만으로는
        #   불충분, 4/4는 아니지만 재현됨). 문장 맨 앞에 긍정 단언을 추가 — 부정문보다 앞쪽의
        #   긍정 진술이 모델 조건화에 더 강하게 anchor된다는 관찰에 따른 보강.
        # PLATING-001-3(2026-07-20): 두 번째 강화도 실패(프렌치토스트 재현 지속) — "propped up"
        #   부정문만으로는 못 이기는 강한 모델 편향(빵/토스트를 기대 세워 찍는 흔한 음식사진
        #   프로핑 연출)으로 판단. 긍정 단언을 이 지점에도 추가하고, 빵/토스트류를 구체적으로
        #   호명해 눕혀진 상태를 명시 — BUG-KTX-001의 "컵 아님" 성공 패턴(부정 대신 긍정 우선)을
        #   재적용.
        "This is a plated food photograph resting flat on a table, photographed from above or at a gentle angle "
        "— never a food item standing upright or propped on its edge. If the food is a slice of bread, toast, "
        "cake or similarly flat-cut item, it lies flat on its widest cut face, the same way it was photographed "
        "originally. There is no cup, mug, tumbler, lid or straw anywhere in this image. "
        "Edit this exact food photograph. Keep every food item, plate, sauce and garnish exactly as "
        "photographed: the same count, shape, doneness, texture and colors. "
        # BUG-KTX-001(2026-07-20): top-down 원형 접시 샌드위치가 4/4 시드에서 테이크아웃 컵으로
        #   정규화됨(접시의 원형·방사형 골이 컵 뚜껑 시각신호와 겹침). 객체 변환 부정문으로 차단
        #   — seed42 단독 검증에서 정체성·구도 복원 확인.
        "Never convert the food, its plate or bowl into a cup, mug, takeaway container or any different "
        "kind of object. The subject must remain a plated food item, never a beverage. "
        "Do not add, remove, redraw, resize or recolor any food item, and do not rearrange food items relative "
        "to each other. "
        # PLATING-001(2026-07-20): editorial 등 배경·구도를 새로 그리는 스타일에서 "카메라 앵글 고정"
        #   지시를 모델이 절반만 따라 배경만 바뀌고 음식은 원본 각도 그대로 남아, 새 장면(테이블·창문)
        #   위에 붕 뜨거나 단면으로 세워진 것처럼 보이는 부자연스러운 결과가 나옴(육안 확인).
        #   카메라 앵글 고정 대신 "장면에 맞는 자연스러운 접지"를 명시적으로 요구.
        # PLATING-001-2(2026-07-20): "pop" 스타일(강한 각도·다이애거널 섀도 연출)에서 재발 —
        #   프렌치토스트가 접시 위에 기대 세워진 채로 나옴. 기존 문구가 "떠있지 마라"는 다뤘지만
        #   "기대 세우는" 흔한 음식사진 프로핑 연출은 명시적으로 안 막고 있었음 — 추가.
        "You may reorient the whole plate or food as a single rigid object so it sits naturally within the new "
        "scene, but it must always rest fully and flatly on the table surface with its full base or underside in "
        "contact with the plate, casting a single realistic contact shadow, as if simply set down under normal "
        "gravity. Never leave the food floating, tilted upright, propped up, leaned back, leaning against "
        "anything, resting on a thin cut edge, or otherwise unsupported — this is a flat lay or gently-angled "
        "tabletop shot, never a propped-up or upright food-styling shot. This rule applies with no exceptions, "
        "regardless of camera angle, background color or lighting mood. "
        "Change the background, table surface, camera framing and environmental lighting to match the requested "
        "scene. "
    ),
    # 디저트(케이크·타르트·베이커리 등): 접시는 '상품'이 아니라 '연출(용기)' → 예쁜 디저트 접시로
    #   재플레이팅 허용(사용자 지시 2026-07-21 "예쁜 그릇 써 디저트잖아"). product-understanding
    #   상품=보존/용기=조정. 단 BUG-KTX-001(접시→컵)·PLATING-001(붕뜸/기울어짐) 가드는 그대로 유지:
    #   디저트는 여전히 컵/음료 아님, 평평히 접지. 케이크 자체(층·크림·토핑·색)는 완전 보존.
    # RETOUCH-003-2 압축(2026-07-24): 이 락 단독 544 T5토큰 = 예산(512) 단독 초과 —
    #   씬 지시가 통째로 잘려 우드 폴백(에디토리얼 우드 편차 3회의 유력 원인). 가드의
    #   핵심 명사(cup·takeaway·propped·contact shadow)와 테스트 마커는 보존하고 수사만 압축.
    "food_dessert": (
        "This is a plated dessert photograph resting flat on its widest base on a table, photographed "
        "from above or at a gentle angle — never standing upright or propped on its edge. There is no "
        "cup, mug, tumbler, lid or straw. "
        "Edit this exact dessert photograph. Keep the dessert structurally unchanged: the same shape, "
        "layers, cream, toppings, fruit and hue identity — never add, remove, redraw or rearrange any "
        "part of it. "
        # RETOUCH-001(2026-07-24): 본체가 폰사진 노출 그대로 보존되는 이질감 교정 — 보정 O/변형 X.
        # RETOUCH-003(2026-07-24 아트디렉터 "전혀 먹음직스럽지 않다"): 절제형 보정(-002)의 천장
        #   확인 — tpl_47(케익 단면 템플릿, identity_grade=loose) 정본 철학으로 승격: 원본을
        #   그대로 붙여넣지 않고 '같은 제품으로 인식되는 선'에서 최상의 광고 버전으로 이상화.
        #   정직성 경계 유지: 없는 재료·층·데코 발명 금지.
        + _DESSERT_IDEALIZE +
        # 핵심 개정: '접시 고정'을 풀되 대상은 '용기(접시)'로 한정, 케이크는 위에서 보존한다.
        "You SHOULD replace the plain plate with a designer dessert plate worthy of a high-end "
        "patisserie — artisanal ceramic, sculpted or scalloped rim, soft blush, sage, matte charcoal "
        "or gold-rimmed, never a plain white dish. Restyle only the plate, not the dessert. "
        # BUG-KTX-001 가드 유지: 재플레이팅이 접시를 컵/그릇으로 변형시키지 않도록 명시.
        "Never turn the dessert or its plate into a cup, mug, takeaway container or any different "
        "object — it stays a solid plated dessert, never a beverage. "
        # PLATING-001 가드 유지: 붕뜸/기울어짐 방지.
        "It rests fully and flatly on the new plate with a single realistic contact shadow under "
        "normal gravity — never floating, tilted upright, propped up or resting on a thin cut edge. "
        "Change the background, table surface, framing and lighting to match the requested scene. "
    ),
    "drink": (
        "Edit this exact drink photograph. Preserve every source pixel belonging to the drink and its vessel. "
        "Keep the exact vessel silhouette, rim, base, wall shape, material, transparency and proportions, including "
        "whether a handle or saucer is present or absent. Keep identical foam, ice, toppings, liquid level, colors, "
        "camera angle, crop and arrangement. Do not add any vessel part absent from the source. Do not redraw, move, "
        "rotate, recolor or cover the drink or its vessel. Change only the "
        "background, table surface and environmental lighting. "
    ),
    "object": (
        "Edit this exact product photograph. Preserve the product exactly as photographed: identical silhouette, "
        "proportions, material, surface details, seams, controls, label, logo, lettering, camera angle, crop and "
        "perspective — the same real-world object from the same viewpoint, never reshaped, restyled or redesigned. "
        "Do not redraw, reshape, smooth, duplicate, rotate, recolor or cover the product. "
        # NO-INVENTED-PARTS(2026-07-27 아트디렉터: 매직마우스=휠 없는 매끈한 제품인데 생성이
        #   휠·버튼을 발명 — SKU 위조): 원본에 없는 부품·디테일 추가 금지(긍정 단언 선행).
        "The product has exactly the parts and details visible in the photo and no others — do not add or invent "
        "any button, wheel, seam, port, texture or marking that is not in the original. "
        # POP-SHAPE(2026-07-27: pop 추상 색블록 씬에서 실루엣이 매끈한 조약돌 블롭으로 용해):
        #   스타일라이즈드 씬에서도 실루엣 불변을 명시.
        "Even in a stylized, abstract or color-block scene the product keeps its exact photographed silhouette "
        "and proportions — never simplified, melted, inflated or turned into a smooth featureless blob. "
        # NEW-PRODUCT(2026-07-27 아트디렉터: 형태는 실물처럼 보존하되 '새 상품'처럼 보이게):
        #   형태·디자인·로고는 완전 불변, 표면만 공장 출고 신품처럼 이상화(흠집·먼지·지문·마모 제거).
        "Render it as a brand-new, pristine retail product: a clean, flawless, factory-fresh surface with no "
        "scratches, scuffs, dust, fingerprints, smudges or visible wear — while keeping the exact same shape, "
        "design and markings. Change only the background, supporting surface and environmental lighting. "
    ),
}

# POP-V2(2026-07-23 아트디렉터 판정): 팝 전용 완화 잠금 — 음식 본체는 불변이되,
#   ① 밋밋한 앞접시("식당 앞접시" 문제)를 예쁜 디저트 접시로 교체 허용
#   ② 접시 위 먹음직 가니시 허용 — 단 "그 음식에 실제 보이는 재료"만(정직성: 없는 재료
#      위장 금지는 유지, 데코 수준만 완화). r2 시안 육안 판정으로 채택.
# RETOUCH-003-2: 헤드/리터치/테일 3분할 — 디저트는 리터치 절만 _DESSERT_IDEALIZE로
#   맞교환한다(append 금지: T5 512토큰 예산 — 초과분은 뒤쪽 씬 지시부터 잘려 팔레트·소품
#   소실, 이상화 1차 GPU 실측 3/3 우드 폴백).
_FOOD_POP_HEAD = (
    "This is a real plated food photograph. Keep the food structurally unchanged — same shape, layers, "
    "textures, toppings and hue identity, never redrawn, resized, repainted or turned into a cup or "
    "different object. "
    # COLOR-LOCK(2026-07-25 아트디렉터: 팝에서 다크 초코 베이스가 주황 스펀지로 변색=정체성 위반).
    #   각 층 원본 색을 못 박아 밝은 씬 압력의 warming을 차단(예산 위해 압축).
    "Keep each layer its exact original color: dark chocolate stays dark brown, never recolored, warmed "
    "or lightened into a different tone. "
)
# RETOUCH-001(2026-07-24 아트디렉터: "원본 유지하되 먹음직스럽게 — 뿌연 사진 그대로는
#   너무 별로"): 배경·소품은 스튜디오급인데 본체가 폰사진 노출 그대로라 이질감 —
#   프로 푸드 리터치를 명시 허용(보정 O / 변형 X). A모드 리터치 철학의 스타일 경로 이식.
# RETOUCH-002: tpl_47 질감 어휘 이식 — moist/airy/velvety 조건부 강화("퍼석" 방지)
# RETOUCH-005(2026-07-27): 리터치 텍스처 어휘를 스왑 가능한 상수로 분리. 기본(SWEET)은 디저트용
#   (스펀지·크림·과일) — 짭짤한 음식엔 텍스처 앵커가 없어 햄이 "찰흙"으로 렌더(아트디렉터 리포트).
#   리얼리즘 짭짤 음식은 build 에서 SAVORY로 **등길이 맞교환**(T5 512 예산: append 금지).
_RETOUCH_TEX_SWEET = (
    "sponge moist and airy with visible pores, cream silky with a dewy sheen, fruit glossy and juicy, "
    "sauces glossy, never dry, matte or plastic"
)
# SAVORY-TEX(2026-07-27 워크플로 적대검증 합성안): 가공육/고기 마블링 + 익힘 윤기. 'cured slices'로
#   게이팅(통마블링 꽃등심을 슬라이스로 안 바꿈), 'glossy'로 날/마른 고기 방지, guard 'uniform·
#   claylike'가 아트디렉터 "찰흙"·"매끈 분홍 슬랩" 직격. 음식명·'raw'·부정문 음식명사 없음(소환 방지).
_RETOUCH_TEX_SAVORY = (
    "meat marbled with fat, muscle grain, cured slices thin, folded and glossy, bread crusty, crumb "
    "airy, cheese glossy, vegetables crisp, sauces glossy, never dry, matte, uniform or claylike"
)
# 고기 신호 없는 짭짤 요리(비빔밥·샐러드·플레인 라이스/면)엔 marbling 어휘가 고기를 소환할 수 있어
#   meat 어휘를 뺀 변주(2-tier). build 의 _has_meat 로 분기.
_RETOUCH_TEX_SAVORY_PLAIN = (
    "bread crusty with airy crumb, cheese glossy, vegetables crisp and fresh, rice and noodles moist "
    "and distinct, sauces glossy, never dry, matte, uniform or claylike"
)
_RETOUCH_RESTRAINED = (
    "Retouch it like a professional food ad: brighten exposure, remove haze — "
    + _RETOUCH_TEX_SWEET +
    ". Enhance only what is there, same hues, never restyling. Remove any "
    "screenshot UI, icons or watermarks. "
)
# FOOD-FIDELITY(2026-07-27, T5 맞교환): savory 는 리터치 절의 디저트 질감 어휘(스펀지·크림·
#   과일)를 빼고 그 예산으로 본체 충실 절을 넣는다 — append 금지 원칙(초과분은 뒤 씬부터 잘림).
_RETOUCH_SAVORY = (
    "Retouch it like a professional food ad: brighten exposure, remove haze, sauces glossy, "
    "never dry, matte or plastic. Enhance only what is there, same hues, never restyling. "
    "Remove any screenshot UI, icons or watermarks. "
)
_FOOD_FIDELITY = (
    "Every ingredient, filling and cut surface stays exactly as photographed, never redrawn or "
    "substituted; add no sauce or topping not in the original; never turn it into a cake or a "
    "different dish. "
)
_FOOD_POP_TAIL = (
    "You MAY replace the plain plate with a beautiful dessert plate and add tasteful garnish using "
    "only the same ingredients already visible. "
    # NO-CUTLERY(2026-07-25 아트디렉터: 파스텔에 원본 플라스틱 포크 딸려옴 — 환각 아닌 소스
    #   캐리오버라 제거 명시). 재연출은 디저트만.
    "Show only the dessert — no fork or cutlery carried over from the original photo. "
    # PLATING-001-2/3(pop 사고 이력이라 완화 잠금에도 유지, 예산 위해 압축):
    "The food rests flat on its plate under gravity; a slice of cake or flat-cut item lies on its "
    "widest cut face, never standing upright, propped up or leaning. "
    "Premium food-styling quality, realistic photograph. "
)
_IDENTITY_LOCKS["food_pop"] = _FOOD_POP_HEAD + _RETOUCH_RESTRAINED + _FOOD_POP_TAIL

# SOUP-PRESERVE(2026-07-27 아트디렉터 "육개장 국물을 다 없애버리네 큰일났다"): 국·탕·찌개·면국물은
#   깊은 보울/뚝배기에 국물째 내는 요리. styled 경로(재플레이팅+씬 재구성)가 국물을 비우고 납작
#   접시로 옮겨 마른 파스타로 붕괴(정체성·정직성 파괴). 전 무드 공통 in-place 보존(CLAUDE.md
#   절대함정 #5: 용기 담긴 음식 in-place). 리얼리즘 품질 리터치 + '같은 모양 더 예쁜 보울' 재연출은
#   허용(납작 접시·국물 비우기만 금지 — 아트디렉터 "깊은 보울 모양 유지하면 바꿔도 됨").
_FOOD_SOUP_LOCK = (
    "This is a real photograph of a Korean soup or broth dish served in a deep bowl or pot. "
    "Edit this exact photograph and keep it a soup: keep all of its broth and liquid filling the "
    "bowl at the same level — never drain, pour out, reduce or remove the broth, and never move the "
    "food onto a flat plate. "
    "Keep every noodle, piece of meat, vegetable and topping exactly as photographed — the same kind, "
    "count, thickness and arrangement; keep the noodles their exact original shape and thickness, and "
    "add nothing that is not already there. "
    "Retouch it like a professional food ad: brighten exposure, remove haze, broth rich and glossy, "
    "meat and vegetables fresh and glossy, never dry, matte or claylike. Enhance only what is there, "
    "same hues, never restyling. "
    "You MAY present it in a beautiful deep bowl or earthenware pot, but it stays a deep "
    "broth-holding bowl of the same shape — never a flat plate, cup, mug or takeaway container. It "
    "rests flat on the table under gravity with a single realistic contact shadow. "
    "Change only the background, table surface, camera framing and environmental lighting to match "
    "the requested scene. "
)

# REALISM-FIDELITY(2026-07-27 아트디렉터): 리얼리즘 음식은 원본(고기·반찬·곁들임) 정체성 충실
#   보존 + 품질 리터치 + '같은 종류 접시 업그레이드'만. food_pop(디저트·양식용 재플레이팅+소품
#   스캐터)이 한식/고기에 부적합 — 찰흙 햄·뭉개진 꽈리고추·없는 소품(빨간 덩어리) 소환을 유발해
#   교체. 리터치 절(_RETOUCH_RESTRAINED)은 build 에서 SAVORY 로 스왑(짭짤 텍스처).
_FOOD_REALISM_HEAD = (
    "This is a real plated food photograph. Keep the food and its real side dishes exactly as "
    "photographed — the same dish, the same ingredients, garnishes and accompaniments already on the "
    "plate, the same count, shape, arrangement and colors. Do not add, remove, redraw, resize or "
    "recolor any food item, and do not scatter any new prop, ingredient or garnish that is not "
    "already there. "
)
_FOOD_REALISM_TAIL = (
    "You MAY restyle the serving plate into a more beautiful plate of the same kind and shape, but "
    "keep the food itself untouched, and never turn the food or its plate into a cup, mug, takeaway "
    "container or a different object. The food rests flat on its plate under gravity with a single "
    "realistic contact shadow, never propped up or leaning. "
    "Change the background, table surface, camera framing and environmental lighting to match the "
    "requested scene. "
)
_IDENTITY_LOCKS["food_realism"] = _FOOD_REALISM_HEAD + _RETOUCH_RESTRAINED + _FOOD_REALISM_TAIL

# POP-V2 아키타입 로테이션(2026-07-23): 레퍼런스 4아키타입(광고레퍼런스_v3_재분류_2/01_스타일무드/pop)
#   이 STY-003 추출 과정에서 saturated_color_block 하나로 붕괴("No extra food, props, splashes,
#   floating objects" 금지문까지 박힘)된 드리프트를 교정 — 4연출을 subject+seed 로테이션.
#   공통 문법(레퍼런스 관찰): 화면 채움·제품 톤 앵커({palette}=PAL-002 적응형)·소품/액션.
#   정직성: 소품·부유·액션 전부 "음식에 실제 보이는 재료"로 한정. gradient 는 하드 스플릿으로
#   렌더되는 함정이 있어 "smooth softly blended ... no hard edge" 문구 필수(r1 실측 2회 재현).
# POP-V2.1(2026-07-24 핫픽스, 아트디렉터 리포트 "소품이 찰흙 덩어리"): 소품을 추상 지시
#   ("its own visible ingredients")로 시키면 Kontext가 형태 없는 덩어리를 빚는다(라이브 실측
#   — 케이크 s42 분홍 스펀지 무더기, 파스타 s7 본체 재드로잉까지). 성공 케이스는 전부 명명된
#   소품(파마산 큐브·freeze-dried strawberry slices)이었음 → {props}에 core_ingredients 기반
#   **구체명**을 런타임 주입 + "clearly shaped, photorealistic, no shapeless lumps" 안티-덩어리
#   절 + ①은 "Fill the scene"(씬 재구성 압력, 면류 본체 재드로잉 유발)을 "Scatter around"로
#   낮추고 카메라 앵글·본체 고정 재단언.
_POP_FOOD_VARIANTS: tuple[str, ...] = (
    # ① ingredient_world — 톤온톤 소품 무리 (sports_concept 유래)
    "Keep the food and its camera angle exactly as photographed. Scatter {props} generously across the "
    "table around a scalloped gold-rimmed dessert plate — every prop clearly shaped, glossy and "
    "photorealistic, no shapeless lumps. Use {palette}, keeping the whole scene tone-on-tone with the "
    "product. Bright cheerful studio light with crisp soft shadows, joyful pop energy.",
    # ② styling_cut — 러블리 스타일링 컷 (food_metaphor 유래) + 오브제 다양화(구슬)
    "Style a lovely editorial styling cut: the food on a scalloped gold-rimmed dessert plate with {props} "
    "arranged appetizingly around it on the plate, a soft satin ribbon, a delicate "
    "string of small pearls and a few small glossy decorative beads nearby on the table — every object "
    "clearly shaped and photorealistic. Use {palette}. Soft romantic pop light, sweet gift-like mood.",
    # ③ dynamic_float — 소품 공중 부유 + 소프트 그라데이션 (dynamic_float 유래)
    "Keep the food and its camera angle exactly as photographed, presented on an elegant footed dessert "
    "stand. Surround it with {props} floating weightlessly in mid-air at clearly different heights and "
    "sizes filling the upper frame — each floating piece clearly shaped, glossy and photorealistic with no "
    "contact shadow, never shapeless lumps. Use {palette}, rendered as a smooth softly blended gradient "
    "with no hard edge. Playful dynamic energy, bright studio light.",
    # ④ gradient_action — 그라데이션 + 자기 재료 드리즐 액션 (saturated_color_block 유래)
    #   r3 실측(07-23): "케이크 위로" 붓게 하면 본체 재드로잉 → 접시 옆 + 본체 온전 노출 명시.
    "A continuous glossy stream of the food's own cream or sauce pouring from above onto the plate right "
    "beside the food, captured mid-pour with a delicate splash — the food itself stays fully visible and "
    "unchanged at its original camera angle. {props} beside it on an elegant rimmed dessert plate, each "
    "clearly shaped and photorealistic. Use {palette} — the table clean and seamless, no wooden surfaces, "
    "no unrelated objects — with the background rendered as a smooth softly blended vertical gradient with "
    "no hard edge. Bold playful composition, crisp pop lighting.",
)

# STYLE-V2(2026-07-24, 아트디렉터 판정 "팝과 차이 없다·그릇 엉망·소품 없어 단조"): 모노톤·
#   파스텔도 pop과 동일한 아키타입 붕괴 상태였음 — 레퍼런스(01_스타일무드/monotone·pastel)의
#   각 3아키타입을 로테이션으로 복원. 그릇(스타일 무드 매칭)·소품({props} 재료 기반+비식품
#   무드 오브제) 포함. {palette}=PAL-003 적응형 절.
_MONO_FOOD_VARIANTS: tuple[str, ...] = (
    # ① dark_color_lock — 딥 모노크롬 + 톤 매칭 박스·리본 오브제 스택 (레퍼런스: 블랙 기프트박스)
    "Set a dramatic dark color-lock scene: the food on a matte charcoal stone plate, a neat stack of "
    "tone-matched gift boxes and a satin ribbon in the same deep hue arranged behind it, with {props} "
    "beside the plate. Use {palette}. Keep the food's true colors vivid and isolated against the "
    "monochrome surroundings. Precise warm rim light and one bold diagonal shadow, premium editorial "
    "quality, every object clearly shaped and photorealistic.",
    # ② gold_blush_luxury v3 (구 pale_color_lock — r2 실패: 앞접시 2장 겹침·파스텔과 혼동.
    #   아트디렉터 07-24: "밝게 하려면 골드+핑크" → 페일 락을 골드+블러시 럭셔리로 재정의,
    #   주얼리 캠페인 급 고급감. 접시=골드림 마블 슬랩 단일.)
    "Set a luxurious bright scene in blush and gold: the food kept exactly as photographed, presented "
    "on a single polished pale marble slab plate with a thin brushed-gold rim — one plate only, never "
    "stacked plates — resting on a low marble pedestal. Behind it one small polished gold sphere and "
    "a short round gold pillar-stand as decor. Use {palette} with warm golden accents. Elegant "
    "directional light with one long refined shadow; the food's true colors isolated. Premium "
    "jewelry-campaign quality, every object clearly shaped and photorealistic.",
    # ③ brand_color_lock — 주조색 몰입 + 대각 구도 (레퍼런스: smize 레드 몰입. r-pasta 실측:
    #   연한 제품은 몰입이 밍밍해짐 → 색족의 가장 딥한 톤으로 몰입 채도 강화 + 본체 고정 명시)
    "Set a bold color-immersion scene: the food kept exactly as photographed, while the background, "
    "table surface and a smooth ceramic plate are all drenched in the same color family — use the "
    "deepest, most saturated tone of {palette} for the immersion. The food's true colors stand out as "
    "the only contrast, with {props} placed sparsely beside the plate. Dynamic diagonal framing, "
    "crisp studio light, every object clearly shaped and photorealistic.",
)

_PASTEL_FOOD_VARIANTS: tuple[str, ...] = (
    # ① dreamy_float v3 — 쉬머 실크 표면 (r2: 유리 접시는 성공, 표면 쉬머 약함 + 아트디렉터
    #   07-24 "부드러운 소품 = 쉬머 천·실크, 팝과 차이가 없다" → 파스텔의 소품 언어는 재료가
    #   아니라 소프트 텍스타일. 표면 자체를 흐르는 쉬머 실크로.)
    "Create a dreamy pastel scene: the food on a wavy fluted opalescent glass dessert plate, set on "
    "flowing shimmering silk fabric with a soft satin sheen, gentle folds catching the light all "
    "around — never a flat solid background. Use {palette} as the silk's tint. Only a few small "
    "{props} tucked into the silk folds. Soft diffused dreamy light with gentle bokeh; keep all food "
    "colors fully natural, never pastel-tinted.",
    # ② soft_pedestal — 새틴/시폰 드레이프 위 (레퍼런스: 핑크 시폰 팔찌. r1 통과작 — 실크·시폰
    #   레이어링만 보강)
    "Style the food on a scalloped pastel ceramic plate set on softly draped silk satin fabric with "
    "gentle flowing folds, a sheer chiffon layer drifting at the edge of frame. Use {palette}. A few "
    "{props} nestled in the fabric folds, each clearly shaped. High-key soft light, tender gift-like "
    "romantic mood; keep all food colors fully natural.",
    # ③ pastel_product_hero v3 — 파스텔 공간 감성 + 실크 러너 (아트디렉터 07-24: 소프트
    #   텍스타일이 파스텔의 소품 언어 — 리넨 냅킨 대신 실크 러너로 팝과 차별화)
    "Place the food on a scalloped wavy-rim pastel ceramic plate set on a flowing silk table runner "
    "with a soft sheen, in an airy pastel room corner: a softly textured plaster wall with a gentle "
    "gradient of window light — never a flat solid background — a small pastel ceramic vase with "
    "baby's breath and a pastel mug nearby, a few {props} beside the plate. Use {palette} as the "
    "room's tint. Calm serene styling, every object clearly shaped and photorealistic; keep all food "
    "colors fully natural, never pastel-tinted.",
)

# STYLE-V3(2026-07-25, 아트디렉터 6무드 피드백): editorial/realism/warm_organic 도 pop/mono/
#   pastel 처럼 아키타입 로테이션으로 고도화. 각 스타일 고유 접시·소품·구도 — editorial=warm 과
#   접시 판박이 문제 해결(각자 시그니처 접시 명시), warm=빈티지 소품 추가(현 "no wood" 억제 역전).
#   팔레트 미지원 스타일이라 {palette} 대신 시그니처 톤을 문구에 박음. {props}=재료 기반 가니시.
#   ※ 이 3스타일도 food_pop 공용 완화 잠금(본체 불변+접시 교체+가니시)을 받는다.
# STYLE-V3.1(2026-07-26 아트디렉터: "editorial/realism/warm 접시가 또 식당 앞접시. 고급스럽고
#   다양한 모양 + 하드코딩 반대"). 접시를 프롬프트에 박지 않고 데이터 레지스트리에서 시드로
#   모양 선택({plate} 자리표시자) → 모양 다양성 + 스타일별 마감(톤)만 고정해 정체성 유지.
#   {palette}/{props} 와 동일한 소프트코딩 패턴. "never a plain restaurant plate" 부정으로 앞접시 차단.
# STYLE-V3.3(2026-07-26 아트디렉터: v3.2 rim은 살았으나 "8종이 전부 둥근 접시+rim 변형 —
#   형태가 고정". 평평한 접시·원기둥(받침/케이크스탠드)·프리폼 등 FORM 다양성 요구).
#   → 레지스트리를 rim 변형이 아니라 **서빙 형태(FORM)** 로 재구성. 스타일 대비 마감은 유지
#   (차콜림/반응유약/골드림 = 저대비 앞접시 렌더 회피, v3.2에서 확증).
# STYLE-V3.4(2026-07-26): "square plate" 제거 — Kontext가 케이크 접시를 사각으로 못 그리고
#   (라운드 렌더), realism s14 에서 케이크를 돔→평평 원반으로 재드로잉(정체성 위반, 아트디렉터
#   적발). 접시 형태는 케이크 본체를 재구성하지 않는 것만 유지(스탠드=케이크 그대로 올림,
#   나머지=rim만). 남은 7형태는 셰이프 안전 실측분.
_PLATE_SHAPES: tuple[str, ...] = (
    "a flat round plate with a fluted scalloped rim",
    "a footed cake stand raised on a short cylindrical pedestal",
    "a low pedestal dish lifted on a slim cylindrical foot",
    "a shallow wide coupe with gently curved walls",
    "an organic freeform platter with an irregular hand-shaped edge",
    "a lotus-form dish with layered petal tiers",
    "a hand-thrown stoneware plate with a rippled uneven rim",
)
_STYLE_PLATE_FINISH: dict[str, str] = {
    "editorial": "in crisp white porcelain with a fine dark charcoal rim line",
    "realism": "in sleek dark metallic-glazed ceramic with a bright polished silver-metal rim",
    "warm_organic": "in warm cream ceramic with a bold brushed-gold rim",
}

def _plate_clause(style_key: str, subject: str, seed: int) -> str:
    """프리미엄 접시 — 레지스트리에서 subject:seed 로 **서빙 형태(FORM)** 선택(형태 다양성) +
    스타일 대비 마감(정체성·가시성). 하드코딩 고정 접시 아님, 결정론 로테이션."""
    idx = int(hashlib.sha256(f"{subject}:{seed}:plate".encode("utf-8")).hexdigest()[:8], 16) \
        % len(_PLATE_SHAPES)
    finish = _STYLE_PLATE_FINISH.get(style_key, "in refined premium ceramic")
    return (f"{_PLATE_SHAPES[idx]} {finish}, a striking premium designer serving piece — its distinct "
            "form and rim clearly visible around the dessert, never a plain undecorated plate")

_EDITORIAL_FOOD_VARIANTS: tuple[str, ...] = (
    # ① magazine_minimal — {plate} + 여백
    "Plate the food on {plate}, on a muted cream stone table against a pale warm-gray wall. One softly "
    "folded linen napkin edge and a few {props} placed with restraint, with generous quiet copy space "
    "to one side. Soft directional window light and one gentle shadow, refined minimalist magazine "
    "composition, every object clearly shaped and photorealistic.",
    # ② sculptural_negative — 조형 오브제 + 넓은 네거티브 스페이스
    "Plate the food on {plate}, on a pale greige surface, with a single sculptural pale-stone object "
    "and a few {props} arranged asymmetrically amid wide negative space. Crisp soft-box editorial light "
    "with one clean shadow, elevated minimalist high-end composition, every object clearly shaped and "
    "photorealistic.",
)
# STYLE-V3.5→V3.7(2026-07-26 아트디렉터): 리얼리즘 = 미드센추리 모던 + 스테인리스/메탈("쇠테리어")
#   + 드라마틱 자연광 + macro 질감. V3.7: **메탈 소품 다양화** — 소품 레지스트리에서 시드로 2종
#   선택({metalprops}). 표면 묘사 압축해 예산 확보. {props}(재료 가니시)와 병행.
_REALISM_METAL_PROPS: tuple[str, ...] = (
    "a brushed steel tray",
    "a sleek chrome utensil",
    "a stainless-steel canister",
    "a polished metal ring sculpture",
    "a chrome geometric object",
    "a small aluminium vessel",
    "a mid-century chrome candle holder",
    "a steel wire fruit bowl",
)

def _metal_props_clause(subject: str, seed: int) -> str:
    """리얼리즘 메탈 씬 소품 2종 — 레지스트리에서 subject:seed 로테이션(서로 다른 2개)."""
    n = len(_REALISM_METAL_PROPS)
    i = int(hashlib.sha256(f"{subject}:{seed}:metal".encode("utf-8")).hexdigest()[:8], 16) % n
    off = int(hashlib.sha256(f"{subject}:{seed}:metal2".encode("utf-8")).hexdigest()[:8], 16) % (n - 1)
    j = (i + 1 + off) % n
    return f"{_REALISM_METAL_PROPS[i]} and {_REALISM_METAL_PROPS[j]}"

# V3.8(아트디렉터 "모노톤 다크와 겹침"): 리얼리즘은 어두운 저조도(X, 모노톤 영역)가 아니라
#   **밝고 청량한 미드센추리 모던 메탈** — 올-스텐 접시 + 스틸·티크·크롬 + 밝은 자연광. 모노톤과 구별.
_REALISM_FOOD_VARIANTS: tuple[str, ...] = (
    # ① bright_steel_teak — 밝은 스틸+티크 미드센추리, 밝은 데이라이트, 메탈 반사·소품
    "Photograph the food true to life on a flat round all-stainless-steel plate, on a bright "
    "brushed-steel and teak mid-century modern surface in a clean airy interior of chrome and white, "
    "crisp bright daylight with sharp metallic reflections, {metalprops} and {props} nearby. Clean "
    "bright industrial mid-century realism, macro texture, shallow depth of field.",
    # ② sunlit_steel — 창가 밝은 햇빛 + 스틸/티크 + 메탈 하이라이트·소품
    "Photograph the food true to life on a flat round all-stainless-steel plate, on a sleek "
    "steel-and-teak mid-century table by a bright window, strong daylight throwing crisp shadows and "
    "bright metallic highlights, {metalprops} and {props} beside it. Airy industrial mid-century "
    "realism, macro texture.",
)
# STYLE-V3.5(2026-07-26 아트디렉터 "웜 소품 다양화"): 고정(황동서버·레이스 / 황동포트·밀) 대신
#   빈티지 소품 레지스트리에서 시드로 2종 선택({vintageprops}). {plate}/{props} 와 동일 소프트코딩.
_WARM_VINTAGE_PROPS: tuple[str, ...] = (
    "a brass cake server",
    "a piece of antique lace linen",
    "a sprig of dried wheat",
    "an aged brass candlestick",
    "a small aged copper pot",
    "a bundle of dried lavender",
    "a vintage silver teaspoon",
    "a cloth-bound old recipe book",
    "a few dried orange slices",
    "an aged brass honey dipper",
)

def _vintage_props_clause(subject: str, seed: int) -> str:
    """warm 빈티지 씬 소품 2종 — 레지스트리에서 subject:seed 로테이션(서로 다른 2개)."""
    n = len(_WARM_VINTAGE_PROPS)
    i = int(hashlib.sha256(f"{subject}:{seed}:vintage".encode("utf-8")).hexdigest()[:8], 16) % n
    off = int(hashlib.sha256(f"{subject}:{seed}:vintage2".encode("utf-8")).hexdigest()[:8], 16) % (n - 1)
    j = (i + 1 + off) % n
    return f"{_WARM_VINTAGE_PROPS[i]} and {_WARM_VINTAGE_PROPS[j]}"

_WARM_FOOD_VARIANTS: tuple[str, ...] = (
    # ① vintage_patisserie — {plate} + {vintageprops}(로테이션)
    "Style the food on {plate}, on an aged warm-oak wood table, with {vintageprops} and a few {props} "
    "arranged nearby. Soft golden side light, nostalgic old-world patisserie mood in rich warm tones, "
    "every object clearly shaped and photorealistic.",
    # ② rustic_warm — {plate} + {vintageprops}(로테이션)
    "Style the food on {plate}, on a weathered warm-wood surface, with {vintageprops} and a few {props} "
    "beside it. Warm amber light with soft shadows, cozy vintage bakery feel, every object clearly "
    "shaped and photorealistic.",
)

# 스타일 → food 변형 로테이션 (pop 메커니즘 일반화). 완화 잠금(food_pop)은 6스타일 공용 —
#   내용이 팝 전용이 아니라 "본체 불변 + 접시 교체 + 실재 재료 가니시" 중립 계약.
_STYLE_FOOD_VARIANTS: dict[str, tuple[str, ...]] = {
    "pop": _POP_FOOD_VARIANTS,
    "monotone": _MONO_FOOD_VARIANTS,
    "pastel": _PASTEL_FOOD_VARIANTS,
    "editorial": _EDITORIAL_FOOD_VARIANTS,
    "realism": _REALISM_FOOD_VARIANTS,
    "warm_organic": _WARM_FOOD_VARIANTS,
}

# 면류 안전 변형 인덱스(실측 통과분만 — "펜네 무조건 보존" 아트디렉터 하드 요구, 07-24):
#   pop: ①scatter 제외 / monotone: ③brand 몰입 제외(4/4 재드로잉) / pastel: ①dreamy 전면
#   실크 제외(4/4). 케이크·디저트 등 비면류는 전 변형 로테이션 유지.
_NOODLE_SAFE_IDX: dict[str, tuple[int, ...]] = {
    "pop": (1, 2, 3),
    "monotone": (0, 1),
    "pastel": (1, 2),
}


# 재료명 → 구체 소품 문구 (POP-V2.1). analyze_menu/analyze_photo 의 core_ingredients(영문 ASCII
#   보장)를 시각적 소품 명사구로 변환 — "치즈"류는 노란 큐브, 과일류는 신선 통과일+동결건조 칩,
#   크림류는 파이핑 로제트 등 **그릴 수 있는 형태**를 함께 준다(아트디렉터 07-24: "구슬을 넣던가
#   파스타면 노란 치즈들을 넣던가" — 이름+형태가 있어야 덩어리가 안 나옴).
# 고기 소품 키(조리법 오버라이드 대상 — _props_clause 가 is 로 식별)
_MEAT_PROP_KEYS = ("beef", "pork", "chicken", "duck", "brisket", "meat")

_PROP_SHAPES = (
    (("cheese", "parmesan", "cheddar"), "small yellow {name} cubes"),
    (("strawberry", "berry", "blueberry", "raspberry", "cherry", "grape", "peach",
      "mango", "banana", "apple", "lemon", "orange", "fruit"),
     "glossy fresh whole {name} pieces and a few crisp freeze-dried {name} chips"),
    (("cream", "whipped"), "neatly piped {name} rosettes"),
    (("chocolate", "choco", "cocoa"), "small glossy {name} shards"),
    (("nut", "almond", "peanut", "walnut"), "whole {name}s"),
    (("bacon", "ham"), "crisp {name} curls"),
    # egg 는 소품 부적합(2026-07-24 아트디렉터): 크림소스에 녹는 재료를 반숙/후라이 형태로
    #   올리는 연출은 그 요리의 실제 서빙과 다름 — 소품 후보에서 제외.
    (("herb", "basil", "arugula", "rocket", "parsley", "mint"), "fresh {name} leaves"),
    # savory 한식·짠맛 가니시(2026-07-27 아트디렉터: 곱도리탕 등 savory가 디저트 표에 매칭 안 돼
    #   막연 폴백→Kontext 찰흙 덩어리. 그릴 수 있는 구체 형태의 savory 소품 추가).
    #   한식 메인 재료(고기·김치·곱창)를 상위 우선 — 탕/찌개류가 제대로 매칭되게.
    (("kimchi",), "a small mound of vivid red {name}"),
    # PROP-COOK: 이 키 튜플은 _props_clause 에서 조리법 오버라이드 대상으로 식별된다(is 비교).
    (_MEAT_PROP_KEYS,
     "a few glossy braised {name} pieces"),
    (("tripe", "gopchang", "intestine", "offal"), "a few glossy cooked {name} pieces"),
    (("scallion", "green onion", "spring onion", "leek", "chive"),
     "a few crisp fresh {name} sprigs"),
    (("chili", "gochu", "red pepper", "jalapeno", "cheongyang"),
     "a couple of glossy fresh {name}"),
    (("garlic",), "a few peeled ivory {name} cloves"),
    (("mushroom", "enoki", "shiitake", "oyster mushroom"),
     "a small fresh cluster of {name}"),
    (("tofu",), "a few clean white {name} cubes"),
    (("rice cake", "tteok", "tteokbokki", "garae", "gnocchi"),
     "a few glossy cylindrical {name} pieces"),
    (("sesame",), "a light scatter of toasted {name} seeds"),
    (("shrimp", "prawn", "clam", "mussel", "scallop", "seafood"),
     "a couple of fresh {name}"),
)


# 면류 어휘(NOODLE-GUARD) — subject_en 기준. analyze_menu 산출 변주("cream carbonara pasta",
#   "creamy carbonara pasta" 등)를 모두 잡도록 요리명까지 포함.
_NOODLE_HINTS = ("noodle", "pasta", "ramen", "udon", "soba", "spaghetti", "linguine",
                 "penne", "fettuccine", "carbonara", "naengmyeon", "japchae", "pho",
                 "lo mein", "chow mein")

# ※ 구 SOUP-GUARD 어휘(_SOUP_HINTS/_is_soup_subject)는 develop 의 SOUP-PRESERVE(_is_soup_dish,
#   국물 요리를 styled 경로에서 제외해 in-place 보존)와 중복이라 머지에서 제거했다. 같은 이름의
#   _SOUP_HINTS 가 아래에 다시 정의되어 조용히 덮어쓰는 상태였음 — 국물 판정은 SOUP-PRESERVE 단일 소유.

# 단맛 베이커리 어휘(BAKERY-SPLIT, 2026-07-27): serving_type=bakery 는 짠 빵(치아바타·샌드위치)과
#   단 빵(크루아상·단팥빵)이 섞여 있다. dessert 이상화("Idealize this dessert")를 짠 빵에 적용하면
#   Kontext가 빵+토마토를 케이크로 재구성(치아바타 pop 실측 사고) → 이상화는 sweet 힌트가 있는
#   bakery 에만. 미매칭 bakery 는 안전측(절제형 리터치) — 정직성 리스크 없음.
_SWEET_BAKERY_HINTS = ("croissant", "scone", "muffin", "pastry", "tart", "pie", "donut",
                       "doughnut", "cake", "macaron", "waffle", "pancake", "brioche",
                       "red bean", "cream bread", "cookie", "brownie", "castella", "roll")


def _is_dessert_like(serving_type: str | None, subject_en: str) -> bool:
    """dessert 이상화·디저트 락 적용 대상 판정 — dessert 전부 + sweet bakery 만."""
    if serving_type == "dessert":
        return True
    if serving_type == "bakery":
        low = (subject_en or "").lower()
        return any(h in low for h in _SWEET_BAKERY_HINTS)
    return False


# 조리법 어휘(PROP-COOK, 2026-07-27 아트디렉터 "구운 돼지갈비 위에 띄운 고기가 가짜 같다 —
#   생고기 말고 구운 고기로"): 고기 소품의 조리 상태를 요리의 조리법에 맞춘다. 구이류에 조림
#   고기(기본 shape)를 뿌리면 그 요리에 없는 상태라 이질감·가짜 느낌.
_GRILL_HINTS = ("grill", "roast", "bbq", "barbecue", "char", "smoked", "seared", "broiled",
                "galbi", "kalbi", "bulgogi", "samgyeopsal", "gui", "steak", "skewer", "kebab")
_FRY_HINTS = ("fried", "fry", "katsu", "tempura", "cutlet", "karaage", "nugget", "twigim")


def _meat_prop_shape(subject_en: str) -> str:
    """고기 소품 형태 — 요리의 조리법을 따라간다(구이=구운 고기, 튀김=튀긴 고기, 그 외=조림)."""
    low = (subject_en or "").lower()
    if any(h in low for h in _GRILL_HINTS):
        return "a few glossy grilled {name} pieces with light charred grill marks"
    if any(h in low for h in _FRY_HINTS):
        return "a few crisp golden fried {name} pieces"
    return "a few glossy braised {name} pieces"


def _props_clause(core_ingredients: list[str] | None, subject_en: str = "") -> str:
    """core_ingredients → 명명된 소품 문구 (최대 2종).

    순회는 재료 나열 순이 아니라 _PROP_SHAPES 표 순(소품 적합도 순 — 치즈·크림·과일이
    상위): 까르보나라(pasta, cream, bacon, parmesan)에서 "노란 파마산 큐브"가 뽑히게
    (아트디렉터 07-24 "파스타면 노란 치즈들"). 형태 매칭 없으면 첫 재료의 일반형,
    재료 자체가 없으면 일반 폴백(안전측).
    """
    names = [str(i).strip().lower() for i in (core_ingredients or []) if str(i).strip()]
    items: list[str] = []
    for keys, shape in _PROP_SHAPES:  # 표 순 = 적합도 순
        for name in names:
            if any(k in name for k in keys):
                # PROP-COOK: 고기 소품만 요리의 조리법으로 형태를 덮어쓴다(구이→구운 고기).
                if keys is _MEAT_PROP_KEYS:
                    shape = _meat_prop_shape(subject_en)
                items.append(shape.format(name=name))
                break
        if len(items) >= 2:
            break
    if not items and names:
        # (a) savory 미등록 재료: 구체 명사 + 반-찰흙 앵커(간결 — T5 예산). {props}가 문장 중간에
        #   박혀 literal omit은 문장을 깨므로, 최소·사실 소품으로 대체하고 찰흙/반죽을 부정한다.
        items.append(f"a few small glossy fresh {names[0]} pieces, never clay-like or dough-like")
    if not items:
        return "a few small glossy fresh garnish pieces, never clay-like or dough-like"
    return " and ".join(items)


def _plan(style_key: str, domain: str, archetype: str,
          reference_ids: tuple[str, ...], direction: str) -> ReferenceStylePlan:
    return ReferenceStylePlan(style_key, domain, archetype, reference_ids, direction)


_PLANS: dict[tuple[str, str], ReferenceStylePlan] = {
    ("food", "editorial"): _plan(
        "editorial", "food", "asymmetric_copyspace + food_hero",
        ("01_에디토리얼__IMG_4597", "03_리얼리즘__IMG_4604", "03_리얼리즘__IMG_4675"),
        # CONTAINER-001: {hero}는 용기 분류에 따라 "the plate"(기본) 또는 실제 용기 묘사로
        # 치환되는 자리표시자 — build_reference_instruction()이 채운다.
        "Create a premium culinary editorial environment with a muted cream stone table and a pale warm-gray "
        "background, soft directional window light and generous quiet copy space above {hero}. Restrained "
        "high-end restaurant campaign. No added cutlery, napkin, ingredients, garnish, hands or text.",
    ),
    ("food", "pop"): _plan(
        "pop", "food", "saturated_color_block + macro_texture",
        ("02_팝_pop__IMG_4606", "02_팝_pop__IMG_4608", "03_리얼리즘__IMG_4680"),
        # PALETTE-001(2026-07-20): {palette}는 상품명(subject_en) 기준 결정론적으로 선택되는
        # 자리표시자 — build_reference_instruction()이 채운다. _POP_PALETTES 참고.
        "Create a bold contemporary food campaign with {palette}, crisp hard side light and one strong graphic "
        "diagonal shadow behind {hero}. Keep the food's true appetizing colors. No extra food, props, hands, "
        "splashes, floating objects or text.",
    ),
    ("food", "realism"): _plan(
        "realism", "food", "macro_texture + food_hero",
        ("03_리얼리즘__IMG_4604", "03_리얼리즘__IMG_4675", "03_리얼리즘__IMG_4691"),
        # BUG-KTX-001-2(2026-07-20): 이 스타일만 컵 변환이 재발했다. 다른 스타일과 달리 접시가
        #   "테이블 위에 평평히 놓임"을 명시하지 않고 흐린 배경만 지시해, 근접 제품샷(컵) 구도로
        #   미끄러지기 쉬웠던 것으로 추정 — 접시·테이블 접지를 명시적으로 보강.
        # CONTAINER-001: {container_clause}는 기본 "the plate resting flat", 장식 용기(vessel)면
        #   "the <용기> standing upright on its own base" — 굽 용기에 물리적으로 참인 접지만 지시.
        "Create a true-to-life premium restaurant photograph with {container_clause} on a dark charcoal stone "
        "table and a softly blurred neutral dining background behind it. Use realistic directional light that "
        "reveals the exact natural food texture without exaggeration. No smoke, fire, utensils, ingredients, "
        "garnish, hands or text.",
    ),
    ("food", "pastel"): _plan(
        "pastel", "food", "pastel_tabletop + food_hero",
        ("04_파스텔__IMG_4674", "04_파스텔__IMG_4710", "04_파스텔__IMG_4712"),
        "Create a refined pastel culinary set with {palette}, high-key diffused light and a very soft contact "
        "shadow. Keep all food colors fully natural, never pastel-tinted. No geometric props, flowers, extra "
        "food, hands or text.",
    ),
    ("food", "monotone"): _plan(
        "monotone", "food", "dark_color_lock + food_hero",
        ("05_모노톤__IMG_4704", "05_모노톤__IMG_4705", "03_리얼리즘__IMG_4604"),
        "Create {palette} in the background and table. Add a precise warm rim light and one bold diagonal "
        "shadow. Keep all food colors true and isolated from the monochrome surroundings. No props, extra food, "
        "hands or text.",
    ),
    ("food", "warm_organic"): _plan(
        "warm_organic", "food", "warm_tabletop + organic_material",
        ("06_웜빈티지__IMG_4667", "06_웜빈티지__IMG_4678", "03_리얼리즘__IMG_4683"),
        "Create a warm organic dining environment on a pale travertine table against a softly textured beige wall. "
        "Use gentle golden side light, tactile natural materials and an intimate premium restaurant mood. No wood "
        "grain, linen, dried plants, extra food, utensils, hands or text.",
    ),
    ("drink", "editorial"): _plan(
        "editorial", "drink", "asymmetric_copyspace + drink_hero",
        ("01_에디토리얼__IMG_4598", "01_에디토리얼__IMG_4631", "01_에디토리얼__IMG_4703"),
        "Create an airy premium cafe editorial environment with a pale cream stone table, a very light cool-gray "
        "background, soft window light and generous copy space in the upper-left. Minimal high-end magazine look. "
        "No spoon, napkin, beans, pastries, flowers, hands or text.",
    ),
    ("drink", "pop"): _plan(
        "pop", "drink", "saturated_color_block + drink_hero",
        ("02_팝_pop__IMG_4697", "02_팝_pop__IMG_4698", "02_팝_pop__IMG_4699"),
        "Create a bold contemporary beverage campaign with {palette}, crisp hard side light and one graphic "
        "shadow. No fruit, packets, beans, ice, splash, straw, hands, food or text.",
    ),
    ("drink", "realism"): _plan(
        "realism", "drink", "natural_cafe + drink_hero",
        ("03_리얼리즘__IMG_4602", "03_리얼리즘__IMG_4657", "03_리얼리즘__IMG_4683"),
        "Create a true-to-life modern cafe photograph on a clean warm-gray stone tabletop beside a softly sunlit "
        "neutral wall. Use realistic morning window light, accurate container material and natural drink texture, "
        "with restrained depth of field. No props, food, beans, hands, added steam or text.",
    ),
    ("drink", "pastel"): _plan(
        "pastel", "drink", "pastel_tabletop + drink_hero",
        ("04_파스텔__IMG_4674", "04_파스텔__IMG_4710", "04_파스텔__IMG_4712"),
        "Create a soft pastel cafe set with {palette}, ethereal high-key diffused light and soft contact "
        "shadows. Keep the drink and container grounded and true to their original colors. No shapes, flowers, "
        "props, food, hands or text.",
    ),
    ("drink", "monotone"): _plan(
        "monotone", "drink", "brand_color_lock + drink_hero",
        ("05_모노톤__IMG_4705", "05_모노톤__IMG_4713"),
        "Create {palette} in the background and table. Add clean even lighting and one bold diagonal shadow. "
        "Preserve the drink and container's real colors exactly. No props, beans, food, hands or text.",
    ),
    ("drink", "warm_organic"): _plan(
        "warm_organic", "drink", "warm_tabletop + organic_material",
        ("06_웜빈티지__IMG_4667", "06_웜빈티지__IMG_4678", "06_웜빈티지__IMG_4620"),
        "Create a warm organic cafe environment on a pale travertine table against a softly textured beige wall. "
        "Use gentle golden side light, tactile natural materials and a quiet premium morning atmosphere. No wood "
        "grain, linen, dried plants, spoon, beans, pastries, hands or text.",
    ),
    ("object", "editorial"): _plan(
        "editorial", "object", "asymmetric_copyspace + minimal_studio",
        ("01_에디토리얼__IMG_4632", "01_에디토리얼__IMG_4703", "IMG_4792"),
        "Create a restrained high-end product editorial environment with a cool off-white studio sweep, one thin "
        "translucent acrylic plane in the distant background, soft directional daylight and generous clean copy "
        "space in the upper-left. No accessories, hands, cables or text outside the unchanged product label.",
    ),
    ("object", "pop"): _plan(
        "pop", "object", "saturated_color_block + commercial_hero",
        ("02_팝_pop__IMG_4609", "02_팝_pop__IMG_4621", "IMG_4790"),
        "Create an energetic graphic product campaign with {palette}. Add two large matte geometric blocks far "
        "behind the product and crisp hard directional shadows. No food, spheres, hands, extra products or text "
        "outside the unchanged product label.",
    ),
    ("object", "realism"): _plan(
        "realism", "object", "natural_material + commercial_hero",
        ("03_리얼리즘__IMG_4637", "IMG_4809", "IMG_4813"),
        "Create a true-to-life natural product photograph on a light gray limestone surface beside a softly sunlit "
        "neutral wall. Use realistic morning window light, accurate material texture, subtle contact shadows and "
        "restrained depth of field. No extra products, flowers, hands or text outside the unchanged product label.",
    ),
    ("object", "pastel"): _plan(
        "pastel", "object", "soft_pedestal + pastel_product_hero",
        ("04_파스텔__IMG_4674", "04_파스텔__IMG_4710", "IMG_4808"),
        "Create a soft pastel product set with {palette}. Use ethereal high-key diffused light and soft contact "
        "shadows. Keep the product grounded. No mist, ribbons, flowers or text outside the unchanged product "
        "label.",
    ),
    ("object", "monotone"): _plan(
        "monotone", "object", "brand_color_lock + minimal_studio",
        ("05_모노톤__IMG_4688", "05_모노톤__IMG_4713", "IMG_4793"),
        "Create a strict tone-on-tone campaign using one restrained color family only in a seamless geometric "
        "studio background, with a shallow platform, clean even lighting and one bold diagonal shadow. Preserve the "
        "product's own colors and material. No text outside the unchanged product label.",
    ),
    ("object", "warm_organic"): _plan(
        "warm_organic", "object", "neutral_stilllife + organic_material",
        ("06_웜빈티지__IMG_4618", "06_웜빈티지__IMG_4626", "IMG_4809"),
        "Create a warm organic editorial still life on a pale travertine surface with a softly textured beige wall. "
        "Add one small sculptural stone in the distant background and a subtle window shadow. Use gentle golden side "
        "light. No wood grain, plants, wrapping, flowers or text outside the unchanged product label.",
    ),
}


def _validate_drink_recipe_alignment() -> None:
    """프로덕션 StylePlan이 승인 대기 recipe와 다른 레퍼런스로 회귀하지 않게 한다."""
    from .reference_recipe import canonical_reference_id
    from .reference_recipe_data import REFERENCE_RECIPES

    for (domain, style), plan in _PLANS.items():
        if domain != "drink":
            continue
        recipe = REFERENCE_RECIPES.get(f"drink/{plan.archetype.split(' + ')[0]}/{style}")
        if recipe is None:
            # 기존 plan의 표시용 archetype과 recipe key가 다른 경우 mood로 유일하게 대조한다.
            matches = [item for item in REFERENCE_RECIPES.values()
                       if item.domain == "drink" and item.mood.key == style]
            if len(matches) != 1:
                raise ValueError(f"drink recipe 누락/중복: {style}")
            recipe = matches[0]
        plan_ids = tuple(canonical_reference_id(value) for value in plan.reference_ids)
        if plan_ids != recipe.canonical_reference_ids:
            raise ValueError(
                f"drink StylePlan/reference recipe 근거 불일치: {style} "
                f"{plan_ids!r} != {recipe.canonical_reference_ids!r}")


_validate_drink_recipe_alignment()


def normalize_style(style_key: str) -> str | None:
    """프로덕션 스타일 별칭을 실험 무드 키로 정규화한다."""
    return _STYLE_ALIASES.get((style_key or "").strip().lower())


def normalize_domain(domain: str | None) -> str:
    """분석 결과의 도메인을 StylePlan의 food/drink/object 세 축으로 정규화한다."""
    value = (domain or "food").strip().lower()
    if value in {"drink", "cafe", "beverage"}:
        return "drink"
    if value in {"object", "product", "beauty", "fashion", "general_object"}:
        return "object"
    return "food"


def get_reference_plan(style_key: str, domain: str | None) -> ReferenceStylePlan | None:
    """지원하는 6무드면 도메인별 계획을 반환하고, 특수 포맷이면 None을 반환한다."""
    style = normalize_style(style_key)
    if style is None:
        return None
    return _PLANS[(normalize_domain(domain), style)]


# 디저트 판정(2026-07-21): food 도메인 안에서 케이크·타르트류를 골라 접시 재플레이팅 잠금을
#   적용한다. subject_en(analyze_menu 영문)만으로 판정 → build_reference_instruction 단일 지점
#   결정(별도 배선 불필요). vessel(유리 디저트 용기) 분류가 우선이므로 빙수·파르페는 해당 없음.
_DESSERT_HINTS = (
    "cake", "cheesecake", "cupcake", "shortcake", "gateau", "tart", "tarte", "pie",
    "macaron", "macaroon", "pastry", "croissant", "cookie", "brownie", "waffle",
    "pancake", "muffin", "scone", "pudding", "mousse", "tiramisu", "eclair", "donut",
    "doughnut", "parfait", "dessert", "roll cake",
)


def _is_dessert_subject(subject_en: str) -> bool:
    """subject_en(영문 상품 설명)이 케이크·베이커리 디저트인지. 접시 재플레이팅 대상 판정용.

    ⚠️ 레거시 폴백 전용(SRV-ROUTE-001): substring이라 "rice cake soup"(떡국)도 True가 되는
    구조적 오탐이 있다 — serving_type(LLM 의미 판정)이 있으면 그쪽이 정본, 이 함수는
    serving_type=None(구캐시·킬스위치)일 때만 기존 동작 그대로 쓴다.
    """
    low = (subject_en or "").lower()
    return any(hint in low for hint in _DESSERT_HINTS)


# SRV-ROUTE-001 §4-4: 재플레이팅 부적합 가드 — food_dessert 락 문구("단일 디저트가 접시 위에
#   평평히 누움" + 접시 교체)의 전제가 거짓이 되는 제시 형태를 이름 근거로 걸러, 안전측
#   (락 미적용=기존 문구)으로 보낸다. serving_type 분기 안에서만 사용 — 레거시 substring
#   경로는 바이트 동일 유지(회귀 가드).
_REPLATE_UNSAFE_SET = ("set", "box", "gift", "assort", "bundle")    # 세트·박스·다중개체
_REPLATE_UNSAFE_VESSEL = ("bingsu", "parfait", "affogato", "sundae", "float")  # 유리용기 디저트
_REPLATE_UNSAFE_WHOLE = ("whole", "tier")                           # 홀케이크(기립형 다단)


def _replate_unsafe(subject_en: str, container_desc: str | None) -> bool:
    """디저트 접시 재플레이팅이 시각적으로 부조리해지는 케이스 판정(SRV-ROUTE-001 적대검증 방어).

    - 세트·박스: 박스 정렬 상품에 '접시 교체' 지시 = 포장(상품 정체성) 파괴 — 온라인셀러 세트 보호
    - 유리용기 디저트인데 Vision 용기 정보 없음: vessel 분류가 못 가로챈 케이스를 안전측으로
    - 홀케이크: 락의 '평평히 누운 조각' 전제가 기립형 다단 구조와 모순 → 형태 왜곡 위험
    """
    low = (subject_en or "").lower()
    if any(w in low for w in _REPLATE_UNSAFE_SET + _REPLATE_UNSAFE_WHOLE):
        return True
    return container_desc is None and any(w in low for w in _REPLATE_UNSAFE_VESSEL)


# SOUP-PRESERVE 탐지 — subject_en(analyze_menu 영문. 국·탕·찌개→"...soup"/"broth" 안정 산출:
#   golden fixture "육개장"→"korean spicy beef soup") 우선 + 용기(뚝배기/스톤팟) 보조. category=
#   "soup" 는 build 로 전달 안 되고 threading 에 style_gen(병행세션 편집중) 수정이 필요해, 이
#   파일 안에서 subject_en/container 만으로 자족 판정한다.
_SOUP_HINTS = (
    "soup", "broth", "stew", "chowder", "bisque", "ramen", "ramyeon", "pho", "jjigae",
    "jjamppong", "champon", "gukbap", "sundubu", "kalguksu", "sujebi", "gomtang",
    "seolleongtang", "samgyetang", "noodle soup",
)


# NOODLE-PRESERVE(2026-07-27 아트디렉터 "크림 펜네 파스타 모노톤은 정체성이 아예 바껴서 큰일"):
#   라이브 실측 — 펜네가 스파게티 둥지 + 갈색 타워로 재구성됐다. 기존 방어(면 안전 변형 서브셋
#   _NOODLE_SAFE_IDX + "never convert penne into spaghetti" 부정문)를 **둘 다 통과하고도** 붕괴.
#   부정문이 Kontext에서 약하다는 패턴이 반복 확증(초코 드리즐·치아바타 케이크화·휠 발명)이라,
#   국물(SOUP-PRESERVE)과 동일하게 **면 요리는 styled 재연출 경로 자체에서 제외**하고 in-place
#   보존으로 라우팅한다. 면은 형태(관·가닥·굵기)가 정체성이라 재드로잉 허용 폭이 0에 가깝다.
_FOOD_NOODLE_LOCK = (
    "This is a real photograph of a noodle or pasta dish. "
    "Edit this exact photograph and keep the noodles exactly as they are: the same noodle shape, "
    "cut and thickness — short tubes stay short tubes, long strands stay long strands — the same "
    "count, the same tangle and arrangement on the same dish, never restacked, re-piled, molded "
    "into a tower or ring, or rearranged. "
    "Keep every topping, sauce, meat, vegetable and garnish exactly as photographed, and add "
    "nothing that is not already there. "
    "Retouch it like a professional food ad: brighten exposure, remove haze, sauce glossy and "
    "creamy, noodles and toppings fresh, never dry, matte or claylike. Enhance only what is there, "
    "same hues, never restyling. "
    "It stays served in the same kind of dish, resting flat on the table under gravity with a "
    "single realistic contact shadow. "
    "Change only the background, table surface, camera framing and environmental lighting to match "
    "the requested scene. "
)


def _is_noodle_dish(subject_en: str) -> bool:
    """면·파스타 요리 판정 → in-place 보존 라우팅(국물 면은 SOUP-PRESERVE 가 선행 처리)."""
    return any(h in (subject_en or "").lower() for h in _NOODLE_HINTS)


def _is_soup_dish(subject_en: str, container_desc: str | None = None) -> bool:
    """국물 요리(국·탕·찌개·면국물) 판정 → in-place 보존 라우팅.

    subject_en(analyze_menu 영문, 국·탕·찌개→"...soup"/"broth" 안정 산출)만으로 판정한다.
    용기(뚝배기/스톤볼) 기반 감지는 돌솥밥·돌솥비빔밥(국물 아님)을 오탐해 제외 — 국물 여부는
    요리명이 정본. container_desc 인자는 시그니처 호환용(현재 미사용).
    """
    low = (subject_en or "").lower()
    return any(h in low for h in _SOUP_HINTS)


# SAVORY 텍스처의 marbling 어휘는 고기/해산물이 실제 있을 때만(없는 고기 소환 방지, 워크플로 지적).
_MEAT_HINTS = (
    "meat", "beef", "pork", "chicken", "ham", "bacon", "sausage", "steak", "brisket",
    "rib", "lamb", "duck", "turkey", "cutlet", "cured", "deli", "pepperoni", "salami",
    "prosciutto", "chorizo", "meatball", "patty", "bulgogi", "galbi", "jerky", "katsu",
    "fish", "salmon", "tuna", "shrimp", "prawn", "squid", "crab", "seafood",
)


def _has_meat(subject_en: str, core_ingredients: list[str] | None) -> bool:
    """고기·해산물 신호(SAVORY marbling 절 적용 여부)."""
    blob = " ".join([(subject_en or "").lower()]
                    + [str(i).lower() for i in (core_ingredients or [])])
    return any(h in blob for h in _MEAT_HINTS)


def build_reference_instruction(style_key: str, domain: str | None, subject_en: str,
                                container_desc: str | None = None,
                                container_opacity: str | None = None,
                                finish_profile: str | None = None,
                                palette_override: str | None = None,
                                scene_tone: str | None = None,
                                scene_seed: int = 0,
                                serving_type: str | None = None,
                                core_ingredients: list[str] | None = None) -> str | None:
    """StylePlan을 Kontext용 정체성 보존 편집 지시로 변환한다.

    container_desc·container_opacity(analyze_photo Vision 산출)가 유리 디저트 용기(vessel)로
    분류되면 food 프리앰블과 플랜의 용기 문구를 "원본 용기 유지+프리미엄 연출" 긍정 단언으로
    치환한다(CONTAINER-001). 미지정·접시류·분류 실패는 전부 기존 문구와 바이트 동일 —
    컵 변환(BUG-KTX-001)·프로핑(PLATING-001) 회귀 가드.

    serving_type(SRV-ROUTE-001 §4-4, 이 브랜치에서 소비 활성): 디저트 락 판정의 정본 —
    serving_type in ('dessert','bakery') and not _replate_unsafe(...) 이면 food_dessert 락.
    None이면 레거시 substring(_is_dessert_subject) — 바이트 동일. vessel 체크 선행 순서 불변.
    """
    plan = get_reference_plan(style_key, domain)
    if plan is None:
        return None
    subject = (subject_en or "product").strip()
    identity_lock = _IDENTITY_LOCKS[plan.domain]
    is_vessel = (plan.domain == "food"
                 and classify_container(container_desc, container_opacity) == "vessel")
    # SOUP-PRESERVE(전 무드): 국물 요리는 vessel 과 동일하게 in-place 보존(styled 스킵) — 국물·용기
    #   유지, 재플레이팅 금지. is_vessel(유리 디저트) 아닐 때만.
    is_soup = (plan.domain == "food" and not is_vessel
               and _is_soup_dish(subject, container_desc))
    # NOODLE-PRESERVE: 국물 면(라멘·쌀국수)은 위 soup 이 이미 잡으므로 마른 면만 여기로.
    is_noodle_dish = (plan.domain == "food" and not is_vessel and not is_soup
                      and _is_noodle_dish(subject))
    if is_vessel:
        container = container_desc.strip().lower()  # analyze_photo 계약상 ASCII 보장
        identity_lock = _prompts.fmt(_NS, "container.identity_lock_vessel",
                                     container=container).strip() + " "
        hero = f"the {container}"
        container_clause = _prompts.fmt(_NS, "container.realism_clause_vessel",
                                        container=container)
    elif is_soup:
        identity_lock = _FOOD_SOUP_LOCK
        hero = "the bowl of soup"
        container_clause = "the deep bowl resting flat on the table"
    elif is_noodle_dish:
        # NOODLE-PRESERVE(전 무드): 면 요리도 국물과 동일하게 in-place 보존 — 면 형태가 정체성.
        identity_lock = _FOOD_NOODLE_LOCK
        hero = "the dish of noodles"
        container_clause = "the dish resting flat on the table"
    else:
        # 디저트(케이크류)는 접시를 상품이 아닌 연출요소로 보고 예쁜 접시로 재플레이팅한다.
        #   vessel(유리 디저트 용기)이 아닐 때만 — 굽 유리볼 빙수 등은 위에서 이미 보존 처리.
        # SRV-ROUTE-001 §4-4 게이트: serving_type(LLM 의미 판정)이 있으면 그것이 정본 —
        #   substring 오탐("rice cake soup"→디저트 락, "bread" 베이커리 누락) 차단 +
        #   재플레이팅 부적합(_replate_unsafe: 세트/박스·무Vision 유리용기·홀케이크) 가드.
        #   None(구캐시·SERVING_TYPE_ROUTING=0)이면 레거시 substring — 바이트 동일.
        # BAKERY-SPLIT(2026-07-27): bakery 는 sweet 힌트가 있을 때만 디저트 취급 —
        #   짠 빵(치아바타+토마토)이 디저트 락으로 케이크화되는 사고 차단.
        if serving_type is not None:
            dessert = (_is_dessert_like(serving_type, subject)
                       and not _replate_unsafe(subject, container_desc))
        else:
            dessert = _is_dessert_subject(subject)
        if plan.domain == "food" and dessert:
            # DESSERT-AB: 재플레이팅(238c288) before/after 인세션 토글. 기본 on=현행(바이트 동일),
            #   DESSERT_REPLATE=0 이면 구 동작(접시 보존=freeze plate)으로 폴백 → A/B 대조군.
            if os.environ.get("DESSERT_REPLATE", "1") != "0":
                identity_lock = _IDENTITY_LOCKS["food_dessert"]
        hero = _prompts.get(_NS, "container.hero_default")
        container_clause = _prompts.get(_NS, "container.realism_clause_default")
    direction = plan.direction
    # POP-V2(2026-07-23): food×pop 은 4아키타입 로테이션 + 완화 잠금(food_pop) — vessel(유리
    #   디저트 용기)은 용기 보존이 우선이라 제외(기존 pop direction 유지). 로테이션은
    #   subject+scene_seed 결정론(palette_gen 레시피 로테이션과 동일 패턴) — 같은 가게도
    #   재생성마다 다른 연출, 같은 시드는 재현 가능.
    # 락 우선순위(머지 정합 2026-07-24): styled 로테이션(pop·monotone·pastel)이면 food_pop
    #   공용 완화 잠금이 디저트 락을 덮는다(의도 — 접시 교체·가니시 허용 포함). 디저트
    #   재플레이팅 락은 비-로테이션 스타일(에디토리얼·리얼리즘 등) 전용.
    # STYLE-V3(2026-07-26): editorial/realism/warm 도 styled 로테이션 편입 → 재플레이팅 안전
    #   가드(_replate_unsafe: 기프트세트/박스·홀케이크·무Vision 유리용기)를 styled 경로에도
    #   적용. 부적합 디저트는 로테이션·접시교체 대신 플레인 food 락(씬 고정)으로 폴백.
    # REALISM-FIDELITY(리얼리즘만): 리얼리즘 음식(비-vessel·비-soup·비-dessert)은 원본 충실 보존
    #   경로 — food_pop 재플레이팅/소품 스캐터 대신 보존 락 + 짭짤 텍스처(아래에서 적용).
    _dessert_flag = ((serving_type in ("dessert", "bakery")) if serving_type is not None
                     else _is_dessert_subject(subject))
    is_realism_food = (plan.domain == "food" and plan.style_key == "realism"
                       and not is_vessel and not is_soup and not is_noodle_dish
                       and not _dessert_flag
                       and not _replate_unsafe(subject, container_desc))
    styled_v2 = (plan.domain == "food" and plan.style_key in _STYLE_FOOD_VARIANTS
                 and not is_vessel and not is_soup and not is_noodle_dish
                 and not is_realism_food
                 and not _replate_unsafe(subject, container_desc))
    # ※ 구 SOUP-GUARD 의 is_soup 재계산 라인은 제거(머지 정합) — develop 의 SOUP-PRESERVE 가
    #   위에서 이미 container_desc 까지 반영해 판정한 값을 덮어쓰고 있었다.
    if styled_v2:
        variants = _STYLE_FOOD_VARIANTS[plan.style_key]
        is_noodle = any(h in subject.lower() for h in _NOODLE_HINTS)
        # NOODLE-GUARD 변형 서브셋(2026-07-24 실측 확정): 전면 재구성 강도가 높은 변형은 면을
        #   재드로잉한다(pop① scatter, mono③ brand 몰입 4/4, pastel① dreamy 전면 실크 4/4 —
        #   프롬프트 보강으로도 못 막음). 면류는 각 스타일에서 실측 통과 변형만 로테이션:
        #   pop {②③④} · monotone {dark, gold} · pastel {pedestal, hero}. 비면류는 전 변형.
        if is_noodle:
            safe = _NOODLE_SAFE_IDX.get(plan.style_key)
            if safe:
                variants = tuple(variants[i] for i in safe)
        # SOUP-GUARD 변형 필터(2026-07-27): 국물요리는 기립 연출 변형(footed dessert stand,
        #   pop③)이 국물을 몰드 탑으로 재조형 → 스탠드 변형 제외(전멸 시 원본 유지).
        #   ⚠️ noodle 서브셋(원본 인덱스) **뒤에** 적용 — 순서 바꾸면 IndexError.
        if is_soup:
            no_stand = tuple(v for v in variants if "dessert stand" not in v)
            if no_stand:
                variants = no_stand
        idx = int(hashlib.sha256(f"{subject}:{scene_seed}".encode("utf-8"))
                  .hexdigest()[:8], 16) % len(variants)
        direction = variants[idx]
        # 3스타일 공용 완화 잠금(중립 계약). RETOUCH-003: 디저트는 절제형 리터치 절을
        #   tpl_47급 이상화로 맞교환(같은 제품 인식 + 무발명 경계) — append가 아닌 교체
        #   (T5 512토큰 예산: 초과 시 뒤쪽 씬 지시가 잘려 팔레트·소품 소실, GPU 실측 3/3).
        #   짭짤한 음식·serving_type 미상(구캐시)은 절제형 유지(재드로잉 리스크).
        # BAKERY-SPLIT(2026-07-27): 이상화는 dessert + sweet bakery 만 — 짠 빵(치아바타)이
        #   "Idealize this dessert"로 케이크 재구성되는 사고(pop 실측) 차단.
        if _is_dessert_like(serving_type, subject):
            identity_lock = _FOOD_POP_HEAD + _DESSERT_IDEALIZE + _FOOD_POP_TAIL
        elif serving_type in ("dish", "bakery"):
            # FOOD-FIDELITY(2026-07-27 아트디렉터 "음식은 리얼리즘 기준 — 김밥 속재료가
            #   무드마다 달라짐"): savory 본체 충실 — 속재료·단면 원본 고정 + 없던 소스/드리즐
            #   금지(버터감자 초코 사고) + 타 요리/디저트 전환 금지. 리터치 절의 디저트 질감
            #   어휘와 맞교환(T5 예산). 연출(케이크스탠드)은 유지 — 판정 "괜찮아, 예뻐".
            identity_lock = (_FOOD_POP_HEAD + _RETOUCH_SAVORY + _FOOD_POP_TAIL
                             + _FOOD_FIDELITY)
        else:
            identity_lock = _IDENTITY_LOCKS["food_pop"]
        # NOODLE-GUARD 레이어2: 면 전용 보강절(긍정 단언). ⚠️ 'egg' 같은 명사는 부정문에
        #   넣어도 조건화로 소환됨(brand 실측 — 정중앙 계란 후라이) → 위험 명사 자체를 쓰지
        #   않는다(BUG-KTX-001 계열 교훈 재확인).
        if is_noodle:
            identity_lock += (
                "The noodles keep their exact pasta type, thickness and arrangement — never convert "
                "penne into spaghetti or redraw them; add no topping not visible in the original. "
            )
    # REALISM-FIDELITY 락 적용 + 짭짤 텍스처 스왑. 고기 있으면 marbling 어휘(_RETOUCH_TEX_SAVORY),
    #   없으면 고기 소환 방지 변주(_RETOUCH_TEX_SAVORY_PLAIN)로 등길이 맞교환.
    # ※ 머지 정합(2026-07-27): 구 SOUP-GUARD 레이어2(styled 안에서 국물 보울 단언·dessert plate
    #   치환)는 develop 의 SOUP-PRESERVE 가 국물 요리를 styled 경로에서 통째로 제외(in-place 보존)
    #   하면서 도달 불가 코드가 되어 제거했다. 국물 보존 계약은 SOUP-PRESERVE 가 단일 소유.
    if is_realism_food:
        identity_lock = _IDENTITY_LOCKS["food_realism"]
        _savory = (_RETOUCH_TEX_SAVORY if _has_meat(subject, core_ingredients)
                   else _RETOUCH_TEX_SAVORY_PLAIN)
        identity_lock = identity_lock.replace(_RETOUCH_TEX_SWEET, _savory, 1)
    # SOUP/REALISM: 씬 방향의 "No ... ingredients, garnish" 부정문이 보존 락의 "원본 곁들임 유지"와
    #   충돌해 원본 반찬을 지울 수 있어, 리얼리즘 방향에서 garnish 금지만 제거(추가 방지는 락이 담당).
    if is_soup or is_realism_food or is_noodle_dish:
        direction = direction.replace("utensils, ingredients, garnish, hands", "utensils, hands")
    # RETOUCH-004: 초코 디저트는 이상화의 generic 질감 절(스펀지 pores·일반 크림)이 약해
    #   크럼블리하게 남는다(2차 시안 관찰) — 초코 전용 어휘(fudgy·ganache 수사)로 등길이
    #   맞교환. 이상화 절이 실제로 들어간 잠금(food_dessert·styled 디저트)에만 작동하고,
    #   비초코·비디저트는 replace 미매치로 바이트 동일.
    if "Idealize this dessert" in identity_lock:
        blob = " ".join([subject.lower()] + [str(i).lower() for i in (core_ingredients or [])])
        if "choco" in blob:
            identity_lock = identity_lock.replace(_IDEALIZE_TEX_GENERIC, _IDEALIZE_TEX_CHOCO, 1)
    # DIV-2: scene_tone 미지정(기본)이면 무변경 → 바이트 동일. 지정 시에만 표면/배경 스팬을
    #   입력 사진 톤에 맞춰 교체(다양성의 원천 = 유저 사진). 자리표시자 치환보다 먼저 수행.
    #   styled 로테이션 변형에는 대응 스팬이 없으므로 비-로테이션 방향에만 적용.
    if scene_tone is not None and not styled_v2:
        direction = _apply_scene_tone(plan.domain, plan.style_key, direction,
                                      scene_tone, subject, scene_seed)
    # 자리표시자는 한 번에 치환 — {palette}+{hero} 동시 보유 플랜(food pop)에서 str.format이
    # 누락 키로 KeyError를 내지 않게 한다.
    fmt_args: dict[str, str] = {}
    if "{palette}" in direction:
        # PAL-001: palette_override(제품 적응형 생성기 산출)가 오면 그것으로, 아니면 기존 고정
        #   팔레트 조회로 폴백(바이트 동일 — palette_override 미전달 시 회귀 없음).
        fmt_args["palette"] = (palette_override
                               or _style_palette_clause(plan.style_key, plan.domain, subject))
    if "{props}" in direction:
        # POP-V2.1: 소품은 core_ingredients 기반 구체명 — 추상 지시는 덩어리 렌더(라이브 실측)
        fmt_args["props"] = _props_clause(core_ingredients, subject)
    if "{plate}" in direction:
        # STYLE-V3.1: 접시는 레지스트리에서 시드로 모양 선택(하드코딩 반대) + 스타일 마감.
        # SOUP-GUARD: 국물요리는 접시 레지스트리 대신 깊은 보울 고정(국물 유지).
        if is_soup:
            fmt_args["plate"] = ("a deep glazed ceramic bowl that keeps its liquid broth "
                                 "clearly visible")
        else:
            fmt_args["plate"] = _plate_clause(plan.style_key, subject, scene_seed)
    if "{vintageprops}" in direction:
        # STYLE-V3.5: warm 빈티지 소품 레지스트리에서 시드로 2종 로테이션(다양화)
        fmt_args["vintageprops"] = _vintage_props_clause(subject, scene_seed)
    if "{metalprops}" in direction:
        # STYLE-V3.7: realism 메탈 소품 레지스트리에서 시드로 2종 로테이션(다양화)
        fmt_args["metalprops"] = _metal_props_clause(subject, scene_seed)
    if "{hero}" in direction:
        fmt_args["hero"] = hero
    if "{container_clause}" in direction:
        fmt_args["container_clause"] = container_clause
    if fmt_args:
        direction = direction.format(**fmt_args)
    # REAL-001: finish_profile 미지정 시 plan 기본값("none") → 절 무주입 → 바이트 동일.
    finish = _finish_clause(finish_profile if finish_profile is not None else plan.finish_profile)
    return (
        f"The photographed subject is {subject}. "
        f"{identity_lock}{direction} {finish}"
        "Do not generate any new logo, label, lettering, watermark or advertising copy."
    )


def build_clip_anchor(style_key: str, domain: str | None, subject_en: str,
                      staging: str = "preserve") -> str | None:
    """CLIP 77토큰용 짧은 스타일 앵커. 전체 편집 명령은 T5 prompt_2가 담당한다.

    staging="recompose"(P5 음료 재연출): "original drink unchanged" 류 보존 문구가 재연출
    지시(앵글·구도 자유)와 CLIP 층위에서 충돌하므로 제거하고 짧은 광고 앵커만 쓴다(개정 #5).
    """
    plan = get_reference_plan(style_key, domain)
    if plan is None:
        return None
    subject = (subject_en or "product").strip()
    if staging == "recompose":
        return f"{subject} beverage advertisement, {_CLIP_STYLE_ANCHORS[plan.style_key]}, no text"
    return f"{subject}, {_CLIP_STYLE_ANCHORS[plan.style_key]}, original {plan.domain} unchanged, no text"


# 온도별 물리 효과(P5) — 그 음료에 물리적으로 참인 효과만(정직성). 이름 추정 금지, Vision이 원천.
_RECOMPOSE_EFFECTS = {
    "iced": "fresh condensation droplets on the outside of the container",
    "hot": "gentle natural steam rising from the drink",
}

# 무드별 연출 분화(PU-001 3단계) — 배경색만 다르고 앵글·크기·구도가 6무드 동일하던 문제 해결.
#   음료 재연출은 이미 앵글·스케일·배치 자유(정직성 경계는 음료·용기 종류/색/토핑 보존이 담당)라
#   여기서 "화면 내 스케일·카메라 앵글·구도"만 무드별로 규정한다. 팀장 §7 연출 프리셋 기반.
_RECOMPOSE_STAGING = {
    "editorial": ("Shoot at eye level and place the drink smaller and off to one side, leaving "
                  "generous negative space for an asymmetric high-end magazine layout."),
    "pop": ("Shoot from a bold low angle and make the drink large and dominant in frame, with a "
            "tilted dynamic diagonal composition and strong energetic movement."),
    "realism": ("Shoot at natural eye level with the drink medium-large and grounded, centered like "
                "a candid modern cafe photograph with shallow depth of field."),
    "pastel": ("Shoot from a slightly high angle with a soft, airy, balanced composition at medium "
               "size and gentle breathing space around the drink."),
    "monotone": ("Shoot from a dramatic low side angle with a strong single graphic diagonal shadow, "
                 "bold minimal composition, medium-large scale."),
    "warm_organic": ("Shoot at a relaxed three-quarter angle at medium size for a warm, inviting, "
                     "lived-in morning composition."),
}

_ANGLE_INSTRUCTIONS = {
    "eye": "eye level",
    "slightly_high": "a slightly elevated angle",
    "high": "a high angle",
    "low": "a low angle",
    "three_quarter": "a relaxed three-quarter angle",
    "top_down": "a top-down angle",
}
_PLACEMENT_INSTRUCTIONS = {
    "center": "centered",
    "left_third": "on the left third",
    "right_third": "on the right third",
    "upper_third": "on the upper third",
    "lower_third": "on the lower third",
}


def _recipe_staging(style_key: str) -> str | None:
    """승인 대기 SceneArchetype을 실험용 영문 재연출 지시로 변환한다."""
    if os.environ.get("REFERENCE_RECIPE_EXPERIMENT", "0") != "1":
        return None
    from .reference_recipe_data import get_reference_recipe

    recipe = get_reference_recipe("drink", style_key, allow_unapproved=True)
    if recipe is None:
        return None
    archetype = recipe.archetype
    angle = _ANGLE_INSTRUCTIONS[archetype.camera_angles[0]]
    placement = _PLACEMENT_INSTRUCTIONS[archetype.placements[0]]
    scale = round(sum(archetype.subject_scale) * 50)
    return (
        f"Shoot at {angle}. Place the drink {placement}, occupying about {scale}% of the "
        "canvas width. Follow the reference archetype's product scale and negative-space balance."
    )


_VESSEL_WORDS = ("cup", "glass", "mug", "saucer", "container", "bowl", "plate", "tumbler")


def build_recompose_instruction(style_key: str, subject_en: str,
                                container_desc: str | None = None,
                                temperature: str | None = None,
                                text_zone: str | None = None,
                                flexible_parts: list[str] | None = None,
                                finish_profile: str | None = None,
                                scene_tone: str | None = None,
                                scene_seed: int = 0) -> str | None:
    """P5 음료 재연출 지시 — 보존 편집이 아니라 같은 음료의 '새 연출'을 만든다.

    재연출 계약(원본 승계): 같은 음료·토핑 / 앵글·구도 자유 / 외래 재료·손·글자 금지 /
    text_zone 카피 여백. container_desc·temperature·flexible_parts는 analyze_photo(Vision)
    산출값만 사용한다(개정 #2 — 이름 추정 함수 만들지 말 것).

    제품 이해(PU-001): flexible_parts에 용기(컵·잔·받침)가 있으면 "그 용기는 상품이 아니라
    담는 그릇"이므로 색·재질을 장면 팔레트에 맞게 리스타일 허용(형태는 유지). 음료 자체와
    라떼아트·토핑은 언제나 보존. flexible이 비면 기존처럼 용기까지 그대로 승계(안전 폴백).
    """
    plan = get_reference_plan(style_key, "drink")
    if plan is None:
        return None
    subject = (subject_en or "beverage").strip()
    container = (container_desc or "container").strip()
    zone = (text_zone or "top").replace("_", " ")
    flex_text = " ".join(flexible_parts or []).lower()
    vessel_is_flexible = any(word in flex_text for word in _VESSEL_WORDS)
    if vessel_is_flexible:
        vessel_clause = (
            f"You may restyle the {container}'s color and finish to harmonize with the scene's "
            "palette, but keep its shape and proportions unchanged. Keep the drink itself exactly "
            "as photographed: identical liquid color, foam, latte art, ice and toppings. "
        )
    else:
        vessel_clause = (
            f"Keep the exact same {container} and the exact same drink inside: identical liquid "
            "color, foam, ice and toppings as photographed. "
        )
    effect = _RECOMPOSE_EFFECTS.get((temperature or "").strip().lower())
    effect_txt = f" You may add only {effect}." if effect else ""
    staging_txt = _recipe_staging(plan.style_key) or _RECOMPOSE_STAGING.get(plan.style_key, "")
    # direction 말미의 소품 금지문("No fruit, ... ice, splash ...")은 보존 편집용 —
    # 재연출 계약의 "identical ice/toppings as photographed"와 충돌한다(그 음료의 진짜 얼음까지
    # 지우라는 뜻으로 읽힘). 씬 묘사만 취하고 금지는 아래 계약 문장이 일원화해서 담당한다.
    raw_direction = plan.direction
    # DIV-2: scene_tone 미지정이면 무변경(바이트 동일). 지정 시 표면/배경을 입력 톤에 맞춰 교체.
    if scene_tone is not None:
        raw_direction = _apply_scene_tone(plan.domain, plan.style_key, raw_direction,
                                          scene_tone, subject, scene_seed)
    if "{palette}" in raw_direction:  # PALETTE-001: build_reference_instruction과 동일 치환
        raw_direction = raw_direction.format(palette=_style_palette_clause(plan.style_key, plan.domain, subject))
    scene_direction = ". ".join(
        s.rstrip(".") for s in raw_direction.split(". ") if not s.strip().startswith("No ")
    ) + "."
    # REAL-001: 미지정 시 plan 기본값("none") → 무주입 → 바이트 동일.
    finish = _finish_clause(finish_profile if finish_profile is not None else plan.finish_profile)
    return (
        f"Restage this {subject} into a new advertisement composition. "
        f"{vessel_clause}"
        "You may freely change the camera angle, composition, scale and placement for a more "
        f"dynamic advertising shot. {staging_txt}{effect_txt} "
        f"{scene_direction} "
        f"Leave clean empty copy space in the {zone} area. "
        f"{finish}"
        "Do not add any new ingredients, fruit, garnish, props, hands or people. "
        "Do not generate any new logo, label, lettering, watermark or advertising copy."
    )
