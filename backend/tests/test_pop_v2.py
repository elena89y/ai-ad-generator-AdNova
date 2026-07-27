"""POP-V2 — 팝 4아키타입 로테이션 + 완화 잠금 (2026-07-23 아트디렉터 판정 채택분).

계약: food×pop(비-vessel)만 로테이션·food_pop 잠금, 그 외 스타일·도메인은 바이트 동일.
로테이션은 subject+scene_seed 결정론. {palette}는 PAL-002 적응형/고정 폴백이 채움.
"""
import pytest

from app.services.reference_style_plans import (_IDENTITY_LOCKS, _POP_FOOD_VARIANTS,
                                                build_reference_instruction)


def _instr(style="pop", domain="food", subject="strawberry cream cake", **kw):
    return build_reference_instruction(style, domain, subject, **kw)


def test_four_variants_exist_and_distinct():
    assert len(_POP_FOOD_VARIANTS) == 4
    assert len(set(_POP_FOOD_VARIANTS)) == 4


def test_rotation_deterministic():
    a = _instr(scene_seed=42)
    b = _instr(scene_seed=42)
    assert a == b


def test_rotation_varies_by_seed():
    """시드를 돌리면 복수 아키타입이 실제로 나와야 한다(로테이션 실효)."""
    outs = {_instr(scene_seed=s) for s in range(12)}
    assert len(outs) >= 3


def test_pop_food_uses_relaxed_lock():
    instr = _instr(scene_seed=0)
    assert "You MAY replace the plain plate" in instr          # 접시 교체 허용(판정)
    assert "same ingredients already visible" in instr          # 정직성: 보이는 재료만
    # 기존 드리프트 금지문("No extra food, props...")이 사라졌는지
    assert "No extra food, props" not in instr


def test_palette_placeholder_filled():
    for s in range(6):
        instr = _instr(scene_seed=s)
        assert "{palette}" not in instr
        assert "background" in instr


def test_editorial_realism_warm_now_styled():
    """STYLE-V3(2026-07-26): editorial/realism/warm_organic food 도 로테이션으로 고도화 —
    이제 시드로 변형이 바뀌고(단일 연출 아님) food_pop 공용 완화 잠금을 받는다.
    (구 test_non_pop_styles_unchanged 를 계약 변경에 맞춰 대체.)"""
    for style in ("editorial", "realism", "warm_organic"):
        outs = {_instr(style=style, subject="chocolate cream cake", scene_seed=s,
                       serving_type="dessert", core_ingredients=["chocolate", "cream"])
                for s in range(12)}
        assert len(outs) >= 3, style                          # 로테이션 실효
        one = _instr(style=style, subject="chocolate cream cake", scene_seed=0,
                     serving_type="dessert", core_ingredients=["chocolate", "cream"])
        assert "You MAY replace the plain plate" in one       # food_pop 완화 잠금
        if style == "realism":
            # V3.8: realism은 미드센추리 메탈 = 고정 올-스텐 접시(레지스트리 미사용)
            assert "all-stainless-steel plate" in one
        else:
            assert "premium designer serving piece" in one    # editorial/warm 접시 레지스트리


def test_drink_object_pop_unchanged():
    """v1 스코프: 로테이션은 food만 — drink/object pop은 기존 direction."""
    for dom in ("drink", "object"):
        base = _instr(domain=dom, subject="iced latte" if dom == "drink" else "hand cream")
        seeded = _instr(domain=dom, subject="iced latte" if dom == "drink" else "hand cream",
                        scene_seed=9)
        assert base == seeded
        assert "You MAY replace the plain plate" not in base


def test_vessel_excluded_from_rotation():
    """유리 디저트 용기(vessel)는 용기 보존 우선 — 로테이션·완화 잠금 미적용."""
    kw = dict(container_desc="glass", container_opacity="transparent")
    a = _instr(subject="mango bingsu", scene_seed=1, **kw)
    b = _instr(subject="mango bingsu", scene_seed=5, **kw)
    assert a == b                                   # 시드 무관(로테이션 안 탐)
    assert "You MAY replace the plain plate" not in a


@pytest.mark.parametrize("marker", [
    "joyful pop energy",         # ① ingredient_world
    "string of small pearls",    # ② styling_cut
    "floating weightlessly",     # ③ dynamic_float
    "captured mid-pour",         # ④ gradient_action
])
def test_each_archetype_reachable(marker):
    """12개 시드 안에서 4아키타입 각각이 최소 1회 등장."""
    joined = " ".join(_instr(scene_seed=s) for s in range(12))
    assert marker in joined


# --- POP-V2.1: 소품 구체명 ({props}) — "찰흙 덩어리" 핫픽스 -------------------

def test_props_clause_named_shapes():
    """재료명 → 형태 있는 소품 명사구. 치즈 우선(까르보나라→노란 큐브, 07-24 판정)."""
    from app.services.reference_style_plans import _props_clause
    carbonara = _props_clause(["pasta", "cream", "bacon", "parmesan"])
    assert "yellow parmesan cubes" in carbonara
    cake = _props_clause(["strawberry", "cream", "sponge"])
    assert "fresh whole strawberry" in cake and "freeze-dried strawberry chips" in cake
    assert "never clay-like or dough-like" in _props_clause(None)  # 반-찰흙 폴백(2026-07-27)


def test_props_placeholder_filled_and_anti_lump():
    """{props} 잔존 금지 + 안티-덩어리 절 포함(①③ 계열)."""
    for s in range(12):
        instr = _instr(scene_seed=s, core_ingredients=["strawberry", "cream"])
        assert "{props}" not in instr
    joined = " ".join(_instr(scene_seed=s, core_ingredients=["strawberry", "cream"])
                      for s in range(12))
    assert "no shapeless lumps" in joined


def test_props_without_ingredients_safe():
    """core_ingredients 미전달(구캐시·스텁)이어도 {props}는 일반 폴백으로 채워진다."""
    for s in range(4):
        instr = _instr(scene_seed=s)
        assert "{props}" not in instr


# --- NOODLE-GUARD: 면류는 ①(scatter) 제외 — 본체 재드로잉 라이브 2회 실측 ------

@pytest.mark.parametrize("subject", [
    "creamy carbonara pasta", "cream carbonara pasta", "spicy ramen noodles",
    "cold buckwheat soba", "japchae glass noodles", "beef pho",
])
def test_noodle_never_gets_scatter_archetype(subject):
    """면류 subject는 전 시드에서 ①(마커: 'joyful pop energy')이 절대 안 나와야 한다 —
    유닛 보증이 GPU 1샷보다 강함(전수)."""
    for s in range(24):
        instr = _instr(subject=subject, scene_seed=s)
        assert "joyful pop energy" not in instr, (subject, s)
        assert "You MAY replace the plain plate" in instr  # 완화 잠금은 유지


def test_noodle_still_rotates_among_three():
    """면류도 ②③④ 3종 로테이션은 유지(단일 고정 아님)."""
    outs = {_instr(subject="creamy carbonara pasta", scene_seed=s) for s in range(12)}
    assert len(outs) >= 2


@pytest.mark.parametrize("style,bad_marker", [
    ("monotone", "color-immersion"),   # ③ brand — 면류 4/4 재드로잉
    ("pastel", "shimmering silk"),     # ① dreamy — 면류 4/4 재드로잉
])
def test_noodle_excludes_unsafe_variants_all_styles(style, bad_marker):
    """면류 안전 서브셋(실측 통과분만): 전 시드에서 위험 변형 절대 미발생 + 잠금 보강절.
    ⚠️ 보강절에 'egg' 같은 위험 명사 금지(부정문 조건화 소환 실측)."""
    for s in range(24):
        instr = _instr(style=style, subject="cream carbonara pasta", scene_seed=s,
                       serving_type="dish")
        assert bad_marker not in instr, (style, s)
        assert "never convert penne into spaghetti" in instr
        assert "egg" not in instr
    # 비면류(케이크)는 해당 변형 여전히 도달 가능
    joined = " ".join(_instr(style=style, scene_seed=s) for s in range(12))
    assert bad_marker in joined


def test_non_noodle_keeps_four():
    """비면류(케이크)는 4종 그대로 — ① 마커가 12시드 안에 등장."""
    joined = " ".join(_instr(scene_seed=s) for s in range(12))
    assert "joyful pop energy" in joined


def test_retouch_clause_present():
    """RETOUCH-001→003: 짭짤한 음식=절제형 보정, 디저트=tpl_47급 이상화(같은 제품 인식 +
    무발명 경계) — '전혀 먹음직스럽지 않다'(07-24 아트디렉터) 판정 반영."""
    pop = _instr(scene_seed=0)
    assert "Retouch it like a professional food ad" in pop          # 공용 절제형(전 음식, 압축판)
    # 디저트: 스타일 로테이션·food_dessert 락 모두 이상화 절
    pop_dessert = _instr(scene_seed=0, serving_type="dessert")
    assert "Idealize this dessert" in pop_dessert
    editorial_dessert = _instr(style="editorial", serving_type="dessert")  # STYLE-V3: styled+idealize
    assert "Idealize this dessert" in editorial_dessert
    assert "never add ingredients, layers or decoration" in editorial_dessert  # 무발명 경계
    # 짭짤한 음식은 이상화 미적용
    savory = _instr(subject="grilled beef", serving_type="dish", scene_seed=0)
    assert "Idealize this dessert" not in savory

# --- RETOUCH-004: 초코 디저트 질감 어휘 등길이 맞교환 ---------------------------

def test_choco_dessert_texture_swap():
    """초코 디저트는 generic 질감 절 → fudgy·ganache 수사(무발명: 기존 크림의 렌더 수사).
    비초코 디저트는 generic 유지, 짭짤(예: 초코 글레이즈 립)은 이상화 자체가 없어 미작동."""
    from app.services.reference_style_plans import _IDEALIZE_TEX_GENERIC
    choco_kw = dict(serving_type="dessert",
                    core_ingredients=["strawberry", "chocolate", "cream"])
    pop_choco = _instr(subject="strawberry chocolate cream cake", scene_seed=0, **choco_kw)
    assert "fudgy" in pop_choco and "ganache" in pop_choco
    assert _IDEALIZE_TEX_GENERIC not in pop_choco
    ed_choco = _instr(style="editorial", subject="strawberry chocolate cream cake", **choco_kw)
    assert "fudgy" in ed_choco                       # food_dessert 락 경로도 동일
    bb = _instr(subject="blueberry cream cake", scene_seed=0, serving_type="dessert")
    assert "fudgy" not in bb and _IDEALIZE_TEX_GENERIC in bb
    savory = _instr(subject="chocolate glazed pork ribs", scene_seed=0, serving_type="dish")
    assert "fudgy" not in savory and "Idealize" not in savory


# --- 2026-07-25 아트디렉터 6무드 피드백: 팝 색보존 + 포크 제거 --------------------

def test_pop_color_lock_present():
    """팝에서 다크 초코 베이스가 주황 스펀지로 변색되던 것 차단(color-lock, 공용 락)."""
    for style in ("pop", "monotone", "pastel"):
        instr = _instr(style=style, subject="chocolate cream cake", scene_seed=0,
                       serving_type="dessert", core_ingredients=["chocolate", "cream"])
        assert "dark chocolate stays dark brown" in instr, style
        assert "recolored" in instr


def test_no_cutlery_carryover():
    """원본 잡기물(플라스틱 포크)이 재연출로 딸려오지 않게 — 공용 락 no-cutlery 절.
    팝②의 의도적 'polished dessert fork'도 제거(전 시드에서 미등장)."""
    joined = " ".join(_instr(style="pastel", subject="chocolate cream cake", scene_seed=s,
                             serving_type="dessert", core_ingredients=["chocolate", "cream"])
                      for s in range(12))
    assert "no fork or cutlery carried over from the original" in joined
    pop_joined = " ".join(_instr(style="pop", subject="strawberry cream cake", scene_seed=s)
                          for s in range(12))
    assert "polished dessert fork" not in pop_joined   # 팝② 의도적 포크 제거


# --- STYLE-V3: editorial/realism/warm 고도화 + 접시 레지스트리 --------------------

def test_plate_registry_form_diversity():
    """접시는 하드코딩 고정이 아니라 _PLATE_SHAPES 레지스트리에서 subject:seed 로테이션 —
    editorial 24시드에서 복수 FORM(평평·원기둥 스탠드·프리폼 등)이 실제로 등장(다양성)."""
    from app.services.reference_style_plans import _PLATE_SHAPES, _plate_clause
    forms = {_plate_clause("editorial", "chocolate cream cake", s).split(" in ")[0]
             for s in range(24)}
    assert len(forms) >= 4, f"접시 FORM 다양성 부족(고정 의심): {len(forms)}"
    # 데이터 레지스트리에 '평평' 과 '원기둥(스탠드/페데스탈)' 형태가 실재
    joined = " ".join(_PLATE_SHAPES)
    assert "flat round plate" in joined
    assert "cake stand" in joined or "pedestal" in joined


def test_plate_clause_style_finish_and_no_placeholder():
    """스타일별 대비 마감(정체성) + {plate} 자리표시자 잔존 없음."""
    from app.services.reference_style_plans import _plate_clause
    assert "charcoal rim" in _plate_clause("editorial", "cake", 0)   # editorial=차콜림 화이트
    assert "brushed-gold rim" in _plate_clause("warm_organic", "cake", 0)  # warm=골드림
    for style in ("editorial", "realism", "warm_organic"):
        instr = _instr(style=style, subject="chocolate cream cake", scene_seed=3,
                       serving_type="dessert", core_ingredients=["chocolate", "cream"])
        assert "{plate}" not in instr and "{props}" not in instr


def test_style_v3_no_palette_pollution():
    """editorial/realism/warm 은 팔레트 미지원 → {palette} 미사용, 'None' 오염 없음."""
    for style in ("editorial", "realism", "warm_organic"):
        instr = _instr(style=style, subject="chocolate cream cake", scene_seed=0,
                       serving_type="dessert", core_ingredients=["chocolate", "cream"])
        assert "{palette}" not in instr and " None " not in instr
