from fastapi import APIRouter, Depends

from app.deps.auth import get_current_user
from app.models.auth import AuthUser

router = APIRouter()


@router.get("/me")
async def me(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    return user
