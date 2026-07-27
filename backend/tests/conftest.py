"""테스트 전역 설정 — 담당: 한의정.

RETENTION_PURGE_ENABLED=0: TestClient 로 app.main 을 띄우는 테스트가 startup 훅으로
리텐션 파기 스케줄러를 실 DB(SessionLocal)에서 돌리지 않도록 하는 안전 기본값
(연정님 #202 리뷰 요청, 2026-07-22). setdefault 라 개별 테스트가 명시적으로 켤 수 있음.
"""
import os

os.environ.setdefault("RETENTION_PURGE_ENABLED", "0")

# 타이포 z-order 정밀 마스크(rembg birefnet)는 CPU에서 장당 ~24s → 로컬/CI 단위 테스트를
# 막는다. 단위 테스트는 조판 레이아웃 구조만 검증하므로 스튜디오 배경 근사(색거리) 마스크로
# 대체한다. 운영 GPU 워커는 birefnet 세션 상주라 이 스텁과 무관.
# (음식이 TS-1_2 배경 레터링으로 합류하며 다수 테스트가 이 경로를 타게 되어 필요, 2026-07-26.)
from app.services import typography_system as _typography_system  # noqa: E402

_typography_system._subject_mask_precise = _typography_system._subject_mask
