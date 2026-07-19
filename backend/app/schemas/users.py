from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class UserSummary(BaseModel):
    id: str
    email: str
    role: UserRole
    created_at: datetime


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    role: UserRole = UserRole.VIEWER


class UserRoleUpdateRequest(BaseModel):
    role: UserRole


class UserPasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=255)
