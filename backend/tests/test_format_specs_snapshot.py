"""L1 게이트: 포맷 규격 데이터화 스냅샷 — 담당: 한의정. (DIRECTION_v6-1 L1)

format_specs.yaml 로드 결과가 데이터화 이전 하드코딩 값과 동일해야 통과.
규격을 의도적으로 바꾸는 실험이면 아래 _EXPECTED 를 같은 커밋에서 갱신할 것.
"""
from __future__ import annotations

from app.schemas.ads import AdPurpose
from app.services.pipeline_v5.format_spec import primary_spec, specs_for

# (canvas, label, hero_fit, copy_density, safe_margin) — 데이터화 전 하드코딩 값 고정.
_EXPECTED = {
    "sns": [((1080, 1080), "square", "cover", "medium", 0.06)],
    "banner": [
        ((1080, 1080), "commerce_square", "cover", "minimal", 0.05),
        ((1920, 600), "commerce_wide", "cover", "minimal", 0.05),
        ((860, 860), "smartstore_detail", "cover", "minimal", 0.05),
        ((1080, 1350), "commerce_vertical", "cover", "minimal", 0.06),
    ],
    "card_news": [((1080, 1350), "cover", "cover", "medium", 0.07)],
    "flyer": [((2480, 3508), "A4", "contain", "dense", 0.08)],
    "detail_page": [((860, 2600), "smartstore", "reflow", "dense", 0.06)],
}


def _tuple(spec):
    return (spec.canvas, spec.label, spec.hero_fit, spec.copy_density, spec.safe_margin)


def test_format_specs_yaml_matches_baseline():
    for pkey, expected in _EXPECTED.items():
        got = [_tuple(s) for s in specs_for(AdPurpose(pkey))]
        assert got == expected, f"{pkey} 규격 변경 감지: {got}"


def test_all_purposes_covered_and_primary_first():
    for p in AdPurpose:
        specs = specs_for(p)
        assert specs, f"{p.value} 규격 없음"
        assert primary_spec(p) is specs[0]


def test_specs_are_immutable():
    """FormatSpec 은 frozen — 규격을 런타임에 못 바꾼다(원장이 단일 진실)."""
    import dataclasses
    import pytest
    spec = primary_spec(AdPurpose.BANNER)
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.label = "hacked"  # type: ignore[misc]
