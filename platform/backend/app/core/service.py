"""Base service.

Every module's service subclasses this. The point is that there is exactly one
write path, and that path always runs the same four steps in the same order:

    1. mutate           apply the caller's change
    2. enforce          run every invariant registered for the entity
    3. cascade          propagate to related entities
    4. audit            record what happened, including the gate evaluation

Skipping any of them is not possible from a router, because routers never touch
the session directly.
"""

from __future__ import annotations

from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.engine import AuditTrail, StateMachine, TransitionContext, cascades, invariants

T = TypeVar("T")


class LifecycleService(Generic[T]):
    """Generic CRUD plus gated transitions for one entity type."""

    model: type
    machine: StateMachine
    entity_name: str
    reference_prefix: str = ""
    reference_field: str = "reference"

    # Fields whose permitted values come from config/governance.yml rather than
    # from a CHECK constraint, so an organisation can change its taxonomy
    # without a schema migration. Validated on every create and update.
    taxonomy: dict[str, str] = {}

    def __init__(self, session: Session, actor_id: str | None, actor_roles: Sequence[str] = ()):
        self.session = session
        self.actor_id = actor_id
        self.actor_roles = tuple(actor_roles)

    # -- context ----------------------------------------------------------

    def context(self, **payload: Any) -> TransitionContext:
        return TransitionContext(
            session=self.session,
            actor_id=self.actor_id,
            actor_roles=self.actor_roles,
            payload=payload,
        )

    # -- reads ------------------------------------------------------------

    def get(self, entity_id: str) -> T:
        entity = self.session.get(self.model, entity_id)
        if entity is None:
            raise NotFound(self.entity_name + " " + entity_id + " not found")
        return entity

    def list(self, **filters: Any) -> list[T]:
        stmt = select(self.model)
        for field, value in filters.items():
            if value is None:
                continue
            column = getattr(self.model, field, None)
            if column is None:
                continue
            stmt = stmt.where(column == value)
        return list(self.session.execute(stmt).scalars().all())

    # -- references -------------------------------------------------------

    def next_reference(self) -> str:
        """Human-readable sequential identifier, e.g. RISK-004."""
        if not self.reference_prefix:
            raise NotImplementedError(self.entity_name + " has no reference prefix")
        column = getattr(self.model, self.reference_field)
        count = self.session.execute(select(func.count()).select_from(self.model)).scalar_one()
        candidate = self.reference_prefix + "-" + str(count + 1).zfill(3)
        # Tolerate gaps from deletions without ever colliding.
        while self.session.execute(select(column).where(column == candidate)).first():
            count += 1
            candidate = self.reference_prefix + "-" + str(count + 1).zfill(3)
        return candidate

    # -- taxonomy ---------------------------------------------------------

    def validate_taxonomy(self, values: dict[str, Any]) -> None:
        # Refuse a value that is not in the configured list, and name the
        # configuration key so the operator knows where to add it.
        from app.core.governance import governance

        for field, config_key in self.taxonomy.items():
            if field not in values:
                continue
            value = values[field]
            if value is None:
                continue
            allowed = getattr(governance, config_key)
            if value not in allowed:
                raise Conflict(
                    str(value)
                    + " is not a permitted "
                    + field.replace("_", " ")
                    + ". Configured values are: "
                    + ", ".join(str(a) for a in allowed)
                    + ". Add it to config/governance.yml and restart the API "
                    + "to widen the taxonomy.",
                    detail={"field": field, "allowed": list(allowed)},
                )

    # -- enforcement ------------------------------------------------------

    def enforce(self, entity: Any, entity_name: str | None = None, **payload: Any) -> None:
        invariants.enforce(
            entity_name or self.entity_name, entity, self.context(**payload)
        )

    def invariant_report(self, entity: Any, entity_name: str | None = None) -> list[dict[str, Any]]:
        return invariants.evaluate_all(
            entity_name or self.entity_name, entity, self.context()
        )

    # -- writes -----------------------------------------------------------

    def apply(self, entity: Any, changes: dict[str, Any], *, action: str = "UPDATE") -> Any:
        """Apply a partial update, enforce invariants, audit the field-level diff."""
        self.validate_taxonomy(changes)
        before = {k: getattr(entity, k, None) for k in changes}
        for field, value in changes.items():
            if not hasattr(entity, field):
                continue
            setattr(entity, field, value)
        self.session.flush()
        self.enforce(entity)
        diff = AuditTrail.diff(before, {k: getattr(entity, k, None) for k in changes})
        if diff:
            AuditTrail.record(
                self.session,
                actor_id=self.actor_id,
                entity_type=self.entity_name,
                entity_id=entity.id,
                action=action,
                changed_fields=diff,
            )
        return entity

    def create(self, entity: Any, *, action: str = "CREATE") -> Any:
        self.validate_taxonomy(
            {f: getattr(entity, f, None) for f in self.taxonomy}
        )
        self.session.add(entity)
        self.session.flush()
        self.enforce(entity)
        AuditTrail.record(
            self.session,
            actor_id=self.actor_id,
            entity_type=self.entity_name,
            entity_id=entity.id,
            action=action,
            changed_fields={"created": True},
        )
        return entity

    # -- transitions ------------------------------------------------------

    def gate_report(self, entity: Any) -> list[dict[str, Any]]:
        return self.machine.gate_report(entity, self.context())

    def evaluate(self, entity: Any, target: str, **payload: Any) -> dict[str, Any]:
        return self.machine.evaluate(entity, target, self.context(**payload)).as_dict()

    def transition(
        self, entity: Any, target: str, system: bool = False, **payload: Any
    ) -> dict[str, Any]:
        """Fire a gated transition. Gate, invariants, cascades and audit all land
        in one transaction; any failure rolls the whole thing back.

        `system=True` is for transitions the specification makes automatic, not
        discretionary. It waives the role check and nothing else."""
        ctx = self.context(**payload)
        result, transition = self.machine.fire(entity, target, ctx, system=system)

        self.on_transition(entity, result, transition, payload)
        self.session.flush()

        # Invariants run after the transition so rules that only bind in the new
        # state (RINV-6 at readout, CINV-8 at deprecation) are actually evaluated.
        self.enforce(entity, **payload)

        effects = cascades.emit_all(
            transition.cascades,
            self.session,
            self.entity_name,
            entity.id,
            self.actor_id,
            **payload,
        )
        self.session.flush()

        AuditTrail.record_transition(
            self.session,
            actor_id=self.actor_id,
            entity_type=self.entity_name,
            entity_id=entity.id,
            gate_result=result,
            cascade_effects=effects,
        )
        self.session.commit()
        return {
            "entity_id": entity.id,
            "from": result.source,
            "to": result.target,
            "gate": result.gate,
            "checks": [c.as_dict() for c in result.checks],
            "cascades": effects,
        }

    def on_transition(self, entity: Any, result: Any, transition: Any, payload: dict) -> None:
        """Hook for module-specific side effects that belong to the transition
        itself rather than to a cascade. Overridden where needed."""
        return None

    # -- helpers ----------------------------------------------------------

    def require_role(self, *roles: str) -> None:
        if not any(r in self.actor_roles for r in roles):
            raise Conflict("this action requires one of: " + ", ".join(roles))
