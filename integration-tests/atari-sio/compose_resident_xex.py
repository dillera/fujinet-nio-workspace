#!/usr/bin/env python3
"""Compose the real DOS INITAD installer phase plus a second XEX probe.

This does not emulate loading: it writes a standard XEX whose original
installer RUNAD is converted to INITAD.  Atari DOS calls that code while it
continues parsing the file, then loads and runs the separately linked probe.
"""
from __future__ import annotations

import argparse
from pathlib import Path

RUNAD = 0x02E0
INITAD = 0x02E2


def segments(blob: bytes):
    pos = 0
    while pos < len(blob):
        if blob[pos:pos + 2] == b"\xff\xff":
            pos += 2
            continue
        if pos + 4 > len(blob):
            break
        start = blob[pos] | blob[pos + 1] << 8
        end = blob[pos + 2] | blob[pos + 3] << 8
        pos += 4
        size = end - start + 1
        if end < start or pos + size > len(blob):
            raise ValueError("truncated or malformed XEX segment")
        yield start, end, blob[pos:pos + size]
        pos += size


def emit(out: bytearray, start: int, end: int, data: bytes) -> None:
    if len(data) != end - start + 1:
        raise ValueError("segment length mismatch")
    out.extend((start & 0xff, start >> 8, end & 0xff, end >> 8))
    out.extend(data)


def compose(installer: bytes, probe: bytes) -> bytes:
    out = bytearray(b"\xff\xff")
    found_runad = False
    for start, end, data in segments(installer):
        if start == RUNAD and end == RUNAD + 1:
            emit(out, INITAD, INITAD + 1, data)
            found_runad = True
        elif start != INITAD:
            emit(out, start, end, data)
    if not found_runad:
        raise ValueError("installer lacks a RUNAD to convert to INITAD")
    for start, end, data in segments(probe):
        if start == INITAD:
            raise ValueError("probe must not add another INITAD phase")
        emit(out, start, end, data)
    return bytes(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("installer", type=Path)
    ap.add_argument("probe", type=Path)
    ap.add_argument("output", type=Path)
    ns = ap.parse_args()
    ns.output.write_bytes(compose(ns.installer.read_bytes(), ns.probe.read_bytes()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
