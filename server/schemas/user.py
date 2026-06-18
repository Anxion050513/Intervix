"""User & auth schemas."""
from pydantic import BaseModel, EmailStr


class UserRegister(BaseModel):
    name: str
    email: str  # use str not EmailStr to avoid extra dependency
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserProfile"


class UserProfile(BaseModel):
    id: str
    name: str
    email: str
    has_resume: bool = False
    latest_resume_id: str | None = None
    tech_stack: list | None = None
    years_experience: int | None = None
