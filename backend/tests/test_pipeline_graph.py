"""v6 T2 회귀 — 담당: 한의정. API 편집 예산가드·지시문 빌더·그래프 라우팅/폴백 검증(네트워크 0)."""
from __future__ import annotations

import pytest
from PIL import Image

from app.services import api_image_service, pipeline_graph


@pytest.fixture(autouse=True)
def _reset_budget(monkeypatch):
    """세션 지출 누적을 테스트 간 격리."""
    monkeypatch.setattr(api_image_service, "_session_spend_usd", 0.0)


def _img(tmp_path, size=64, name="x.png"):
    p = tmp_path / name
    Image.new("RGB", (size, size), (180, 60, 60)).save(p)
    return str(p)


# --- 예산 하드스톱 -----------------------------------------------------------------
def test_budget_blocks_before_network(tmp_path, monkeypatch):
    monkeypatch.setenv("API_BUDGET_USD", "0.001")

    def _no_client():
        raise AssertionError("예산 초과인데 클라이언트 생성됨 — 네트워크 호출 전 차단 실패")

    from app.services import gpt_service
    monkeypatch.setattr(gpt_service, "_get_client", _no_client)
    with pytest.raises(api_image_service.ApiBudgetExceeded):
        api_image_service.edit_image(_img(tmp_path), "restage")


def test_budget_accumulates(monkeypatch):
    monkeypatch.setenv("API_BUDGET_USD", "0.03")
    api_image_service._reserve_budget(0.015)
    api_image_service._reserve_budget(0.014)
    with pytest.raises(api_image_service.ApiBudgetExceeded):
        api_image_service._reserve_budget(0.015)


# --- 업로드 다운스케일 (입력 토큰 절감 — 2026-07-17 실측 근거) ------------------------
def test_downscale_large_source(tmp_path):
    big = _img(tmp_path, size=2400, name="big.png")
    out = api_image_service._downscale_for_upload(big)
    assert out != big
    with Image.open(out) as im:
        assert max(im.size) <= 1024


def test_downscale_small_source_untouched(tmp_path):
    small = _img(tmp_path, size=500, name="small.png")
    assert api_image_service._downscale_for_upload(small) == small


# --- edit 지시문 빌더 (정직성 경계 계승) ---------------------------------------------
def test_edit_instruction_food_with_parts():
    text = api_image_service.build_edit_instruction(
        "cafe latte", style_hint="warm cafe scene",
        identity_parts=["coffee", "latte art"], flexible_parts=["cup"])
    assert "cafe latte" in text and "coffee, latte art" in text
    assert "You may restyle cup" in text
    assert "Do not add any ingredient" in text          # 외래 소품 차단
    assert "Do not render any text" in text             # 타이포는 코드 담당(함정 3)


def test_edit_instruction_object_locks_shape():
    text = api_image_service.build_edit_instruction(
        "wireless mouse", is_object=True, flexible_parts=["pad"])
    assert "retail product (SKU)" in text
    assert "You may restyle" not in text                # 사물은 flexible 무시(전체 보존)


# --- 원장 자동 합류 (G2 실측에서 발견: run 핸들 없는 호출부의 비용 누락) ----------------
def test_edit_records_cost_via_current_run(tmp_path, monkeypatch):
    import base64
    import io
    import json as _json
    from types import SimpleNamespace

    from app.harness.run_logger import RunLogger

    monkeypatch.setenv("API_BUDGET_USD", "1.0")
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 10, 10)).save(buf, "PNG")
    fake_resp = SimpleNamespace(data=[SimpleNamespace(
        b64_json=base64.b64encode(buf.getvalue()).decode())])
    fake_client = SimpleNamespace(images=SimpleNamespace(edit=lambda **kw: fake_resp))

    from app.services import gpt_service
    monkeypatch.setattr(gpt_service, "_get_client", lambda: fake_client)

    runs_path = tmp_path / "runs.jsonl"
    with RunLogger(phase="TEST", mode="C", engine="graph:api", input="x.png",
                   runs_path=runs_path, auto_llm=False):
        out = api_image_service.edit_image(_img(tmp_path), "restage",
                                           out_dir=str(tmp_path / "out"))
    assert out.endswith(".png")
    row = _json.loads(runs_path.read_text().strip().splitlines()[-1])
    assert row["image_api"][0]["model"] == api_image_service.DEFAULT_MODEL
    assert row["kpi"]["cost"]["image_api_usd"] > 0     # run 인자 없이도 원장 합류


# --- 그래프 라우팅·폴백 ---------------------------------------------------------------
@pytest.fixture()
def _stub_nodes(monkeypatch, tmp_path):
    """분석·생성·게이트를 스텁으로 치환 — 라우팅 로직만 검증."""
    calls = {"api": 0, "local": 0}
    out = _img(tmp_path, name="gen.png")

    monkeypatch.setattr(pipeline_graph, "_do_analyze", lambda s: s)

    def _gen_api(state):
        calls["api"] += 1
        return out

    def _gen_local(state):
        calls["local"] += 1
        return out

    monkeypatch.setattr(pipeline_graph, "_do_generate_api", _gen_api)
    monkeypatch.setattr(pipeline_graph, "_do_generate_local", _gen_local)
    return calls


def _seq(state):
    return pipeline_graph._run_sequential(dict(state))


def test_policy_api_routes_api(_stub_nodes):
    final = _seq({"image_path": "x", "name": "n", "policy": "api",
                  "domain": "food", "attempts": 0})
    assert final["engine"] == "api" and _stub_nodes == {"api": 1, "local": 0}
    assert final["gate_passed"] is True and final["attempts"] == 1


def test_hybrid_object_goes_api(_stub_nodes):
    final = _seq({"image_path": "x", "name": "n", "policy": "hybrid",
                  "domain": "object", "texture_hero": False, "attempts": 0})
    assert final["engine"] == "api"


def test_hybrid_plain_food_goes_local(_stub_nodes):
    final = _seq({"image_path": "x", "name": "n", "policy": "hybrid",
                  "domain": "food", "texture_hero": False, "attempts": 0})
    assert final["engine"] == "local" and _stub_nodes == {"api": 0, "local": 1}


def test_gate_fail_hybrid_crosses_engine(monkeypatch, _stub_nodes):
    """hybrid: 1차 실패 → 반대 엔진 1회 교차 폴백, 추가 생성 ≤1 (총 attempts 2 상한)."""
    verdicts = iter([False, False])  # 둘 다 실패해도 2회에서 멈춰야 함
    monkeypatch.setattr(pipeline_graph, "_gate",
                        lambda s: {**s, "gate_passed": next(verdicts, False)})
    final = _seq({"image_path": "x", "name": "n", "policy": "hybrid",
                  "domain": "food", "texture_hero": False, "attempts": 0})
    assert final["attempts"] == 2
    assert _stub_nodes == {"api": 1, "local": 1}         # local → api 교차 1회


def test_gate_fail_pure_policy_stays_same_engine(monkeypatch, _stub_nodes):
    """단일 정책(api)은 폴백도 같은 엔진 — 3암 A/B 암 순수성(타 엔진 혼입 금지)."""
    verdicts = iter([False, True])
    monkeypatch.setattr(pipeline_graph, "_gate",
                        lambda s: {**s, "gate_passed": next(verdicts, False)})
    final = _seq({"image_path": "x", "name": "n", "policy": "api",
                  "domain": "food", "attempts": 0})
    assert final["attempts"] == 2
    assert _stub_nodes == {"api": 2, "local": 0}


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("USE_PIPELINE_GRAPH", raising=False)
    assert pipeline_graph.enabled() is False
    monkeypatch.setenv("ENGINE_POLICY", "nonsense")
    assert pipeline_graph.engine_policy() == "local"     # 미지값 안전 폴백
