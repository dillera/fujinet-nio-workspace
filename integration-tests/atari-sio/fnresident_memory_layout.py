#!/usr/bin/env python3
"""Static and runtime safety gate for the Story 2.5 resident CIO image."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

RESIDENT_START = 0x1D00


def parse_map(path: Path) -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    pattern = re.compile(r"^(STARTUP|ONCE|CODE|RODATA|DATA|BSS)\s+([0-9A-F]{6})\s+([0-9A-F]{6})")
    for line in path.read_text(errors="replace").splitlines():
        match = pattern.match(line)
        if match:
            found[match.group(1)] = (int(match.group(2), 16), int(match.group(3), 16))
    return found


def validate_map(segments: dict[str, tuple[int, int]]) -> dict[str, int]:
    required = ("STARTUP", "CODE", "RODATA", "DATA", "BSS")
    if any(name not in segments for name in required):
        raise ValueError("resident map lacks a required linked segment")
    if segments["STARTUP"][0] != RESIDENT_START:
        raise ValueError("resident image does not start at its protected address")
    starts = [entry[0] for entry in segments.values()]
    ends = [entry[1] for entry in segments.values()]
    if min(starts) != RESIDENT_START or any(end < start for start, end in segments.values()):
        raise ValueError("resident map has invalid segment boundaries")
    return {"resident_start": RESIDENT_START, "resident_end": max(ends) + 1}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=Path, required=True)
    ns = ap.parse_args()
    report = validate_map(parse_map(ns.map))
    print(f"resident map: ${report['resident_start']:04X}-${report['resident_end']:04X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
