from pydantic import BaseModel, ConfigDict

from app.models.user import UserRole


class GoogleCallbackRequest(BaseModel):
    code: str


class UserPublic(BaseModel):
    # Email format already verified upstream (Google OAuth / dev token script);
    # keep permissive so internal TLDs like `.local` round-trip cleanly.
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: UserRole
    is_active: bool


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic


class RefreshRequest(BaseModel):
    refresh_token: str
