"""v4 P4-1 장면 플랜 회귀 테스트 — 담당: 한의정."""
from __future__ import annotations

from app.services import scene_plans
from app.services.scene_plans import PLANS, build_bg_prompt, get_plan, map_props


def test_plan_keys_unique_and_complete():
    keys = [p.key for p in PLANS]
    assert len(keys) == len(set(keys))
    # 6무드 × 2도메인 모두 비-재연출 플랜이 1개 이상 (합성 경로 폴백 없는 구멍 방지)
    for style in ("pop", "editorial", "realism", "pastel", "monotone", "warm_vintage"):
        for domain in ("drink", "object"):
            assert scene_plans.plans_for(style, domain), f"{style}/{domain} 플랜 없음"


def test_bg_prompt_within_clip_budget_and_rules():
    for p in PLANS:
        for props in ((), tuple(p.prop_slots)):
            prompt = build_bg_prompt(p, props)
            assert len(prompt.split()) <= 60, f"{p.key} 프롬프트 60단어 초과"
            assert "no product" in prompt and "no text" in prompt
            assert f"{p.light_dir}-side" in prompt  # light_dir 단일 출처 보장
            assert not any(ord(c) > 0x2E7F for c in prompt), "프롬프트에 비ASCII(한글) 금지"


def test_geometry_ranges():
    for p in PLANS:
        assert 0.2 <= p.subject_scale <= 0.6
        assert 0.4 <= p.surface_y <= 0.9
        assert 0.0 < p.subject_pos[0] < 1.0 and 0.0 < p.subject_pos[1] < 1.0
        assert p.light_dir in ("left", "right")


def test_rotation_and_recompose_filter():
    a = get_plan("pop", "drink", seed=0)
    b = get_plan("pop", "drink", seed=1)
    assert a and b and a.key != b.key  # 아키타입 로테이션(결정 D-2)
    # 재연출 전용 플랜은 기본 선택에서 제외(결정 D-4)
    for seed in range(10):
        p = get_plan("pastel", "drink", seed=seed, allow_recompose=False)
        assert p and not p.requires_recompose


def test_map_props_honesty_boundary():
    assert map_props(["coffee beans", "milk"], []) == {"beans", "splash"}
    assert map_props(["orange zest"], ["steam"]) == {"fruit", "steam"}
    assert map_props(None, []) == set()          # 매핑 불가 → 소품 없는 판
    assert map_props(["truffle"], []) == set()   # 미등록 재료는 소품 금지
