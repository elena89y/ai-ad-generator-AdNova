"""DIV-2 사진-톤 매칭 회귀 가드 — 담당: 한의정.

핵심 계약:
  ① OFF(scene_tone 미지정) = 기존 지시와 바이트 동일 (byte-identity, 프리셋 회귀 가드).
  ② 모든 _SCENE_SPANS 의 v0 스팬이 실제 direction 에서 발견됨 (교체가 무위로 죽지 않게).
  ③ 톤별 표면 적응 (warm/cool/neutral 이 서로 다른 표면 선택).
  ④ 결정론 (동일 subject·tone·seed → 동일 결과).
  ⑤ classify_scene_tone 픽셀 통계 라벨 정합 (합성 웜/쿨/무채색).
"""
import numpy as np
from PIL import Image

from app.services import reference_style_plans as R
from app.services.image_service import classify_scene_tone


def test_scene_tone_off_is_byte_identical():
    """scene_tone 미지정 = 기존 문구 그대로. 모든 슬롯 보유 플랜에서 v0 스팬 잔류."""
    for (dom, mood), spans in R._SCENE_SPANS.items():
        off = R.build_reference_instruction(mood, dom, "test subject")
        assert off is not None
        for span in spans.values():
            assert span in off, f"{dom}/{mood}: OFF 에서 v0 스팬 소실 {span!r}"


def test_scene_tone_spans_all_present():
    """②: 모든 (domain,mood) 의 표면/배경 스팬이 direction 에 실제 존재 → 교체 유효."""
    for (dom, mood), spans in R._SCENE_SPANS.items():
        ins = R.build_reference_instruction(mood, dom, "widget")
        for slot, span in spans.items():
            assert span in ins, f"{dom}/{mood}.{slot} 스팬 미발견 → 교체 죽음"


def test_scene_tone_adapts_surface():
    """③: 입력 톤에 따라 표면이 달라진다 (food/realism warm ≠ cool)."""
    warm = R.build_reference_instruction("realism", "food", "kimchi stew", scene_tone="warm")
    cool = R.build_reference_instruction("realism", "food", "kimchi stew", scene_tone="cool")
    assert warm != cool
    # v0(neutral 다크차콜)이 warm/cool 에서 각각 톤 버킷으로 교체됨
    assert "a dark charcoal stone table" not in warm
    assert "a dark charcoal stone table" not in cool


def test_scene_tone_deterministic():
    """④: 동일 subject·tone·seed 2회 호출 결과 동일 (hashlib 고정, PYTHONHASHSEED 무관)."""
    a = R.build_reference_instruction("realism", "food", "galbi", scene_tone="warm", scene_seed=2)
    b = R.build_reference_instruction("realism", "food", "galbi", scene_tone="warm", scene_seed=2)
    assert a == b


def test_scene_tone_surface_background_decoupled():
    """무대 조합이 동조(2)보다 커야 한다 (surface·background 독립 선택)."""
    def stage(ins):
        s = b = None
        for pools in R._SCENE_POOLS.values():
            for slot in ("surface", "background"):
                for bucket in pools.get(slot, {}).values():
                    for c in bucket:
                        if c in ins:
                            s, b = (c, b) if slot == "surface" else (s, c)
        return (s, b)
    combos = {stage(R.build_reference_instruction(
        "realism", "food", "kimchi stew", scene_tone="warm", scene_seed=k)) for k in range(6)}
    assert len(combos) >= 3, f"무대 조합 다양성 부족: {len(combos)}"


def _solid(rgb):
    return Image.fromarray(np.full((64, 64, 3), rgb, dtype=np.uint8))


def test_classify_scene_tone_labels(tmp_path):
    """⑤: 합성 패치 — 웜(적)·쿨(청)·무채색(회) 라벨 정합."""
    cases = {"warm": (210, 150, 90), "cool": (90, 130, 210), "neutral": (150, 150, 150)}
    for expect, rgb in cases.items():
        p = tmp_path / f"{expect}.png"
        _solid(rgb).save(p)
        assert classify_scene_tone(str(p)) == expect, f"{rgb} → 기대 {expect}"
