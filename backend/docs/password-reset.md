# 비밀번호 재설정

## 요청

`POST /api/auth/password-reset/request`

```json
{ "email": "user@example.com" }
```

가입 여부와 관계없이 같은 안내를 반환합니다. 가입된 계정이면 30분 동안 한 번 사용할 수 있는 재설정 링크를 SMTP 이메일로 보냅니다.

## 확인

`POST /api/auth/password-reset/confirm`

```json
{ "token": "메일의 토큰", "new_password": "NewPassword1!" }
```

성공하면 토큰을 폐기하고 기존 사용자 refresh token을 모두 폐기합니다. 메일 링크의 프론트 주소는 `FRONTEND_URL` 환경변수를 사용합니다.
