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
    ap.add_argument("--max-initialized", type=lambda text: int(text, 0),
                    help="fail when CODE+RODATA+DATA exceeds this byte count")
    ap.add_argument("--max-bss", type=lambda text: int(text, 0),
                    help="fail when BSS exceeds this byte count")
    ap.add_argument("--forbid-module", action="append", default=[],
                    help="fail when a linked module basename matches")
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
        for segment in ("CODE", "RODATA", "DATA", "BSS"):
            ranked = sorted(
                ((parts.get(segment, 0), name)
                 for name, parts in report["modules"].items() if parts.get(segment, 0)),
                reverse=True,
            )
            print(f"{segment} modules:")
            for size, name in ranked[:12]:
                print(f"{size:5d} {name}")

    initialized = sum(report["segments"].get(name, {}).get("size", 0)
                      for name in ("CODE", "RODATA", "DATA"))
    bss = report["segments"].get("BSS", {}).get("size", 0)
    if ns.max_initialized is not None and initialized > ns.max_initialized:
        raise SystemExit(
            f"initialized footprint {initialized} exceeds {ns.max_initialized}")
    if ns.max_bss is not None and bss > ns.max_bss:
        raise SystemExit(f"BSS footprint {bss} exceeds {ns.max_bss}")
    modules = report["modules"]
    for forbidden in ns.forbid_module:
        if any(name.endswith(forbidden) for name in modules):
            raise SystemExit(f"forbidden resident module linked: {forbidden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
