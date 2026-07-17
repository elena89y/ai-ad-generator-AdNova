"""Langfuse 트레이싱 초기화 — 담당: 한의정.

호출 시점: 각 FastAPI 진입점(main.py, generation_app.py) 시작 시 1회, 반드시
  env 로드(load_dotenv) *이후* · 첫 OpenAI/LangChain 호출 *이전*.
  (langfuse 공식 가이드 "Common Mistakes": Langfuse import를 env 로드 전에 하면
   자격증명 누락으로 초기화됨 — 여기서는 지연 임포트 + 명시적 init 호출로 방지.)

마스킹: gpt_service._vision_part 등이 업로드/생성 이미지를 base64 data URL 로
  통째로 GPT Vision 프롬프트에 실어 보낸다. 원문 그대로 트레이싱하면
  (a) 트레이스가 수백 KB~수 MB로 부풀고 (b) 사용자 상품 사진 원본이 Langfuse
  서버에 그대로 저장된다 → data URL 부분만 잘라내 마스킹한다(PII/용량 보호).

LANGFUSE_PUBLIC_KEY 가 없으면 트레이싱 없이 조용히 넘어간다(로컬 개발 중 Langfuse
계정 없이도 앱이 그대로 동작해야 하므로 — 필수 의존성으로 만들지 않는다).
"""
from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from typing import Callable

logger = logging.getLogger(__name__)

# data:image/png;base64,iVBORw0KG... 형태의 data URL 전체를 치환 대상으로 잡는다.
_DATA_URL_RE = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+")

_initialized = False


def _mask_base64_images(data, **_kwargs):  # noqa: ANN001, ANN201
    """트레이스 input/output/metadata 전송 직전에 호출되는 Langfuse 마스킹 훅.

    문자열 안의 base64 이미지 data URL만 잘라내고, 그 외 값(문구·상품명·점수 등)은
    그대로 통과시켜 트레이스 가독성을 유지한다.
    """
    if isinstance(data, str):
        return _DATA_URL_RE.sub("[IMAGE_DATA_REDACTED]", data)
    if isinstance(data, dict):
        return {k: _mask_base64_images(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_mask_base64_images(v) for v in data]
    return data


def init_langfuse() -> None:
    """앱 프로세스당 1회 호출. 두 번째 호출부터는 무시(멱등)."""
    global _initialized
    if _initialized:
        return
    _initialized = True  # 실패해도 재시도 스팸 방지 — 트레이싱은 best-effort

    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        logger.info("LANGFUSE_PUBLIC_KEY 미설정 — Langfuse 트레이싱 비활성화(정상 동작에는 영향 없음)")
        return

    try:
        from langfuse import Langfuse

        # mask 는 클라이언트 생성 시 1회만 등록 가능 — 이후 get_client() 로 어디서든 재사용.
        Langfuse(mask=_mask_base64_images)
        logger.info("Langfuse 트레이싱 초기화 완료")
    except Exception as e:  # noqa: BLE001 — 트레이싱 실패가 서비스 기동을 막으면 안 됨
        logger.warning(f"Langfuse 초기화 실패(트레이싱 없이 계속 진행): {e}")


def shutdown_langfuse() -> None:
    """앱 종료 시 큐에 남은 이벤트 flush. LANGFUSE_PUBLIC_KEY 미설정이면 무해하게 스킵."""
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return
    try:
        from langfuse import get_client

        get_client().shutdown()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Langfuse shutdown 중 오류(무해): {e}")


def observe(name: str | None = None):  # noqa: ANN201
    """langfuse.observe optional wrapper. 패키지/키가 없으면 원 함수 그대로 반환."""
    try:
        from langfuse import observe as _observe
        return _observe(name=name) if name else _observe()
    except Exception:  # noqa: BLE001
        def _decorator(func: Callable) -> Callable:
            return func
        return _decorator


@contextmanager
def propagate_attributes(**attrs):  # noqa: ANN003, ANN201
    """langfuse.propagate_attributes optional wrapper. 없으면 no-op context.

    ⚠️ setup(import) 실패만 폴백으로 흡수한다. 본문에서 난 예외를 감싸면 안 된다 —
    예전 구조(try 안에서 yield, except에서 다시 yield)는 본문 예외가 throw될 때 두 번째
    yield를 실행해 원래 예외를 `generator didn't stop after throw()`로 덮어썼다(사용자 400
    오류가 500으로 변질 — P4D 게이트 실행 중 문어괄사 입력 게이트 거부에서 실측)."""
    cm = None
    try:
        from langfuse import propagate_attributes as _propagate_attributes
        cm = _propagate_attributes(**attrs)
    except Exception:  # noqa: BLE001 — langfuse 미설치/초기화 실패는 무해히 no-op
        cm = None
    if cm is None:
        yield
        return
    with cm:  # 본문 예외는 여기서 정상 전파된다(흡수 금지)
        yield
