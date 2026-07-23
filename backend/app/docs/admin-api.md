# 관리자 계정 및 감사 로그

## 관리자 계정 생성

`POST /api/admin/accounts`는 최고 관리자만 호출할 수 있습니다.

```json
{
  "username": "adminuser",
  "email": "admin@example.com",
  "password": "Password1!",
  "name": "관리자",
  "role": "operator"
}
```

일반 회원을 관리자 권한으로 변경하지 않고, 새 사용자 계정과 관리자 계정을 함께 생성합니다. 생성된 계정은 `/api/auth/admin-login`에서만 로그인할 수 있습니다.

## 관리자 로그인 실패 기록

`POST /api/auth/admin-login`이 실패하면 시도한 아이디, 실패 사유, 시간만 기록합니다. 비밀번호와 인증 토큰은 저장하지 않습니다.

`GET /api/admin/audit-logs`는 기존 관리자 작업 기록과 관리자 로그인 실패 기록을 시간순으로 함께 반환합니다. 로그인 실패 기록의 `action` 값은 `admin.login_failed`입니다.

## 보너스 크레딧 지급

`POST /api/admin/users/{user_id}/bonus-credits`는 최고 관리자만 호출할 수 있습니다.

```json
{
  "amount": 10
}
```

`amount`는 1~10,000 사이의 정수입니다. 보너스 크레딧은 무료 일일 충전과 프리미엄 월간 30개와 별도로 누적되며, 광고 생성 시 가장 먼저 차감됩니다. 지급 작업은 감사 로그에 `user.bonus_credits_granted`로 기록됩니다.
