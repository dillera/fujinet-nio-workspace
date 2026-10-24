#!/usr/bin/env python3
"""Compose the transient FNR1 loader, staged o65 image, and load probe.

MyPicoDOS is deliberately only an engineering launcher: unlike a production
DOS XEX loader, it continues to use memory below MEMLO while it reads later
segments.  The bounded resident loader therefore runs only after every staged
and independently linked probe segment has arrived.  A transient launcher
above the loader calls it and then enters the separately linked probe.
"""
from __future__ import annotations

import argparse
from pathlib import Path

RUNAD, INITAD = 0x02E0, 0x02E2
LAUNCHER = 0x4500


def segments(blob: bytes):
    pos = 0
    while pos < len(blob):
        if blob[pos:pos + 2] == b"\xff\xff":
            pos += 2
            continue
        if pos + 4 > len(blob):
            raise ValueError("truncated XEX header")
        start = blob[pos] | blob[pos + 1] << 8
        end = blob[pos + 2] | blob[pos + 3] << 8
        pos += 4
        size = end - start + 1
        if end < start or pos + size > len(blob):
            raise ValueError("malformed XEX segment")
        yield start, end, blob[pos:pos + size]
        pos += size


def emit(out: bytearray, start: int, end: int, payload: bytes) -> None:
    if end < start or len(payload) != end - start + 1:
        raise ValueError("invalid composed segment")
    out.extend((start & 0xff, start >> 8, end & 0xff, end >> 8))
    out.extend(payload)


def entry(blob: bytes) -> int:
    for start, end, data in segments(blob):
        if start == RUNAD and end == RUNAD + 1:
            return data[0] | data[1] << 8
    raise ValueError("loader has no RUNAD")


def prelude(memlo: int | None, foreign: bool) -> bytes:
    code = bytearray()
    if memlo is not None:
        code.extend((0xa9, memlo & 0xff, 0x8d, 0xe7, 0x02,
                     0xa9, memlo >> 8, 0x8d, 0xe8, 0x02))
    if foreign:
        code.extend((0xa9, ord("N"), 0x8d, 0x1a, 0x03,
                     0xa9, 0x00, 0x8d, 0x1b, 0x03,
                     0xa9, 0xd0, 0x8d, 0x1c, 0x03))
    code.append(0x60)
    return bytes(code)


def launcher(loader_entry: int, probe_entry: int, repeat: bool) -> bytes:
    """Return the post-load caller which remains outside the resident range."""
    calls = bytes((0x20, loader_entry & 0xff, loader_entry >> 8))
    if repeat:
        calls += calls
    return calls + bytes((0x4c, probe_entry & 0xff, probe_entry >> 8))


def compose(loader: bytes, staged: bytes, probe: bytes, *, memlo: int | None,
            foreign: bool, repeat: bool) -> bytes:
    out = bytearray(b"\xff\xff")
    if memlo is not None or foreign:
        code = prelude(memlo, foreign)
        emit(out, 0x3000, 0x3000 + len(code) - 1, code)
        emit(out, INITAD, INITAD + 1, b"\x00\x30")
    for start, end, data in segments(loader):
        if start not in (RUNAD, INITAD):
            emit(out, start, end, data)
    stage_segments = [item for item in segments(staged) if item[0] not in (RUNAD, INITAD)]
    if len(stage_segments) != 1:
        raise ValueError("staged FNR1 image must have one XEX segment")
    for start, end, data in stage_segments:
        emit(out, start, end, data)
    for start, end, data in segments(probe):
        if start not in (RUNAD, INITAD):
            emit(out, start, end, data)
    code = launcher(entry(loader), entry(probe), repeat)
    emit(out, LAUNCHER, LAUNCHER + len(code) - 1, code)
    emit(out, RUNAD, RUNAD + 1, bytes((LAUNCHER & 0xff, LAUNCHER >> 8)))
    return bytes(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loader", type=Path, required=True)
    ap.add_argument("--staged", type=Path, required=True)
    ap.add_argument("--probe", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--memlo", type=lambda text: int(text, 0))
    ap.add_argument("--foreign", action="store_true")
    ap.add_argument("--repeat", action="store_true")
    ns = ap.parse_args()
    ns.output.write_bytes(compose(ns.loader.read_bytes(), ns.staged.read_bytes(),
                                  ns.probe.read_bytes(), memlo=ns.memlo,
                                  foreign=ns.foreign, repeat=ns.repeat))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
