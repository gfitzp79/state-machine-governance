"""Generic, declarative state machine.

Every lifecycle in the platform (risk, control objective, control deployment,
policy, policy exception, treatment, threat model) is expressed as an instance of
`StateMachine`. A module declares its states, its legal edges, and the named
preconditions guarding each edge. Nothing else in the codebase is permitted to
mutate a lifecycle field directly.

Design principle carried over from the specification: gates are enforced here, at
the service layer, never in the UI. The UI may hide a button for convenience but
correctness does not depend on it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import GateBlocked, InvalidTransition


@dataclass(frozen=True)
class TransitionContext:
    """Everything a precondition may consult beyond the entity itself."""

    session: Any
    actor_id: str | None = None
    actor_roles: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)

    def has_role(self, *roles: str) -> bool:
        return any(r in self.actor_roles for r in roles)


@dataclass(frozen=True)
class CheckResult:
    """The outcome of a single named precondition. Surfaced verbatim to the UI so
    a blocked transition tells the user exactly which condition failed."""

    id: str
    name: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class GateResult:
    gate: str
    source: str
    target: str
    checks: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.passed)

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "source": self.source,
            "target": self.target,
            "passed": self.passed,
            "checks": [c.as_dict() for c in self.checks],
        }


Predicate = Callable[[Any, TransitionContext], bool]


@dataclass(frozen=True)
class Precondition:
    """A single, individually reportable gate condition.

    `id` is the specification reference (a gate item number, or the invariant the
    condition enforces) so every block is traceable back to the codified rules.
    """

    id: str
    name: str
    predicate: Predicate
    detail: str = ""

    def evaluate(self, entity: Any, ctx: TransitionContext) -> CheckResult:
        try:
            passed = bool(self.predicate(entity, ctx))
        except Exception as exc:  # a precondition must never 500 the request
            return CheckResult(self.id, self.name, False, "evaluation error: " + str(exc))
        return CheckResult(self.id, self.name, passed, "" if passed else self.detail)


@dataclass(frozen=True)
class Transition:
    source: str
    target: str
    gate: str
    preconditions: tuple[Precondition, ...] = ()
    cascades: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()  # empty means any authenticated role
    description: str = ""


class StateMachine:
    """Declarative lifecycle definition plus the single entry point for firing a
    transition. `fire` is the only sanctioned way to change a lifecycle field."""

    def __init__(
        self,
        entity: str,
        state_field: str,
        initial: str,
        states: Sequence[str],
        transitions: Iterable[Transition],
        terminal: Sequence[str] = (),
    ) -> None:
        self.entity = entity
        self.state_field = state_field
        self.initial = initial
        self.states = tuple(states)
        self.terminal = tuple(terminal)
        self._edges: dict[tuple[str, str], Transition] = {}
        for t in transitions:
            if t.source != "*" and t.source not in self.states:
                raise ValueError(entity + ": unknown source state " + t.source)
            if t.target not in self.states:
                raise ValueError(entity + ": unknown target state " + t.target)
            self._edges[(t.source, t.target)] = t

    # -- introspection ----------------------------------------------------

    @property
    def transitions(self) -> tuple[Transition, ...]:
        return tuple(self._edges.values())

    def lookup(self, source: str, target: str) -> Transition | None:
        return self._edges.get((source, target)) or self._edges.get(("*", target))

    def targets_from(self, source: str) -> tuple[str, ...]:
        direct = [t for (s, t) in self._edges if s == source]
        wildcard = [t for (s, t) in self._edges if s == "*" and t != source]
        return tuple(dict.fromkeys(direct + wildcard))

    def describe(self) -> dict[str, Any]:
        """Machine-readable definition. Served to the UI so the client renders the
        lifecycle from the specification rather than a hard-coded copy of it."""
        return {
            "entity": self.entity,
            "state_field": self.state_field,
            "initial": self.initial,
            "states": list(self.states),
            "terminal": list(self.terminal),
            "transitions": [
                {
                    "source": t.source,
                    "target": t.target,
                    "gate": t.gate,
                    "roles": list(t.roles),
                    "cascades": list(t.cascades),
                    "description": t.description,
                    "preconditions": [
                        {"id": p.id, "name": p.name, "detail": p.detail}
                        for p in t.preconditions
                    ],
                }
                for t in self._edges.values()
            ],
        }

    # -- evaluation -------------------------------------------------------

    def current_state(self, entity: Any) -> str:
        return getattr(entity, self.state_field)

    def evaluate(self, entity: Any, target: str, ctx: TransitionContext) -> GateResult:
        """Evaluate a gate without mutating anything. Drives the UI's
        'what is blocking this?' panel."""
        source = self.current_state(entity)
        transition = self.lookup(source, target)
        if transition is None:
            raise InvalidTransition(
                self.entity + ": " + source + " -> " + target + " is not a valid transition",
                detail={
                    "source": source,
                    "target": target,
                    "allowed": list(self.targets_from(source)),
                },
            )
        checks = tuple(p.evaluate(entity, ctx) for p in transition.preconditions)
        return GateResult(transition.gate, source, target, checks)

    def gate_report(self, entity: Any, ctx: TransitionContext) -> list[dict[str, Any]]:
        """Every outbound edge from the current state, each with its live gate
        evaluation. This is what the lifecycle panel in the UI renders."""
        source = self.current_state(entity)
        report: list[dict[str, Any]] = []
        for target in self.targets_from(source):
            transition = self.lookup(source, target)
            if transition is None:
                continue
            result = self.evaluate(entity, target, ctx)
            report.append(
                {
                    **result.as_dict(),
                    "roles": list(transition.roles),
                    "role_permitted": not transition.roles or ctx.has_role(*transition.roles),
                    "description": transition.description,
                }
            )
        return report

    def fire(
        self, entity: Any, target: str, ctx: TransitionContext, system: bool = False
    ) -> tuple[GateResult, Transition]:
        """Attempt the transition. Raises GateBlocked with the full precondition
        breakdown if any condition is unmet. Does not commit; the caller owns the
        transaction so cascades and audit land atomically with the state change.

        `system=True` marks a transition the specification makes automatic rather
        than discretionary, such as a failing control test propagating to Failed
        (DL-1). It skips the role check, because no human is choosing to make the
        transition. It never skips a precondition.
        """
        source = self.current_state(entity)
        transition = self.lookup(source, target)
        if transition is None:
            raise InvalidTransition(
                self.entity + ": " + source + " -> " + target + " is not a valid transition",
                detail={
                    "source": source,
                    "target": target,
                    "allowed": list(self.targets_from(source)),
                },
            )
        if not system and transition.roles and not ctx.has_role(*transition.roles):
            raise GateBlocked(
                transition.gate + ": your roles do not permit this transition",
                detail={"gate": transition.gate, "required_roles": list(transition.roles)},
            )

        result = self.evaluate(entity, target, ctx)
        if not result.passed:
            raise GateBlocked(
                transition.gate
                + " blocked: "
                + "; ".join(c.id + " " + c.name for c in result.failures),
                detail=result.as_dict(),
            )

        setattr(entity, self.state_field, target)
        return result, transition
