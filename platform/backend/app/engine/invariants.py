"""Invariant engine.

An invariant is a hard rule the system must never violate regardless of role,
lifecycle state, or API path. Each one declares the specification ID it comes
from (RINV / CINV / PINV / TINV), the layer that enforces it, and the mechanism.

Service-layer invariants are checked here, on every write, before commit.
Schema-layer invariants are additionally enforced by CHECK / NOT NULL / FK
constraints and by immutability triggers in the migration, so a direct SQL write
cannot bypass them either. Neither layer operates without the other.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from app.core.errors import InvariantViolation

SCHEMA = "schema"
SERVICE = "service"
BOTH = "both"


@dataclass(frozen=True)
class Invariant:
    """One codified rule.

    `holds` returns True when the rule is satisfied. It receives the entity and a
    context object carrying the session, so rules that must consult related
    records (linked controls, linked risks) can do so.
    """

    id: str
    entity: str
    rule: str
    layer: str
    mechanism: str
    violation: str
    spec_ref: str
    holds: Callable[[Any, Any], bool]

    def check(self, entity: Any, ctx: Any) -> None:
        try:
            ok = bool(self.holds(entity, ctx))
        except InvariantViolation:
            raise
        except Exception as exc:
            raise InvariantViolation(
                self.id, self.id + " could not be evaluated: " + str(exc)
            ) from exc
        if not ok:
            raise InvariantViolation(
                self.id,
                self.id + ": " + self.rule,
                detail={
                    "rule": self.rule,
                    "violation_behaviour": self.violation,
                    "spec_ref": self.spec_ref,
                    "enforcement_layer": self.layer,
                },
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entity": self.entity,
            "rule": self.rule,
            "layer": self.layer,
            "mechanism": self.mechanism,
            "violation": self.violation,
            "spec_ref": self.spec_ref,
        }


class InvariantRegistry:
    """Central catalogue. Modules register their invariants at import time; the
    service layer calls `enforce` before every commit that touches an entity."""

    def __init__(self) -> None:
        self._by_entity: dict[str, list[Invariant]] = {}
        self._by_id: dict[str, Invariant] = {}

    def register(self, *invariants: Invariant) -> None:
        for inv in invariants:
            if inv.id in self._by_id:
                raise ValueError("duplicate invariant id: " + inv.id)
            self._by_id[inv.id] = inv
            self._by_entity.setdefault(inv.entity, []).append(inv)

    def for_entity(self, entity: str) -> list[Invariant]:
        return list(self._by_entity.get(entity, ()))

    def get(self, invariant_id: str) -> Invariant | None:
        return self._by_id.get(invariant_id)

    def all(self) -> Iterator[Invariant]:
        for inv in self._by_id.values():
            yield inv

    def catalogue(self) -> list[dict[str, Any]]:
        """Served at /api/engine/invariants. The UI renders the live catalogue
        straight from the running engine, not from a copied-out table."""
        return [inv.as_dict() for inv in self._by_id.values()]

    def enforce(self, entity_name: str, entity: Any, ctx: Any) -> None:
        """Raise on the first violation. Called before commit on every write path."""
        for inv in self._by_entity.get(entity_name, ()):
            inv.check(entity, ctx)

    def evaluate_all(self, entity_name: str, entity: Any, ctx: Any) -> list[dict[str, Any]]:
        """Non-raising evaluation, for the per-record compliance panel in the UI."""
        results: list[dict[str, Any]] = []
        for inv in self._by_entity.get(entity_name, ()):
            try:
                ok = bool(inv.holds(entity, ctx))
                detail = ""
            except Exception as exc:
                ok = False
                detail = str(exc)
            results.append({**inv.as_dict(), "satisfied": ok, "detail": detail})
        return results


invariants = InvariantRegistry()
