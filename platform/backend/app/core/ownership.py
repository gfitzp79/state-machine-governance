"""A person named as owner holds the role that name implies.

Every owner field in the platform accepted any user. The roles were configured,
the role levels were configured, the ownership matrix was configured, and the
acting user's role gated every transition. But the person a record named as
accountable was checked against nothing, so a risk could be owned by the GRC
Engineer, a policy by a Control Operator, and an asset by somebody with no
system ownership anywhere in their role set.

The failure is quiet, which is what makes it worth a rule. Nothing breaks. The
record simply asserts an accountability that the person does not hold, and every
downstream gate that trusts the field inherits the lie.

One predicate, used by each domain, so the rule reads the same everywhere and
the owner pickers can ask `/users?role=` for exactly the set it will accept.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# The platform administrator is accepted in any owner field. Somebody has to be
# able to unstick a record whose owner has left, and the audit trail records
# that it was them rather than the role they were standing in for.
ADMIN = "Admin"


def holder_of(*, fields: dict[str, str]) -> Callable[[Any, Any], bool]:
    """Build an invariant predicate for a mapping of field to required role.

    Roles match on a prefix, so a required role of `AppSec` is satisfied by
    AppSec_Lead or AppSec_Engineer, consistent with how `/users?role=` filters.

    An empty field passes. These rules are about who is named, not about whether
    somebody is named at all: that is a separate question, and several of these
    fields are legitimately unassigned early in a lifecycle.
    """

    def holds(entity: Any, ctx: Any) -> bool:
        session = getattr(ctx, "session", None)
        if session is None:
            return True
        from app.modules.identity.models import User

        for field, required in fields.items():
            user_id = getattr(entity, field, None)
            if not user_id:
                continue
            person = session.get(User, user_id)
            if person is None:
                # A named owner who is not a user is a worse problem than a
                # wrong role, and this is the only rule positioned to see it.
                return False
            held = person.role_names
            if not any(r == ADMIN or r.startswith(required) for r in held):
                return False
        return True

    return holds


def describe(fields: dict[str, str]) -> str:
    """The mechanism text, so each registration does not restate it by hand."""
    pairs = ", ".join(field + " requires " + role for field, role in sorted(fields.items()))
    return (
        "Checked against the named user's roles on every write: "
        + pairs
        + ". Admin is accepted in any owner field. The owner pickers request the "
        + "same role from /users, so the interface does not offer a person the "
        + "rule would refuse."
    )
