#!/usr/bin/env bash
# 로컬모델 트랙 통합 배치 — 4 arm before/after 를 한 VM 세션에서 "몰아서" (Kontext 1회 로드).
#   1) REAL A/B (finish none/photographic)  2) dessert A/B (재플레이팅 off/on)
#   3) PAL A/B (팔레트 고정/적응)           4) item1 C (studio 강화, DINO)
# 판정: 각 육안(정본) + item1 DINO. 완료 시 sentinel /tmp/localmodel_batch.DONE.
#
# env: CLONE(레포), INPUTS_DIR(입력 이미지), PY(python) — 미지정 시 VM 기본값.
set -u
CLONE="${CLONE:-/home/spai0820/ai-ad-generator-AdNova}"
INPUTS_DIR="${INPUTS_DIR:-$HOME/HOLDOUT_inputs}"
PY="${PY:-$CLONE/.venv/bin/python}"
LOG="${LOG:-/tmp/localmodel_batch.log}"
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
rm -f /tmp/localmodel_batch.DONE /tmp/localmodel_batch.FAIL
cd "$CLONE/backend" || { echo "clone 없음: $CLONE"; touch /tmp/localmodel_batch.FAIL; exit 1; }

{
  echo "=== localmodel batch start $(date -u) | inputs=$INPUTS_DIR ==="
  set -x
  # 1) REAL A/B — 리얼리즘 finish 절 on/off (food/drink 3 × 2)
  $PY scripts/real001_finish_ab.py run --manifest experiments/real001_inputs.yaml \
      --inputs-dir "$INPUTS_DIR" --styles realism || echo "!! REAL 실패"
  # 2) dessert A/B — 재플레이팅 off/on (디저트 2 × 2)
  $PY scripts/scene_env_ab.py run --phase DESSERT-AB --env-key DESSERT_REPLATE \
      --off 0 --on 1 --style editorial --manifest experiments/dessert_inputs.yaml \
      --inputs-dir "$INPUTS_DIR" || echo "!! dessert 실패"
  # 3) PAL A/B — 팔레트 고정/적응 (pop food 2 × 2)
  $PY scripts/scene_env_ab.py run --phase PAL-AB --env-key PAL_ADAPTIVE \
      --off 0 --on 1 --style pop --manifest experiments/pal_inputs.yaml \
      --inputs-dir "$INPUTS_DIR" || echo "!! PAL 실패"
  # 4) item1 C — studio 강화 신생성 + DINO (객체 3; before=로컬 baseline 0.70)
  $PY scripts/item1_cmode_ab.py run --inputs-dir "$INPUTS_DIR" || echo "!! item1-C 실패"
  set +x
  # 요약
  $PY scripts/real001_finish_ab.py summary || true
  $PY scripts/scene_env_ab.py summary --phase DESSERT-AB || true
  $PY scripts/scene_env_ab.py summary --phase PAL-AB || true
  $PY scripts/item1_cmode_ab.py summary || true
  echo "=== localmodel batch done $(date -u) ==="
} > "$LOG" 2>&1

if grep -q "batch done" "$LOG"; then touch /tmp/localmodel_batch.DONE; else touch /tmp/localmodel_batch.FAIL; fi
echo "batch finished — log: $LOG"
