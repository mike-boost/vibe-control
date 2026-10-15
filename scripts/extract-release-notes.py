#!/usr/bin/env python3
"""Extract one Keep-a-Changelog section and format GitHub Release notes.

Usage:
  scripts/extract-release-notes.py 0.5.10
  scripts/extract-release-notes.py 0.5.10 --changelog CHANGELOG.md
  scripts/extract-release-notes.py 0.5.10 --raw   # section body only

Never pass the whole CHANGELOG.md to `gh release create --notes-file`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SECTION_RE = re.compile(
    r"^## \[([^\]]+)\][^\n]*\n(.*?)(?=^## \[|\Z)",
    re.MULTILINE | re.DOTALL,
)


def extract_section(changelog: str, version: str) -> str:
    ver = version.lstrip("v")
    for match in SECTION_RE.finditer(changelog):
        if match.group(1).strip() == ver:
            return match.group(2).strip() + "\n"
    raise SystemExit(f"No CHANGELOG section found for version {ver}")


def format_github_notes(*, version: str, section: str) -> str:
    ver = version.lstrip("v")
    tag = f"v{ver}"
    # Drop redundant "Tag: `vX.Y.Z`." line — title already shows it.
    lines = [
        ln
        for ln in section.splitlines()
        if not re.match(r"^Tag:\s*`?v?[\d.]+`?\s*\.?$", ln.strip())
    ]
    body = "\n".join(lines).strip() + "\n"
    return (
        f"## Summary\n\n"
        f"{body}\n"
        f"## Install\n\n"
        f"```bash\n"
        f"git checkout {tag}\n"
        f"./scripts/install-user.sh\n"
        f"vibe --version   # vibe-control {ver}\n"
        f"```\n\n"
        f"See `CHANGELOG.md` for the full historical notes.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="SemVer with or without leading v (e.g. 0.5.10)")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="Path to CHANGELOG.md",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print CHANGELOG section only (no Summary/Install wrapper)",
    )
    args = parser.parse_args()
    text = args.changelog.read_text(encoding="utf-8")
    section = extract_section(text, args.version)
    if args.raw:
        sys.stdout.write(section)
        return
    sys.stdout.write(format_github_notes(version=args.version, section=section))


if __name__ == "__main__":
    main()
