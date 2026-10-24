#!/usr/bin/env python3
"""Assert the generated load/run values and fixed run-address operand."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def labels(path: Path) -> dict[str, int]:
    found: dict[str, int] = {}
    pattern = re.compile(r"al ([0-9A-F]{6}) \.([A-Za-z0-9_]+)$")
    for line in path.read_text().splitlines():
        match = pattern.match(line)
        if match:
            found[match.group(2)] = int(match.group(1), 16)
    return found


def main() -> int:
    binary = Path(sys.argv[1]).read_bytes()
    found = labels(Path(sys.argv[2]))
    load = found["__DATA_LOAD__"]
    run = found["__DATA_RUN__"]
    size = found["__DATA_SIZE__"]
    if (load, run, size) != (0x5004, 0x2400, 2):
        raise SystemExit(f"unexpected generated segment symbols: {load:04x} {run:04x} {size}")
    # CODE is LDA absolute / RTS.  Its operand is the link-time RUN address,
    # demonstrating why copying the file bytes alone cannot select MEMLO.
    if binary[:4] != bytes((0xAD, 0x00, 0x24, 0x60)):
        raise SystemExit(f"unexpected fixed-run code bytes: {binary[:4].hex()}")
    if binary[4:] != bytes((0x5A, 0xA5)):
        raise SystemExit(f"unexpected load image bytes: {binary[4:].hex()}")
    print("load/run probe: DATA load=$5004 run=$2400 size=2; operand is fixed $2400")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
