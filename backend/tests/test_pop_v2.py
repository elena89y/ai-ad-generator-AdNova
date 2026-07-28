"""POP-V2 — 팝 4아키타입 로테이션 + 완화 잠금 (2026-07-23 아트디렉터 판정 채택분).

계약: food×pop(비-vessel)만 로테이션·food_pop 잠금, 그 외 스타일·도메인은 바이트 동일.
로테이션은 subject+scene_seed 결정론. {palette}는 PAL-002 적응형/고정 폴백이 채움.
"""
import pytest

from app.services.reference_style_plans import (_IDENTITY_LOCKS, _INGREDIENT_TEX,
                                                _POP_FOOD_VARIANTS,
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


# --- NOODLE-PRESERVE: 마른 면도 국물처럼 in-place 보존 (2026-07-27 라이브 사고) ------
#   구 NOODLE-GUARD(안전 변형 서브셋 + "never convert penne into spaghetti" 부정문)는 라이브에서
#   둘 다 통과하고도 펜네→스파게티 둥지+갈색 타워로 붕괴 → 계약을 '보존'으로 격상.

@pytest.mark.parametrize("subject", [
    "creamy carbonara pasta", "cream carbonara pasta",
    "cold buckwheat soba", "japchae glass noodles",
])
def test_noodle_never_gets_scatter_archetype(subject):
    """건식 면류는 스캐터 아키타입은 물론 styled 재연출 자체를 안 탄다(보존 라우팅)."""
    for s in range(24):
        instr = _instr(subject=subject, scene_seed=s)
        assert "joyful pop energy" not in instr, (subject, s)
        assert "keep the noodles exactly as they are" in instr, (subject, s)
        assert "You MAY replace the plain plate" not in instr  # 재플레이팅 아님


@pytest.mark.parametrize("subject", ["spicy ramen noodles", "beef pho", "korean spicy beef soup"])
def test_soup_noodle_preserved(subject):
    """SOUP-PRESERVE(2026-07-27): 국물 요리(라멘·쌀국수·육개장)는 전 무드에서 in-place 보존
    락으로 라우팅 — 스캐터·재플레이팅 없이 국물·용기 유지(아트디렉터 "육개장 국물이 사라짐")."""
    for s in range(24):
        instr = _instr(subject=subject, scene_seed=s)
        assert "joyful pop energy" not in instr, (subject, s)
        assert "keep it a soup" in instr, (subject, s)          # 국물 보존 락
        assert "never move the food onto a flat plate" in instr  # 재플레이팅 금지
        assert "You MAY replace the plain plate" not in instr    # food_pop 재플레이팅 아님


def test_noodle_instruction_is_stable_across_seeds():
    """보존 라우팅이라 면 요리는 시드로 연출이 흔들리지 않는다(씬 배경만 스타일별로 다름)."""
    outs = {_instr(subject="creamy carbonara pasta", scene_seed=s) for s in range(12)}
    assert len(outs) == 1


@pytest.mark.parametrize("style,bad_marker", [
    ("monotone", "color-immersion"),   # ③ brand — 면류 4/4 재드로잉
    ("pastel", "shimmering silk"),     # ① dreamy — 면류 4/4 재드로잉
])
def test_noodle_excludes_unsafe_variants_all_styles(style, bad_marker):
    """면류는 위험 변형은 물론 어떤 styled 변형도 안 탄다 + 보존 락으로 형태 고정.
    ⚠️ 'egg' 같은 위험 명사는 부정문에도 넣지 않는다(조건화 소환 실측)."""
    for s in range(24):
        instr = _instr(style=style, subject="cream carbonara pasta", scene_seed=s,
                       serving_type="dish")
        assert bad_marker not in instr, (style, s)
        assert "the same noodle shape" in instr        # 보존 락(면 형태 고정)
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


# --- BAKERY-SPLIT + FOOD-FIDELITY (2026-07-27, 치아바타 케이크화·김밥 속재료 사고) ----

def test_savory_bakery_never_idealized():
    """짠 빵(치아바타)은 스타일 불문 디저트 이상화 금지 + savory 본체 충실 절."""
    for style in ("pop", "editorial", "monotone", "pastel", "warm_organic"):
        for s in range(8):
            instr = _instr(style=style, subject="ciabatta bread with marinated tomatoes",
                           scene_seed=s, serving_type="bakery")
            assert "Idealize this dessert" not in instr, (style, s)
            assert "cut surface stays" in instr, (style, s)


def test_sweet_bakery_keeps_idealize():
    """단 빵(크루아상·단팥빵)은 기존 이상화 유지."""
    for subj in ("butter croissant", "butter red bean bread"):
        instr = _instr(subject=subj, scene_seed=0, serving_type="bakery")
        assert "Idealize this dessert" in instr


def test_dish_gets_fidelity_not_dessert_texture():
    """dish 는 본체 충실 절 + 없던 소스 금지, 디저트 질감 어휘(스펀지·크림)는 맞교환 제거."""
    instr = _instr(subject="grilled beef", scene_seed=0, serving_type="dish")
    assert "cut surface stays" in instr and "add no sauce or topping" in instr
    assert "sponge moist" not in instr          # T5 맞교환: 디저트 질감 어휘 제거
    assert "Retouch it like a professional food ad" in instr  # 리터치 자체는 유지


def test_dessert_unaffected_by_fidelity():
    """디저트는 기존 이상화 경로 그대로 — fidelity 절 미적용."""
    instr = _instr(scene_seed=0, serving_type="dessert")
    assert "Idealize this dessert" in instr
    assert "cut surface stays" not in instr


# --- NOODLE-PRESERVE + PROP-COOK (2026-07-27 라이브: 펜네→스파게티 타워, 생고기 소품) ----

@pytest.mark.parametrize("style", ["pop", "monotone", "pastel", "editorial", "realism",
                                   "warm_organic"])
def test_noodle_dish_preserved_all_moods(style):
    """마른 면(펜네·파스타)은 전 무드에서 in-place 보존 — styled 재연출 미적용.
    라이브 사고: 크림 펜네 파스타 monotone 이 스파게티 둥지+갈색 타워로 재구성."""
    for s in range(8):
        instr = _instr(style=style, subject="cream penne pasta", scene_seed=s,
                       serving_type="dish", core_ingredients=["penne", "cream"])
        assert "keep the noodles exactly as they are" in instr, (style, s)
        assert "molded" in instr                                  # 타워/링 재조형 금지
        assert "You MAY replace the plain plate" not in instr     # 재플레이팅 아님


def test_soup_noodle_still_routes_to_soup():
    """국물 면(라멘·쌀국수)은 여전히 SOUP-PRESERVE 가 선행 — 이중 라우팅 없음."""
    for subj in ("spicy ramen noodles", "beef pho"):
        instr = _instr(subject=subj, scene_seed=0, serving_type="dish")
        assert "keep it a soup" in instr
        assert "keep the noodles exactly as they are" not in instr


def test_non_noodle_unaffected():
    """비면 요리는 기존 경로 유지(회귀 가드)."""
    beef = _instr(subject="grilled pork ribs", scene_seed=0, serving_type="dish")
    assert "keep the noodles exactly as they are" not in beef
    assert "You MAY replace the plain plate" in beef


def test_meat_prop_follows_cooking_method():
    """PROP-COOK: 고기 소품의 조리 상태가 요리의 조리법을 따른다(구이=구운 고기)."""
    from app.services.reference_style_plans import _props_clause
    grilled = _props_clause(["pork"], "grilled pork ribs")
    assert "grilled" in grilled and "charred grill marks" in grilled
    fried = _props_clause(["chicken"], "fried chicken cutlet")
    assert "fried" in fried
    braised = _props_clause(["beef"], "braised beef stew pot")
    assert "braised" in braised
    # 고기 아닌 소품은 조리법 무관(회귀)
    assert "grilled" not in _props_clause(["strawberry"], "grilled pork ribs")


# --- NOODLE-SHAPE-ANCHOR (2026-07-27: 보존 락만으로 monotone·pastel 이 펜네→긴면 4/6) ----

def test_noodle_shape_named_at_front():
    """면 종류를 구체 명사로 문두에 긍정 단언 — 조건형("short tubes stay...") 대신 앵커."""
    instr = _instr(style="monotone", subject="cream penne pasta", scene_seed=0,
                   serving_type="dish", core_ingredients=["pasta"])
    assert "short ridged penne tubes" in instr
    # 앵커는 지시문 앞부분(1/3 이내)에 위치해야 조건화가 강하다
    assert instr.index("short ridged penne tubes") < len(instr) // 3
    assert "{noodle}" not in instr


@pytest.mark.parametrize("subject,marker", [
    ("cream penne pasta", "penne tubes"),
    ("carbonara spaghetti", "long thin round strands"),
    ("japchae glass noodles", "sweet-potato strands"),
    ("cold buckwheat soba", "buckwheat strands"),
])
def test_noodle_shape_registry_matches(subject, marker):
    """레지스트리가 면 종류별 구체 형태를 준다(하드코딩 대신 데이터)."""
    for style in ("monotone", "pastel", "pop"):
        assert marker in _instr(style=style, subject=subject, scene_seed=0,
                                serving_type="dish")


def test_unknown_noodle_falls_back_safely():
    """미등록 면은 중립 폴백 — 없는 형태를 지어내지 않는다."""
    instr = _instr(subject="mystery house noodles", scene_seed=0, serving_type="dish")
    assert "exactly the shape, cut and thickness seen in the photo" in instr


# --- INGREDIENT-TEX (2026-07-27: "다른 가니시들과 재료들도 사실적으로") -----------------
#   질감 어휘는 정적 상시 문구가 아니라 **그 요리에 실제 있는 재료**로 선택된다(T5 예산 보호).

@pytest.mark.parametrize("core,marker", [
    (["arugula", "cheese"], "leafy greens veined"),
    (["cheese"], "grated cheese dry and granular"),
    (["kimchi", "tofu"], "kimchi glossy"),
    (["shrimp"], "seafood plump"),
    (["seaweed"], "seaweed matte"),
    (["potato"], "potato matte"),   # 내부 구조어(inside) 제거된 안전 문구
])
def test_ingredient_texture_selected_by_ingredient(core, marker):
    """재료가 있으면 그 재료의 질감 어휘가 실린다(여유 있는 경로 기준)."""
    instr = _instr(style="realism", subject="mixed dish", scene_seed=0,
                   serving_type="dish", core_ingredients=core)
    assert marker in instr, (core, marker)


def test_ingredient_texture_absent_without_ingredients():
    """재료 미상(구캐시·스텁)이면 질감 절 미주입 — 없는 재료를 지어내지 않는다."""
    instr = _instr(style="realism", subject="mixed dish", scene_seed=0, serving_type="dish")
    for _, _, tex in _INGREDIENT_TEX:
        assert tex not in instr


def test_glossy_cheese_vocab_removed():
    """갈아놓은 경성치즈에 'glossy'는 오지시(왁스 덩어리) — 건조·알갱이 어휘로 대체됐다."""
    for subject in ("cream penne pasta", "grilled pork ribs", "korean spicy beef soup"):
        for style in ("realism", "monotone", "pop"):
            instr = _instr(style=style, subject=subject, scene_seed=0, serving_type="dish",
                           core_ingredients=["cheese"])
            assert "cheese glossy" not in instr, (style, subject)


def test_texture_never_exceeds_two_phrases():
    """예산 보호: 재료가 많아도 최대 2종까지만 실린다."""
    instr = _instr(style="pop", subject="loaded dish", scene_seed=0, serving_type="dish",
                   core_ingredients=["cheese", "kimchi", "tofu", "shrimp", "potato", "rice"])
    hits = [t for _, _, t in _INGREDIENT_TEX if t in instr]
    assert len(hits) <= 2, hits


# --- 워크플로 적대 검증 반영(2026-07-27): substring 키 붕괴·예산 가드 무력화 ------------

@pytest.mark.parametrize("ingredient", [
    "donut", "doughnut",          # nut → 견과 (베이커리 최빈 입력, 확정 사고였음)
    "hamburger", "graham cracker",  # ham → 가공육
    "rice noodles", "rice flour",   # rice → 밥알
    "green tea powder", "mint syrup", "basil pesto",  # green/mint/basil → 생잎
    "black pepper", "chili powder",  # pepper → 통고추
    "sesame oil", "potato starch", "tomato sauce", "mushroom powder",
    "peanut butter", "coconut milk",
])
def test_no_texture_for_lookalike_ingredients(ingredient):
    """substring 오매칭으로 없는 재료를 소환하지 않는다 — 전부 실측으로 확인된 사고 목록."""
    from app.services.reference_style_plans import _ingredient_tex_clause
    assert _ingredient_tex_clause([ingredient]) == "", ingredient


@pytest.mark.parametrize("ingredient,marker", [
    ("arugula", "leafy greens"), ("parmesan", "grated cheese"), ("kimchi", "kimchi glossy"),
    ("shrimp", "seafood plump"), ("seaweed", "seaweed matte"), ("potato", "potato matte"),
    ("rice", "rice grains"), ("tteok", "rice cakes"),
])
def test_real_ingredients_still_match(ingredient, marker):
    """정상 재료는 그대로 매칭된다(오매칭 차단이 과잉이 아님)."""
    from app.services.reference_style_plans import _ingredient_tex_clause
    assert marker in _ingredient_tex_clause([ingredient]), ingredient


def test_zero_budget_injects_nothing():
    """예산 없음(limit<=0) 판정이 무력화되지 않는다 — 루프가 1개를 흘리던 결함 가드."""
    from app.services.reference_style_plans import _ingredient_tex_clause
    assert _ingredient_tex_clause(["cheese", "tomato", "bacon"], limit=0) == ""


def test_soup_excludes_submerged_ingredients():
    """국물에 잠기는 건더기(두부·감자·버섯·해산물)는 질감 지시 제외 — 국물 위로 끌어올리지 않는다."""
    from app.services.reference_style_plans import _ingredient_tex_clause
    got = _ingredient_tex_clause(["tofu", "potato", "kimchi"], is_soup=True)
    assert "tofu" not in got and "potato" not in got
    assert "kimchi" in got            # 잠기지 않는 재료는 유지


# --- BAKE-TEX (2026-07-27 라이브: 말차베리쿠키가 매끈한 찰흙 돔으로) --------------------

@pytest.mark.parametrize("subject,core", [
    ("matcha berry cookie", ["matcha", "berry", "white chocolate"]),  # 초코 스왑 오발동 케이스
    ("chocolate chip cookie", ["chocolate", "flour"]),
    ("butter scone", ["butter", "flour"]),
    ("almond macaron", ["almond", "cream"]),
])
def test_baked_goods_get_crisp_texture(subject, core):
    """구움과자는 케이크 스펀지 어휘가 아니라 바삭·균열 어휘를 받는다.
    특히 재료의 'white chocolate' 이 초코 스왑을 오발동시켜 쿠키에 '촉촉한 초코 스펀지'가
    실리던 라이브 사고(찰흙 돔)를 막는다."""
    instr = _instr(style="pastel", subject=subject, scene_seed=3,
                   serving_type="dessert", core_ingredients=core)
    assert "craggy crust" in instr, subject
    assert "moist airy sponge" not in instr
    assert "fudgy chocolate sponge" not in instr


@pytest.mark.parametrize("subject,core,marker", [
    ("strawberry chocolate cream cake", ["chocolate", "cream"], "fudgy chocolate sponge"),
    ("blueberry fresh cream cake", ["blueberry", "cream"], "moist airy sponge"),
])
def test_cakes_keep_their_texture(subject, core, marker):
    """케이크류는 기존 질감 어휘 유지(구움과자 분기가 과잉이 아님)."""
    instr = _instr(style="pastel", subject=subject, scene_seed=3, serving_type="dessert",
                   core_ingredients=core)
    assert marker in instr, subject
