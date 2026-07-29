from pathlib import Path

from PIL import Image

from app.api.ads import _compose_banner_response
from app.schemas.ads import GenerateAdResponse, StylePreset
from app.services import image_service


def test_existing_generate_response_can_expand_to_banner_pack(monkeypatch, tmp_path):
    monkeypatch.setattr(image_service, "RESULTS_DIR", tmp_path)
    source = tmp_path / "hero.png"
    Image.new("RGB", (900, 900), (180, 120, 80)).save(source)
    response = GenerateAdResponse(
        asset_id="abcdef123456", seed=7, style=StylePreset.MONOTONE,
        copy_text="오늘을 부드럽게\n시그니처 라떼", image_url="/api/ads/image/hero.png",
        poster=False, image_without_typography_url="/api/ads/image/hero.png",
        generate_seconds=1.0, harmonize_seconds=0.1,
    )
    expanded = _compose_banner_response(response, "라떼", ["commerce_wide"])
    assert expanded.purpose.value == "banner"
    assert len(expanded.format_outputs) == 1
    assert Path(expanded.format_outputs[0]).name.endswith("banner_1920x600_commerce_wide.jpg")
