# 알림 API

## 사용자 알림 설정

- `GET /api/account/notifications`
- `PATCH /api/account/notifications`

`credit_depletion_alert`를 켜면 생성 성공 후 전체 잔여 크레딧이 1개 이하일 때 알림 메일을 받습니다.
`marketing_updates`를 켜면 관리자가 발송한 마케팅 메일을 받을 수 있습니다.

## 관리자 마케팅 메일

`POST /api/admin/notifications/marketing`

```json
{
  "subject": "AdNova 새 소식",
  "message": "새로운 템플릿이 추가됐어요.",
  "user_ids": [1, 2]
}
```

`user_ids`를 생략하면 마케팅 수신에 동의한 활성 사용자 전체를 대상으로 합니다.
응답에는 발송 대상 수, 성공 수, 실패 수가 포함되며 발송 작업은 관리자 감사 로그에 기록됩니다.
