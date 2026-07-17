# AdNova 관리자 백엔드 연동 안내

## 1. 포함된 변경 사항

- 실제 관리자 권한을 로그인 응답에 포함
- 회원 조회, 활성/정지, 플랜 변경 관리자 API
- 전체 결제 내역 관리자 API
- 환불 신청, 승인, 거절, 관리자 직접 환불 API
- 1:1 문의 등록, 조회, 관리자 답변 API
- 관리자 비밀번호 변경 API
- 관리자 변경 작업 `admin_logs` 기록
- 관리자 페이지의 임시 데이터 모드 해제

## 2. 파일 반영

이 압축 파일의 `backend/`와 `frontend/`를 프로젝트 최상위 폴더에 덮어씁니다.
새로 추가되는 파일은 다음과 같습니다.

- `backend/app/api/support.py`
- `backend/app/schemas/support.py`
- `backend/app/scripts/seed_admin.py`

## 3. 일반 사용자 로그인 함수 수정

일반 `frontend/html/index.html`에서 기존 `handleLogin` 함수 전체를 아래 코드로 교체합니다.
기존에 프론트에서 `admin/admin`을 직접 검사하던 임시 코드는 삭제해야 합니다.

```javascript
async function handleLogin(e){
  if(e) e.preventDefault();

  const username=document.getElementById('loginUsername').value.trim();
  const password=document.getElementById('loginPassword').value;

  if(!username){toast('아이디를 입력해주세요.');return;}
  if(!password){toast('비밀번호를 입력해주세요.');return;}

  // 일반 회원은 7~12자이며, DB에 등록된 기본 관리자 admin은 예외로 허용합니다.
  if(username!=='admin' && !USERNAME_PATTERN.test(username)){
    toast('아이디는 영문과 숫자를 사용해 7~12자로 입력해주세요.');
    return;
  }

  try{
    const data=await loginWithCredentials(username,password);
    const user=data?.user || getStoredUser();

    if(user?.is_admin===true || user?.role==='admin'){
      toast('관리자로 로그인되었습니다.');
      window.location.href='./admin/';
      return;
    }

    toast('로그인되었습니다.');
    go('dashboard');
  }catch(err){
    toast(err.message || '로그인에 실패했습니다.');
  }
}
```

## 4. 관리자 계정 생성

프로젝트 최상위 폴더에서 다음을 실행합니다.

```bash
cd backend
python3 -m app.scripts.seed_admin
cd ..
```

Docker로 백엔드를 실행 중이라면 다음 명령을 사용합니다.

```bash
docker compose exec backend python -m app.scripts.seed_admin
```

초기 계정은 `admin / admin`입니다. 로그인 후 관리자 페이지에서 강한 비밀번호로 즉시 변경합니다.

## 5. 서버 재시작

현재 사용하는 실행 방식에 맞춰 백엔드를 재시작합니다. 시작 시 새 테이블
`refund_requests`, `inquiries`, `admin_logs`가 생성됩니다.

## 6. 추가된 API

- `GET /api/admin/users`
- `PATCH /api/admin/users/{user_id}/status`
- `PATCH /api/admin/users/{user_id}/subscription`
- `GET /api/admin/payments`
- `POST /api/admin/refunds`
- `POST /api/admin/refunds/{refund_id}/approve`
- `POST /api/admin/refunds/{refund_id}/reject`
- `GET /api/admin/inquiries`
- `POST /api/admin/inquiries/{inquiry_id}/reply`
- `PATCH /api/admin/password`
- `POST /api/inquiries`
- `GET /api/inquiries`
- `POST /api/refunds`
- `GET /api/refunds`

모든 `/api/admin/*` API는 JWT 로그인과 `admin_accounts` 권한을 백엔드에서 검사합니다.
