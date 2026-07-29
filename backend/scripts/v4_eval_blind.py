"""v4 P7 — 블라인드 평가 러너 — 담당: 한의정.

OLD(v4-eval-old 태그, 플래그 전부 off) vs NEW(플래그 on) 산출물을 사람 평가로 판정한다.
이 스크립트는 CPU 순수 도구: 쌍 구성·좌우 무작위화(블라인드 키)·집계·Wilson CI·혼동행렬.
이미지 생성 자체는 워커/GPU 몫이고, 판정은 평가자(3+명) 몫이다.

절차(SSOT P7):
  1. OLD 동결: develop에 `git tag v4-eval-old` + 플래그 전부 off로 30장 생성.
  2. NEW: 같은 입력·시드로 플래그 on 30장 생성 (음식10/음료10/사물10).
  3. make-blind → 좌우 무작위 배치 시트(HTML)+정답 키. 평가자에게는 시트만 전달.
  4. 평가 CSV 수집 → score-blind (선호율+Wilson 95% CI, 도메인별).
  5. 스타일 식별 36장(6무드×6) → score-style (6×6 혼동행렬+오인율 CI).
  6. check → 판정 축별 통과/미달 표. 미달 축은 해당 플래그 off + 기각 기록(V4P7-001).

판정 기준: 선호≥70% / 하드셋 치명 0 / 스타일 오인≤20%(CI 상한 기준) / p95≤110s / 콜 3·2.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import random
import sys
from pathlib import Path

DOMAINS = ("food", "drink", "object")
STYLES = ("editorial", "pop", "realism", "pastel", "monotone", "warm_vintage")


# --- 통계 --------------------------------------------------------------------
def wilson_ci(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score 95% 신뢰구간. n=0이면 (0,1) — 판단 불가를 보수적으로 표현."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


# --- 블라인드 시트 -----------------------------------------------------------------
def make_blind(old_dir: str, new_dir: str, out_dir: str, seed: int = 20260717) -> dict:
    """OLD/NEW 동일 파일명 쌍 → 좌우 무작위 시트(HTML)+정답 키(key.jsonl).

    파일명이 곧 pair_id (예: food_01.png). 평가자에게는 sheet.html만 전달하고
    key.jsonl은 집계 전까지 공개하지 않는다(블라인드 유지).
    """
    old_p, new_p = Path(old_dir), Path(new_dir)
    names = sorted({f.name for f in old_p.glob("*.png")} & {f.name for f in new_p.glob("*.png")})
    if not names:
        sys.exit("OLD/NEW 공통 파일명 쌍 없음")
    rng = random.Random(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    key_rows, cells = [], []
    for name in names:
        pair_id = Path(name).stem
        new_on_left = rng.random() < 0.5
        left = (new_p / name) if new_on_left else (old_p / name)
        right = (old_p / name) if new_on_left else (new_p / name)
        key_rows.append({"pair_id": pair_id, "left": "NEW" if new_on_left else "OLD",
                         "right": "OLD" if new_on_left else "NEW"})
        cells.append(
            f'<div class="pair"><h3>{html.escape(pair_id)}</h3>'
            f'<div class="row"><figure><img src="{left.resolve()}"><figcaption>A(왼쪽)'
            f'</figcaption></figure><figure><img src="{right.resolve()}">'
            f"<figcaption>B(오른쪽)</figcaption></figure></div></div>")
    (out / "key.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in key_rows), encoding="utf-8")
    (out / "sheet.html").write_text(
        '<meta charset="utf-8"><style>body{font-family:sans-serif;background:#111;color:#eee}'
        ".row{display:flex;gap:12px}figure{margin:0}img{width:420px}"
        "figcaption{text-align:center;font-size:13px;padding:4px}</style>"
        "<h2>블라인드 A/B — 각 쌍에서 광고로 더 좋은 쪽(A/B)을 기록하세요</h2>"
        "<p>CSV 형식: rater,pair_id,choice(A|B)</p>" + "\n".join(cells),
        encoding="utf-8")
    print(f"쌍 {len(names)}개 → {out}/sheet.html (평가자 전달) · key.jsonl (비공개)")
    return {"pairs": len(names)}


def score_blind(key_path: str, judgments_csv: str) -> dict:
    """judgments CSV(rater,pair_id,choice A|B) + 키 → NEW 선호율과 Wilson CI.

    pair_id 접두사(food_/drink_/object_)로 도메인별 분해도 낸다.
    """
    key = {json.loads(line)["pair_id"]: json.loads(line)
           for line in Path(key_path).read_text(encoding="utf-8").splitlines() if line.strip()}
    totals: dict[str, list[int]] = {"all": [0, 0]}
    with open(judgments_csv, encoding="utf-8") as fp:
        for row in csv.DictReader(fp):
            pair_id = row["pair_id"].strip()
            choice = row["choice"].strip().upper()
            if pair_id not in key or choice not in ("A", "B"):
                continue
            side = "left" if choice == "A" else "right"
            new_won = key[pair_id][side] == "NEW"
            domain = next((d for d in DOMAINS if pair_id.startswith(d)), "other")
            for bucket in ("all", domain):
                totals.setdefault(bucket, [0, 0])
                totals[bucket][0] += int(new_won)
                totals[bucket][1] += 1
    report = {}
    for bucket, (wins, n) in sorted(totals.items()):
        lo, hi = wilson_ci(wins, n)
        report[bucket] = {"new_wins": wins, "n": n,
                          "preference": round(wins / n, 4) if n else None,
                          "wilson_95": [round(lo, 4), round(hi, 4)]}
    return report


def score_style(judgments_csv: str) -> dict:
    """스타일 식별 CSV(item_id,true_style,guessed_style) → 6×6 혼동행렬 + 오인율 CI.

    판정 기준은 오인율 ≤20%인데 표본이 작으므로(스타일당 6장) 점추정이 아니라
    Wilson CI **상한**으로 본다 — 상한>0.20이면 그 스타일은 미달로 보고한다.
    """
    matrix = {t: {g: 0 for g in STYLES} for t in STYLES}
    with open(judgments_csv, encoding="utf-8") as fp:
        for row in csv.DictReader(fp):
            t = row["true_style"].strip()
            g = row["guessed_style"].strip()
            if t in matrix and g in STYLES:
                matrix[t][g] += 1
    per_style = {}
    total_wrong = total_n = 0
    for t in STYLES:
        n = sum(matrix[t].values())
        wrong = n - matrix[t][t]
        total_wrong += wrong
        total_n += n
        lo, hi = wilson_ci(wrong, n)
        per_style[t] = {"n": n, "misid": wrong,
                        "misid_rate": round(wrong / n, 4) if n else None,
                        "wilson_95": [round(lo, 4), round(hi, 4)],
                        "exceeds_20pct_ci": bool(n and hi > 0.20)}
    lo, hi = wilson_ci(total_wrong, total_n)
    return {"matrix": matrix, "per_style": per_style,
            "overall": {"n": total_n, "misid": total_wrong,
                        "misid_rate": round(total_wrong / total_n, 4) if total_n else None,
                        "wilson_95": [round(lo, 4), round(hi, 4)]}}


def latency_p95(runs_path: str, phase_prefix: str = "V4") -> float | None:
    """runs.jsonl에서 총 소요(p95, 초). timing.total_s 필드 기준."""
    path = Path(runs_path)
    if not path.is_file():
        return None
    vals = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if phase_prefix and not str(row.get("phase", "")).startswith(phase_prefix):
            continue
        total = (row.get("timing") or {}).get("total_s")
        if isinstance(total, (int, float)):
            vals.append(float(total))
    if not vals:
        return None
    vals.sort()
    return vals[min(len(vals) - 1, int(round(0.95 * (len(vals) - 1))))]


# --- CLI ----------------------------------------------------------------------
def _cmd_make_blind(args) -> None:
    make_blind(args.old, args.new, args.out, args.seed)


def _cmd_score_blind(args) -> None:
    report = score_blind(args.key, args.judgments)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    pref = report.get("all", {}).get("preference")
    if pref is not None:
        verdict = "통과" if pref >= 0.70 else "미달"
        print(f"\n판정(선호≥70%): {pref:.1%} → {verdict}")


def _cmd_score_style(args) -> None:
    report = score_style(args.judgments)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    bad = [s for s, r in report["per_style"].items() if r["exceeds_20pct_ci"]]
    print("\n판정(오인≤20%, CI 상한 기준): "
          + ("전 스타일 통과" if not bad else f"미달 스타일 {bad}"))


def _cmd_p95(args) -> None:
    val = latency_p95(args.runs, args.phase_prefix)
    if val is None:
        sys.exit("측정할 run 없음")
    verdict = "통과" if val <= 110 else "미달"
    print(f"p95 = {val:.1f}s (기준 ≤110s) → {verdict}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make-blind")
    m.add_argument("--old", required=True)
    m.add_argument("--new", required=True)
    m.add_argument("--out", required=True)
    m.add_argument("--seed", type=int, default=20260717)
    m.set_defaults(fn=_cmd_make_blind)
    b = sub.add_parser("score-blind")
    b.add_argument("--key", required=True)
    b.add_argument("--judgments", required=True)
    b.set_defaults(fn=_cmd_score_blind)
    s = sub.add_parser("score-style")
    s.add_argument("--judgments", required=True)
    s.set_defaults(fn=_cmd_score_style)
    p = sub.add_parser("p95")
    p.add_argument("--runs", default=str(Path(__file__).resolve().parents[1]
                                         / "experiments" / "runs.jsonl"))
    p.add_argument("--phase-prefix", default="V4")
    p.set_defaults(fn=_cmd_p95)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
