"""G2 게이트: API 이미지 경로 실호출 스모크 (A/B/C 각 1장) — 담당: 한의정. (DIRECTION_v6 T2)

VM(spai0820)에서 실행 — OPENAI/LANGFUSE 키는 backend/.env 에만 있다:
    cd backend && API_BUDGET_USD=0.5 ../.venv/bin/python scripts/g2_api_smoke.py \
        사진A.png:육개장 사진B.png:자몽에이드 사진C.png:무선마우스

게이트 판정 기준(DIRECTION_v6 §T2): 3장 생성 성공 + runs.jsonl kpi 3축 기록
+ Langfuse 트레이스 + 지출 ≤ $0.5 (예산 가드 하드스톱이 이중 방어).
결과: 이미지 backend/results/ai/api_edit/ · 요약 md 같은 폴더 · 원장 experiments/runs.jsonl
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND / ".env")  # observability 규약: langfuse import 전에 env 로드

from app.core.observability import init_langfuse, shutdown_langfuse  # noqa: E402

init_langfuse()

from app.services import api_image_service, pipeline_graph  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    rows = []
    for arg in sys.argv[1:]:
        path, _, name = arg.partition(":")
        if not name or not Path(path).exists():
            print(f"입력 오류(경로:이름): {arg}")
            return 2
        try:
            final = pipeline_graph.run_pipeline(path, name, policy="api")
            rows.append({"input": path, "name": name,
                         "out": final.get("out_path"),
                         "gate_passed": final.get("gate_passed"),
                         "attempts": final.get("attempts"),
                         "engine": final.get("engine"),
                         "error": final.get("error")})
        except api_image_service.ApiBudgetExceeded as exc:
            rows.append({"input": path, "name": name, "error": f"BUDGET: {exc}"})
        print(json.dumps(rows[-1], ensure_ascii=False))

    spend = api_image_service.session_spend_usd()
    ok = all(r.get("out") for r in rows) and spend <= 0.5
    summary = [
        f"# G2 API 실호출 스모크 — {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"- 판정: {'PASS' if ok else 'FAIL'} / 세션 지출 추정 ${spend:.3f} (상한 $0.5)",
        f"- 정책: api (단일 엔진 — 폴백도 api 재시도 1회)",
        "",
        "| 입력 | 이름 | 결과 | gate | attempts | error |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        summary.append(f"| {Path(r['input']).name} | {r['name']} | "
                       f"{Path(r['out']).name if r.get('out') else '—'} | "
                       f"{r.get('gate_passed')} | {r.get('attempts')} | {r.get('error') or ''} |")
    out_md = _BACKEND / "results" / "ai" / "api_edit" / "G2_smoke.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"\n요약 저장: {out_md}\n판정: {'PASS' if ok else 'FAIL'} (지출 ${spend:.3f})")
    shutdown_langfuse()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
