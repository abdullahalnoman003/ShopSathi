from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.auth import _check_password


class StaffCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str

    _pw = field_validator("password")(_check_password)

    @field_validator("full_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Must not be blank")
        return v


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
