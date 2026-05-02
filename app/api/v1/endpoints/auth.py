from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.dependencies import get_db
from app.models.user import User
from app.schemas.auth import (
    GoogleCallbackRequest,
    LoginResponse,
    RefreshRequest,
    UserPublic,
)
from app.services import auth_service
from app.services.auth_service import AuthError

router = APIRouter()


@router.get("/google/login")
def google_login():
    """Redirect to Google's consent screen. Frontend just links here."""
    try:
        url = auth_service.build_google_auth_url()
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.post("/google/callback", response_model=LoginResponse)
async def google_callback(
    payload: GoogleCallbackRequest, db: AsyncSession = Depends(get_db)
) -> LoginResponse:
    try:
        user, access, refresh = await auth_service.login_with_google(db, code=payload.code)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    return LoginResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserPublic.model_validate(user),
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    try:
        user, access, new_refresh = await auth_service.refresh_access(
            db, refresh_token=payload.refresh_token
        )
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    return LoginResponse(
        access_token=access,
        refresh_token=new_refresh,
        user=UserPublic.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await auth_service.logout_user(db, user_id=user_id)


@router.get("/me", response_model=UserPublic)
async def me(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user
