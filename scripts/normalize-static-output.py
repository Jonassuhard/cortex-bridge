#!/usr/bin/env python3
"""Normalize generated text artifacts so release diffs remain clean."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".htm",
    ".js",
    ".json",
    ".map",
    ".svg",
    ".txt",
    ".xml",
}
TRAILING_WHITESPACE = re.compile(rb"[ \t]+(?=\r?$)", re.MULTILINE)


def normalize(root: Path) -> tuple[int, int]:
    changed = 0
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        scanned += 1
        original = path.read_bytes()
        normalized = TRAILING_WHITESPACE.sub(b"", original)
        if normalized != original:
            path.write_bytes(normalized)
            changed += 1
    return scanned, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print("[static-output] invalid_root")
        return 2
    scanned, changed = normalize(root)
    print(f"[static-output] PASS scanned={scanned} changed={changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
