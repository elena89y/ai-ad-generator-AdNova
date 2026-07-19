from app.services.pipeline_v5.commercial_copy import copy_for
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
