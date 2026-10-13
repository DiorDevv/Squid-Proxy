from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class UserSummary(BaseModel):
    id: str
    username: str
    full_name: str
    email: str | None = None
    note: str | None = None
    role: UserRole
    branch: str | None = None
    is_active: bool
    must_change_password: bool
    totp_enabled: bool
    last_login_at: datetime | None = None
    last_login_ip: str | None = None
    password_changed_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime
    # Filled in by the route, not stored on the row.
    active_sessions: int = 0
    # Too many recent failed sign-ins (see core.security.LoginThrottle) --
    # an admin can clear it with POST /{id}/unlock.
    throttled: bool = False


class UserCreateRequest(BaseModel):
    # Normalized/validated in user_service (core.password_policy).
    username: str = Field(min_length=1, max_length=64)
    full_name: str = Field(default="", max_length=120)
    note: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    role: UserRole = UserRole.VIEWER
    # None (default) is unrestricted. Set to one of
    # Settings.effective_log_sources' branch tags to scope this account to
    # that branch's data only. Must stay None for a super admin.
    branch: str | None = None


class UserCreatedResponse(BaseModel):
    user: UserSummary
    # Shown exactly once -- the user must change it at first sign-in.
    temporary_password: str


class UserProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None


class UserRoleUpdateRequest(BaseModel):
    role: UserRole


class UserBranchUpdateRequest(BaseModel):
    branch: str | None = None


class UserActiveRequest(BaseModel):
    active: bool


class UserPasswordResetResponse(BaseModel):
    user: UserSummary
    temporary_password: str
