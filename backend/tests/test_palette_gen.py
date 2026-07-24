"""PAL-001 제품 적응형 팝 팔레트 생성기 테스트.

설계: ~/ai-ad-generator-AdNova-rule/제품적응형_팔레트_설계_v1.md
검증: 분류 정확성(부분문자열 오매칭 회귀 포함) · 레시피 로테이션 · 식욕 게이트 ·
      문구 형식 계약 · 이미지 없음 폴백 · build_reference_instruction 바이트 동일.
"""
import re

import pytest

from app.services import palette_gen as pg


# --- 제품군 분류 -------------------------------------------------------------
@pytest.mark.parametrize("subject,domain,expected", [
    # PAL-004(2026-07-24): 케이크류는 초코가 들어가도 SOFT — 라이브 원색 사고(historyId=213)
    #   교정. 구 기대값 RICH는 그 사고의 원인이었음.
    ("strawberry chocolate cream cake", "food", "SOFT"),
    ("blueberry cream cake", "food", "SOFT"),
    ("fresh lemonade", "drink", "ZESTY"),
    ("iced lemon ade", "drink", "ZESTY"),
    ("fried chicken", "food", "PUNCHY"),
    ("rainbow candy", "food", "PUNCHY"),
    ("iced americano", "drink", "RICH"),
    ("vanilla latte", "drink", "SOFT"),
    ("ceramic mug", "object", "OBJECT"),
    ("무엇인지 모를 신메뉴", "food", "SOFT"),                # 미분류 → SOFT 안전측
])
def test_classify(subject, domain, expected):
    assert pg._classify(subject, domain) == expected


@pytest.mark.parametrize("subject", [
    "chocolate cake",       # 'cola' in 'chocolate' 오매칭 금지
    "sublime chocolate",    # 'lime' in 'sublime' 오매칭 금지
    "marmalade toast",      # 'ade' in 'marmalade' 오매칭 금지(옛 힌트 제거)
])
def test_classify_no_substring_false_positive(subject):
    assert pg._classify(subject, "food") != "ZESTY"


# --- 문구 형식 계약(드롭인) ---------------------------------------------------
_CLAUSE_RE = re.compile(r"^a .+ background and a clean .+ table surface$")


@pytest.mark.parametrize("subject,domain", [
    ("blueberry cream cake", "food"), ("fresh lemonade", "drink"),
    ("fried chicken", "food"), ("iced americano", "drink"), ("", "food"),
])
def test_clause_format(subject, domain):
    for seed in range(6):
        clause = pg.pop_palette_clause(subject, domain, image_path=None, seed=seed)
        assert _CLAUSE_RE.match(clause), clause


def test_no_image_fallback_never_raises():
    assert pg.pop_palette_clause("완전 미지 상품", "food", image_path=None)
    assert pg.pop_palette_clause("cake", "food", image_path="/does/not/exist.png")


# --- 레시피 로테이션(같은 상품, 다른 seed → 조합 다양화) ----------------------
def test_recipe_rotation_varies():
    seen = {pg.pop_palette_clause("lemonade", "drink", None, s) for s in range(6)}
    assert len(seen) >= 2  # 고정 1개가 아니라 seed 로 다양화


# --- 식욕 게이트: 고형 음식 배경에 쨍한 파랑 큰 면 금지 ------------------------
def test_appetite_gate_solid_food_no_saturated_blue():
    hsv = pg._appetite_gate((220.0, 0.9, 0.9), "PUNCHY", "food")
    assert hsv[1] <= 0.3  # 채도 완화됨
    # 드링크는 파랑 허용(완화 안 함)
    assert pg._appetite_gate((220.0, 0.9, 0.9), "PUNCHY", "drink")[1] == 0.9


def test_appetite_gate_no_saturated_blue_phrase_for_food():
    for subject in ("lemon soda gummy", "blueberry snack", "grape candy"):
        for seed in range(8):
            clause = pg.pop_palette_clause(subject, "food", None, seed)
            bg = clause.split(" background")[0]
            blue_names = ("cobalt-blue", "sky-blue", "cyan", "indigo")
            assert not ("saturated" in bg and any(b in bg for b in blue_names)), clause


# --- 이미지 추출이 출력에 반영되는지(합성 이미지) ------------------------------
def test_extraction_influences_output(tmp_path):
    from PIL import Image
    violet = Image.new("RGB", (256, 256), (110, 60, 150))  # 보라 지배 제품 근사
    p = tmp_path / "violet.png"
    violet.save(p)
    extracted = pg._extract_colors(str(p))
    assert extracted is not None
    (fh, fs, fv), _ = extracted
    assert 250 <= fh <= 300  # 보라 계열 hue 추출


# --- build_reference_instruction: override 미전달 시 바이트 동일 --------------
def test_build_reference_instruction_byte_identity_without_override():
    from app.services import reference_style_plans as rsp
    base = rsp.build_reference_instruction("pop", "food", "chocolate cake")
    same = rsp.build_reference_instruction("pop", "food", "chocolate cake",
                                           palette_override=None)
    assert base == same
    # 고정 팔레트 문구(_POP_PALETTES) 중 하나가 그대로 들어가 있어야 함(폴백 경로 유지)
    assert any(v in base for v in rsp._POP_PALETTES["food"])


def test_build_reference_instruction_uses_override():
    from app.services import reference_style_plans as rsp
    override = "a soft violet background and a clean warm ivory table surface"
    out = rsp.build_reference_instruction("pop", "food", "blueberry cake",
                                          palette_override=override)
    assert override in out
    # 고정 팔레트가 override 로 대체됐는지
    assert not any(v in out for v in rsp._POP_PALETTES["food"])


# --- PAL-003: 파스텔·모노톤 롤아웃 (2026-07-24) ------------------------------

def test_style_dispatch():
    """통합 진입점: pop/pastel/monotone만 절 반환, 미지원 스타일은 None(기존 고정 조회)."""
    from app.services.palette_gen import style_palette_clause as spc
    assert spc("editorial", "cake", "food") is None
    assert spc("realism", "cake", "food") is None
    for style in ("pop", "pastel", "monotone"):
        assert spc(style, "strawberry cake", "food", None, 42)


def test_pastel_form_and_anchor():
    """파스텔: 검증된 문구 형태(pale…low muted…table plane) + 의미 hue 우선(우드 오염 방어)."""
    from app.services.palette_gen import _pastel_clause
    c = _pastel_clause("strawberry cream cake", "food", None, 42)
    assert c.startswith("a pale ") and "table plane" in c
    obj = _pastel_clause("hand cream", "object", None, 42)
    assert "pedestal behind the product" in obj


def test_monotone_semantic_names():
    """모노톤: 관용 딥 색명(버건디·에스프레소) — 'deep orange' 같은 부적합명 금지.

    딥/페일 2변주 로테이션이므로 시드 스캔으로 딥 변주 도달을 확인한다."""
    from app.services.palette_gen import _monotone_clause
    straw = " ".join(_monotone_clause("strawberry cream cake", "food", None, s)
                     for s in range(4))
    coffee = " ".join(_monotone_clause("americano coffee", "food", None, s)
                      for s in range(4))
    assert "burgundy" in straw            # 딸기=레드 계열 → 버건디 딥
    assert "espresso brown" in coffee     # 커피=브라운 계열
    assert "deep orange" not in coffee and "deep orange" not in straw


def test_monotone_achromatic_fallback():
    """무채 제품(추출상 저채도)은 기존 도브그레이 유지 — 적응 근거 없음."""
    from app.services import palette_gen
    fh, chromatic = palette_gen._anchor_hue("mystery dish", None)
    assert chromatic  # 추출 실패 시 웜뉴트럴 유채
    # 저채도 추출 모사: chromatic=False 경로
    import unittest.mock as mock
    with mock.patch.object(palette_gen, "_anchor_hue", return_value=(200.0, False)):
        c = palette_gen._monotone_clause("gray thing", "food", None, 1)
    assert "dove-gray" in c


def test_pal003_deterministic():
    from app.services.palette_gen import style_palette_clause as spc
    for style in ("pastel", "monotone"):
        assert (spc(style, "strawberry cake", "food", None, 42)
                == spc(style, "strawberry cake", "food", None, 42))


def test_pal004_dessert_forces_soft():
    """PAL-004(라이브 원색 사고 historyId=213): '초코 케이크'가 RICH로 낚여 알몸 원색을
    받던 구멍 — serving_type=dessert|bakery → SOFT 강제 + SOFT 힌트가 RICH보다 우선."""
    from app.services.palette_gen import _classify, pop_palette_clause
    assert _classify("strawberry chocolate cream cake", "food", "dessert") == "SOFT"
    assert _classify("strawberry choco cream cake", "food") == "SOFT"  # 이름만으로도(cake>choco)
    clause = pop_palette_clause("strawberry choco cream cake", "food", None, 42,
                                serving_type="dessert")
    assert "pastel" in clause
    # 진짜 RICH·PUNCHY는 유지
    assert _classify("americano coffee", "food") == "RICH"
    assert _classify("fried chicken", "food", "dish") == "PUNCHY"


def test_pal004_no_bare_color_names():
    """알몸 색명("a red background") 금지 — 모든 군·시드에서 수식어 필수."""
    import re
    from app.services.palette_gen import pop_palette_clause
    for subj in ("strawberry choco cream cake", "americano coffee", "fried chicken",
                 "pink lemonade"):
        for s in range(8):
            clause = pop_palette_clause(subj, "food", None, s)
            for m in re.finditer(r"a ([a-z-]+) background", clause):
                assert m.group(1) not in ("red", "orange", "pink", "green", "cyan",
                                          "magenta", "violet"), (subj, s, clause)


def test_pal005_no_saturated_token_ever():
    """PAL-005(설계 v1 정본 회귀): 적응형 절에 'saturated' 토큰 금지 — 07-22 '강하게'
    실험(기각)의 잔재가 원색 플랫 배경의 소스였음. 설계엔 원색 단색 배경이 없다
    (ZESTY/PUNCHY도 보색 '조합'+60-30-10+앵커)."""
    from app.services.palette_gen import style_palette_clause as spc
    for style in ("pop", "pastel", "monotone"):
        for subj in ("strawberry choco cream cake", "pink lemonade", "fried chicken",
                     "americano coffee"):
            for s in range(6):
                clause = spc(style, subj, "food", None, s)
                assert "saturated" not in clause, (style, subj, s, clause)
