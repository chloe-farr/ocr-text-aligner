#!/usr/bin/env python3
"""
Placeholder for Git LFS or release-zip downloads if demo binaries grow too large.

Today, example data lives under examples/daily_colonist_1972_10_12/ in the repo;
see examples/README.md.
Reference: docs/STAGE_IO.md (align-only demo path).
"""
from __future__ import annotations

from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    example = root / "examples" / "daily_colonist_1972_10_12"
    if (example / "page_0014" / "page_0014.xml").is_file():
        print(f"Demo assets already present under {example}")
        return 0
    print(
        "No bundled demo assets found; clone the full repo or add the "
        "daily_colonist_1972_10_12/ directory under examples/. "
        "(Future: extend this script to fetch a release archive.)"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
