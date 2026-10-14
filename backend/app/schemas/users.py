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
    # Scope tag -- None only when unrestricted (kept for older clients).
    branch: str | None = None
    # None/[] = every branch; otherwise the branches this account is limited to.
    branches: list[str] | None = None
    # None = the role's defaults (see `effective_permissions` for the result).
    permissions: list[str] | None = None
    # Filled in by the route.
    effective_permissions: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
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
    # Several branches at once; takes precedence over `branch`. []/None =
    # unrestricted.
    branches: list[str] | None = None
    # None = the role's defaults; a list is the exact set (core/permissions.py).
    permissions: list[str] | None = None
    # Access ends at this moment; None = no end date.
    expires_at: datetime | None = None


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
    # Takes precedence over `branch` when sent. []/None = unrestricted.
    branches: list[str] | None = None


class UserPermissionsUpdateRequest(BaseModel):
    # None restores the role's defaults.
    permissions: list[str] | None = None


class UserExpiryUpdateRequest(BaseModel):
    # None removes the end date.
    expires_at: datetime | None = None


class UserActiveRequest(BaseModel):
    active: bool


class UserPasswordResetResponse(BaseModel):
    user: UserSummary
    temporary_password: str
