"""Effectiveness reviews API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.core.security import CurrentUser, DbSession
from app.modules.review.machine import CONTROL_REVIEW_MACHINE
from app.modules.review.models import ControlReview
from app.modules.review.service import ReviewService

router = APIRouter(prefix="/control-reviews", tags=["control reviews"])


class TransitionRequest(BaseModel):
    target: str
    reason: str | None = None


def _svc(session, user) -> ReviewService:
    return ReviewService(session, user.id, user.role_names)


@router.get("")
def list_reviews(
    session: DbSession, user: CurrentUser, state: str | None = None,
    objective_id: str | None = None,
) -> list[dict[str, Any]]:
    svc = _svc(session, user)
    stmt = select(ControlReview).order_by(ControlReview.opened_at.desc())
    if state:
        stmt = stmt.where(ControlReview.lifecycle_state == state)
    if objective_id:
        stmt = stmt.where(ControlReview.objective_id == objective_id)
    return [svc.detail(r) for r in session.execute(stmt).scalars()]


@router.get("/machine")
def review_machine(user: CurrentUser) -> dict[str, Any]:
    return CONTROL_REVIEW_MACHINE.describe()


@router.get("/{review_id}")
def get_review(review_id: str, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    svc = _svc(session, user)
    return svc.detail(svc.get(review_id))


@router.post("/{review_id}/transition")
def transition_review(
    review_id: str, payload: TransitionRequest, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    svc = _svc(session, user)
    review = svc.get(review_id)
    result = svc.transition(review, payload.target, **payload.model_dump(exclude={"target"}))
    return {"transition": result, "review": svc.detail(review)}
