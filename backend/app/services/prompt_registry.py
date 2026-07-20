"""프롬프트 레지스트리 — LLM 프롬프트 문구의 단일 저장소 로더 — 담당: 한의정.

배경(DIRECTION_v6 T1): 멘토 지적 — 프롬프트가 코드에 인라인 하드코딩돼 있어 수정·검수·
버전관리가 어렵다. 문구를 backend/app/prompts/*.yaml 로 외부화하고 코드는 이 로더만 쓴다.

설계 결정:
  - 치환은 string.Template(${name}) — .format()과 달리 프롬프트에 흔한 JSON 예시 중괄호를
    이스케이프할 필요가 없어 외부화 과정의 오탈자 위험이 구조적으로 낮다.
  - substitute()는 누락 키에서 KeyError를 던진다(조용한 빈칸 방지).
  - 파일은 네임스페이스당 1개(gpt_service.yaml 등), lru_cache 로 프로세스당 1회 로드.
  - ⚠️ 문구는 실측 튜닝값 — tests/test_prompt_snapshots.py 바이트 동일성 게이트가 지킨다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

import yaml

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache(maxsize=None)
def _load(namespace: str) -> dict:
    path = _PROMPTS_DIR / f"{namespace}.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"프롬프트 파일 형식 오류(최상위가 매핑 아님): {path}")
    return data


def get(namespace: str, key: str):  # noqa: ANN201 — str | dict (데이터 맵도 제공)
    """'a.b' 점 표기 키로 원문 조회. 없으면 KeyError(조용한 폴백 금지)."""
    node = _load(namespace)
    for part in key.split("."):
        node = node[part]
    return node


def fmt(namespace: str, key: str, **kwargs) -> str:
    """템플릿 조회 + ${name} 치환. 누락 변수는 KeyError."""
    return Template(get(namespace, key)).substitute(**kwargs)
