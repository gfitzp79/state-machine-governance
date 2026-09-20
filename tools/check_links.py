"""Every relative markdown link resolves, including its anchor.

The previous check lived inline in the workflow and threw the fragment away:

    \\[[^\\]]*\\]\\((\\.{1,2}/[^)#]*)(#[^)]*)?\\)

Group 2 captured the anchor and nothing ever looked at it, so a link to a real
file and a section that does not exist passed. Two such links were in the
repository and both passed CI: the README pointed at
`state-transitions.md#7-cross-lifecycle-cascade-rules`, which is section 10, and
a methodology document pointed at a re-grounding section numbered 3, which is 4.

A link to the wrong section of the right file is worse than a dead one. A dead
link announces itself; this one silently lands the reader somewhere plausible.

Anchors are slugged the way GitHub does it: lowercase, strip anything that is
not a word character, space or hyphen, then spaces to hyphens. Duplicate
headings get -1, -2 and so on.

Run from the repository root.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

LINK = re.compile(r"\[[^\]]*\]\((\.{1,2}/[^)\s#]*)(#[^)\s]*)?\)")
SAME_FILE_ANCHOR = re.compile(r"\[[^\]]*\]\((#[^)\s]+)\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$", re.M)
SKIP_DIRS = {"node_modules", ".venv", ".git", "dist", "__pycache__"}


def slug(heading: str) -> str:
    """GitHub's heading slug, closely enough for link checking."""
    text = heading.strip().lower()
    text = re.sub(r"`([^`]*)`", r"\1", text)          # inline code keeps its text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links keep their label
    text = re.sub(r"[*_~]", "", text)                  # emphasis markers
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", "-", text.strip())


def anchors_of(path: pathlib.Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    seen: dict[str, int] = {}
    out: set[str] = set()
    for _, heading in HEADING.findall(text):
        base = slug(heading)
        if not base:
            continue
        n = seen.get(base, 0)
        out.add(base if n == 0 else base + "-" + str(n))
        seen[base] = n + 1
    # Explicit anchors people sometimes add by hand.
    out.update(re.findall(r'<a\s+(?:id|name)="([^"]+)"', text))
    return out


def main() -> int:
    files = [
        pathlib.Path(f)
        for f in subprocess.run(
            ["git", "ls-files", "*.md"], capture_output=True, text=True, check=True
        ).stdout.split()
    ]
    files = [f for f in files if not SKIP_DIRS & set(f.parts)]

    anchor_cache: dict[pathlib.Path, set[str]] = {}
    missing_file: list[str] = []
    missing_anchor: list[str] = []

    for md in files:
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for target, fragment in LINK.findall(text):
            resolved = (md.parent / target).resolve()
            if not resolved.exists():
                missing_file.append(str(md) + " -> " + target)
                continue
            if not fragment or resolved.suffix.lower() != ".md":
                continue
            if resolved not in anchor_cache:
                anchor_cache[resolved] = anchors_of(resolved)
            want = fragment[1:].lower()
            if want and want not in anchor_cache[resolved]:
                missing_anchor.append(
                    str(md) + " -> " + target + fragment + "  (no such section)"
                )

        for fragment in SAME_FILE_ANCHOR.findall(text):
            if md not in anchor_cache:
                anchor_cache[md] = anchors_of(md)
            want = fragment[1:].lower()
            if want and want not in anchor_cache[md]:
                missing_anchor.append(str(md) + " -> " + fragment + "  (no such section)")

    for item in missing_file:
        print("broken link:   " + item)
    for item in missing_anchor:
        print("broken anchor: " + item)

    total = len(missing_file) + len(missing_anchor)
    print(
        "\nchecked "
        + str(len(files))
        + " markdown files: "
        + str(len(missing_file))
        + " broken links, "
        + str(len(missing_anchor))
        + " broken anchors"
    )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
