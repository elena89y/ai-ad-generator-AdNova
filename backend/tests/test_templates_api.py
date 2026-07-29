"""v6 T4 회귀 — 담당: 한의정. 템플릿 목록/썸네일 엔드포인트 + 와이어 프리셋 매핑 검증."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.ads import get_template_thumbnail, list_ad_templates
from app.core.config import settings
from app.schemas.ads import StylePreset
from app.services import template_service


def test_wire_presets_are_valid_enum_values():
    """WIRE_PRESET 값은 전부 /ads/generate 가 받는 StylePreset 이어야 한다(드리프트 가드)."""
    for spec_key, wire in template_service.WIRE_PRESET.items():
        StylePreset(wire)
    for preset in template_service.load_templates().values():
        assert preset.style in template_service.WIRE_PRESET


def test_list_endpoint_serializes_thumb_url_and_wire_preset():
    items = list_ad_templates(target=None, current_user=None)
    assert len(items) == 6
    for item in items:
        StylePreset(item["style_preset"])
        assert item["thumbnail"] == (
            f"{settings.API_PREFIX}/ads/template-thumb/{item['id']}")
        assert item["palette"] and item["title"]


def test_list_endpoint_target_filter():
    foods = list_ad_templates(target="food", current_user=None)
    assert foods and all(t["target"] in ("food", "any") for t in foods)
    objects = list_ad_templates(target="object", current_user=None)
    assert any(t["id"] == "object_studio_sku" for t in objects)


def test_thumbnail_endpoint_serves_generated_png():
    resp = get_template_thumbnail("pop_vivid_promo", current_user=None)
    assert str(resp.path).endswith("assets/templates/pop_vivid_promo.png")
    assert resp.media_type == "image/png"


def test_thumbnail_endpoint_unknown_id_404():
    with pytest.raises(HTTPException) as exc:
        get_template_thumbnail("no_such_template", current_user=None)
    assert exc.value.status_code == 404
