"""Identity API: authentication, users, notifications, audit trail."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select

from app.core.errors import Conflict, Forbidden, NotFound
from app.core.governance import governance
from app.core.security import CurrentUser, DbSession, create_token, verify_password
from app.modules.identity.admin import MANAGERS, UserAdmin, accountabilities, traces
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
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    job_title: str | None = None
    seniority: str | None = None
    roles: list[str] | None = None


class DeactivateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class PasswordReset(BaseModel):
    password: str = Field(min_length=8)


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
        "deactivated_at": user.deactivated_at,
    }


@router.post("/auth/login")
def login(payload: LoginRequest, session: DbSession) -> dict[str, Any]:
    user = session.execute(
        select(User).where(func.lower(User.email) == payload.email.strip().lower())
    ).scalar_one_or_none()
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
    created = UserAdmin(session, user).create(**payload.model_dump())
    session.commit()
    return _user_dict(created)


@router.get("/users/{user_id}")
def get_user(user_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    """One account, with what it is accountable for. The accountability list is
    what a deactivation or a role removal would be refused over (USR-3)."""
    target = session.get(User, user_id)
    if target is None:
        raise NotFound("user not found")
    body = _user_dict(target)
    if user.has_role(*MANAGERS):
        body["accountable_for"] = accountabilities(session, target.id)
        body["deletable"] = not traces(session, target.id) and target.id != user.id
    return body


@router.patch("/users/{user_id}")
def update_user(
    user_id: str, payload: UserUpdate, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    target = UserAdmin(session, user).update(user_id, **payload.model_dump())
    session.commit()
    return _user_dict(target)


@router.post("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: str, payload: DeactivateRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    target = UserAdmin(session, user).deactivate(user_id, payload.reason)
    session.commit()
    return _user_dict(target)


@router.post("/users/{user_id}/reactivate")
def reactivate_user(user_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    target = UserAdmin(session, user).reactivate(user_id)
    session.commit()
    return _user_dict(target)


@router.post("/users/{user_id}/password")
def reset_password(
    user_id: str, payload: PasswordReset, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    UserAdmin(session, user).reset_password(user_id, payload.password)
    session.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    summary = UserAdmin(session, user).delete(user_id)
    session.commit()
    return {"deleted": summary}


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
