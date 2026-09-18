"""The built page carries no inline script.

nginx sets `script-src 'self'`, so an inline `<script>` is blocked at runtime:
the build passes, the page loads, and the script simply never executes. That is
how the theme bootstrap broke, and neither a typecheck nor a build would have
caught it. Anything that must run before the bundle belongs in `public/`.

This lives in a file rather than inline in the workflow because the first
version of it was a grep with a `\\b` in the pattern, written through a Python
heredoc into YAML. The backslash-b was interpreted on the way and landed in
ci.yml as a literal backspace character, which both inverted the regex and made
the workflow file unparseable. Escaping through three layers is not worth it for
one pattern.

Run from the repository root.
"""

from __future__ import annotations

import pathlib
import re
import sys

# A <script> tag with no src attribute, i.e. one with a body.
INLINE = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>", re.IGNORECASE)

DEFAULT = pathlib.Path("platform/frontend/dist/index.html")


def main(argv: list[str]) -> int:
    target = pathlib.Path(argv[1]) if len(argv) > 1 else DEFAULT
    if not target.is_file():
        print("no built page at " + str(target) + "; run the build first")
        return 1

    html = target.read_text(encoding="utf-8")
    found = INLINE.findall(html)
    if found:
        print(str(target) + " contains an inline script, which the CSP will block:")
        for tag in found:
            print("  " + tag)
        print(
            "\n  Move it to platform/frontend/public/ and reference it with src.\n"
            "  A same-origin file satisfies script-src 'self' and still runs\n"
            "  before first paint; a hash in the CSP would work and would break\n"
            "  silently the next time anyone edited a character of the script."
        )
        return 1

    total = len(re.findall(r"<script", html, re.IGNORECASE))
    print("no inline scripts (" + str(total) + " script tags, all with src)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
