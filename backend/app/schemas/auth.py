from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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
    email: str | None = None
    branch: str | None = None
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
