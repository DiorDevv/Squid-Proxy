from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class UserSummary(BaseModel):
    id: str
    email: str
    role: UserRole
    branch: str | None = None
    created_at: datetime


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    role: UserRole = UserRole.VIEWER
    # None (default) is unrestricted, same as every user before this field
    # existed. Set to one of Settings.effective_log_sources' branch tags to
    # scope this account to that branch's data only.
    branch: str | None = None


class UserRoleUpdateRequest(BaseModel):
    role: UserRole


class UserBranchUpdateRequest(BaseModel):
    branch: str | None = None


class UserPasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=255)
