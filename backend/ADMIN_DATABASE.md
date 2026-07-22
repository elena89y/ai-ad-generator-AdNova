# 관리자 데이터베이스

관리자 계정, 관리자 감사 로그, 관리자 로그인 실패 로그는 일반 서비스 DB와 분리된 `admin.db`에 저장한다.

## 설정

기본 경로는 `backend/data/admin.db`다. 별도 경로 또는 DB 서버를 사용할 때만 환경 변수로 지정한다.

```env
ADMIN_DATABASE_URL=sqlite:///./data/admin.db
```

## 기존 관리자 계정 이전

기존 일반 DB의 `admin_accounts` 데이터를 새 관리자 DB로 복사한다. 원본 일반 사용자와 기존 테이블은 자동으로 삭제하지 않는다.

```bash
cd backend
python -m app.scripts.migrate_admin_accounts
```

출력된 이전 건수를 확인한 뒤 관리자 페이지 로그인을 점검한다.

## 관리자 계정 생성

최고 관리자는 관리자 페이지에서 계정을 생성할 수 있다. 서버에서 초기 계정을 준비해야 할 때는 아래 스크립트를 사용한다.

```bash
cd backend
python scripts/create_admin.py admin admin@adnova.local 'Password1!' --role super_admin
```

개발 환경의 기본 계정만 만들거나 갱신할 때는 다음 명령을 사용한다.

```bash
cd backend
python -m app.scripts.seed_admin
```

`seed_admin`은 `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` 환경 변수를 사용하며, 이미 같은 아이디가 있으면 비밀번호와 역할을 갱신한다.
