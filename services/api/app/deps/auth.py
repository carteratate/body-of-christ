from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.verify import verify_supabase_jwt
from app.models.auth import AuthUser

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    return await verify_supabase_jwt(credentials.credentials)
