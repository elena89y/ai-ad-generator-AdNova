"""OpenAI 이미지 편집 경로 (API 하이브리드 축) — 담당: 한의정. (DIRECTION_v6 T2)

로컬 GPU 파이프라인의 하이브리드 짝. gpt-image-2 edit 는 A/B/C 전 모드 정체성 보존이
실측 검증됨(2026-07-17: quality=low 1024² 장당 $0.011~0.018, 투명 유리잔·로고 SKU 무결점,
눕힌 제품의 3D 형상 이해). GCP 종료 후에는 이 경로가 서비스 생존 경로(ENGINE_POLICY=api).

비용 가드(팀 한도 $30 보호):
  - API_BUDGET_USD (기본 2.0): 프로세스 세션 누적 지출 하드스톱 — 초과 예상 시 호출 전 차단.
  - 소스는 업로드 전 장변 1024 로 다운스케일 — 입력 토큰이 원본 해상도에 비례(실측:
    4032² = 1452tok vs 소형 575~650tok)하므로 필수.

지시문은 backend/app/prompts/api_image.yaml (초안 — T3 A/B 에서 튜닝, 이후 스냅샷 게이트 편입).
정직성 경계는 로컬 경로와 동일: 없는 재료·소품 생성 금지, 사물(SKU) 형태·색·로고 불변.
"""
from __future__ import annotations

import base64
import logging
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Optional

from . import prompt_registry as _prompts
from ..harness.pricing import image_cost_of

logger = logging.getLogger(__name__)

_NS = "api_image"

DEFAULT_MODEL = os.environ.get("API_IMAGE_MODEL", "gpt-image-2")
_MAX_SIDE = 1024  # 입력 토큰 절감(실측 근거) — 업로드 전 다운스케일 상한

# --- 세션 예산 가드 ---------------------------------------------------------------
_spend_lock = threading.Lock()
_session_spend_usd = 0.0


class ApiBudgetExceeded(RuntimeError):
    """API_BUDGET_USD 초과 — 개발 중 반복 호출 폭주로부터 팀 한도($30)를 보호한다."""


def budget_usd() -> float:
    try:
        return float(os.environ.get("API_BUDGET_USD", "2.0"))
    except ValueError:
        return 2.0


def session_spend_usd() -> float:
    return _session_spend_usd


def _reserve_budget(estimated_usd: float) -> None:
    """호출 '전' 예산 확인·선점 — 초과 예상이면 네트워크 호출 없이 차단한다."""
    global _session_spend_usd
    with _spend_lock:
        if _session_spend_usd + estimated_usd > budget_usd():
            raise ApiBudgetExceeded(
                f"API 이미지 예산 초과: 사용 {_session_spend_usd:.3f} + 예상 {estimated_usd:.3f} "
                f"> 한도 {budget_usd():.2f} USD (env API_BUDGET_USD 로 조정)")
        _session_spend_usd += estimated_usd


def _downscale_for_upload(image_path: str, max_side: int = _MAX_SIDE) -> str:
    """장변 max_side 초과 시 축소 PNG 임시본 생성(입력 토큰 절감). 이하면 원본 그대로."""
    from PIL import Image

    with Image.open(image_path) as im:
        if max(im.size) <= max_side:
            return image_path
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        tmp = Path(tempfile.gettempdir()) / f"apiimg_{uuid.uuid4().hex[:8]}.png"
        im.save(tmp, "PNG")
        return str(tmp)


def build_edit_instruction(subject_en: str, style_hint: str = "",
                           identity_parts: Optional[list[str]] = None,
                           flexible_parts: Optional[list[str]] = None,
                           is_object: bool = False) -> str:
    """analyze_photo 결과 → 정체성 보존 edit 지시문 (문구는 YAML 원장).

    파트별 보존등급(제품 이해, 2026-07-17)을 그대로 계승: identity=불변, flexible=용기만 무드 변경.
    """
    identity_clause = (
        _prompts.fmt(_NS, "identity_clause", identity_parts=", ".join(identity_parts))
        if identity_parts else "")
    text = _prompts.fmt(
        _NS, "edit_base",
        subject=subject_en or "product",
        identity_clause=identity_clause,
        style_hint=style_hint or _prompts.get(_NS, "style_hint_default"))
    if flexible_parts and not is_object:
        text += _prompts.fmt(_NS, "flexible_clause",
                             flexible_parts=", ".join(flexible_parts))
    if is_object:
        text += " " + _prompts.get(_NS, "object_lock")
    return text


def edit_image(image_path: str, instruction: str,
               out_dir: str = "backend/results/ai/api_edit",
               model: str = DEFAULT_MODEL, quality: str = "low",
               size: str = "1024x1024", run=None) -> str:  # noqa: ANN001 — RunLogger optional
    """gpt-image edit 1회 호출 → 결과 PNG 경로. 예산 선점 실패 시 ApiBudgetExceeded.

    run(RunLogger) 을 주면 image_api 비용축이 KPI 원장에 자동 기록된다(T0 계약).
    """
    estimated = image_cost_of(model) or 0.02  # 미등록 모델은 보수적으로 상한 근사
    _reserve_budget(estimated)

    if run is None:  # 그래프 노드 등 핸들 없는 호출부 → 활성 원장에 자동 합류(G2 실측 갭)
        from ..harness.run_logger import current_run

        run = current_run()

    from .gpt_service import _get_client  # Langfuse drop-in 트레이싱 계승

    upload_path = _downscale_for_upload(image_path)
    client = _get_client()
    with open(upload_path, "rb") as f:
        response = client.images.edit(
            model=model, image=f, prompt=instruction, size=size, quality=quality)

    b64 = response.data[0].b64_json
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    out_path = out / f"api_{uuid.uuid4().hex[:8]}.png"
    out_path.write_bytes(base64.b64decode(b64))

    if run is not None:
        try:
            run.add_image_api_usage(model, n=1)
        except Exception:  # noqa: BLE001 — 계측 실패가 생성 응답을 막으면 안 됨
            logger.debug("image_api usage 기록 실패(무해)", exc_info=True)
    logger.info("api edit 완료 model=%s quality=%s cost≈$%.3f → %s",
                model, quality, estimated, out_path)
    return str(out_path)
