#!/usr/bin/env python3
"""
Placeholder for Git LFS or release-zip downloads if demo binaries grow too large.

Today, minimal fixtures live under examples/sample_page/ in the repo; see examples/README.md.
Reference: docs/STAGE_IO.md (align-only demo path).
"""
from __future__ import annotations

from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sample = root / "examples" / "sample_page"
    if (sample / "page-1.xml").is_file() and (sample / "page-1_cleantext.txt").is_file():
        print(f"Demo assets already present under {sample}")
        return 0
    print(
        "No bundled demo assets found; clone the full repo or add page-1.xml + page-1_cleantext.txt "
        "under examples/sample_page/. (Future: extend this script to fetch a release archive.)"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
