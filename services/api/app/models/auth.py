from pydantic import BaseModel


class AuthUser(BaseModel):
    user_id: str
    email: str | None = None
    role: str | None = None
