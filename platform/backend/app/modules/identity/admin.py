"""Managing the people the platform holds accountable (codified-rules 2.6).

A user is not just a login here. Owner fields name people, the invariants check
those people hold the role the field implies (ROLE-1), and approvals record who
gave them (ROLE-4). So adding, changing and removing users are governance acts:
taking a role away from someone who owns open risks would leave every one of
those risks failing RINV-15 on its next write, and deactivating them would
leave the risks with an owner who can no longer act.

None of the owner columns carry a foreign key to `users`, so the database would
let a person be deleted out from under their records. Everything below is the
service layer refusing what the schema would allow.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, Text, func, select

from app.core.errors import Conflict, Forbidden, NotFound
from app.core.ownership import ADMIN
from app.core.security import hash_password
from app.engine import AuditTrail
from app.modules.identity.models import APP_ROLES, SENIORITY, AuditLog, Notification, User, UserRole

# USR-1: who may manage users. [CUSTOMISE] in codified-rules 2.6.
MANAGERS = ("Admin", "CISO")


def _accountable_fields() -> list[tuple[Any, Any, dict[str, str | None], str]]:
    """Every field that names a person as accountable, the role it requires
    (ROLE-1), the machine whose terminal states end the accountability, and a
    label. Built from the same role maps the invariants use, so the two cannot
    drift apart."""
    from app.modules.compliance.models import RequirementAssessment
    from app.modules.control.invariants import (
        ACTIVITY_OWNER_ROLES,
        OBJECTIVE_OWNER_ROLES,
        SURFACE_OWNER_ROLES,
    )
    from app.modules.control.machine import CONTROL_ACTIVITY_MACHINE, CONTROL_OBJECTIVE_MACHINE
    from app.modules.control.models import AttackSurface, ControlActivity, ControlObjective
    from app.modules.policy.invariants import POLICY_OWNER_ROLES
    from app.modules.policy.machine import POLICY_MACHINE
    from app.modules.policy.models import Policy
    from app.modules.risk.invariants import OWNER_ROLES
    from app.modules.risk.machine import RISK_MACHINE
    from app.modules.risk.models import Risk
    from app.modules.threat.invariants import MODEL_OWNER_ROLES
    from app.modules.threat.machine import THREAT_MODEL_MACHINE
    from app.modules.threat.models import ThreatModel
    from app.modules.treatment.invariants import TREATMENT_OWNER_ROLES
    from app.modules.treatment.machine import TREATMENT_MACHINE
    from app.modules.treatment.models import Treatment

    return [
        (Risk, RISK_MACHINE, OWNER_ROLES, "risk"),
        (Treatment, TREATMENT_MACHINE, TREATMENT_OWNER_ROLES, "treatment"),
        (ControlObjective, CONTROL_OBJECTIVE_MACHINE, OBJECTIVE_OWNER_ROLES, "control"),
        (ControlActivity, CONTROL_ACTIVITY_MACHINE, ACTIVITY_OWNER_ROLES, "control activity"),
        (Policy, POLICY_MACHINE, POLICY_OWNER_ROLES, "policy"),
        (ThreatModel, THREAT_MODEL_MACHINE, MODEL_OWNER_ROLES, "threat model"),
        # Assets have no lifecycle, so their owner is accountable for as long as
        # the asset exists. Requirement owners carry no role (ROLE-1 does not
        # list them), and the requirement lifecycle has no terminal state.
        (AttackSurface, None, SURFACE_OWNER_ROLES, "asset"),
        (RequirementAssessment, None, {"owner_id": None}, "requirement"),
    ]


def accountabilities(session, user_id: str) -> list[dict[str, Any]]:
    """Open records naming this person as accountable, with the role each
    field requires. A record in a terminal state no longer needs an owner who
    can act, so it does not hold anybody in post."""
    found: list[dict[str, Any]] = []
    for model, machine, fields, label in _accountable_fields():
        for field, role in fields.items():
            column = getattr(model, field)
            stmt = select(model).where(column == user_id)
            if machine is not None:
                state = getattr(model, machine.state_field)
                stmt = stmt.where(state.not_in(machine.terminal))
            for record in session.execute(stmt).scalars():
                found.append({
                    "kind": label,
                    "id": record.id,
                    "reference": getattr(record, "reference", None),
                    "title": (getattr(record, "title", None) or getattr(record, "name", None)
                              or getattr(record, "requirement_id", None)),
                    "state": getattr(record, machine.state_field) if machine else None,
                    "field": field,
                    "role": role,
                    "path": _path(label, record),
                })
    return found


def _path(kind: str, record: Any) -> str:
    """Where the interface shows this record, so a refusal can link to it."""
    return {
        "risk": "/risks/" + record.id,
        "treatment": "/treatments/" + record.id,
        "control": "/controls/" + record.id,
        "control activity": "/controls/" + str(getattr(record, "objective_id", "")),
        "policy": "/policies/" + record.id,
        "threat model": "/threat-models/" + record.id,
        "asset": "/controls",
        "requirement": "/compliance",
    }.get(kind, "/")


def _role_satisfies(held: str, required: str) -> bool:
    return held == ADMIN or held.startswith(required)


def traces(session, user_id: str) -> list[str]:
    """Every place this person appears outside their own account: as an actor
    in the audit trail, or in any column of any record. Ids are UUIDs, so a
    match on any string column is a reference, whatever the column is called.
    Their own role rows, the audit entries about their account, and their
    notifications go with the account and do not count."""
    from app.core.db import Base

    found: list[str] = []
    if session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == user_id)):
        found.append("audit_log.user_id")
    # Named in what somebody else changed: an owner field set to them and then
    # reassigned leaves no column pointing at them, but the audit entry that
    # recorded it does, and it would read as nobody once the account was gone.
    about_others = (
        select(func.count()).select_from(AuditLog)
        .where(AuditLog.changed_fields.cast(Text).contains(user_id))
        .where(~((AuditLog.entity_type == "user") & (AuditLog.entity_id == user_id)))
    )
    if session.scalar(about_others):
        found.append("audit_log.changed_fields")
    skip = {("user_roles", "user_id"), ("audit_log", "entity_id"), ("audit_log", "user_id"),
            ("notifications", "recipient_id"), ("users", "id")}
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if (table.name, column.name) in skip or column.primary_key:
                continue
            if not isinstance(column.type, String) or (column.type.length or 0) < 36:
                continue
            if session.scalar(select(func.count()).select_from(table).where(column == user_id)):
                found.append(table.name + "." + column.name)
    return found


class UserAdmin:
    def __init__(self, session, actor) -> None:
        self.session = session
        self.actor = actor

    # -- guards -----------------------------------------------------------

    def _require_manager(self) -> None:
        if not self.actor.has_role(*MANAGERS):
            raise Forbidden("USR-1: managing users requires one of: " + ", ".join(MANAGERS))

    def _get(self, user_id: str) -> User:
        user = self.session.get(User, user_id)
        if user is None:
            raise NotFound("user not found")
        return user

    def _not_self(self, target: User, what: str) -> None:
        if target.id == self.actor.id:
            raise Forbidden("USR-2: nobody " + what + " their own account. Ask another administrator.")

    def _check_roles(self, roles: list[str], before: tuple[str, ...] = ()) -> list[str]:
        roles = list(dict.fromkeys(roles))
        invalid = [r for r in roles if r not in APP_ROLES]
        if invalid:
            raise Conflict("unknown roles: " + ", ".join(invalid))
        admin_changes = (ADMIN in roles) != (ADMIN in before)
        if admin_changes and not self.actor.has_role(ADMIN):
            raise Forbidden("USR-1: only an Admin grants or removes the Admin role")
        return roles

    def _check_seniority(self, seniority: str | None) -> None:
        if seniority is not None and seniority not in SENIORITY:
            raise Conflict("unknown seniority: " + seniority + ". One of: " + ", ".join(SENIORITY))

    def _active_admins(self) -> int:
        return self.session.scalar(
            select(func.count()).select_from(User).join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role == ADMIN, User.deactivated_at.is_(None))
        ) or 0

    def _keep_an_admin(self, target: User) -> None:
        if ADMIN in target.role_names and target.is_active and self._active_admins() <= 1:
            raise Conflict("USR-6: " + target.full_name + " is the last active Admin. "
                           "Make someone else an Admin first.")

    def _still_accountable(self, target: User, lost: set[str] | None) -> None:
        """USR-3. `lost` is the set of roles being removed, or None when the
        whole account is being deactivated."""
        blocking = []
        remaining = [r for r in target.role_names if lost is None or r not in lost]
        for item in accountabilities(self.session, target.id):
            if lost is None:
                blocking.append(item)
            elif item["role"] and not any(_role_satisfies(r, item["role"]) for r in remaining):
                blocking.append(item)
        if blocking:
            what = "be deactivated" if lost is None else "lose " + ", ".join(sorted(lost))
            raise Conflict(
                "USR-3: " + target.full_name + " cannot " + what + " while named on "
                + str(len(blocking)) + " open record" + ("s" if len(blocking) != 1 else "")
                + ". Reassign them first.",
                detail={"rule": "USR-3", "records": blocking},
            )

    def _audit(self, target_id: str, action: str, changes: dict[str, Any]) -> None:
        AuditTrail.record(self.session, actor_id=self.actor.id, entity_type="user",
                          entity_id=target_id, action=action, changed_fields=changes)

    # -- operations ---------------------------------------------------------

    def create(self, *, email: str, full_name: str, password: str, job_title: str | None,
               seniority: str, roles: list[str]) -> User:
        self._require_manager()
        email = email.strip().lower()
        if self.session.execute(select(User).where(func.lower(User.email) == email)).first():
            raise Conflict("a user with that email already exists")
        roles = self._check_roles(roles)
        self._check_seniority(seniority)
        user = User(email=email, full_name=full_name.strip(), password_hash=hash_password(password),
                    job_title=job_title, seniority=seniority)
        self.session.add(user)
        self.session.flush()
        for role in roles:
            self.session.add(UserRole(user_id=user.id, role=role))
        self._audit(user.id, "USER_CREATED", {"email": email, "roles": roles, "seniority": seniority})
        self.session.flush()
        self.session.refresh(user)
        return user

    def update(self, user_id: str, *, full_name: str | None, job_title: str | None,
               seniority: str | None, roles: list[str] | None) -> User:
        self._require_manager()
        target = self._get(user_id)
        changes: dict[str, Any] = {}
        if roles is not None:
            before = target.role_names
            roles = self._check_roles(roles, before)
            if set(roles) != set(before):
                self._not_self(target, "changes the roles on")
                lost = set(before) - set(roles)
                if ADMIN in lost:
                    self._keep_an_admin(target)
                if lost:
                    self._still_accountable(target, lost)
                for existing in list(target.roles):
                    self.session.delete(existing)
                self.session.flush()
                for role in roles:
                    self.session.add(UserRole(user_id=target.id, role=role))
                changes["roles"] = {"from": sorted(before), "to": sorted(roles)}
        self._check_seniority(seniority)
        for field, value in (("full_name", full_name), ("job_title", job_title), ("seniority", seniority)):
            if value is not None and value != getattr(target, field):
                changes[field] = {"from": getattr(target, field), "to": value}
                setattr(target, field, value)
        if changes:
            self._audit(target.id, "USER_UPDATED", changes)
        self.session.flush()
        self.session.refresh(target)
        return target

    def deactivate(self, user_id: str, reason: str) -> User:
        self._require_manager()
        target = self._get(user_id)
        self._not_self(target, "deactivates")
        if not target.is_active:
            raise Conflict(target.full_name + " is already deactivated")
        if not reason.strip():
            raise Conflict("USR-4: record why the account is being deactivated")
        self._keep_an_admin(target)
        self._still_accountable(target, None)
        target.deactivated_at = datetime.now(timezone.utc)
        self._audit(target.id, "USER_DEACTIVATED", {"reason": reason.strip()})
        self.session.flush()
        return target

    def reactivate(self, user_id: str) -> User:
        self._require_manager()
        target = self._get(user_id)
        if target.is_active:
            raise Conflict(target.full_name + " is already active")
        target.deactivated_at = None
        self._audit(target.id, "USER_REACTIVATED", {})
        self.session.flush()
        return target

    def reset_password(self, user_id: str, password: str) -> None:
        self._require_manager()
        target = self._get(user_id)
        target.password_hash = hash_password(password)
        # The password itself is never written anywhere but its hash.
        self._audit(target.id, "PASSWORD_RESET", {})
        self.session.flush()

    def delete(self, user_id: str) -> dict[str, Any]:
        self._require_manager()
        target = self._get(user_id)
        self._not_self(target, "deletes")
        self._keep_an_admin(target)
        found = traces(self.session, target.id)
        if found:
            raise Conflict(
                "USR-5: " + target.full_name + " has acted in the platform or is named on a "
                "record, so deleting the account would erase who did what. Deactivate it instead.",
                detail={"rule": "USR-5", "references": found},
            )
        summary = {"email": target.email, "full_name": target.full_name,
                   "roles": sorted(target.role_names)}
        self.session.execute(Notification.__table__.delete().where(Notification.recipient_id == target.id))
        self.session.delete(target)
        self._audit(user_id, "USER_DELETED", summary)
        self.session.flush()
        return summary
