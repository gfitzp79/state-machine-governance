"""Immutable audit trail and notification writer.

Every state transition is recorded with entity, previous state, new state,
timestamp, actor, and the full gate evaluation result, so an auditor can see not
only that a transition happened but which preconditions were checked and what
each of them returned at that moment.

The underlying tables reject UPDATE and DELETE at the database layer via
triggers installed in the migration, so this is append-only regardless of how the
row is reached.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session


class AuditTrail:
    """Thin writer over the audit and notification tables. Imported lazily inside
    the methods to keep the engine package free of model-layer imports at module
    load time."""

    @staticmethod
    def record(
        session: Session,
        *,
        actor_id: str | UUID | None,
        entity_type: str,
        entity_id: str | UUID | None,
        action: str,
        changed_fields: dict[str, Any] | None = None,
    ) -> None:
        from app.modules.identity.models import AuditLog

        session.add(
            AuditLog(
                user_id=str(actor_id) if actor_id else None,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id else None,
                action=action,
                changed_fields=AuditTrail.jsonable(changed_fields or {}),
            )
        )

    @staticmethod
    def record_transition(
        session: Session,
        *,
        actor_id: str | UUID | None,
        entity_type: str,
        entity_id: str | UUID,
        gate_result: Any,
        cascade_effects: list[dict[str, Any]] | None = None,
    ) -> None:
        AuditTrail.record(
            session,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action="STATE_TRANSITION",
            changed_fields={
                "gate": gate_result.gate,
                "from": gate_result.source,
                "to": gate_result.target,
                "gate_evaluation": [c.as_dict() for c in gate_result.checks],
                "cascades": AuditTrail.jsonable(cascade_effects or []),
            },
        )

    @staticmethod
    def notify(
        session: Session,
        *,
        recipient_id: str | UUID | None,
        entity_type: str,
        entity_id: str | UUID | None,
        event_type: str,
        title: str,
        body: str = "",
    ) -> None:
        if recipient_id is None:
            return
        from app.modules.identity.models import Notification

        session.add(
            Notification(
                recipient_id=str(recipient_id),
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id else None,
                event_type=event_type,
                title=title,
                body=body,
            )
        )

    @staticmethod
    def jsonable(value: Any) -> Any:
        """Coerce a value into something the JSONB column can store.

        Audit entries carry whatever field changed, including dates, decimals and
        UUIDs. Handing those to the driver raw fails at commit time, which would
        roll back the very write being audited.
        """
        from datetime import date, datetime
        from decimal import Decimal
        from uuid import UUID

        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, dict):
            return {str(k): AuditTrail.jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [AuditTrail.jsonable(v) for v in value]
        return str(value)

    @staticmethod
    def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        """Field-level before/after, restricted to fields that actually changed."""
        changed: dict[str, Any] = {}
        for key, new_value in after.items():
            old_value = before.get(key)
            if old_value != new_value:
                changed[key] = {
                    "from": AuditTrail.jsonable(old_value),
                    "to": AuditTrail.jsonable(new_value),
                }
        return changed
