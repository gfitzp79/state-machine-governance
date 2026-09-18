"""Every invariant's spec_ref points at a section that actually exists.

Four threat invariants once cited codified-rules sections 19.4 and 19.5, which
had never been written. A rule whose stated reason does not exist is the first
rule somebody removes, so this fails the build rather than waiting to be noticed.

Run from the repository root.
"""

from __future__ import annotations

import pathlib
import re
import sys

SECTION = "§"

spec = pathlib.Path("specification/codified-rules.md").read_text(encoding="utf-8")
present = set(re.findall(r"^#{1,4} " + SECTION + r"([0-9]+(?:\.[0-9]+)?)", spec, re.M))

if not present:
    print("no sections found in codified-rules.md - has the heading style changed?")
    sys.exit(1)

missing = []
for f in sorted(pathlib.Path("platform/backend/app/modules").glob("*/invariants.py")):
    text = f.read_text(encoding="utf-8")
    for m in re.finditer(
        r'id="([^"]+)".*?spec_ref="codified-rules sections? ([0-9.]+)', text, re.S
    ):
        if m.group(2) not in present:
            missing.append(m.group(1) + " cites codified-rules section " + m.group(2))

for item in sorted(set(missing)):
    print("dangling reference:", item)

print("sections defined:", len(present), "| dangling references:", len(set(missing)))
sys.exit(1 if missing else 0)
