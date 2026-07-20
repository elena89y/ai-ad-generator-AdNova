"""챗봇 검색 품질 평가 — 유형별 집계 (골든셋 기반, OpenAI 호출 0회) — 담당: 한의정.

측정 (전체 + 유형별):
  답변가능(direct/paraphrase/typo): hit@1 / hit@3 / MRR / confident 판정률
  에스컬레이션(adjacent/offtopic/injection): recall (confident=False 가 정답)
  게이트 종합: escalation precision

실행 (backend/ 에서):
  ../.venv/bin/python scripts/eval_chatbot_retrieval.py            # BM25 단독 (기본)
  ../.venv/bin/python scripts/eval_chatbot_retrieval.py --dense    # +KURE-v1 dense 아암 (CHAT-002 A/B)
산출:
  results/ai/chatbot_eval_retrieval{_dense}.md    사람용 리포트 (오답 상세 포함)
  results/ai/chatbot_eval_retrieval{_dense}.json  기계용 지표 — check_chatbot_release_gate.py 입력 계약
  --dense 실행 시 baseline json 이 있으면 유형별 델타를 자동 출력 (클린 A/B — 단일변수=embed_fn)

임계값 튜닝: retrieval.MIN_BM25_SCORE / MIN_COVERAGE / typo_normalize 임계값을
  바꿔가며 재측정 (클린 A/B 원칙 — 단일 변수만 변경).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.chatbot.retrieval import HybridRetriever, build_transformers_embedder  # noqa: E402

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "experiments" / "chatbot_golden_v1.yaml"
OUT_DIR = Path(__file__).resolve().parents[1] / "results" / "ai"
TOP_K = 3

ANSWERABLE_TYPES = ("direct", "paraphrase", "typo")
ESCALATE_TYPES = ("adjacent", "offtopic", "injection")


def _answerable_metrics(rows: list) -> dict:
    """rows: (q, expected, top_ids, rank, confident)"""
    n = len(rows)
    if not n:
        return {"n": 0}
    hit1 = sum(1 for r in rows if r[3] == 0)
    hit3 = sum(1 for r in rows if r[3] is not None)
    mrr = sum(1.0 / (r[3] + 1) for r in rows if r[3] is not None) / n
    return {
        "n": n,
        "hit1": round(hit1 / n, 4),
        "hit3": round(hit3 / n, 4),
        "mrr": round(mrr, 4),
        "confident_rate": round(sum(1 for r in rows if r[4]) / n, 4),
    }


def _escalation_metrics(rows: list) -> dict:
    """rows: (q, confident, top_ids, top_score)"""
    n = len(rows)
    if not n:
        return {"n": 0}
    return {"n": n, "recall": round(sum(1 for r in rows if not r[1]) / n, 4)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dense", action="store_true", help="KURE-v1 dense 아암 (BM25+RRF, CHAT-002)")
    ap.add_argument("--rewrite", action="store_true",
                    help="쿼리 리라이팅 아암 (CHAT-003) — ⚠️ 저신뢰 케이스당 LLM 1회 (OPENAI_API_KEY 필요)")
    args = ap.parse_args()

    cases = yaml.safe_load(GOLDEN_PATH.read_text(encoding="utf-8"))["cases"]
    embed_fn = build_transformers_embedder() if args.dense else None
    retriever = HybridRetriever(embed_fn=embed_fn)
    suffix = ("_dense" if args.dense else "") + ("_rewrite" if args.rewrite else "")
    if args.rewrite:
        from app.services.chatbot.chat_service import retrieve_with_rewrite  # noqa: PLC0415

    rewrites: list[tuple[str, str]] = []
    ans_by_type: dict[str, list] = defaultdict(list)
    esc_by_type: dict[str, list] = defaultdict(list)
    for c in cases:
        ctype = c.get("type", "direct")
        if args.rewrite:
            hits, confident, rewritten = retrieve_with_rewrite(retriever, c["q"], top_k=TOP_K)
            if rewritten:
                rewrites.append((c["q"], rewritten))
        else:
            hits = retriever.search(c["q"], top_k=TOP_K)
            confident = HybridRetriever.is_confident(hits)
        top_ids = [h.faq.id for h in hits]
        if c.get("escalate"):
            esc_by_type[ctype].append((c["q"], confident, top_ids, hits[0].bm25_score if hits else 0.0))
        else:
            expected = set(c["expected"])
            rank = next((i for i, fid in enumerate(top_ids) if fid in expected), None)
            ans_by_type[ctype].append((c["q"], expected, top_ids, rank, confident))

    ans_all = [r for t in ANSWERABLE_TYPES for r in ans_by_type.get(t, [])]
    esc_all = [r for t in ESCALATE_TYPES for r in esc_by_type.get(t, [])]

    esc_correct = sum(1 for r in esc_all if not r[1])
    predicted_esc = esc_correct + sum(1 for r in ans_all if not r[4])
    metrics = {
        "golden": GOLDEN_PATH.name,
        "arm": ("bm25+dense(KURE-v1,RRF)" if args.dense else "bm25")
        + ("+rewrite" if args.rewrite else ""),
        "rewrites": [{"q": q, "rewritten": r} for q, r in rewrites],
        "overall": {
            "answerable": _answerable_metrics(ans_all),
            "escalation": {
                **_escalation_metrics(esc_all),
                "precision": round(esc_correct / predicted_esc, 4) if predicted_esc else 0.0,
            },
        },
        "by_type": {
            **{t: _answerable_metrics(ans_by_type.get(t, [])) for t in ANSWERABLE_TYPES},
            **{t: _escalation_metrics(esc_by_type.get(t, [])) for t in ESCALATE_TYPES},
        },
    }

    ov_a, ov_e = metrics["overall"]["answerable"], metrics["overall"]["escalation"]
    lines = [
        "# 챗봇 검색 평가 리포트 (유형별)",
        "",
        f"- 답변가능 {ov_a['n']}건: **hit@1 {ov_a['hit1']:.0%}** · hit@3 {ov_a['hit3']:.0%} · "
        f"MRR {ov_a['mrr']:.3f} · confident {ov_a['confident_rate']:.0%}",
        f"- 에스컬레이션 {ov_e['n']}건: **recall {ov_e['recall']:.0%}** · precision {ov_e['precision']:.0%}",
        "",
        "| 유형 | n | hit@1 | hit@3 | MRR | recall |",
        "|---|---|---|---|---|---|",
    ]
    for t in ANSWERABLE_TYPES:
        m = metrics["by_type"][t]
        lines.append(f"| {t} | {m['n']} | {m['hit1']:.0%} | {m['hit3']:.0%} | {m['mrr']:.3f} | — |")
    for t in ESCALATE_TYPES:
        m = metrics["by_type"][t]
        lines.append(f"| {t} | {m['n']} | — | — | — | {m['recall']:.0%} |")

    lines += ["", "## 오답 상세", "", "### 답변가능인데 miss/게이트 오작동"]
    for t in ANSWERABLE_TYPES:
        for q, expected, top_ids, rank, confident in ans_by_type.get(t, []):
            if rank != 0 or not confident:
                lines.append(f"- [{t}] `{q}` → expected {sorted(expected)}, got {top_ids}, "
                             f"rank={rank}, confident={confident}")
    lines += ["", "### 에스컬레이션인데 confident 오판 (환각 위험)"]
    for t in ESCALATE_TYPES:
        for q, confident, top_ids, top_score in esc_by_type.get(t, []):
            if confident:
                lines.append(f"- [{t}] `{q}` → top={top_ids[0]} (bm25={top_score:.2f})")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = "\n".join(lines) + "\n"
    (OUT_DIR / f"chatbot_eval_retrieval{suffix}.md").write_text(report, encoding="utf-8")
    (OUT_DIR / f"chatbot_eval_retrieval{suffix}.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(report)
    print(f"[saved] {OUT_DIR / f'chatbot_eval_retrieval{suffix}.md'}")
    print(f"[saved] {OUT_DIR / f'chatbot_eval_retrieval{suffix}.json'}")

    # --- 클린 A/B 자동 델타 (dense 아암 실행 시, baseline 이 있으면) -------------
    base_path = OUT_DIR / "chatbot_eval_retrieval.json"
    if rewrites:
        print("\n== 리라이팅 발동 케이스 ==")
        for q, r in rewrites:
            print(f"  {q!r} → {r!r}")
    if (args.dense or args.rewrite) and base_path.exists():
        base = json.loads(base_path.read_text(encoding="utf-8"))
        print(f"\n== A/B 델타 ({metrics['arm']} − bm25) — 단일변수 ==")
        for t in ANSWERABLE_TYPES:
            b, d = base["by_type"].get(t, {}), metrics["by_type"].get(t, {})
            if b.get("n"):
                print(f"  {t:<11} hit@1 {b['hit1']:.0%} → {d['hit1']:.0%} ({d['hit1']-b['hit1']:+.0%})  "
                      f"MRR {b['mrr']:.3f} → {d['mrr']:.3f} ({d['mrr']-b['mrr']:+.3f})")
        for t in ESCALATE_TYPES:
            b, d = base["by_type"].get(t, {}), metrics["by_type"].get(t, {})
            if b.get("n"):
                print(f"  {t:<11} recall {b['recall']:.0%} → {d['recall']:.0%} ({d['recall']-b['recall']:+.0%})")
        ba, da = base["overall"]["answerable"], metrics["overall"]["answerable"]
        print(f"  {'overall':<11} hit@1 {ba['hit1']:.0%} → {da['hit1']:.0%} ({da['hit1']-ba['hit1']:+.0%})  "
              f"MRR {ba['mrr']:.3f} → {da['mrr']:.3f} ({da['mrr']-ba['mrr']:+.3f})")


if __name__ == "__main__":
    main()
