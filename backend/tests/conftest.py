"""테스트 전역 설정 — 담당: 한의정.

RETENTION_PURGE_ENABLED=0: TestClient 로 app.main 을 띄우는 테스트가 startup 훅으로
리텐션 파기 스케줄러를 실 DB(SessionLocal)에서 돌리지 않도록 하는 안전 기본값
(연정님 #202 리뷰 요청, 2026-07-22). setdefault 라 개별 테스트가 명시적으로 켤 수 있음.
"""
import os

os.environ.setdefault("RETENTION_PURGE_ENABLED", "0")
