"""generate_platform_copy 의 플랫폼별 해시태그 하드 상한 검증.

공유 파이프라인(export_service)의 백엔드 태그 생성이 제거되면서(07-24) 태그 개수 보장이
카피 생성 쪽으로 이관됐다. 특히 X는 280자 규격상 최대 15개 — 모델이 과다 반환해도 잘려야 한다.
관련: [[sns-share-tags-mismatch]]
"""
from app.schemas.ads import ProductInfo, StylePreset
from app.services import gpt_service


def _fake_result(n: int) -> dict:
    block = {"headline": "h", "body": "b", "hashtags": [f"#t{i}" for i in range(n)]}
    return {
        "claimed_ingredients": [],
        "instagram": dict(block),
        "facebook": dict(block),
        "x": dict(block),
        "threads": dict(block),
    }


def test_platform_copy_caps_hashtags_per_platform(monkeypatch):
    # 모델이 40개를 반환해도 플랫폼별 상한으로 잘린다(X=15, 그 외=30).
    monkeypatch.setattr(gpt_service, "_chat_json", lambda *a, **k: _fake_result(40))

    out = gpt_service.generate_platform_copy(
        ProductInfo(name="테스트상품", description="설명"),
        StylePreset.MONOTONE,
    )

    assert len(out["x"]["hashtags"]) == 15
    assert len(out["instagram"]["hashtags"]) == 30
    assert len(out["facebook"]["hashtags"]) == 30
    assert len(out["threads"]["hashtags"]) == 30


def test_platform_copy_keeps_hashtags_under_cap(monkeypatch):
    # 상한 이하이면 그대로 보존(순서 유지).
    monkeypatch.setattr(gpt_service, "_chat_json", lambda *a, **k: _fake_result(3))

    out = gpt_service.generate_platform_copy(
        ProductInfo(name="p"),
        StylePreset.POP,
    )

    assert out["x"]["hashtags"] == ["#t0", "#t1", "#t2"]
    assert out["instagram"]["hashtags"] == ["#t0", "#t1", "#t2"]
