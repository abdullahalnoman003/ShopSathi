from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import get_settings


def _check_password(v: str) -> str:
    min_len = get_settings().password_min_length
    if len(v) < min_len:
        raise ValueError(f"Password must be at least {min_len} characters")
    if len(v.encode()) > 72:  # bcrypt limit
        raise ValueError("Password must be at most 72 bytes")
    return v


class SignupRequest(BaseModel):
    shop_name: str = Field(min_length=1, max_length=200)
    owner_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str
    # Extension point (Prompt 3): the plan choice (Free/Basic/Pro) will be added here.

    _pw = field_validator("password")(_check_password)

    @field_validator("shop_name", "owner_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Must not be blank")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    new_password: str

    _pw = field_validator("new_password")(_check_password)


class ShopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    status: str
    created_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: str
    shop_id: int | None
    is_active: bool


class MeResponse(BaseModel):
    user: UserOut
    shop: ShopOut | None


class AuthResponse(MeResponse):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str
