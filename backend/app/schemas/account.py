import re

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import PASSWORD_PATTERN


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=20)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if not re.match(PASSWORD_PATTERN, value):
            raise ValueError(
                "비밀번호는 8~20자이며 영문 대문자, 영문 소문자, 숫자, "
                "특수문자를 각각 최소 1개 이상 포함해야 합니다."
            )
        return value


class AccountDeleteRequest(BaseModel):
    current_password: str = Field(min_length=1)


class AccountMessageResponse(BaseModel):
    message: str
