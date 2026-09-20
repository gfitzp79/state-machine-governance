"""Treatment invariants (RINV-16).

Treatments carry the risk vocabulary rather than one of their own. They are
Phase 5 of the risk lifecycle, every rule about them is stated in the risk
sections of the specification, and giving them a fourth prefix would have
implied a domain boundary that does not exist. The compliance module already
registers `CINV-12` for the same reason: the prefix follows the vocabulary the
rule belongs to, not the file it happens to live in.

Separation of duties on treatments (`SEP-2`, `SEP-5`) is enforced in the
treatment gates, where the acting user is known. This file holds the one rule
about who the record is allowed to name.
"""

from __future__ import annotations

from app.core import ownership
from app.engine import SERVICE, Invariant, invariants

TREATMENT = "treatment"

TREATMENT_OWNER_ROLES = {
    "treatment_owner_id": "Risk_Treatment_Owner",
}

invariants.register(
    Invariant(
        id="RINV-16",
        entity=TREATMENT,
        rule="A person named as treatment owner holds the Risk_Treatment_Owner role",
        layer=SERVICE,
        mechanism=ownership.describe(TREATMENT_OWNER_ROLES),
        violation="Named owner does not hold the required role",
        spec_ref="codified-rules section 2.4",
        holds=ownership.holder_of(fields=TREATMENT_OWNER_ROLES),
    ),
)
