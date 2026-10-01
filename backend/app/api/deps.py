from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_access_token
from app.models import User

_bearer = HTTPBearer(auto_error=False)
DENYLIST_PREFIX = "jwt:deny:"


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def get_token_payload(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    if creds is None:
        raise _unauthorized()
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError:
        raise _unauthorized("Invalid or expired token")
    if get_redis().exists(DENYLIST_PREFIX + payload["jti"]):
        raise _unauthorized("Token has been revoked")
    return payload


def get_current_user(
    payload: dict[str, Any] = Depends(get_token_payload), db: Session = Depends(get_db)
) -> User:
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise _unauthorized()
    if user.shop is not None and user.shop.status == "suspended":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Shop suspended")
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
        return user

    return checker


def get_current_shop_id(user: User = Depends(get_current_user)) -> int:
    """The only way shop-scoped endpoints obtain the shop id. Never take shop_id from the client."""
    if user.shop_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This endpoint needs a shop account")
    return user.shop_id
