"""P6B 인라인 품질 게이트 — 담당: 한의정. DIRECTION_v4 P6B (결정 D-5·D-7).

워커 요청 경로 안에서 도는 검사라 **numpy 경량만** 허용한다(D-7: 평가 모델 워커 금지).
무거운 정체성 지표(DINO/LPIPS/OCR)는 P6A 오프라인 audit(v4_audit_runs.py)의 몫이고,
여기서는 0초에 가까운 세 가지만 본다:
  1. compose_stats — 합성 경로가 이미 계산한 cutout 통계(fg_ratio·dominant_ratio)의 재검
  2. product_delta_e — 합성 경로의 색 조화 ΔE 상한(구조상 ≤6이지만 회귀 안전망)
  3. style_stats — 스타일별 발색 방향(style_finish 재사용, CPU 수 ms)

GATE_MODE: off(기본) | audit(채점만 기록) | enforce(실패 시 개입).
⚠️ enforce는 P6A 캘리브레이션(V4P6-001, ≥30건) 후에만 켠다(결정 D-5). 아래 THRESHOLDS는
   보수적 임시값 — 캘리브레이션 표가 나오면 이 dict만 교체한다.

실패 처리(enforce, 스펙 6B):
  - style 실패 → style_finish strength 0.8 재마감(추가 생성 0회·0초).
  - identity 실패의 폴백(사물→합성 / 음료→Level-1)은 이 모듈이 아니라 라우팅에 이미 존재:
    합성 부적격·cutout 실패는 compose_scene이 ok=False로 Kontext에 폴백하고(P4D D-11),
    음료 재연출 부적격은 P5 라우팅이 preserve로 남긴다. 인라인에서 무거운 identity 재검은
    D-7 위반이라 하지 않는다.
  - 재마감 후에도 실패 → 결과는 그대로 반환하되 gate_failed를 반환값에 마킹.
    응답 스키마 노출은 범수 조율 전 금지 — 호출부는 runs.jsonl(add_metric)에만 기록한다.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ⚠️ 임시 임계값 — V4P6-001 캘리브레이션(audit.jsonl ≥30건, 알려진 실패 STY003·STY004와
#   정상 STY007 분리 실측)으로 확정 후 교체. 그 전에는 GATE_MODE=off가 기본이라 미적용.
THRESHOLDS: dict[str, dict[str, float]] = {
    "compose": {
        "fg_ratio_min": 0.05,
        "fg_ratio_max": 0.70,
        "dominant_ratio_min": 0.85,
        "delta_e_max": 6.5,       # 구조 상한 6.0 + 부동소수 여유
    },
    # style_stats 방향 하한 — 해당 무드가 최소한의 발색 정체성을 갖는지(스타일 오인 방지)
    "style": {
        "monotone_hue_concentration_min": 0.35,
        "pop_mean_sat_min": 0.25,
        "warm_vintage_warmth_min": 1.05,
    },
}


def gate_mode() -> str:
    """off | audit | enforce. 알 수 없는 값은 off로 취급(안전 기본값)."""
    mode = os.environ.get("GATE_MODE", "off").strip().lower()
    return mode if mode in ("off", "audit", "enforce") else "off"


def _check_compose_stats(compose_stats: Optional[dict], failures: list[dict]) -> None:
    if not compose_stats:
        return
    t = THRESHOLDS["compose"]
    fg = compose_stats.get("fg_ratio")
    if isinstance(fg, (int, float)) and not (t["fg_ratio_min"] <= fg <= t["fg_ratio_max"]):
        failures.append({"check": "compose.fg_ratio", "value": round(float(fg), 4),
                         "threshold": f"[{t['fg_ratio_min']}, {t['fg_ratio_max']}]"})
    dom = compose_stats.get("dominant_ratio")
    if isinstance(dom, (int, float)) and dom < t["dominant_ratio_min"]:
        failures.append({"check": "compose.dominant_ratio", "value": round(float(dom), 4),
                         "threshold": f">={t['dominant_ratio_min']}"})
    de = compose_stats.get("delta_e")
    if isinstance(de, (int, float)) and de > t["delta_e_max"]:
        failures.append({"check": "compose.delta_e", "value": round(float(de), 3),
                         "threshold": f"<={t['delta_e_max']}"})


def _check_style_stats(final_path: str, style_key: Optional[str],
                       failures: list[dict]) -> Optional[dict]:
    from . import style_finish

    try:
        stats = style_finish.style_stats(final_path)
    except Exception as exc:  # noqa: BLE001 — 게이트가 요청을 죽이면 안 됨
        logger.warning("inline_gate style_stats 실패(검사 생략): %s", exc)
        return None
    t = THRESHOLDS["style"]
    style = (style_key or "").strip().lower()
    if style == "monotone" and stats["hue_concentration"] < t["monotone_hue_concentration_min"]:
        failures.append({"check": "style.monotone_hue_concentration",
                         "value": round(stats["hue_concentration"], 4),
                         "threshold": f">={t['monotone_hue_concentration_min']}"})
    elif style == "pop" and stats["mean_sat"] < t["pop_mean_sat_min"]:
        failures.append({"check": "style.pop_mean_sat",
                         "value": round(stats["mean_sat"], 4),
                         "threshold": f">={t['pop_mean_sat_min']}"})
    elif style in ("warm_vintage", "warm_organic") and stats["warmth"] < t["warm_vintage_warmth_min"]:
        failures.append({"check": "style.warm_vintage_warmth",
                         "value": round(stats["warmth"], 4),
                         "threshold": f">={t['warm_vintage_warmth_min']}"})
    return stats


def evaluate(final_path: str, style_key: Optional[str] = None,
             compose_stats: Optional[dict] = None) -> dict:
    """경량 검사 실행. 반환 {"pass": bool, "failures": [...], "style_stats": {...}|None}."""
    failures: list[dict] = []
    _check_compose_stats(compose_stats, failures)
    stats = _check_style_stats(final_path, style_key, failures)
    return {
        "pass": not failures,
        "failures": failures,
        "style_stats": {k: round(v, 4) for k, v in stats.items()} if stats else None,
    }


def enforce(final_path: str, style_key: Optional[str] = None,
            compose_stats: Optional[dict] = None) -> dict:
    """GATE_MODE=enforce 개입. 반환 {"path", "gate": 평가결과, "gate_failed": bool,
    "refinished": bool}.

    style 계열 실패만 개입 대상(style_finish 0.8 재마감, 추가 생성 0회). 재마감 후 재평가에도
    실패하면 보수적으로 결과를 그대로 두고 gate_failed=True — 호출부는 runs.jsonl에만 기록.
    """
    first = evaluate(final_path, style_key, compose_stats)
    if first["pass"]:
        return {"path": final_path, "gate": first, "gate_failed": False, "refinished": False}

    style_failures = [f for f in first["failures"] if f["check"].startswith("style.")]
    path = final_path
    refinished = False
    if style_failures:
        from . import style_finish

        refinished_path = style_finish.apply(final_path, style_key or "", strength=0.8)
        if refinished_path != final_path:
            path = refinished_path
            refinished = True

    second = evaluate(path, style_key, compose_stats) if refinished else first
    return {
        "path": path,
        "gate": second,
        "gate_failed": not second["pass"],
        "refinished": refinished,
    }
