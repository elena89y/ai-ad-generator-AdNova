"""기능 1(브리프 → 멀티포맷, pipeline_brief 패키지) CPU 검증 — 담당: 한의정.

GPU·OpenAI 실호출 없음: expand_brief 는 _chat_json mock, 배경 생성은 로컬 고정 이미지 주입.
검증 축: (1) 규정 게이트 순수 로직 (2) 정보줄 원문 무결성 (3) 브리프 히어로 조립
(4) 정보줄 포함 멀티포맷 조판이 규격대로 렌더 (5) 폴백(함정 #6) (6) 모듈 탈부착 계약.
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from app.schemas.ads import AdPurpose
from app.services import gpt_service, pipeline_brief
from app.services.pipeline_brief import background, compliance, plan as plan_mod
from app.services.pipeline_v5 import generate_v5
from app.services.pipeline_v5.format_spec import specs_for
from app.services.pipeline_v5.hero import hero_from_existing


# --- 규정 게이트 (순수 함수) ---------------------------------------------------
def test_gate_flags_banned_terms_but_does_not_block():
    r = compliance.gate("국내 최초 100% 완벽 축제", "무조건 오세요",
                        ["4/5~4/7", "○○공원"], "event")
    assert not r.ok
    assert any("과장·허위" in v for v in r.violations)
    # 게이트는 차단이 아니라 보조 체크리스트 — 정보줄은 그대로 통과한다.
    assert r.info_lines == ("4/5~4/7", "○○공원")


def test_gate_passes_clean_copy():
    r = compliance.gate("봄, 벚꽃 아래에서", "온 가족이 즐기는 축제",
                        ["문의 02-123-4567"], "event")
    assert r.ok
    assert r.violations == ()


def test_info_integrity_preserves_verbatim_order_and_dedups():
    lines = ["  4/5~4/7  ", "○○공원", "", "○○공원", "문의 02-123-4567"]
    assert compliance.enforce_info_integrity(lines) == (
        "4/5~4/7", "○○공원", "문의 02-123-4567")


def test_unknown_vertical_falls_back_to_event():
    assert compliance.get_rule("nonexistent").key == "event"


# --- expand_brief (OpenAI mock — 호출은 gpt_service 단일 창구 경유) -------------
_PLAN_JSON = {
    "scene_en": "soft cherry blossom park at golden hour, no text",
    "headline_ko": "봄, 벚꽃 아래에서",
    "subcopy_ko": "온 가족이 즐기는 봄맞이 축제",
    "info_lines": ["4/5~4/7", "○○공원", "문의 02-123-4567"],
    "palette_hint": "soft spring pink and cream",
}


def test_expand_brief_parses_plan():
    with patch.object(gpt_service, "_chat_json", return_value=dict(_PLAN_JSON)):
        plan = plan_mod.expand_brief("○○구 벚꽃축제 4/5~4/7 ○○공원", "event")
    assert plan.scene_en.startswith("soft cherry blossom")
    assert plan.headline_ko == "봄, 벚꽃 아래에서"
    assert plan.info_lines == ["4/5~4/7", "○○공원", "문의 02-123-4567"]


def test_expand_brief_falls_back_on_api_failure():
    """함정 #6: 응답 형태 변동·API 실패에도 크래시 없이 폴백 — 정보는 지어내지 않는다."""
    with patch.object(gpt_service, "_chat_json", side_effect=RuntimeError("boom")):
        plan = plan_mod.expand_brief("여름 세일 안내", "event")
    assert plan.headline_ko == "여름 세일 안내"
    assert plan.info_lines == []           # 창작 금지 — 실패 시 빈 정보줄
    assert "no text" in plan.scene_en


# --- 브리프 히어로 조립 (배경 생성 주입) ----------------------------------------
def _fake_bg(tmp_path) -> str:
    src = tmp_path / "bg.png"
    yy, xx = np.mgrid[:1024, :1024]
    px = np.zeros((1024, 1024, 3), dtype=np.uint8)
    px[..., 0] = (xx / 1024 * 120 + 120).astype(np.uint8)
    px[..., 1] = (yy / 1024 * 80 + 140).astype(np.uint8)
    px[..., 2] = 160
    Image.fromarray(px).save(src)
    return str(src)


def test_build_hero_from_brief_wires_copy_info_and_background(tmp_path):
    bg = _fake_bg(tmp_path)
    with patch.object(gpt_service, "_chat_json", return_value=dict(_PLAN_JSON)), \
         patch.object(background, "generate_background", return_value=bg) as gen:
        hero, gate = pipeline_brief.build_hero_from_brief(
            "○○구 벚꽃축제 · 4/5~4/7 · ○○공원", vertical="event", engine="api")
    assert hero.image_path == bg
    assert hero.headline == "봄, 벚꽃 아래에서"
    assert hero.info_lines == ("4/5~4/7", "○○공원", "문의 02-123-4567")
    # 키커 슬롯(product_name)엔 서브카피 — 헤드라인 중복·커머스 placeholder 방지
    assert hero.product_name == "온 가족이 즐기는 봄맞이 축제"
    assert gate.ok
    # 배경 프롬프트는 expand_brief 의 영어 scene 이 그대로 전달된다(한글 오염 금지, 함정 #1)
    assert gen.call_args.args[0].isascii()


# --- 정보줄 포함 멀티포맷 조판 ---------------------------------------------------
def _event_hero(tmp_path):
    return hero_from_existing(
        _fake_bg(tmp_path),
        headline="봄, 벚꽃 아래에서", subcopy="온 가족이 즐기는 봄맞이 축제",
        domain="event",
        info_lines=("4/5~4/7", "○○공원", "문의 02-123-4567"),
        fine_print="※ 주최·주관: ○○구청 문화체육과",
    )


def test_banner_pack_with_info_lines_keeps_registered_sizes(tmp_path):
    result = generate_v5(
        purpose=AdPurpose.BANNER, hero_asset=_event_hero(tmp_path),
        output_dir=str(tmp_path / "out"),
    )
    expected = {spec.canvas for spec in specs_for(AdPurpose.BANNER)}
    actual = {Image.open(p).size for p in result.outputs}
    assert actual == expected


def test_sns_with_info_lines_renders_panel_1080(tmp_path):
    result = generate_v5(
        purpose=AdPurpose.SNS, hero_asset=_event_hero(tmp_path),
        output_dir=str(tmp_path / "out"),
    )
    assert len(result.outputs) == 1
    assert Image.open(result.outputs[0]).size == (1080, 1080)


def test_sns_without_info_lines_keeps_legacy_overlay(tmp_path):
    """상품 경로 회귀 0 — 정보줄 없으면 종전 overlay 조판 그대로."""
    hero = hero_from_existing(
        _fake_bg(tmp_path), headline="카페라떼", subcopy="부드러운 한 잔", domain="cafe")
    result = generate_v5(
        purpose=AdPurpose.SNS, hero_asset=hero, output_dir=str(tmp_path / "out"))
    assert Image.open(result.outputs[0]).size == (1080, 1080)


def test_generate_v5_accepts_hero_only_call(tmp_path):
    """기능 1 계약: image_path 없이 hero_asset 만으로 호출 가능해야 한다."""
    result = generate_v5(
        hero_asset=_event_hero(tmp_path), purpose=AdPurpose.BANNER,
        sizes=["commerce_wide"], output_dir=str(tmp_path / "out"))
    assert Image.open(result.outputs[0]).size == (1920, 600)


# --- run_from_brief 의 purpose별 sizes 교집합 (리뷰 확정 결함 회귀) --------------
def _patched_run(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setattr(gpt_service, "_chat_json", lambda *a, **k: dict(_PLAN_JSON))
    monkeypatch.setattr(background, "generate_background",
                        lambda *a, **k: _fake_bg(tmp_path))
    return pipeline_brief.run_from_brief(
        "○○구 벚꽃축제 · 4/5~4/7 · ○○공원", output_dir=str(tmp_path / "out"), **kwargs)


def test_sizes_filter_applies_per_purpose_without_crashing(tmp_path, monkeypatch):
    """배너 규격 + 기본 purposes[SNS,BANNER] 조합이 SNS 반복에서 ValueError 로 죽지 않는다."""
    res = _patched_run(tmp_path, monkeypatch, sizes=["commerce_wide"])
    # SNS 는 해당 규격 없음 → 건너뜀, BANNER 만 1장.
    assert res.purposes == ["banner"]
    assert len(res.outputs) == 1
    assert Image.open(res.outputs[0]).size == (1920, 600)


def test_sizes_none_renders_full_pack_across_purposes(tmp_path, monkeypatch):
    res = _patched_run(tmp_path, monkeypatch, sizes=None)
    assert res.purposes == ["sns", "banner"]
    assert len(res.outputs) == 5  # SNS 1 + BANNER 4


def test_bogus_size_raises_clear_error(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="사용 가능"):
        _patched_run(tmp_path, monkeypatch, sizes=["print_a4"])


# --- 배경 엔진: 로컬 CLIP 프롬프트 ASCII 정제 (함정 #1, 리뷰 확정 결함) -----------
def test_local_prompt_strips_korean_and_no_text_phrases():
    from app.services.pipeline_brief.background import _local_prompt

    p = _local_prompt("봄 벚꽃 park at golden hour, no text", "soft 핑크 pink")
    assert p.isascii()               # 한글 유입 0 (CLIP 오염 방지)
    assert "no text" not in p.lower()  # 부정문은 negative 담당


def test_brief_engine_env_defaults_to_api(monkeypatch):
    from app.services.pipeline_brief import background as bg

    monkeypatch.delenv("BRIEF_ENGINE", raising=False)
    assert bg._default_engine() == "api"
    monkeypatch.setenv("BRIEF_ENGINE", "hybrid")   # 미지원 값 → api 폴백
    assert bg._default_engine() == "api"
    monkeypatch.setenv("BRIEF_ENGINE", "local")
    assert bg._default_engine() == "local"


def test_compliance_has_no_import_time_coupling_to_copy_graph():
    """제거 가능 모듈 독립: compliance 가 copy_graph 를 최상위 import 하지 않는다."""
    import ast
    from pathlib import Path

    src = Path("app/services/pipeline_brief/compliance.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("copy_graph" in (m or "") for m in imported)


# --- 모듈 탈부착 계약 (제거 가능 설계) ------------------------------------------
def test_flag_disables_pipeline(monkeypatch):
    """USE_BRIEF_PIPELINE=0 → 코드 삭제 없이 진입 차단."""
    monkeypatch.setenv("USE_BRIEF_PIPELINE", "0")
    with pytest.raises(RuntimeError, match="비활성화"):
        pipeline_brief.run_from_brief("아무 브리프")


def test_generation_service_delegate_survives_missing_package(monkeypatch):
    """패키지 제거 시 generation_service 는 명확한 에러만 내고 코어는 무영향(guarded import)."""
    import sys

    import app.services as services_pkg
    from app.services import generation_service

    # 실제 삭제 시뮬레이션: sys.modules 캐시 + 부모 패키지 attribute 둘 다 제거해야
    # `from . import pipeline_brief` 가 fresh import 를 시도하고 ImportError 로 떨어진다.
    monkeypatch.setitem(sys.modules, "app.services.pipeline_brief", None)
    monkeypatch.delattr(services_pkg, "pipeline_brief", raising=False)
    with pytest.raises(RuntimeError, match="미설치"):
        generation_service.run_from_brief("아무 브리프")