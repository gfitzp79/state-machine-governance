"""Identity API: authentication, users, notifications, audit trail."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.core.errors import Conflict, Forbidden, NotFound
from app.core.governance import governance
from app.core.security import CurrentUser, DbSession, create_token, hash_password, verify_password
from app.modules.identity.models import (
    APP_ROLES,
    ROLE_LEVELS,
    SENIORITY,
    AuditLog,
    Notification,
    User,
    UserRole,
)

router = APIRouter(tags=["identity"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8)
    job_title: str | None = None
    seniority: str = "Manager"
    roles: list[str] = []


class UserUpdate(BaseModel):
    full_name: str | None = None
    job_title: str | None = None
    seniority: str | None = None
    roles: list[str] | None = None


def _user_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "job_title": user.job_title,
        "seniority": user.seniority,
        "roles": list(user.role_names),
        "role_level": user.max_role_level,
        "is_active": user.is_active,
    }


@router.post("/auth/login")
def login(payload: LoginRequest, session: DbSession) -> dict[str, Any]:
    user = session.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise Forbidden("invalid email or password")
    if not user.is_active:
        raise Forbidden("this account is deactivated")
    return {
        "token": create_token(user.id, user.email, list(user.role_names)),
        "user": _user_dict(user),
    }


@router.get("/auth/me")
def me(user: CurrentUser) -> dict[str, Any]:
    return _user_dict(user)


@router.get("/users")
def list_users(
    session: DbSession,
    user: CurrentUser,
    role: list[str] = Query(default=[]),
    active_only: bool = Query(True),
) -> list[dict[str, Any]]:
    """Users, optionally narrowed to those holding any of the named roles.

    `role` is repeatable and matches on a prefix, so `role=AppSec` covers
    AppSec_Lead and AppSec_Engineer. An unknown role name is a 409 rather than
    an empty list: a typo in a caller should not look like "nobody holds this".
    """
    unknown = [
        r for r in role if not any(known.startswith(r) for known in APP_ROLES)
    ]
    if unknown:
        raise Conflict("unknown roles: " + ", ".join(unknown))

    users = session.execute(select(User).order_by(User.full_name)).scalars().all()
    if active_only:
        users = [u for u in users if u.is_active]
    if role:
        users = [
            u
            for u in users
            if any(held.startswith(r) for r in role for held in u.role_names)
        ]
    return [_user_dict(u) for u in users]


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    if not user.has_role("Admin", "CISO"):
        raise Forbidden("creating users requires Admin or CISO")
    if session.execute(select(User).where(User.email == payload.email)).first():
        raise Conflict("a user with that email already exists")
    invalid = [r for r in payload.roles if r not in APP_ROLES]
    if invalid:
        raise Conflict("unknown roles: " + ", ".join(invalid))

    created = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        job_title=payload.job_title,
        seniority=payload.seniority,
    )
    session.add(created)
    session.flush()
    for role in payload.roles:
        session.add(UserRole(user_id=created.id, role=role))
    session.commit()
    session.refresh(created)
    return _user_dict(created)


@router.patch("/users/{user_id}")
def update_user(
    user_id: str, payload: UserUpdate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    if not user.has_role("Admin", "CISO"):
        raise Forbidden("updating users requires Admin or CISO")
    target = session.get(User, user_id)
    if target is None:
        raise NotFound("user not found")
    if payload.full_name is not None:
        target.full_name = payload.full_name
    if payload.job_title is not None:
        target.job_title = payload.job_title
    if payload.seniority is not None:
        target.seniority = payload.seniority
    if payload.roles is not None:
        invalid = [r for r in payload.roles if r not in APP_ROLES]
        if invalid:
            raise Conflict("unknown roles: " + ", ".join(invalid))
        for existing in list(target.roles):
            session.delete(existing)
        session.flush()
        for role in payload.roles:
            session.add(UserRole(user_id=target.id, role=role))
    session.commit()
    session.refresh(target)
    return _user_dict(target)


@router.get("/roles")
def roles(user: CurrentUser) -> dict[str, Any]:
    return {
        "roles": list(APP_ROLES),
        "levels": ROLE_LEVELS,
        "seniority": list(SENIORITY),
        "definitions": governance.role_definitions,
        "ownership_by_severity": governance.ownership_by_severity,
    }


@router.get("/notifications")
def notifications(
    session: DbSession, user: CurrentUser, unread_only: bool = Query(False)
) -> list[dict[str, Any]]:
    stmt = select(Notification).where(Notification.recipient_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    rows = session.execute(stmt.order_by(Notification.created_at.desc()).limit(100)).scalars()
    return [
        {
            "id": n.id,
            "entity_type": n.entity_type,
            "entity_id": n.entity_id,
            "event_type": n.event_type,
            "title": n.title,
            "body": n.body,
            "is_read": n.is_read,
            "created_at": n.created_at,
        }
        for n in rows
    ]


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    notification = session.get(Notification, notification_id)
    if notification is None or notification.recipient_id != user.id:
        raise NotFound("notification not found")
    notification.is_read = True
    session.commit()
    return {"ok": True}


@router.get("/audit")
def audit(
    session: DbSession,
    user: CurrentUser,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(100, le=500),
) -> list[dict[str, Any]]:
    """The audit trail is append-only at the database layer, so this is a read of
    what actually happened rather than a reconstruction."""
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    rows = session.execute(stmt.order_by(AuditLog.created_at.desc()).limit(limit)).scalars()
    users = {u.id: u.full_name for u in session.execute(select(User)).scalars()}
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_name": users.get(r.user_id or "", "system"),
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "action": r.action,
            "changed_fields": r.changed_fields,
            "created_at": r.created_at,
        }
        for r in rows
    ]
