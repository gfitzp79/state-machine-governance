"""Cross-lifecycle cascade bus.

State changes in one lifecycle propagate to related entities. That propagation is
the mechanism by which the platform keeps interconnected state machines
consistent: a control failing does not merely record a failure, it locks residual
scores on every risk that control was reducing.

Cascades run inside the caller's transaction, so the state change, the cascade
effects and the audit entries commit atomically or not at all.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

Handler = Callable[["CascadeEvent"], None]


@dataclass
class CascadeEvent:
    name: str
    session: Any
    entity_type: str
    entity_id: Any
    actor_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    # Effects appended by handlers, returned to the caller so the API response can
    # tell the user exactly what else changed as a result of their action.
    effects: list[dict[str, Any]] = field(default_factory=list)

    def record(self, target_type: str, target_id: Any, description: str, **extra: Any) -> None:
        self.effects.append(
            {
                "cascade": self.name,
                "target_type": target_type,
                "target_id": str(target_id),
                "description": description,
                **extra,
            }
        )


class CascadeBus:
    """Handlers are registered by module at import time and keyed by event name."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self._descriptions: dict[str, str] = {}

    def on(self, event: str, description: str = "") -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            self._handlers.setdefault(event, []).append(fn)
            if description:
                self._descriptions[event] = description
            return fn

        return decorator

    def emit(
        self,
        name: str,
        session: Any,
        entity_type: str,
        entity_id: Any,
        actor_id: str | None = None,
        **payload: Any,
    ) -> list[dict[str, Any]]:
        event = CascadeEvent(
            name=name,
            session=session,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            payload=payload,
        )
        for handler in self._handlers.get(name, ()):
            handler(event)
        return event.effects

    def emit_all(
        self,
        names: tuple[str, ...],
        session: Any,
        entity_type: str,
        entity_id: Any,
        actor_id: str | None = None,
        **payload: Any,
    ) -> list[dict[str, Any]]:
        effects: list[dict[str, Any]] = []
        for name in names:
            effects.extend(
                self.emit(name, session, entity_type, entity_id, actor_id, **payload)
            )
        return effects

    def registered(self) -> list[dict[str, Any]]:
        return [
            {
                "event": name,
                "handlers": len(handlers),
                "description": self._descriptions.get(name, ""),
            }
            for name, handlers in sorted(self._handlers.items())
        ]


cascades = CascadeBus()
