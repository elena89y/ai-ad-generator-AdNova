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
from ..schemas.ads import AdPurpose, GenerateAdResponse, ProductInfo, StylePreset
from . import image_service

# 780s (2026-07-21 재상향): 570s 추정은 낙관적이었다 — 라이브 실측에서 웜 card_news 가
#   601s(워커는 200 완료했으나 웹→워커 클라이언트가 600s 에 먼저 포기 → 사용자 500).
#   카드뉴스 조판이 상세보다 ~80s 무겁고, 콜드(모델 로드)까지 겹치면 더 늘어난다.
#   실측 웜 601s 위에 콜드·변동 여유를 얹어 780s. **nginx /api/ read timeout(840s)보다 작아야**
#   502 대신 유의미한 응답이 나간다. (근본 단축은 하이브리드/API 경로 = FMT-001, 별도 트랙)
_MIN_TIMEOUT_S = 780


def _request_timeout() -> int:
    """GPU queue 대기와 warm 생성을 함께 견디는 최소 HTTP timeout."""
    return max(_MIN_TIMEOUT_S, settings.GENERATION_TIMEOUT_S)


def is_remote() -> bool:
    return bool(settings.GENERATION_SERVICE_URL)


def _fetch_and_localize(body: dict) -> GenerateAdResponse:
    """생성 서비스 응답의 이미지를 로컬로 내려받고, image_url 을 웹 서빙 경로로 재작성.

    생성 서비스는 /result/{name} 로 반환 → 웹 백엔드는 로컬 저장 후 api/ads/image/{name} 로 서빙.
    """
    import requests

    base = settings.GENERATION_SERVICE_URL.rstrip("/")
    image_service.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    localized: dict[str, str] = {}
    for field in (
        "image_url", "image_without_typography_url", "image_with_typography_url",
    ):
        remote_url = body.get(field)
        if not remote_url:
            continue
        if remote_url not in localized:
            name = Path(remote_url).name
            resp = requests.get(f"{base}{remote_url}", timeout=_request_timeout())
            resp.raise_for_status()
            (image_service.RESULTS_DIR / name).write_bytes(resp.content)
            localized[remote_url] = f"{settings.API_PREFIX}/ads/image/{name}"
        body[field] = localized[remote_url]
    format_outputs = []
    for remote_url in body.get("format_outputs", []):
        if remote_url not in localized:
            name = Path(remote_url).name
            resp = requests.get(f"{base}{remote_url}", timeout=_request_timeout())
            resp.raise_for_status()
            (image_service.RESULTS_DIR / name).write_bytes(resp.content)
            localized[remote_url] = f"{settings.API_PREFIX}/ads/image/{name}"
        format_outputs.append(localized[remote_url])
    body["format_outputs"] = format_outputs
    return GenerateAdResponse(**body)


def generate_remote(
    image_path: str,
    product: ProductInfo,
    style: StylePreset,
    seed: Optional[int],
    use_vision: bool,
    poster: bool,
    purpose: AdPurpose = AdPurpose.SNS,
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
            "purpose": purpose.value,
        }
        if seed is not None:
            data["seed"] = str(seed)
        resp = requests.post(
            f"{base}/generate", files=files, data=data,
            timeout=_request_timeout(),
        )
    resp.raise_for_status()
    return _fetch_and_localize(resp.json())


def regenerate_remote(payload: dict) -> GenerateAdResponse:
    """asset_id 재생성 원격 호출."""
    import requests

    base = settings.GENERATION_SERVICE_URL.rstrip("/")
    resp = requests.post(
        f"{base}/regenerate", json=payload, timeout=_request_timeout()
    )
    resp.raise_for_status()
    return _fetch_and_localize(resp.json())
