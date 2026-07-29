"""T4 템플릿 프리셋 원장·로더 검증 — 담당: 한의정.

원장(templates.yaml)의 데이터 오타(스타일 키·포맷·knob 상한)를 커밋 전에 잡는 게 목적.
포맷 키는 하드코딩 목록이 아니라 pipeline_v5/formats/ 디렉터리와 대조한다(드리프트 방지).
"""
from pathlib import Path

import pytest

from app.services import template_service
from app.services.style_specs import STYLE_SPECS


def test_load_all_and_ids_unique():
    presets = template_service.load_templates()
    assert len(presets) >= 6
    assert all(p.id == tid for tid, p in presets.items())


def test_styles_resolve_and_palette_derived():
    for p in template_service.load_templates().values():
        assert p.style in STYLE_SPECS
        assert p.palette == STYLE_SPECS[p.style].palette  # 파생값 정합


def test_known_formats_match_pipeline_v5_dir():
    formats_dir = Path(template_service.__file__).parent / "pipeline_v5" / "formats"
    on_disk = {f.stem for f in formats_dir.glob("*.py") if f.stem != "__init__"}
    assert template_service.KNOWN_FORMATS == on_disk


def test_knob_within_honesty_cap():
    for p in template_service.load_templates().values():
        if p.knob is not None:
            assert 0.0 < p.knob <= 0.65  # 허위광고 방지 상한 — 템플릿도 예외 없음


def test_list_filter_by_target():
    drink = template_service.list_templates(target="drink")
    assert drink and all(t["target"] in ("drink", "any") for t in drink)
    assert {t["target"] for t in template_service.list_templates()} >= {"any"}


def test_get_template_unknown_raises():
    with pytest.raises(KeyError):
        template_service.get_template("no_such_template")
