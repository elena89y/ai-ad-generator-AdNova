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
    ("strawberry chocolate cream cake", "food", "RICH"),   # 초코 = RICH (ZESTY 오분류 회귀)
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
