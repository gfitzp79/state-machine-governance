"""Authentication and request-scoped identity.

Local password auth with JWT bearer tokens. The role claims in the token are the
`actor_roles` the state machine consults when deciding whether a caller may fire
a transition, so the token is the identity boundary for gate enforcement.

In a deployment with an OIDC provider, swap `authenticate` for token validation
against the provider and map group claims onto the same role list. Nothing else
in the codebase changes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends, Header
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_session
from app.core.errors import Forbidden

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_token(user_id: str, email: str, roles: list[str]) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "roles": roles,
        "exp": expires,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise Forbidden("invalid or expired token") from exc


def get_current_user(
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
):
    from app.modules.identity.models import User

    if not authorization or not authorization.lower().startswith("bearer "):
        raise Forbidden("authentication required")
    claims = decode_token(authorization.split(" ", 1)[1])
    user = session.get(User, claims.get("sub"))
    if user is None or not user.is_active:
        raise Forbidden("user not found or deactivated")
    return user


CurrentUser = Annotated[Any, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_session)]
