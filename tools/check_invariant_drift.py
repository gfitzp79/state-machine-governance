"""Every invariant registered in code appears in the catalogue, and vice versa,
with the same enforcement layer. Run from the repository root."""
import ast
import pathlib
import re
import sys

LAYER = {"SCHEMA": "Schema", "SERVICE": "Service", "BOTH": "Both"}

code = {}
for f in sorted(pathlib.Path("platform/backend/app/modules").glob("*/invariants.py")):
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Invariant":
            kw = {k.arg: k.value for k in node.keywords}
            ident = kw["id"].value
            code[ident] = LAYER.get(getattr(kw["layer"], "id", ""), "?")

doc = {}
for line in pathlib.Path("specification/invariants-catalogue.md").read_text(
    encoding="utf-8"
).splitlines():
    m = re.match(r"\|\s*\*{0,2}([A-Z]+-[A-Z0-9]+)\*{0,2}\s*\|(.*)$", line)
    if not m:
        continue
    cells = [c.strip() for c in m.group(2).split("|")]
    if len(cells) >= 2:
        doc[m.group(1)] = cells[1]

problems = []
for ident, layer in sorted(code.items()):
    if ident not in doc:
        problems.append("in code, missing from catalogue: " + ident)
    elif doc[ident] != layer:
        problems.append(
            "enforcement layer disagrees for "
            + ident
            + ": code says "
            + layer
            + ", catalogue says "
            + doc[ident]
        )
for ident in sorted(doc):
    if ident not in code:
        problems.append("in catalogue, not registered in code: " + ident)

for p in problems:
    print("drift:", p)
print("code:", len(code), "catalogue:", len(doc))
sys.exit(1 if problems else 0)
