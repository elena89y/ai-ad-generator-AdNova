"""T1 게이트: 스타일 디자인 토큰 동등성 스냅샷 — 담당: 한의정.

YAML 외부화(app/styles/specs.yaml)가 리팩토링 전 in-code 값과 완전 동일함을 보장한다.
깨졌다면 토큰 값이 바뀐 것 — 의도적 변경이면 실험로그 기록 후 골든을 같은 커밋에서 갱신.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from app.services import style_specs as ss

GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "style_specs.json"


def _canon(value):  # noqa: ANN001, ANN202 — tuple→list 정규화(JSON 왕복 대칭)
    return json.loads(json.dumps(value, ensure_ascii=False))


def test_style_specs_equal_golden():
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    current = {
        "specs": {k: dataclasses.asdict(v) for k, v in ss.STYLE_SPECS.items()},
        "button_map": dict(ss.BUTTON_STYLE_MAP),
    }
    assert _canon(current["button_map"]) == golden["button_map"]
    assert sorted(current["specs"]) == sorted(golden["specs"])
    for key in golden["specs"]:
        assert _canon(current["specs"][key]) == golden["specs"][key], f"토큰 변경 감지: {key}"


def test_fallbacks_unchanged():
    """미지 키 폴백 계약(editorial)은 로더 전환 후에도 동일해야 한다."""
    assert ss.get_spec("no-such-style").key == "editorial"
    assert ss.resolve_style("없는버튼") == "editorial"
    assert ss.resolve_style("비비드") == "pop"
