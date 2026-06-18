"""User & auth service — register, login, profile."""
import uuid
import hashlib
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.user import User
from server.models.resume import Resume
from server.utils.auth import create_access_token
from server.schemas.user import UserProfile, TokenResponse


def hash_password(password: str) -> str:
    """Simple password hashing with SHA256 + salt."""
    salt = "ai-interviewer-salt"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


class UserService:
    """Handles user registration, login, and profile."""

    async def register(
        self, db: AsyncSession, name: str, email: str, password: str
    ) -> dict:
        """Register a new user.

        Returns:
            dict with user_id, name, email or raises ValueError.
        """
        # Check if email already exists
        result = await db.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError("该邮箱已注册，请直接登录")

        user = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name,
            password_hash=hash_password(password),
        )
        db.add(user)
        await db.flush()

        token = create_access_token(user.id, user.email)
        return {
            "user_id": user.id,
            "name": user.name,
            "email": user.email,
            "access_token": token,
        }

    async def login(
        self, db: AsyncSession, email: str, password: str
    ) -> TokenResponse:
        """Authenticate user and return JWT token with profile."""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or user.password_hash != hash_password(password):
            raise ValueError("邮箱或密码错误")

        token = create_access_token(user.id, user.email)

        # Get latest resume
        result = await db.execute(
            select(Resume)
            .where(Resume.user_id == user.id, Resume.status == "completed")
            .order_by(Resume.created_at.desc())
            .limit(1)
        )
        latest_resume = result.scalar_one_or_none()

        profile = UserProfile(
            id=user.id,
            name=user.name,
            email=user.email,
            has_resume=latest_resume is not None,
            latest_resume_id=latest_resume.id if latest_resume else None,
            tech_stack=latest_resume.tech_stack if latest_resume else None,
            years_experience=latest_resume.years_experience if latest_resume else None,
        )

        return TokenResponse(access_token=token, user=profile)

    async def get_profile(
        self, db: AsyncSession, user_id: str
    ) -> UserProfile:
        """Get user profile with latest resume data auto-bound."""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("用户不存在")

        # Auto-bind: fetch latest completed resume
        result = await db.execute(
            select(Resume)
            .where(Resume.user_id == user_id, Resume.status == "completed")
            .order_by(Resume.created_at.desc())
            .limit(1)
        )
        latest_resume = result.scalar_one_or_none()

        return UserProfile(
            id=user.id,
            name=user.name,
            email=user.email,
            has_resume=latest_resume is not None,
            latest_resume_id=latest_resume.id if latest_resume else None,
            tech_stack=latest_resume.tech_stack if latest_resume else None,
            years_experience=latest_resume.years_experience if latest_resume else None,
        )

    async def get_user_id_by_email(self, db: AsyncSession, email: str) -> str | None:
        """Get user ID by email. Utility for service layer."""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        return user.id if user else None


# Singleton
_user_service: Optional[UserService] = None


def get_user_service() -> UserService:
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service
