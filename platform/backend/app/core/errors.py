"""Domain error types. These map to HTTP responses in app.main."""

from typing import Any


class DomainError(Exception):
    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class GateBlocked(DomainError):
    """A state transition was refused because one or more gate preconditions
    evaluated false. `detail` carries the full per-precondition breakdown so the
    UI can show exactly what is missing."""

    status_code = 409
    code = "gate_blocked"


class InvalidTransition(DomainError):
    """The requested source -> target edge does not exist on the state machine."""

    status_code = 409
    code = "invalid_transition"


class InvariantViolation(DomainError):
    """A hard rule (RINV/CINV/PINV/TINV) would have been broken. Never advisory."""

    status_code = 422
    code = "invariant_violation"

    def __init__(self, invariant_id: str, message: str, detail: Any = None) -> None:
        super().__init__(message, detail)
        self.invariant_id = invariant_id

    def payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "invariant": self.invariant_id,
            "message": self.message,
            "detail": self.detail,
        }


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class Forbidden(DomainError):
    status_code = 403
    code = "forbidden"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"
