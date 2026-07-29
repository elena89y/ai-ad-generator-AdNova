"""v6-1 F1 상세페이지 문구 엔진 테스트 — 담당: 한의정.

전 케이스 GPT 모킹(비용 0). 조판 반복 검증은 골든 카피 픽스처(_FIXTURE)로 —
개발 중 실 API 재호출 금지 원칙(DIRECTION_v6-1 §2 P1).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw

from app.schemas.ads import AdPurpose
from app.services import gpt_service
from app.services.pipeline_v5 import commercial_copy, generate_v5
from app.services.pipeline_v5.commercial_copy import detail_copy_for
from app.services.pipeline_v5.formats import detail_page
from app.services.pipeline_v5.hero import DetailCut, DetailCutRole, hero_from_existing

# 골든 카피 픽스처 — 조판 테스트 공용 (실 GPT 응답 형태와 동일 키).
_FIXTURE = {
    "intro_headline": "오늘의 상큼함을 담다",
    "story_title": "수제 청으로 만든 한 잔",
    "story_body": "매일 아침 딸기를 손질해 청을 담급니다. 설탕은 줄이고 과육은 살렸습니다.",
    "benefit_bullets": ["수제 딸기청", "당일 제조", "생과육 가득"],
    "top_view_label": "위에서 본 한 잔",
    "closeup_caption": "과육이 그대로",
    "profile_title": "한 잔의\n밀도",
    "profile_caption": "바닥까지 가라앉지 않는 과육",
    "lifestyle_line": "오후를 깨우는 붉은 한 모금",
    "cta_title": "지금 맛보세요",
    "cta_label": "주문하기",
    "claimed_ingredients": ["strawberry"],
}


def _fixture_detail_copy() -> gpt_service.DetailCopy:
    f = _FIXTURE
    return gpt_service.DetailCopy(
        intro_headline=f["intro_headline"], story_title=f["story_title"],
        story_body=f["story_body"], benefit_bullets=list(f["benefit_bullets"]),
        top_view_label=f["top_view_label"], closeup_caption=f["closeup_caption"],
        profile_title=f["profile_title"], profile_caption=f["profile_caption"],
        lifestyle_line=f["lifestyle_line"], cta_title=f["cta_title"],
        cta_label=f["cta_label"])


# --- generate_detail_copy (gpt_service) --------------------------------------

def test_generate_detail_copy_parses_full_json():
    with patch.object(gpt_service, "_chat_json", return_value=dict(_FIXTURE)) as mocked:
        copy = gpt_service.generate_detail_copy(
            "딸기 에이드", "strawberry ade", "drink", "달콤한 한 잔",
            core_ingredients=["strawberry"], style_key="pop")
    mocked.assert_called_once()
    assert copy.intro_headline == "오늘의 상큼함을 담다"
    assert copy.story_body.startswith("매일 아침")
    assert copy.benefit_bullets == ["수제 딸기청", "당일 제조", "생과육 가득"]
    assert copy.profile_title == "한 잔의\n밀도"
    assert copy.cta_label == "주문하기"


def test_generate_detail_copy_rejects_hallucinated_ingredient_with_one_correction():
    """D4b 패턴: 자기보고 재료가 core 밖이면 교정 프롬프트로 1회 재생성한다."""
    bad = dict(_FIXTURE, claimed_ingredients=["mint"])
    calls: list[str] = []

    def _fake(messages, label):  # noqa: ANN001
        calls.append(messages[0]["content"])
        return bad if len(calls) == 1 else dict(_FIXTURE)

    with patch.object(gpt_service, "_chat_json", side_effect=_fake):
        copy = gpt_service.generate_detail_copy(
            "딸기 에이드", "strawberry ade", "drink", "달콤한 한 잔",
            core_ingredients=["strawberry", "sparkling water"])
    assert len(calls) == 2
    assert "mint" in calls[1]          # 교정 프롬프트에 위반 재료 명시
    assert copy.cta_title == "지금 맛보세요"


def test_generate_detail_copy_without_core_ingredients_skips_gate():
    """core 미제공이면 재료 검증 불가 → 관대 통과(D4b 동일)."""
    bad = dict(_FIXTURE, claimed_ingredients=["mint"])
    with patch.object(gpt_service, "_chat_json", return_value=bad) as mocked:
        gpt_service.generate_detail_copy("딸기 에이드", "strawberry ade", "drink", "한 잔")
    mocked.assert_called_once()


def test_generate_detail_copy_missing_required_field_raises():
    broken = dict(_FIXTURE, story_body="")
    with patch.object(gpt_service, "_chat_json", return_value=broken):
        with pytest.raises(RuntimeError, match="필드 누락"):
            gpt_service.generate_detail_copy("딸기 에이드", "strawberry ade", "drink", "한 잔")


# --- detail_copy_for (commercial_copy) ---------------------------------------

def _hero(**kw):
    defaults = dict(product_name="딸기 에이드", headline="달콤한 한 잔",
                    subcopy="수제 청의 상큼함", domain="drink",
                    subject_en="strawberry ade", style="pop")
    defaults.update(kw)
    return hero_from_existing("x.png", **defaults)


def test_detail_copy_for_maps_gpt_result_and_caches():
    commercial_copy._detail_copy.cache_clear()
    with patch.object(gpt_service, "generate_detail_copy",
                      return_value=_fixture_detail_copy()) as mocked:
        copy = detail_copy_for(_hero())
        detail_copy_for(_hero())
    mocked.assert_called_once()          # 같은 (상품, 스타일) 캐싱 — GPT 1회
    assert copy.product_name == "딸기 에이드"
    assert copy.intro_headline == "오늘의 상큼함을 담다"
    assert copy.benefit_bullets == ("수제 딸기청", "당일 제조", "생과육 가득")


def test_detail_copy_for_cache_varies_by_style():
    commercial_copy._detail_copy.cache_clear()
    with patch.object(gpt_service, "generate_detail_copy",
                      return_value=_fixture_detail_copy()) as mocked:
        detail_copy_for(_hero(style="pop"))
        detail_copy_for(_hero(style="editorial"))
    assert mocked.call_count == 2        # 스타일이 다르면 톤이 달라 재생성


def test_detail_copy_for_falls_back_to_legacy_composition():
    """GPT 실패 시 종전 렌더와 동일한 문구 구성 — 화면 회귀 없음(D2 폴백 강등 확인)."""
    commercial_copy._detail_copy.cache_clear()
    with patch.object(gpt_service, "generate_detail_copy", side_effect=RuntimeError("boom")):
        copy = detail_copy_for(_hero())
    assert copy.intro_headline == "달콤한 한 잔"        # 기존 headline 재사용
    assert copy.story_body == "수제 청의 상큼함"        # 기존 subcopy
    assert copy.benefit_bullets == ()                   # 혜택 섹션 생략
    assert copy.top_view_label == "위에서 만나는 한 잔"  # ROUTING-001 도메인 폴백
    assert copy.closeup_caption == "가까이 볼수록 선명하게"  # 종전 하드코딩과 동일 문구
    assert copy.profile_title == "한 잔의\n디테일"
    assert copy.cta_title == "지금 만나보세요" and copy.cta_label == "자세히 보기"


def test_detail_copy_passes_core_ingredients_to_gate():
    commercial_copy._detail_copy.cache_clear()
    hero = _hero(core_ingredients=("strawberry", "sparkling water"))
    with patch.object(gpt_service, "generate_detail_copy",
                      return_value=_fixture_detail_copy()) as mocked:
        detail_copy_for(hero)
    assert mocked.call_args.kwargs["core_ingredients"] == ["strawberry", "sparkling water"]


# --- detail_page 조판 (골든 픽스처 렌더) ---------------------------------------

def _cut_paths(tmp_path, count=5):
    result = []
    for i in range(count):
        path = tmp_path / f"cut_{i}.png"
        image = Image.new("RGB", (800, 900), (235, 235, 235))
        draw = ImageDraw.Draw(image)
        draw.ellipse((40 + i * 120, 80 + i * 90, 220 + i * 120, 300 + i * 90), fill=(60 + i * 25, 90, 120))
        draw.rectangle((i * 70, 650 - i * 80, 260 + i * 70, 780 - i * 80), fill=(120, 60 + i * 20, 80))
        image.save(path)
        result.append(str(path))
    return result


def _render_detail(tmp_path, hero_kw=None):
    paths = _cut_paths(tmp_path)
    cuts = tuple(DetailCut(path, role) for path, role in zip(paths, DetailCutRole))
    hero = hero_from_existing(paths[0], detail_cuts=cuts,
                              **(hero_kw or dict(product_name="딸기 에이드",
                                                 headline="달콤한 한 잔", domain="drink",
                                                 subject_en="strawberry ade", style="pop")))
    return generate_v5(paths[0], "딸기 에이드", purpose=AdPurpose.DETAIL_PAGE,
                       hero_asset=hero, output_dir=str(tmp_path / "out"))


def test_detail_page_renders_with_section_copy_and_benefits(tmp_path):
    commercial_copy._detail_copy.cache_clear()
    with patch.object(gpt_service, "generate_detail_copy",
                      return_value=_fixture_detail_copy()):
        result = _render_detail(tmp_path)
    with_benefits = Image.open(result.outputs[0])

    commercial_copy._detail_copy.cache_clear()
    with patch.object(gpt_service, "generate_detail_copy", side_effect=RuntimeError("boom")):
        result_fb = _render_detail(tmp_path)
    fallback = Image.open(result_fb.outputs[0])

    assert with_benefits.width == 860 and fallback.width == 860
    # 혜택 불릿 3개 = 섹션 96+3*72+48 만큼 폴백(섹션 생략)보다 길어야 한다 (D5 가변 확인).
    assert with_benefits.height >= fallback.height + 300
    assert fallback.height >= 4000        # 폴백도 종전 규격 유지


def test_palette_follows_style_ledger():
    """D4: 스타일이 다르면 상세페이지 팔레트도 달라진다 (styles/specs.yaml accent 연동)."""
    pop, editorial = detail_page._palette("pop"), detail_page._palette("editorial")
    assert pop["accent"] != editorial["accent"]
    unknown = detail_page._palette("no-such-style")
    assert unknown["accent"] == editorial["accent"]   # 미지 키는 editorial 폴백
