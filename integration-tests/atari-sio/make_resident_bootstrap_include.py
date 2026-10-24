#!/usr/bin/env python3
"""Generate fixed bootstrap bounds from the actual resident linker map."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

STAGE = 0x5000
BOOTSTRAP = 0x3800
LIMIT = 0x9400
REQUIRED = ("STARTUP", "ONCE", "CODE", "RODATA", "DATA", "BSS")


def parse_map(path: Path) -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    pattern = re.compile(r"^(STARTUP|ONCE|CODE|RODATA|DATA|BSS)\s+([0-9A-F]{6})\s+([0-9A-F]{6})")
    for line in path.read_text(errors="replace").splitlines():
        match = pattern.match(line)
        if match:
            found[match.group(1)] = (int(match.group(2), 16), int(match.group(3), 16))
    return found


def xex_entry(path: Path) -> int:
    raw = path.read_bytes()
    pos = 0
    while pos < len(raw):
        if raw[pos:pos + 2] == b"\xff\xff":
            pos += 2
            continue
        if pos + 4 > len(raw):
            break
        start = raw[pos] | raw[pos + 1] << 8
        end = raw[pos + 2] | raw[pos + 3] << 8
        pos += 4
        size = end - start + 1
        if end < start or pos + size > len(raw):
            raise ValueError("malformed resident XEX")
        if start == 0x02E0 and end == 0x02E1:
            return raw[pos] | raw[pos + 1] << 8
        pos += size
    raise ValueError("resident XEX lacks RUNAD")


def handler_table(path: Path) -> int:
    pattern = re.compile(r"^al ([0-9A-F]{6}) \._fnresident_handler_table$")
    for line in path.read_text(errors="replace").splitlines():
        match = pattern.match(line)
        if match:
            return int(match.group(1), 16)
    raise ValueError("resident labels lack fnresident_handler_table")


def bounds(segments: dict[str, tuple[int, int]], entry: int) -> dict[str, int]:
    if any(name not in segments for name in REQUIRED):
        raise ValueError("resident map lacks a required segment")
    start = segments["STARTUP"][0]
    image_end = segments["DATA"][1] + 1
    bss_start, bss_end = segments["BSS"][0], segments["BSS"][1] + 1
    if start != 0x1D00 or image_end != bss_start:
        raise ValueError("resident initialized image is not contiguous at $1D00")
    if not (BOOTSTRAP < STAGE < STAGE + (image_end - start) <= LIMIT):
        raise ValueError("resident staging image exceeds its temporary safe window")
    if not start <= entry < image_end:
        raise ValueError("resident RUNAD is outside its initialized image")
    return {"start": start, "entry": entry, "image_end": image_end,
            "bss_start": bss_start, "end": bss_end, "stage": STAGE}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--xex", type=Path, required=True)
    ap.add_argument("--lbl", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ns = ap.parse_args()
    values = bounds(parse_map(ns.map), xex_entry(ns.xex))
    values["table"] = handler_table(ns.lbl)
    ns.output.write_text("\n".join(
        f"RESIDENT_{name.upper()} = ${value:04X}" for name, value in values.items()
    ) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
