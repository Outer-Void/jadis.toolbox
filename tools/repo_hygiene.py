#!/usr/bin/env python3
"""Repository hygiene for CI: no secrets, no personal paths, no broken relative Markdown links.

Secrets are found with jadis's own redaction patterns. Test files may contain deliberately fake secrets
only when assembled from fragments (as tests/test_redaction.py does), so the literal never appears.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from jadis.redact import PATTERNS  # noqa: E402

PERSONAL = re.compile(r"(?<!com\.termux/files)/home/(?!dev\b|user\b|<)[a-z][a-z0-9_-]*/")
# PATTERNS[:SHAPE] match secret *shapes* (keys, tokens) and are enforced everywhere. The rest match
# `NAME=value`, bearer and URL-credential *contexts*; test sources legitimately assign fake values to secret-named variables.
SHAPE = 7
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")


def tracked() -> list[Path]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-co", "--exclude-standard"], capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines() if (ROOT / p).is_file()]


def main() -> int:
    problems = []
    for path in tracked():
        rel = path.relative_to(ROOT)
        try:
            text = path.read_text("utf-8")
        except UnicodeDecodeError:
            continue
        patterns = PATTERNS[:SHAPE] if rel.parts[0] == "tests" else PATTERNS
        for pattern, _ in patterns:
            for m in pattern.finditer(text):
                if "REDACTED" not in m.group(0):
                    problems.append(f"{rel}: looks like a secret: {m.group(0)[:24]}...")
        for m in PERSONAL.finditer(text):
            problems.append(f"{rel}: personal absolute path {m.group(0)}")
        if path.suffix == ".md":
            for target in LINK.findall(re.sub(r"```.*?```", "", text, flags=re.S)):
                if re.match(r"^[a-z]+:|^#", target):
                    continue
                if not (path.parent / target.split("#")[0]).exists():
                    problems.append(f"{rel}: broken link {target}")
    for p in problems:
        print(f"hygiene: {p}", file=sys.stderr)
    print("hygiene: OK" if not problems else f"hygiene: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
