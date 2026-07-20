from unittest.mock import patch

from app.services import gpt_service
from app.services.pipeline_v5 import commercial_copy
from app.services.pipeline_v5.commercial_copy import copy_for, section_copy_for
from app.services.pipeline_v5.hero import hero_from_existing


def test_copy_uses_only_supplied_commercial_fields():
    hero = hero_from_existing("x.png", product_name=" 시그니처  라떼 ", headline=" 오늘을 부드럽게 ")
    copy = copy_for(hero)
    assert copy.product_name == "시그니처 라떼"
    assert copy.headline == "오늘을 부드럽게"
    assert copy.brand_name == "" and copy.campaign_label == ""


def test_product_name_is_safe_headline_fallback():
    hero = hero_from_existing("x.png", product_name="카페라떼")
    assert copy_for(hero).headline == "카페라떼"


def test_copy_for_never_calls_gpt():
    """배너 등 섹션 라벨이 필요 없는 경로는 GPT 호출 없이 항상 빈 라벨."""
    hero = hero_from_existing("x.png", product_name="카페라떼", domain="drink")
    with patch.object(gpt_service, "generate_section_labels") as mocked:
        copy = copy_for(hero)
    mocked.assert_not_called()
    assert copy.top_view_label == "" and copy.detail_title == ""


def test_section_copy_uses_gpt_result_when_available():
    commercial_copy._section_labels.cache_clear()
    hero = hero_from_existing("x.png", product_name="햄치즈 샌드위치", headline="담백한 한 입",
                              domain="food", subject_en="ham and cheese sandwich")
    fake = gpt_service.SectionLabels(top_view_label="위에서 본 한 입", detail_title="속까지\n꽉 찬")
    with patch.object(gpt_service, "generate_section_labels", return_value=fake) as mocked:
        copy = section_copy_for(hero)
    mocked.assert_called_once()
    assert copy.top_view_label == "위에서 본 한 입"
    assert copy.detail_title == "속까지\n꽉 찬"


def test_section_copy_falls_back_to_domain_label_on_gpt_failure():
    commercial_copy._section_labels.cache_clear()
    hero = hero_from_existing("x.png", product_name="유니크 향수", headline="은은한 향",
                              domain="object", subject_en="perfume bottle")
    with patch.object(gpt_service, "generate_section_labels", side_effect=RuntimeError("boom")):
        copy = section_copy_for(hero)
    assert copy.top_view_label == "위에서 보는 디테일"
    assert copy.detail_title == "디테일까지\n또렷하게"


def test_section_copy_caches_by_product_so_repeat_calls_dont_hit_gpt_again():
    commercial_copy._section_labels.cache_clear()
    hero = hero_from_existing("x.png", product_name="아이스 아메리카노", headline="시원한 한 모금",
                              domain="drink", subject_en="iced americano")
    fake = gpt_service.SectionLabels(top_view_label="위에서 본 얼음", detail_title="한 잔의\n청량함")
    with patch.object(gpt_service, "generate_section_labels", return_value=fake) as mocked:
        section_copy_for(hero)
        section_copy_for(hero)
    mocked.assert_called_once()
