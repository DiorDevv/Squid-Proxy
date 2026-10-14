from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # The username. An email address is still accepted (looked up against
    # the optional contact email) so people who signed in by email before
    # username login existed aren't stranded.
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(max_length=256)


class LoginResponse(BaseModel):
    """Doubles as the response for both login's two possible outcomes on a
    TOTP-enabled account, rather than a separate response type per step --
    `mfa_required=True` means only `challenge_token` is set (password was
    right, but the code is still needed via POST /auth/login/verify-mfa);
    otherwise this is a normal completed login and the token fields are
    populated, exactly as before TOTP existed. A non-2FA account's login
    never sets mfa_required at all, so its response shape is unchanged."""

    access_token: str | None = None
    token_type: str = "bearer"
    expires_in_seconds: int | None = None
    role: str | None = None
    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    # Scope tag (core/branch_scope.scope_tag) -- None only when unrestricted.
    branch: str | None = None
    # [] = every branch; otherwise the branches this account is limited to.
    branches: list[str] = Field(default_factory=list)
    # Effective feature permissions (core/permissions.py).
    permissions: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    # True: the account is on an admin-issued temporary password -- every
    # route but GET /me and POST /password answers 403 until it's changed.
    must_change_password: bool = False
    mfa_required: bool = False
    challenge_token: str | None = None


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in_seconds: int


class VerifyMfaRequest(BaseModel):
    challenge_token: str
    code: str


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class TotpConfirmRequest(BaseModel):
    code: str


class TotpConfirmResponse(BaseModel):
    recovery_codes: list[str]


class TotpDisableRequest(BaseModel):
    password: str


class TotpStatusResponse(BaseModel):
    enabled: bool


class MeResponse(BaseModel):
    id: str
    username: str
    full_name: str
    email: str | None
    role: str
    branch: str | None
    # Filled in by the route: [] = every branch, and the effective
    # permissions (not the stored override).
    branches: list[str] | None = None
    permissions: list[str] | None = None
    expires_at: datetime | None = None
    must_change_password: bool
    totp_enabled: bool
    password_changed_at: datetime | None
    last_login_at: datetime | None


class ReauthRequest(BaseModel):
    password: str = Field(max_length=256)


class ReauthResponse(BaseModel):
    valid_minutes: int


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class ChangePasswordResponse(BaseModel):
    # Sign-ins on other devices closed by the change.
    sessions_closed: int


class SessionOut(BaseModel):
    id: str
    ip: str | None
    user_agent: str | None
    started_at: datetime | None
    last_seen_at: datetime | None
    expires_at: datetime
    current: bool


class SessionsRevokedResponse(BaseModel):
    closed: int
