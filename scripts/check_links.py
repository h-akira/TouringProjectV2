#!/usr/bin/env python3
"""Check that relative links in Markdown files point to existing files or directories."""
from __future__ import annotations

import re
import sys
import urllib.parse
from pathlib import Path

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
EXCLUDED_DIRS = {"node_modules", "tmp", ".git", "docs-parent"}


def iter_links(text: str) -> list[tuple[int, str]]:
    """Return (line number, target) for every Markdown link outside code."""
    links: list[tuple[int, str]] = []
    fence: str | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and line.strip() == marker:
                fence = None
            continue
        if fence is not None:
            continue
        for match in LINK_RE.finditer(INLINE_CODE_RE.sub("", line)):
            links.append((lineno, match.group(1)))
    return links


def _is_external(target: str) -> bool:
    return bool(SCHEME_RE.match(target)) or target.startswith("#")


def check_file(path: Path) -> list[str]:
    """Return one error string per broken relative link in the file."""
    errors: list[str] = []
    for lineno, target in iter_links(path.read_text(encoding="utf-8")):
        if _is_external(target):
            continue
        file_part = target.split("#", 1)[0]
        if not file_part:
            continue
        resolved = (path.parent / urllib.parse.unquote(file_part)).resolve()
        if not resolved.exists():
            errors.append(f"{path}:{lineno}: broken link -> {target}")
    return errors


def _collect(roots: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in roots:
        candidates = [root] if root.is_file() else root.rglob("*.md")
        for path in candidates:
            relative_parts = path.relative_to(root).parts if root.is_dir() else ()
            if any(part in EXCLUDED_DIRS for part in relative_parts):
                continue
            files.add(path)
    return sorted(files)


def main(argv: list[str]) -> int:
    roots = [Path(arg) for arg in argv[1:]] or [Path(".")]
    files = _collect(roots)
    errors = [error for path in files for error in check_file(path)]
    for error in errors:
        print(error)
    print(f"checked {len(files)} files, {len(errors)} broken links")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
