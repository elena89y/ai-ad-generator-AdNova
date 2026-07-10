"""데이터 수확기 (Phase 5 파인튜닝 입력) — 담당: 한의정.

runs.jsonl 원장에서 고품질 결과물을 자동 추출해 LoRA 학습셋 매니페스트를 만든다.
데이터 플라이휠(DIRECTION §5 Phase 5-1, D-'데이터 플라이휠'): 매 생성이 곧 학습자산.
저지·심미 지표가 임계 이상인 (입력 사진 → 명령 → 출력) 트리플릿만 통과시킨다.

사용:
    from app.harness.harvest import harvest
    stats = harvest(min_aesthetic=5.5, min_judge=7, out="backend/experiments/trainset.jsonl")

⚠️ 정직성: 재생성 불가한 과거 실행을 놓치지 않으려 저지 서면 즉시 수확 시작(플라이휠).
   코퍼스가 목표(100+)에 못 미치면 harvest 는 통과 수만 보고하고 학습은 보류 — 규모가 결정.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .run_logger import RUNS_PATH

# LoRA 최소 코퍼스(경험칙: 스타일 LoRA 는 50~100장에서 신호가 잡힘)
MIN_CORPUS_FOR_TRAINING = 100


def _passes(rec: dict, min_aesthetic: float, min_judge: Optional[int]) -> bool:
    """수확 통과 조건: 오류 없음 + 출력 존재 + 심미/저지 임계 충족."""
    if rec.get("error") is not None:
        return False
    if not rec.get("output"):
        return False
    m = rec.get("metrics", {})
    # 심미(NIMA 주지표, aesthetic_primary 산출) 게이트
    aes = m.get("aesthetic") or m.get("aesthetic_nima") or m.get("nima")
    if aes is not None and float(aes) < min_aesthetic:
        return False
    # 저지 overall(있을 때만) 게이트 — judge_ad/judge_ad_calibrated 결과
    if min_judge is not None:
        jd = m.get("judge_overall") or m.get("overall")
        if jd is not None and int(jd) < min_judge:
            return False
    # 지표가 하나도 없으면(초기 실행) 보수적으로 제외 — 라벨 없는 데이터는 학습오염
    if aes is None and (min_judge is None or (m.get("judge_overall") is None and m.get("overall") is None)):
        return False
    return True


def harvest(min_aesthetic: float = 5.5, min_judge: Optional[int] = 7,
            runs_path: Path = RUNS_PATH,
            out: str = "backend/experiments/trainset.jsonl") -> dict[str, Any]:
    """원장 → 학습셋 매니페스트. 통과 트리플릿을 jsonl 로 저장하고 통계를 반환한다.

    매니페스트 1행: {image, instruction, style, mode, metrics} — ai-toolkit/kohya 어댑터가 소비.
    """
    runs_path = Path(runs_path)
    total = passed = 0
    by_style: dict[str, int] = {}
    rows: list[dict] = []
    if runs_path.exists():
        for line in runs_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            if not _passes(rec, min_aesthetic, min_judge):
                continue
            passed += 1
            params = rec.get("params", {})
            style = params.get("style") or params.get("style_key") or rec.get("mode", "?")
            by_style[style] = by_style.get(style, 0) + 1
            rows.append({
                "image": rec["output"],
                "instruction": params.get("instruction", ""),
                "style": style,
                "mode": rec.get("mode", ""),
                "metrics": rec.get("metrics", {}),
                "run_id": rec.get("run_id"),
            })

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    ready = passed >= MIN_CORPUS_FOR_TRAINING
    return {
        "runs_total": total,
        "harvested": passed,
        "by_style": by_style,
        "min_corpus": MIN_CORPUS_FOR_TRAINING,
        "training_ready": ready,
        "manifest": str(out_path),
        "note": ("코퍼스 충분 — LoRA 학습 진입 가능" if ready
                 else f"코퍼스 부족({passed}/{MIN_CORPUS_FOR_TRAINING}) — 플라이휠 축적 후 학습(규모가 결정)"),
    }


if __name__ == "__main__":
    import sys
    st = harvest()
    json.dump(st, sys.stdout, ensure_ascii=False, indent=2)
    print()
