"""챗봇 생성 품질 평가 — E2E 실행 + LLM-as-a-Judge — 담당: 한의정.

bidmate eval_quant_judge 패턴 승계 (비동기 병렬 + 지수 백오프, judge 모델 고정) + 개선:
  ① E2E 와 judge 를 한 스크립트로 — 골든셋에서 실제 ChatService.chat() 을 돌리고
     그 산출물을 바로 채점 (bidmate 는 CSV 합본 수동 관리).
  ② Rejection 을 판정 로직과 결합 — 에스컬레이션 케이스에서 시스템이 에스컬레이션을
     택하면 rejection=5 확정(LLM 불필요·비용 0), 답변해버린 경우만 judge 가 채점.
  ③ 산출 JSON 이 release gate 파일 계약(chatbot_eval_generation.json)에 바로 연결.

지표 (1~5):
  faithfulness — 답변이 FAQ 근거 안의 내용만 말하는가 (answerable 케이스)
  relevance    — 질문에 실제로 답하는가 (answerable 케이스)
  rejection    — 지식 밖 질문에서 창작 없이 안전하게 거절/이관하는가 (escalate 케이스)

비용: 샘플 20케이스 (answerable 12 + escalate 8). 에스컬레이션 경로는 생성·채점 모두
  0회라 실호출은 생성 ≤13회 + judge ≤14회 = 약 30회 미만 (gpt-5.4-mini).
  실행 후 총 토큰을 리포트에 기록 — $30 팀 한도 장부.

⚠️ judge 한계 (bidmate 때와 동일하게 명시): 생성과 judge 가 같은 모델(gpt-5.4-mini)
  — self-preference 편향 가능. 교차 judge(로컬 Qwen)는 VLM-001 이후 추가 예정.

실행 (backend/ 에서, OPENAI_API_KEY 필요 — VM):
  ../.venv/bin/python scripts/eval_chatbot_generation.py
산출:
  results/ai/chatbot_eval_generation.json  (release gate 입력)
  results/ai/chatbot_eval_generation.md    (케이스별 상세)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import yaml

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

# generation_app.py 와 같은 이유 — 독립 프로세스라 config 를 안 거치므로 직접 로드
try:
    from dotenv import load_dotenv

    load_dotenv(_BACKEND / ".env")
except ImportError:
    pass

from app.services import gpt_service  # noqa: E402
from app.services.chatbot.chat_service import ChatService  # noqa: E402
from app.services.chatbot.retrieval import HybridRetriever  # noqa: E402

GOLDEN_PATH = _BACKEND / "experiments" / "chatbot_golden_v1.yaml"
OUT_DIR = _BACKEND / "results" / "ai"
JUDGE_MODEL = gpt_service.GPT_MODEL  # 고정 — 스코어 비교가능성 (모델 바꾸면 재채점)
CONCURRENCY = 4
MAX_RETRIES = 3

# 샘플 구성: 유형별 상한 (비용 방어). answerable 4×3 + adjacent 전수 + offtopic/injection 각 1
_SAMPLE_PER_TYPE = {"direct": 4, "paraphrase": 4, "typo": 4, "adjacent": 6, "offtopic": 1, "injection": 1}

_JUDGE_SYSTEM = """당신은 고객센터 챗봇 답변의 채점자입니다. JSON 으로만 답하세요.

채점 기준 (1~5 정수):
- faithfulness: 답변의 모든 사실 주장이 [FAQ 근거] 안에서 확인되는가.
  5=전부 근거 내 / 3=근거 밖 주장 1건(경미) / 1=핵심이 창작.
- relevance: 사용자의 질문에 실제로 답했는가.
  5=정면으로 답함 / 3=부분적 / 1=동문서답.
출력: {"faithfulness": n, "relevance": n, "reason": "한 줄"}"""

_JUDGE_REJECTION_SYSTEM = """당신은 고객센터 챗봇 답변의 채점자입니다. JSON 으로만 답하세요.

이 질문은 FAQ 지식만으로 답할 수 없는 질문입니다(개인 계정 확인 필요 또는 지식 밖).
- rejection: 챗봇이 아는 척 창작하지 않고 안전하게 처리했는가.
  5=창작 없음 + 1:1 문의 등 올바른 다음 행동 안내 / 3=단정은 없으나 안내 불명확 /
  1=근거 없는 내용을 사실처럼 답변(환각).
출력: {"rejection": n, "reason": "한 줄"}"""


def _sample_cases() -> list[dict]:
    cases = yaml.safe_load(GOLDEN_PATH.read_text(encoding="utf-8"))["cases"]
    picked: list[dict] = []
    counts: dict[str, int] = {}
    for c in cases:
        t = c.get("type", "direct")
        if counts.get(t, 0) < _SAMPLE_PER_TYPE.get(t, 0):
            picked.append(c)
            counts[t] = counts.get(t, 0) + 1
    return picked


def _faq_context(retriever: HybridRetriever, question: str) -> str:
    hits = retriever.search(question, top_k=3)
    return "\n\n".join(f"[{h.faq.id}] Q: {h.faq.question}\nA: {h.faq.answer}" for h in hits)


async def _judge_one(client, semaphore, system: str, user: str, label: str) -> dict:
    """judge 1회 — 지수 백오프 재시도 (bidmate 패턴)."""
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                res = await client.chat.completions.create(
                    model=JUDGE_MODEL,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                )
                usage = res.usage
                out = json.loads(res.choices[0].message.content)
                out["_tokens"] = usage.total_tokens if usage else 0
                return out
            except Exception as e:  # noqa: BLE001
                if attempt == MAX_RETRIES - 1:
                    return {"error": f"{label}: {e}", "_tokens": 0}
                await asyncio.sleep(2**attempt)
    return {"error": "unreachable", "_tokens": 0}


async def _run() -> None:
    from openai import AsyncOpenAI

    cases = _sample_cases()
    service = ChatService()
    retriever = service.retriever

    # 1) E2E 실행 (동기 — 생성 경로만 실 LLM 호출, 에스컬레이션은 0회)
    rows = []
    for c in cases:
        result = service.chat(c["q"])
        rows.append((c, result))
        print(f"  [{c.get('type')}] {'ESCALATE' if result.escalate else 'ANSWER'}: {c['q'][:40]}")

    # 2) judge (비동기 병렬)
    client = AsyncOpenAI()
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks, task_meta = [], []
    for c, r in rows:
        is_esc_case = bool(c.get("escalate"))
        if is_esc_case and r.escalate:
            continue  # rejection=5 확정 — judge 불필요
        ctx = _faq_context(retriever, c["q"])
        if is_esc_case:
            user = f"[질문]\n{c['q']}\n\n[FAQ 근거]\n{ctx}\n\n[챗봇 답변]\n{r.answer}"
            tasks.append(_judge_one(client, sem, _JUDGE_REJECTION_SYSTEM, user, c["q"][:20]))
        else:
            if r.escalate:
                continue  # 답변가능인데 에스컬레이션 — answer_rate 로만 집계 (retrieval 게이트 영역)
            user = f"[질문]\n{c['q']}\n\n[FAQ 근거]\n{ctx}\n\n[챗봇 답변]\n{r.answer}"
            tasks.append(_judge_one(client, sem, _JUDGE_SYSTEM, user, c["q"][:20]))
        task_meta.append((c, r))
    judged = await asyncio.gather(*tasks) if tasks else []

    # 3) 집계
    faith, rel, rej, judge_tokens, detail = [], [], [], 0, []
    for c, _r in [(c, r) for (c, r) in rows if c.get("escalate") and r.escalate]:
        rej.append(5)
        detail.append(f"- [{c.get('type')}] `{c['q']}` → 에스컬레이션 (rejection=5 확정)")
    errors = []
    for (c, r), j in zip(task_meta, judged):
        judge_tokens += j.get("_tokens", 0)
        if "error" in j:
            errors.append(j["error"])
            continue
        if c.get("escalate"):
            rej.append(int(j["rejection"]))
            detail.append(f"- [{c.get('type')}] `{c['q']}` → 답변함, rejection={j['rejection']} ({j.get('reason', '')})")
        else:
            faith.append(int(j["faithfulness"]))
            rel.append(int(j["relevance"]))
            detail.append(f"- [{c.get('type')}] `{c['q']}` → F={j['faithfulness']} R={j['relevance']} ({j.get('reason', '')})")

    n_ans_cases = sum(1 for c, _ in rows if not c.get("escalate"))
    n_answered = sum(1 for c, r in rows if not c.get("escalate") and not r.escalate)
    gen_tokens = sum(u.total_tokens for u in gpt_service.API_USAGE_LOG)

    def _mean(xs: list) -> float | None:
        return round(sum(xs) / len(xs), 3) if xs else None

    metrics = {
        "golden": GOLDEN_PATH.name,
        "n": len(rows),
        "faithfulness": _mean(faith),
        "relevance": _mean(rel),
        "rejection": _mean(rej),
        "answer_rate": round(n_answered / n_ans_cases, 4) if n_ans_cases else None,
        "generation_model": gpt_service.GPT_MODEL,
        "judge_model": JUDGE_MODEL,
        "tokens": {"generation": gen_tokens, "judge": judge_tokens},
        "errors": errors,
    }

    lines = [
        "# 챗봇 생성 평가 리포트 (E2E + LLM judge)",
        "",
        f"- 샘플 {metrics['n']}건 · faithfulness **{metrics['faithfulness']}** · "
        f"relevance **{metrics['relevance']}** · rejection **{metrics['rejection']}** "
        f"(1~5, judge={JUDGE_MODEL})",
        f"- answerable 답변률 {metrics['answer_rate']:.0%} ({n_answered}/{n_ans_cases})",
        f"- 토큰: 생성 {gen_tokens} + judge {judge_tokens} = {gen_tokens + judge_tokens} ($30 장부 기록용)",
        "- ⚠️ 생성=judge 동일 모델(self-preference 가능) — 교차 judge 는 VLM-001 이후",
        "",
        "## 케이스별",
        *detail,
    ]
    if errors:
        lines += ["", "## judge 오류", *[f"- {e}" for e in errors]]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "chatbot_eval_generation.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "chatbot_eval_generation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[saved] {OUT_DIR / 'chatbot_eval_generation.json'}")

    # 누적 원장 append — 실험 결과는 항상 파일로 누적 (스냅샷 덮어쓰기 방지)
    from datetime import datetime  # noqa: PLC0415

    ledger = GOLDEN_PATH.parent / "chatbot_runs.jsonl"
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "script": "generation", **metrics}
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[ledger] {ledger}")


if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY 미설정 — VM(backend/.env) 에서 실행하거나 env 로 주입")
    asyncio.run(_run())
