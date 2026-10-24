#!/usr/bin/env python3
"""Emit a stable, reviewable segment/module summary from an ld65 map."""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

MODULE = re.compile(r"^(.+):$")
SEGMENT = re.compile(r"^\s+(CODE|RODATA|DATA|BSS|ZEROPAGE|STARTUP|ONCE)\s+Offs=[0-9A-F]+\s+Size=([0-9A-F]+)")
SUMMARY = re.compile(r"^(ZEROPAGE|STARTUP|ONCE|CODE|RODATA|DATA|BSS)\s+([0-9A-F]{6})\s+([0-9A-F]{6})\s+([0-9A-F]{6})")


def parse(path: Path) -> dict:
    modules: dict[str, dict[str, int]] = defaultdict(dict)
    segments: dict[str, dict[str, int]] = {}
    current = None
    in_summary = False
    for line in path.read_text(errors="replace").splitlines():
        if line == "Segment list:":
            in_summary = True
            continue
        if in_summary:
            match = SUMMARY.match(line)
            if match:
                name, start, end, size = match.groups()
                segments[name] = {"start": int(start, 16), "end": int(end, 16),
                                  "size": int(size, 16)}
            continue
        match = MODULE.match(line)
        if match and not line.startswith(" "):
            current = match.group(1)
            continue
        match = SEGMENT.match(line)
        if match and current:
            name, size = match.groups()
            modules[current][name] = int(size, 16)
    return {"segments": segments, "modules": modules}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args()
    report = parse(ns.map)
    report["largest_modules"] = sorted(
        ({"module": name, "bytes": sum(parts.values()), "parts": parts}
         for name, parts in report["modules"].items()),
        key=lambda entry: entry["bytes"], reverse=True,
    )[:12]
    if ns.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for name, entry in report["segments"].items():
            print(f"{name:8s} ${entry['start']:04X}-${entry['end']:04X} {entry['size']} bytes")
        for entry in report["largest_modules"]:
            print(f"{entry['bytes']:5d} {entry['module']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
