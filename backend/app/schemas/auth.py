import re

from pydantic import BaseModel, EmailStr, Field, field_validator


PASSWORD_PATTERN = (
    r"^(?=.*[a-z])"
    r"(?=.*[A-Z])"
    r"(?=.*\d)"
    r"(?=.*[@$!%*?&^#()_\-+=])"
    r"[A-Za-z\d@$!%*?&^#()_\-+=]{8,20}$"
)

USERNAME_PATTERN = r"^[A-Za-z0-9]{7,12}$"


class UserCreate(BaseModel):
    email: EmailStr

    username: str = Field(
        ...,
        min_length=7,
        max_length=12,
        description="7~12자의 영문/숫자 아이디",
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=20,
        description="8~20자, 영문 대문자/소문자/숫자/특수문자를 각각 최소 1개 포함",
    )

    name: str | None = Field(
        default=None,
        max_length=15,
        description="사용자 이름",
    )

    business_name: str | None = Field(
        default=None,
        max_length=25,
        description="상호명",
    )

    business_type: str | None = Field(
        default=None,
        max_length=20,
        description="업종",
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not re.match(USERNAME_PATTERN, value):
            raise ValueError(
                "아이디는 영문과 숫자만 사용할 수 있으며 7~12자여야 합니다."
            )
        return value.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.match(PASSWORD_PATTERN, value):
            raise ValueError(
                "비밀번호는 8~20자이며 영문 대문자, 영문 소문자, 숫자, 특수문자를 각각 최소 1개 이상 포함해야 합니다."
            )
        return value


class UserLogin(BaseModel):
    username: str = Field(
        ...,
        min_length=5,
        max_length=12,
        description="일반 계정은 7~12자, 관리자 기본 계정은 admin",
    )
    password: str
    remember_me: bool = False

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if value.lower() == "admin":
            return "admin"
        if not re.match(USERNAME_PATTERN, value):
            raise ValueError(
                "아이디는 영문과 숫자만 사용할 수 있으며 7~12자여야 합니다."
            )
        return value.lower()


class AdminLoginRequest(UserLogin):
    totp_code: str | None = Field(
        default=None,
        pattern=r"^\d{6}$",
        description="TOTP가 설정된 관리자 계정의 6자리 인증 코드",
    )


class UsernameFindRequest(BaseModel):
    email: EmailStr


class UsernameFindResponse(BaseModel):
    username: str


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    username: str | None = None
    name: str | None = None
    business_name: str | None = None
    business_type: str | None = None
    auth_provider: str = "local"
    is_active: bool

    model_config = {
        "from_attributes": True
    }


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class MessageResponse(BaseModel):
    message: str
