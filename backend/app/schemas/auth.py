from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    role: str
    email: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in_seconds: int
