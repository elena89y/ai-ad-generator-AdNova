"""무-상품(브리프) 경로의 배경 생성 엔진 라우터 — 담당: 한의정.

기능 1의 배경(글자 없는 무드/씬)을 어느 엔진으로 뽑을지 스위치한다.
  - api   : api_image_service.generate_image (gpt-image-2, GPU 불필요, Mac E2E 가능, ~$0.01)
  - local : image_service.txt2img (RealVisXL, GPU/VM 전용, 무과금 — local-parity 후속)

역할분리(함정 #3): 여기선 '글자 없는 배경'만 만든다. 타이포·정보·규정문구는 코드(overlay)가 얹는다.
정직성: 무-상품이라 정체성 보존 부담이 없다 → 생성 자유가 자산(정체성 왜곡 리스크 없음).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# 전용 env 스위치 — BRIEF_ENGINE=api|local. 기본 api(즉시 출시·저비용, GPU 불필요).
# ⚠️ pipeline_graph 의 ENGINE_POLICY(local|api|hybrid, 기본 local)와 의미가 다르므로 재사용 금지.
#   호출 시점에 조회한다(프로세스 기동 후 env 변경 반영, import 시점 고정 방지).
_ENGINE_ENV = "BRIEF_ENGINE"

# 확산모델 positive 에 들어가면 안 되는 부정문(negative 담당) — 로컬 프롬프트 조립 시 제거.
_NEG_PHRASE_RE = re.compile(r"\bno\s+(text|letters?|words?|signage|logos?)\b", re.IGNORECASE)


def _default_engine() -> str:
    """호출 시점 엔진 결정 — 미지정·미검증 값은 api 로 안전 폴백(local 만 GPU 경로)."""
    eng = os.getenv(_ENGINE_ENV, "api").strip().lower()
    if eng not in ("api", "local"):
        logger.warning("%s=%r 은(는) 미지원 값 → 'api' 로 폴백", _ENGINE_ENV, eng)
        return "api"
    return eng


def _parse_size(size: str) -> tuple[int, int]:
    """'1024x1024' → (1024,1024). 파싱 실패 시 정사각 폴백."""
    try:
        w, h = size.lower().split("x")
        return int(w), int(h)
    except Exception:  # noqa: BLE001
        return 1024, 1024


def generate_background(scene_en: str, palette_hint: str = "",
                        size: str = "1024x1024", engine: Optional[str] = None,
                        seed: Optional[int] = None, run=None) -> str:  # noqa: ANN001
    """배경 이미지 1장 생성 → 파일 경로. engine 미지정 시 ENGINE_POLICY(기본 api).

    반환 경로는 규격 없는 배경(compose 가 각 FormatSpec 캔버스로 crop/fit).
    """
    eng = (engine or _default_engine()).lower()
    if eng == "local":
        from .. import image_service
        img = image_service.txt2img(
            _local_prompt(scene_en, palette_hint),
            size=_parse_size(size), seed=seed if seed is not None else 7)
        import tempfile
        import uuid
        from pathlib import Path
        out = Path(tempfile.gettempdir()) / f"bg_local_{uuid.uuid4().hex[:8]}.png"
        img.save(out, "PNG")
        return str(out)

    # 기본: API(gpt-image) 경로 — 프롬프트에 no-text 절이 이미 포함된다.
    from .. import api_image_service
    prompt = api_image_service.build_generate_prompt(scene_en, palette_hint)
    return api_image_service.generate_image(prompt, size=size, run=run)


def _ascii_clause(text: str) -> str:
    """CLIP(SDXL/RealVis) positive 안전화: 비-ASCII(한글 등) 제거(함정 #1) + 부정문(negative 담당)
    제거 + 공백 정리. 모델이 계약을 어겨 scene_en 에 한글을 섞어도 프롬프트가 오염되지 않는다.
    """
    ascii_only = "".join(c for c in (text or "") if ord(c) < 128)
    no_neg = _NEG_PHRASE_RE.sub("", ascii_only)
    return re.sub(r"\s*,\s*,+", ", ", " ".join(no_neg.split())).strip(" ,")


def _local_prompt(scene_en: str, palette_hint: str) -> str:
    """로컬 txt2img 용 positive — 배경/무드만(글자 억제는 image_service negative 가 담당).

    ⚠️ CLIP 은 한글을 노이즈로 해석(함정 #1) → scene_en/palette 는 ASCII 로 강제 정제한다.
    """
    base = _ascii_clause(scene_en) or "clean minimal studio background, soft light"
    palette = _ascii_clause(palette_hint)
    tail = f", {palette}" if palette else ""
    return (f"professional advertising background, {base}{tail}, "
            f"clean composition with empty space, high quality, photographic")
