"""Domain 1: Platform and Identity.

Users, RBAC role assignments, the immutable audit log, and the notification
queue that cascade handlers write into.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.governance import governance
from app.core.model_base import Timestamped, UUIDPrimaryKey

# Roles, their seniority ordering and the organisational ladder all come from
# config/governance.yml. Adding a role there makes it assignable; naming it in a
# transition's role list makes it meaningful.
APP_ROLES = governance.roles
ROLE_LEVELS = governance.role_levels
SENIORITY = governance.seniority_ladder


class User(Base, UUIDPrimaryKey, Timestamped):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(200))
    # Organisational seniority, distinct from functional role. Drives the
    # ownership-by-severity matrix and the policy approval rule (PINV-5).
    seniority: Mapped[str] = mapped_column(String(32), nullable=False, default="Manager")
    # Soft delete only. Hard deletion would break audit references.
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def role_names(self) -> tuple[str, ...]:
        return tuple(r.role for r in self.roles)

    @property
    def is_active(self) -> bool:
        return self.deactivated_at is None

    @property
    def max_role_level(self) -> int:
        return max((ROLE_LEVELS.get(r, 0) for r in self.role_names), default=0)

    @property
    def seniority_level(self) -> int:
        return SENIORITY.index(self.seniority) if self.seniority in SENIORITY else 0

    def has_role(self, *roles: str) -> bool:
        return any(r in self.role_names for r in roles)


class UserRole(Base, UUIDPrimaryKey):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_roles_user_role"),)

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(48), nullable=False)

    user: Mapped[User] = relationship(back_populates="roles")


class AuditLog(Base, UUIDPrimaryKey):
    """Immutable. UPDATE and DELETE are rejected by a database trigger."""

    __tablename__ = "audit_log"

    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class Notification(Base, UUIDPrimaryKey):
    __tablename__ = "notifications"

    recipient_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
