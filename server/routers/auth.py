"""Auth API endpoints — register, login, profile."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.services.user_service import UserService, get_user_service
from server.schemas.user import UserRegister, UserLogin, TokenResponse, UserProfile
from server.utils.auth import require_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(
    req: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new account. Returns JWT token + profile on success."""
    # Basic validation
    if not req.email or "@" not in req.email:
        raise HTTPException(status_code=400, detail="请输入有效的邮箱地址")
    if not req.password or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 个字符")
    if not req.name or len(req.name.strip()) < 1:
        raise HTTPException(status_code=400, detail="请输入姓名")

    service = get_user_service()
    try:
        result = await service.register(db, req.name.strip(), req.email.strip(), req.password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Build profile from register result
    profile = UserProfile(
        id=result["user_id"],
        name=result["name"],
        email=result["email"],
        has_resume=False,
    )
    return TokenResponse(access_token=result["access_token"], user=profile)


@router.post("/login", response_model=TokenResponse)
async def login(
    req: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """Login with email + password. Returns JWT token with auto-bound resume data."""
    if not req.email or not req.password:
        raise HTTPException(status_code=400, detail="请输入邮箱和密码")

    service = get_user_service()
    try:
        return await service.login(db, req.email.strip(), req.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=UserProfile)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_user),
):
    """Get current user profile with auto-bound resume data."""
    service = get_user_service()
    try:
        return await service.get_profile(db, current_user["user_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
