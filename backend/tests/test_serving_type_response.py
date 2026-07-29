"""SRV-ROUTE-001 phase2 — serving_type 응답 노출 체인 (ProcessedAd→GenerationOutput→응답).

계약: 전 구간 optional(default None) — 구 생산자(run_generation·template)·구 히스토리 무해.
모놀리식(api/ads)·원격(generation_app) 두 응답 빌더 모두 필드 포함.
"""
from app.api import ads as ads_api
from app.schemas.ads import AdPurpose, GenerateAdResponse, StylePreset
from app.services import generation_service


def _output(**over):
    base = dict(
        final_image_path="/tmp/x/final_abc.png", asset_id="a" * 12, seed=42,
        style=StylePreset.EDITORIAL, copy_text="헤드\n서브", platform_copies={},
        poster=False, generate_seconds=1.0, harmonize_seconds=0.0,
    )
    base.update(over)
    return generation_service.GenerationOutput(**base)


def test_generation_output_default_none():
    """legacy 생산자(run_generation·template_generation)는 무수정으로 유효해야 한다."""
    assert _output().serving_type is None


def test_processed_ad_carries_serving_type():
    r = generation_service.ProcessedAd(
        final_image_path="/tmp/x.png", domain="food", engine="style:pop",
        subject_en="cake", copy_text="a\nb", poster=False, seconds=1.0, seed=1,
        serving_type="dessert",
    )
    assert r.serving_type == "dessert"


def test_monolith_to_response_includes_field():
    resp = ads_api._to_response(_output(serving_type="dessert"))
    assert resp.serving_type == "dessert"
    assert ads_api._to_response(_output()).serving_type is None


def test_remote_to_response_includes_field():
    """원격(GPU 서비스) 빌더 — 이게 없으면 원격 배포는 상시 null(감사 리스크)."""
    from app import generation_app
    resp = generation_app._to_response(_output(serving_type="bakery"))
    assert resp.serving_type == "bakery"


def test_schema_optional_for_old_payloads():
    """구 히스토리 JSON(serving_type 키 없음) 역직렬화 호환."""
    resp = GenerateAdResponse(
        asset_id="a" * 12, seed=1, style=StylePreset.EDITORIAL, copy_text="a\nb",
        image_url="/api/ads/image/x.png", poster=False,
        generate_seconds=1.0, harmonize_seconds=0.0, purpose=AdPurpose.SNS,
    )
    assert resp.serving_type is None
