"""v4.1 P4C-1 장면 플랜·파일럿 빌더 회귀 테스트 — 담당: 한의정."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.services import scene_plans
from app.services.scene_plans import PLANS, build_bg_prompt, get_plan, map_props
from scripts import v4_build_scene_library as scene_builder


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
        assert p.view_angle in ("eye", "high", "top")
        assert p.view_angle == "eye"
        assert 0.0 <= p.shadow_strength <= 1.0
        assert 0.0 <= p.reflection_strength <= 1.0

    reflected = {p.key for p in PLANS if p.reflection_strength > 0}
    assert reflected == {
        "pastel/drink/dreamy_cloud",
        "monotone/drink/dark_mono",
        "monotone/object/dark_mono",
    }


def test_rotation_and_recompose_filter():
    a = get_plan("pop", "drink", seed=0)
    b = get_plan("pop", "drink", seed=1)
    assert a and b and a.key != b.key  # 아키타입 로테이션(결정 D-2)
    # 재연출 전용 플랜은 기본 선택에서 제외(결정 D-4)
    for seed in range(10):
        p = get_plan("pastel", "drink", seed=seed, allow_recompose=False)
        assert p and not p.requires_recompose


def test_map_props_honesty_boundary():
    assert map_props(["coffee", "milk"], []) == {"beans", "splash"}
    assert map_props(["orange"], ["steam"]) == {"orange", "steam"}
    assert map_props(["strawberry"], []) == {"strawberry"}
    assert map_props(["berry"], []) == {"strawberry"}
    assert map_props(["citrus"], []) == set()
    assert map_props(["mint"], []) == set()
    assert map_props(["orange zest"], []) == set()
    assert map_props(None, []) == set()          # 매핑 불가 → 소품 없는 판
    assert map_props(["truffle"], []) == set()   # 미등록 재료는 소품 금지


def test_pilot_contract_is_exactly_24_prop_free_images():
    jobs, seeds = scene_builder._build_jobs("ignored", candidates=6, pilot=True)
    assert len(jobs) == 8
    assert seeds == (11, 23, 37)
    assert len(jobs) * len(seeds) == 24
    assert {p.style for p, _ in jobs} == {"pop", "warm_vintage"}
    assert {p.domain for p, _ in jobs} == {"drink", "object"}
    assert tuple(p.key for p, _ in jobs) == scene_builder.PILOT_PLAN_KEYS
    assert all(props == () for _, props in jobs)


def test_generate_retries_once_then_reports_failure():
    calls = 0

    def fail():
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    image, retries, error = scene_builder._generate_with_retry(fail)
    assert image is None
    assert retries == 1
    assert error == "boom"
    assert calls == 2


def test_sdxl_loader_pins_fp16_local_cache(monkeypatch):
    captured = {}

    class FakePipeline:
        @classmethod
        def from_pretrained(cls, repo, **kwargs):
            captured.update(repo=repo, kwargs=kwargs)
            return cls()

        def to(self, device):
            captured["device"] = device
            return self

    monkeypatch.setitem(
        sys.modules,
        "diffusers",
        SimpleNamespace(StableDiffusionXLPipeline=FakePipeline),
    )

    pipe = scene_builder._load_sdxl_pipeline(SimpleNamespace(float16="float16"))

    assert isinstance(pipe, FakePipeline)
    assert captured["repo"] == scene_builder.SDXL_REPO
    assert captured["kwargs"] == {
        "torch_dtype": "float16",
        "use_safetensors": True,
        "variant": "fp16",
        "local_files_only": True,
    }
    assert captured["device"] == "cuda"


def test_pilot_existing_candidates_require_fresh_outdir(tmp_path):
    jobs, seeds = scene_builder._build_jobs("ignored", candidates=6, pilot=True)
    cand_dir = tmp_path / "candidates"
    cand_dir.mkdir()
    first_plan, first_props = jobs[0]
    first_name = scene_builder._candidate_name(first_plan, first_props, seeds[0])
    (cand_dir / first_name).write_bytes(b"stale")

    assert scene_builder._existing_pilot_candidates(cand_dir, jobs, seeds) == [first_name]


def test_pilot_build_stops_before_model_load_when_outdir_is_stale(tmp_path, monkeypatch):
    jobs, seeds = scene_builder._build_jobs("ignored", candidates=6, pilot=True)
    cand_dir = tmp_path / "candidates"
    cand_dir.mkdir()
    plan, props = jobs[0]
    (cand_dir / scene_builder._candidate_name(plan, props, seeds[0])).write_bytes(b"stale")
    monkeypatch.setattr(scene_builder, "_guard_vram", lambda: None)
    monkeypatch.setattr(
        scene_builder,
        "_load_sdxl_pipeline",
        lambda _torch: (_ for _ in ()).throw(AssertionError("model must not load")),
    )
    args = SimpleNamespace(
        outdir=str(tmp_path), plans="ignored", candidates=6, pilot=True, steps=28,
    )

    with pytest.raises(SystemExit, match="비어 있는 새 --outdir"):
        scene_builder.cmd_build(args)


def test_finalize_plan_key_requires_exact_registered_prefix():
    name = "warm_vintage_drink_linen_organic__none__s11.png"
    assert scene_builder._plan_key_from_candidate(name) == "warm_vintage/drink/linen_organic"
    with pytest.raises(ValueError, match="등록되지 않은"):
        scene_builder._plan_key_from_candidate("warm_drink_linen__none__s11.png")
