"""타이포 OFF/ON API 계약의 로컬·원격 하위호환 회귀."""
from __future__ import annotations

from app.api.ads import _to_response as web_response
from app.generation_app import _to_response as gpu_response
from app.schemas.ads import GenerateAdResponse, StylePreset
from app.services import generation_client, generation_service, image_service


def _output(tmp_path) -> generation_service.GenerationOutput:
    hero = tmp_path / "hero_typography_off.png"
    poster = tmp_path / "hero_typography_on.png"
    hero.write_bytes(b"off")
    poster.write_bytes(b"on")
    return generation_service.GenerationOutput(
        final_image_path=str(poster), asset_id="abc123def456", seed=42,
        style=StylePreset.EDITORIAL, copy_text="헤드라인\n서브카피",
        platform_copies={}, poster=True, generate_seconds=1.0, harmonize_seconds=0.0,
        image_without_typography_path=str(hero),
        image_with_typography_path=str(poster), typography_layout="kr_single_hero",
    )


def test_legacy_response_without_variant_urls_still_parses() -> None:
    response = GenerateAdResponse(
        asset_id="abc123def456", seed=42, style=StylePreset.MONOTONE,
        copy_text="copy", image_url="/api/ads/image/legacy.png", poster=False,
        generate_seconds=1.0, harmonize_seconds=0.0,
    )
    assert response.image_without_typography_url is None
    assert response.typography_enabled is False


def test_local_and_gpu_responses_expose_same_typography_contract(tmp_path) -> None:
    output = _output(tmp_path)
    web = web_response(output)
    gpu = gpu_response(output)
    assert web.image_url.endswith("hero_typography_on.png")
    assert web.image_without_typography_url.endswith("hero_typography_off.png")
    assert gpu.image_with_typography_url == "/result/hero_typography_on.png"
    assert web.typography_enabled is gpu.typography_enabled is True
    assert web.typography_layout == gpu.typography_layout == "kr_single_hero"


def test_remote_client_downloads_both_variants_and_selected_image(tmp_path, monkeypatch) -> None:
    class Response:
        def __init__(self, content: bytes):
            self.content = content

        def raise_for_status(self) -> None:
            return None

    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        return Response(url.encode())

    import requests

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(image_service, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(generation_client.settings, "GENERATION_SERVICE_URL", "http://gpu:8100")
    body = {
        "asset_id": "abc123def456", "seed": 42, "style": "editorial",
        "copy_text": "copy", "platform_copies": {},
        "image_url": "/result/on.png", "poster": True,
        "image_without_typography_url": "/result/off.png",
        "image_with_typography_url": "/result/on.png",
        "typography_enabled": True, "typography_layout": "kr_single_hero",
        "generate_seconds": 1.0, "harmonize_seconds": 0.0,
    }
    response = generation_client._fetch_and_localize(body)
    assert len(calls) == 2  # selected와 ON은 같은 원격 파일이므로 중복 다운로드하지 않음
    assert (tmp_path / "on.png").is_file() and (tmp_path / "off.png").is_file()
    assert response.image_url.endswith("/ads/image/on.png")
    assert response.image_without_typography_url.endswith("/ads/image/off.png")
