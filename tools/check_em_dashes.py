"""No em dashes in the documentation.

`.agents/agents.md` has carried this editorial rule since before the platform
existed, and the repository broke it 213 times, including in the file that
states it. A rule that is written down and not enforced is the exact thing this
project argues against, so it is now a build failure rather than a preference.

SCOPE: Markdown only.

The rule is about prose. In the application code an em dash is a typographic
glyph rather than punctuation: `'—'` is the empty-value placeholder in a table
cell, and `{reference} — {title}` is a label separator. Banning it there would
force worse output for no editorial gain, so the check does not look at code.

Within Markdown there is no exemption, deliberately. An earlier draft of this
allowed a table cell holding nothing but a dash, which is the same "no value"
convention the UI uses. That exemption is a hole the width of a cell: write
anything after the dash and the rule stops applying. The word `None` says the
same thing, reads the same to a screen reader, and leaves no hole.

Run from the repository root.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

EM_DASH = "—"

# What to write instead, in the rule's own words.
GUIDANCE = """
  Use a comma, a colon, or restructure the sentence:

    a parenthetical aside     X - aside - Y   ->  X, aside, Y
    a restatement             X - Y           ->  X: Y
    a gloss on a term         **Term** - Y    ->  **Term**: Y
    an empty table cell       | - |           ->  | None |

  Both dashes of a pair must go together. Converting one and leaving the other
  turns the aside into a run-on, which is how the first attempt at this broke
  several paragraphs.
"""


def main() -> int:
    tracked = subprocess.run(
        ["git", "ls-files", "*.md"], capture_output=True, text=True, check=True
    ).stdout.split()

    offences: list[tuple[str, int, str]] = []
    for name in tracked:
        path = pathlib.Path(name)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if EM_DASH not in text:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if EM_DASH in line:
                offences.append((name, number, line.strip()))

    if not offences:
        print("no em dashes in " + str(len(tracked)) + " markdown files")
        return 0

    print("em dashes found in documentation:\n")
    for name, number, line in offences:
        excerpt = line if len(line) <= 120 else line[:117] + "..."
        print("  " + name + ":" + str(number))
        print("    " + excerpt)
    print(GUIDANCE)
    print("total: " + str(len(offences)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
