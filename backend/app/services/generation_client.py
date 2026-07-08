"""생성 서비스 HTTP 클라이언트 (웹 백엔드 → GPU VM) — 담당: 한의정.

배포 구조 B: 웹 백엔드(Docker)가 GPU 생성 서비스를 원격 호출.
  settings.GENERATION_SERVICE_URL 이 설정된 경우에만 사용.
  결과 이미지는 /result/{name} 에서 받아 로컬(results/ai)에 저장 → 웹 백엔드가 서빙.

의존: requests (표준 사용). 웹 백엔드 requirements 에만 필요(GPU 스택 불필요).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.config import settings
from ..schemas.ads import GenerateAdResponse, ProductInfo, StylePreset
from . import image_service


def is_remote() -> bool:
    return bool(settings.GENERATION_SERVICE_URL)


def _fetch_and_localize(body: dict) -> GenerateAdResponse:
    """생성 서비스 응답의 이미지를 로컬로 내려받고, image_url 을 웹 서빙 경로로 재작성.

    생성 서비스는 /result/{name} 로 반환 → 웹 백엔드는 로컬 저장 후 api/ads/image/{name} 로 서빙.
    """
    import requests

    name = Path(body["image_url"]).name
    base = settings.GENERATION_SERVICE_URL.rstrip("/")
    resp = requests.get(
        f"{base}{body['image_url']}", timeout=settings.GENERATION_TIMEOUT_S
    )
    resp.raise_for_status()
    image_service.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (image_service.RESULTS_DIR / name).write_bytes(resp.content)
    # body["image_url"] = f"/ads/image/{name}"  # 웹 백엔드 서빙 경로로 교체
    body["image_url"] = f"{settings.API_PREFIX}/ads/image/{Path(out.final_image_path).name}" #PREFIX 적용 경로로 통일
    return GenerateAdResponse(**body)


def generate_remote(
    image_path: str,
    product: ProductInfo,
    style: StylePreset,
    seed: Optional[int],
    use_vision: bool,
    poster: bool,
) -> GenerateAdResponse:
    """GPU 생성 서비스에 파일 업로드 → 결과 메타 + 이미지 다운로드."""
    import requests

    base = settings.GENERATION_SERVICE_URL.rstrip("/")
    with open(image_path, "rb") as f:
        files = {"image": (Path(image_path).name, f)}
        data = {
            "product_name": product.name or "",
            "product_description": product.description or "",
            "style": style.value,
            "use_vision": str(use_vision).lower(),
            "poster": str(poster).lower(),
        }
        if seed is not None:
            data["seed"] = str(seed)
        resp = requests.post(
            f"{base}/generate", files=files, data=data,
            timeout=settings.GENERATION_TIMEOUT_S,
        )
    resp.raise_for_status()
    return _fetch_and_localize(resp.json())


def regenerate_remote(payload: dict) -> GenerateAdResponse:
    """asset_id 재생성 원격 호출."""
    import requests

    base = settings.GENERATION_SERVICE_URL.rstrip("/")
    resp = requests.post(
        f"{base}/regenerate", json=payload, timeout=settings.GENERATION_TIMEOUT_S
    )
    resp.raise_for_status()
    return _fetch_and_localize(resp.json())
