"""P7 블라인드 평가 러너 회귀 — 담당: 한의정. 통계·블라인드 키·집계 순수 로직 검증."""
from __future__ import annotations

import json

import pytest
from PIL import Image

from scripts import v4_eval_blind as ev


# --- Wilson CI --------------------------------------------------------------------
def test_wilson_ci_known_values():
    lo, hi = ev.wilson_ci(21, 30)  # 70%
    assert lo == pytest.approx(0.5217, abs=0.01)
    assert hi == pytest.approx(0.8302, abs=0.01)
    assert ev.wilson_ci(0, 0) == (0.0, 1.0)   # 판단 불가는 보수적으로
    lo0, hi0 = ev.wilson_ci(0, 6)
    assert lo0 == pytest.approx(0.0, abs=1e-12)
    assert hi0 > 0.20                          # 6장 전부 정답이어도 CI 상한은 20% 초과


# --- make-blind -------------------------------------------------------------------
def _mk_pairs(tmp_path, names):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    for n in names:
        Image.new("RGB", (8, 8), (10, 10, 10)).save(old / n)
        Image.new("RGB", (8, 8), (200, 200, 200)).save(new / n)
    return old, new


def test_make_blind_writes_key_and_sheet_deterministically(tmp_path):
    names = [f"food_{i:02d}.png" for i in range(6)]
    old, new = _mk_pairs(tmp_path, names)
    out1, out2 = tmp_path / "o1", tmp_path / "o2"
    ev.make_blind(str(old), str(new), str(out1), seed=7)
    ev.make_blind(str(old), str(new), str(out2), seed=7)
    key1 = (out1 / "key.jsonl").read_text()
    assert key1 == (out2 / "key.jsonl").read_text()  # 같은 시드 = 같은 배치(재현성)
    rows = [json.loads(line) for line in key1.splitlines()]
    assert len(rows) == 6
    assert all(sorted((r["left"], r["right"])) == ["NEW", "OLD"] for r in rows)
    sheet = (out1 / "sheet.html").read_text()
    assert "NEW" not in sheet and "OLD" not in sheet  # 시트에는 정답 누출 금지(블라인드)


def test_make_blind_requires_common_pairs(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    Image.new("RGB", (8, 8)).save(old / "only_old.png")
    with pytest.raises(SystemExit):
        ev.make_blind(str(old), str(new), str(tmp_path / "out"))


# --- score-blind ------------------------------------------------------------------
def test_score_blind_counts_new_preference_by_domain(tmp_path):
    key = tmp_path / "key.jsonl"
    key.write_text(
        json.dumps({"pair_id": "food_01", "left": "NEW", "right": "OLD"}) + "\n"
        + json.dumps({"pair_id": "drink_01", "left": "OLD", "right": "NEW"}) + "\n",
        encoding="utf-8")
    judgments = tmp_path / "j.csv"
    judgments.write_text(
        "rater,pair_id,choice\n"
        "r1,food_01,A\n"    # left=NEW → NEW 승
        "r2,food_01,B\n"    # right=OLD → OLD 승
        "r1,drink_01,B\n"   # right=NEW → NEW 승
        "r1,unknown,A\n"    # 키에 없는 쌍 무시
        "r2,drink_01,X\n",  # 잘못된 choice 무시
        encoding="utf-8")

    report = ev.score_blind(str(key), str(judgments))
    assert report["all"]["n"] == 3 and report["all"]["new_wins"] == 2
    assert report["food"] == {"new_wins": 1, "n": 2, "preference": 0.5,
                              "wilson_95": report["food"]["wilson_95"]}
    assert report["drink"]["preference"] == 1.0


# --- score-style ------------------------------------------------------------------
def test_score_style_confusion_matrix_and_ci_flag(tmp_path):
    rows = ["item_id,true_style,guessed_style"]
    # pop 6장 전부 정답, monotone 6장 중 3장을 editorial로 오인
    for i in range(6):
        rows.append(f"p{i},pop,pop")
    for i in range(3):
        rows.append(f"m{i},monotone,monotone")
    for i in range(3, 6):
        rows.append(f"m{i},monotone,editorial")
    judgments = tmp_path / "s.csv"
    judgments.write_text("\n".join(rows), encoding="utf-8")

    report = ev.score_style(str(judgments))
    assert report["matrix"]["pop"]["pop"] == 6
    assert report["matrix"]["monotone"]["editorial"] == 3
    assert report["per_style"]["monotone"]["misid_rate"] == 0.5
    assert report["per_style"]["monotone"]["exceeds_20pct_ci"] is True
    # n=6 표본에선 전부 정답이어도 CI 상한이 20%를 넘는다 — 표본 한계를 숨기지 않는다
    assert report["per_style"]["pop"]["misid_rate"] == 0.0
    assert report["per_style"]["pop"]["exceeds_20pct_ci"] is True
    assert report["overall"]["n"] == 12 and report["overall"]["misid"] == 3


# --- p95 --------------------------------------------------------------------------
def test_latency_p95_filters_phase_and_computes(tmp_path):
    runs = tmp_path / "runs.jsonl"
    rows = [{"phase": "V4P4D", "timing": {"total_s": s}} for s in range(1, 21)]
    rows.append({"phase": "V3P1", "timing": {"total_s": 999}})   # 필터로 제외
    rows.append({"phase": "V4P4D", "timing": {}})                 # total_s 없음 무시
    runs.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    p95 = ev.latency_p95(str(runs), "V4")
    assert p95 == 19.0  # 1..20의 p95(근접 순위법)
    assert ev.latency_p95(str(tmp_path / "none.jsonl")) is None
