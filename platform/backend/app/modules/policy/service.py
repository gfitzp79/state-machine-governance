"""Policy and policy exception services."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.errors import Conflict, NotFound
from app.core.governance import governance
from app.core.model_base import utcnow
from app.core.service import LifecycleService
from app.engine import AuditTrail
from app.modules.policy.machine import POLICY_EXCEPTION_MACHINE, POLICY_MACHINE
from app.modules.policy.models import (
    ANNUAL_AUDIT_FRAMEWORKS,
    Policy,
    PolicyControlLink,
    PolicyException,
    PolicyVersion,
    Standard,
)


class PolicyService(LifecycleService[Policy]):
    model = Policy
    machine = POLICY_MACHINE
    entity_name = "policy"
    reference_prefix = "POL"
    taxonomy = {"policy_type": "policy_types", "review_cycle": "review_cycles"}

    def create_policy(self, data: dict[str, Any]) -> Policy:
        policy = Policy(reference=self.next_reference(), created_by=self.actor_id, **data)
        self.create(policy)
        self._capture_version(policy, "initial draft")
        self.session.commit()
        return policy

    def update_policy(self, policy: Policy, changes: dict[str, Any]) -> Policy:
        """A body change on a policy that has ever been Active captures an
        immutable version first, so the prior text is always recoverable."""
        body_changed = "body" in changes and changes["body"] != policy.body
        if body_changed and policy.lifecycle_state in ("Active", "Under_Revision"):
            self._capture_version(policy, changes.get("change_summary") or "content revision")

        # Compliance mappings must name frameworks the organisation has configured.
        for framework in changes.get("compliance_mappings") or []:
            if framework not in governance.compliance_frameworks:
                raise Conflict(
                    framework
                    + " is not a configured compliance framework. Add it to "
                    + "policy.compliance_frameworks in config/governance.yml."
                )

        # PINV-4 evaluated before the write rather than after.
        mappings = changes.get("compliance_mappings", policy.compliance_mappings) or []
        cycle = changes.get("review_cycle", policy.review_cycle)
        if any(m in ANNUAL_AUDIT_FRAMEWORKS for m in mappings) and cycle != "Annual":
            raise Conflict(
                "PINV-4: this policy is mapped to an annual-audit framework "
                "(" + ", ".join(m for m in mappings if m in ANNUAL_AUDIT_FRAMEWORKS) + ") "
                "and must carry an Annual review cycle."
            )

        self.apply(policy, changes)
        self.session.commit()
        return policy

    def approve(self, policy: Policy, approver_id: str) -> Policy:
        """PINV-5 checked here so the failure message names the rule."""
        from app.modules.identity.models import ROLE_LEVELS, User

        if approver_id == policy.policy_owner_id:
            raise Conflict(
                "PINV-5: a policy owner cannot approve their own policy. "
                "Approval requires CISO or above."
            )
        approver = self.session.get(User, approver_id)
        if approver is None:
            raise NotFound("approver not found")
        if approver.max_role_level < ROLE_LEVELS["CISO"]:
            raise Conflict(
                "PINV-5: policy approval requires CISO or above. "
                + approver.full_name
                + " does not hold a sufficient role."
            )
        self.apply(
            policy,
            {"approved_by": approver_id, "approved_at": utcnow()},
            action="POLICY_APPROVED",
        )
        self.session.commit()
        return policy

    def link_control(self, policy: Policy, objective_id: str) -> PolicyControlLink:
        if any(link.objective_id == objective_id for link in policy.control_links):
            raise Conflict("control already linked to this policy")
        link = PolicyControlLink(
            policy_id=policy.id, objective_id=objective_id, linked_by=self.actor_id
        )
        self.session.add(link)
        self.session.commit()
        self.session.refresh(policy)
        return link

    def unlink_control(self, policy: Policy, link_id: str) -> None:
        link = self.session.get(PolicyControlLink, link_id)
        if link is None or link.policy_id != policy.id:
            raise NotFound("link not found on this policy")
        # PINV-1 checked at the point of removal, not just at activation.
        if policy.lifecycle_state in ("Active", "Under_Revision") and len(policy.control_links) <= 1:
            raise Conflict(
                "PINV-1: an Active policy must retain at least one linked control objective. "
                "Link a replacement before removing this one."
            )
        self.session.delete(link)
        self.session.commit()
        self.session.refresh(policy)

    def _capture_version(self, policy: Policy, summary: str) -> None:
        self.session.add(
            PolicyVersion(
                policy_id=policy.id,
                version=policy.version,
                body=policy.body,
                change_summary=summary,
                lifecycle_state_at_capture=policy.lifecycle_state,
                edited_by=self.actor_id,
            )
        )

    def on_transition(self, entity: Policy, result, transition, payload: dict) -> None:
        if result.gate == "GATE_POLICY_REVISION":
            # PL-3: capture the enforceable version before drafting forward.
            self._capture_version(entity, payload.get("reason") or "revision opened")
        if result.gate == "GATE_POLICY_REVISION_APPROVED":
            new_version = payload.get("version")
            if new_version:
                entity.version = new_version

    def detail(self, policy: Policy) -> dict[str, Any]:
        return {
            **summarise_policy(policy),
            "scope": policy.scope,
            "purpose": policy.purpose,
            "body": policy.body,
            "change_summary": policy.change_summary,
            "controls": [
                {
                    "link_id": l.id,
                    "objective_id": l.objective_id,
                    "reference": l.objective.reference if l.objective else None,
                    "title": l.objective.title if l.objective else None,
                    "lifecycle_state": l.objective.lifecycle_state if l.objective else None,
                    "realignment_required": l.realignment_required,
                    "realignment_due": l.realignment_due,
                }
                for l in policy.control_links
            ],
            "exceptions": [summarise_exception(e) for e in policy.exceptions],
            "standards": [
                {
                    "id": s.id,
                    "reference": s.reference,
                    "title": s.title,
                    "version": s.version,
                    "lifecycle_state": s.lifecycle_state,
                }
                for s in policy.standards
            ],
            "versions": [
                {
                    "id": v.id,
                    "version": v.version,
                    "change_summary": v.change_summary,
                    "lifecycle_state_at_capture": v.lifecycle_state_at_capture,
                    "edited_by": v.edited_by,
                    "created_at": v.created_at,
                }
                for v in policy.versions
            ],
            "gates": self.gate_report(policy),
            "invariants": self.invariant_report(policy),
        }


class ExceptionService(LifecycleService[PolicyException]):
    model = PolicyException
    machine = POLICY_EXCEPTION_MACHINE
    entity_name = "policy_exception"
    reference_prefix = "EXC"

    def create_exception(self, data: dict[str, Any]) -> PolicyException:
        expiry = data.get("expiry_date")
        if isinstance(expiry, str):
            expiry = date.fromisoformat(expiry)
        if expiry is None:
            raise Conflict("PINV-2: an exception must carry an expiry date")
        if expiry <= date.today():
            raise Conflict("PINV-2: the expiry date must be in the future")
        data["expiry_date"] = expiry
        exc = PolicyException(
            reference=self.next_reference(), requested_by=self.actor_id, **data
        )
        self.create(exc)
        self.session.commit()
        return exc

    def detail(self, exc: PolicyException) -> dict[str, Any]:
        return {
            **summarise_exception(exc),
            "business_justification": exc.business_justification,
            "risk_statement": exc.risk_statement,
            "compensating_controls": exc.compensating_controls,
            "rejection_rationale": exc.rejection_rationale,
            "gates": self.gate_report(exc),
            "invariants": self.invariant_report(exc),
        }


class StandardService(LifecycleService[Standard]):
    model = Standard
    machine = POLICY_MACHINE
    entity_name = "standard"
    reference_prefix = "STD"

    def create_standard(self, data: dict[str, Any]) -> Standard:
        std = Standard(reference=self.next_reference(), created_by=self.actor_id, **data)
        self.session.add(std)
        self.session.commit()
        return std


def summarise_policy(policy: Policy) -> dict[str, Any]:
    return {
        "id": policy.id,
        "reference": policy.reference,
        "title": policy.title,
        "policy_type": policy.policy_type,
        "version": policy.version,
        "lifecycle_state": policy.lifecycle_state,
        "review_cycle": policy.review_cycle,
        "requires_annual_review": policy.requires_annual_review,
        "effective_date": policy.effective_date,
        "next_review_date": policy.next_review_date,
        "compliance_mappings": policy.compliance_mappings,
        "control_count": len(policy.control_links),
        "exception_count": policy.active_exception_count,
        "realignment_pending": policy.realignment_pending,
        "realignment_due": policy.realignment_due,
        "policy_owner_id": policy.policy_owner_id,
        "approved_by": policy.approved_by,
        "approved_at": policy.approved_at,
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
    }


def summarise_exception(exc: PolicyException) -> dict[str, Any]:
    return {
        "id": exc.id,
        "reference": exc.reference,
        "policy_id": exc.policy_id,
        "title": exc.title,
        "lifecycle_state": exc.lifecycle_state,
        "expiry_date": exc.expiry_date,
        "days_to_expiry": exc.days_to_expiry,
        "expiring_soon": 0 <= exc.days_to_expiry <= 30,
        "overdue": exc.lifecycle_state == "Approved" and exc.days_to_expiry < 0,
        "has_compensating_controls": bool(exc.compensating_controls),
        "requested_by": exc.requested_by,
        "approved_by": exc.approved_by,
        "promoted_risk_id": exc.promoted_risk_id,
    }
