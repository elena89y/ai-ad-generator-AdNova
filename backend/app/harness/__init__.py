"""AdNova 평가·계측 하네스 (v2) — 담당: 한의정.

모든 생성 실행은 RunLogger 를 통과해야 한다(기록 없는 실험 = 무효).
  - run_logger : RunLogger 컨텍스트 → experiments/runs.jsonl 단일 원장
  - metrics    : identity(DINO/LPIPS)·aesthetic(ImageReward/HPS) 지표 래퍼
  - model_registry : 모델 로드/언로드 + VRAM 원장(합산 상한 강제)
  - report     : runs.jsonl → markdown 집계표

설계 원칙: 서버형 트래킹(MLflow/W&B) 대신 git-friendly JSONL 단일 원장.
  솔로·단일GPU 규모에서 운영비<효익, 이식성 100%, '강제 통과'로 누락 차단.
"""
from .run_logger import RunLogger, RUNS_PATH

__all__ = ["RunLogger", "RUNS_PATH"]
