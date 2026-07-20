"""T1 게이트(G1): gpt_service 프롬프트 바이트 동일성 스냅샷 — 담당: 한의정.

이 테스트가 깨졌다면 프롬프트 문구가 바뀐 것이다. 실측 튜닝값이므로:
  - 리팩토링(YAML 외부화 등) 중이면 → 바이트 동일해질 때까지 수정 (골든 갱신 금지)
  - 문구를 의도적으로 바꾸는 실험이면 → 실험로그 기록 후
    `python -m tests.prompt_capture` 로 골든 갱신을 같은 커밋에 포함
"""
from __future__ import annotations

import json

from tests.prompt_capture import GOLDEN_PATH, capture_all


def test_gpt_prompts_byte_identical(tmp_path):
    assert GOLDEN_PATH.exists(), "골든 없음 — `python -m tests.prompt_capture` 로 생성"
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    captured = capture_all(tmp_path)
    # 사이트 단위로 비교해 어긋난 곳을 바로 지목한다
    assert sorted(captured) == sorted(golden), "프롬프트 사이트 목록이 골든과 다름"
    for key in golden:
        assert captured[key] == golden[key], f"프롬프트 변경 감지: {key}"
