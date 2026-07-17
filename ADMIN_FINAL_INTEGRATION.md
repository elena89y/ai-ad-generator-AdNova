# AdNova 관리자 기능 실행 안내

## 포함 기능

- 관리자 권한 로그인 및 `/admin/` 이동
- 회원 상태와 프리미엄 플랜 변경
- 구매 이력 조회 및 회원/상호명 검색
- 환불 신청 조회, 승인, 거절, 처리 내역 조회
- 1:1 문의 조회 및 답변
- 관리자 비밀번호 변경과 작업 로그

## 최초 실행

프로젝트 루트의 `.env.example`을 `.env`로 복사하고 `SECRET_KEY`, DB 설정,
`ADMIN_PASSWORD`를 실제 값으로 변경합니다. 운영 환경에서는 기본 비밀번호
`admin`을 사용하지 않습니다.

```bash
cd backend
python -m app.scripts.seed_admin
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

다른 터미널에서 프론트를 실행합니다.

```bash
cd frontend/html
python3 -m http.server 5500 --bind 127.0.0.1
```

일반 페이지는 `http://127.0.0.1:5500/`, 관리자 페이지는 관리자 계정으로
로그인한 뒤 `http://127.0.0.1:5500/admin/`에서 확인합니다.

## DB 구조

기존 `users`, `purchase_histories`, `subscriptions` 테이블을 그대로 사용하며
환불 요청 상태만 `refund_requests` 테이블에 저장합니다. 애플리케이션 시작 시
`Base.metadata.create_all()`이 새 테이블을 생성합니다.

## API

- `GET /api/admin/users`
- `PATCH /api/admin/users/{id}/status`
- `PATCH /api/admin/users/{id}/subscription`
- `GET /api/admin/purchases`
- `GET /api/admin/refunds`
- `POST /api/admin/refunds/{id}/approve`
- `POST /api/admin/refunds/{id}/reject`
- `PATCH /api/admin/inquiries/{id}/answer`
- `PATCH /api/admin/password`
- `POST /api/billing/purchases/{id}/refund-request`

관리자 API는 백엔드에서 관리자 권한을 검증하며, 환불 승인·거절과 구독 변경은
`super_admin` 권한이 필요합니다.
