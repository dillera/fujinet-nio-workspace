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
RESIDENT_START = 0x1D00
RESIDENT_STAGE = 0x5000


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


def hatabs_prelude(table: int) -> bytes:
    """Return a tiny preceding INITAD which owns N: for lifecycle tests."""
    return bytes((0xa9, ord('N'), 0x8d, 0x1a, 0x03,
                  0xa9, table & 0xff, 0x8d, 0x1b, 0x03,
                  0xa9, table >> 8, 0x8d, 0x1c, 0x03, 0x60))


def bootstrap_entry(blob: bytes) -> int:
    for start, end, data in segments(blob):
        if start == RUNAD and end == RUNAD + 1:
            return data[0] | data[1] << 8
    raise ValueError("bootstrap lacks a RUNAD")


def emit_staged_installer(out: bytearray, installer: bytes, bootstrap: bytes) -> None:
    """Stage the $1D00-linked image and execute its ownership bootstrap."""
    delta = RESIDENT_STAGE - RESIDENT_START
    for start, end, data in segments(installer):
        if start in (RUNAD, INITAD):
            continue
        if start < RESIDENT_START:
            raise ValueError("resident payload has an unexpected low segment")
        emit(out, start + delta, end + delta, data)
    for start, end, data in segments(bootstrap):
        if start not in (RUNAD, INITAD):
            emit(out, start, end, data)
    entry = bootstrap_entry(bootstrap)
    emit(out, INITAD, INITAD + 1, bytes((entry & 0xff, entry >> 8)))


def compose(installer: bytes, probe: bytes, foreign_hatabs: bool = False,
            own_hatabs: int | None = None, bootstrap: bytes | None = None,
            repeat_bootstrap: bool = False) -> bytes:
    out = bytearray(b"\xff\xff")
    if foreign_hatabs or own_hatabs is not None:
        # A real preceding INITAD phase owns N:.  The foreign case must be
        # rejected; the owned case must be idempotent before fn_init/MEMLO.
        prelude = hatabs_prelude(0xd000 if foreign_hatabs else own_hatabs)
        emit(out, 0x3000, 0x3000 + len(prelude) - 1, prelude)
        emit(out, INITAD, INITAD + 1, b"\x00\x30")
    if bootstrap is not None:
        emit_staged_installer(out, installer, bootstrap)
        if repeat_bootstrap:
            # This is a real second loader phase.  It stages a new installer
            # image, then bootstrap must observe the active N: before copying.
            emit_staged_installer(out, installer, bootstrap)
    else:
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
    ownership = ap.add_mutually_exclusive_group()
    ownership.add_argument("--foreign-hatabs", action="store_true")
    ownership.add_argument("--own-hatabs", type=lambda value: int(value, 0))
    ap.add_argument("--bootstrap", type=Path)
    ap.add_argument("--repeat-bootstrap", action="store_true")
    ns = ap.parse_args()
    if ns.repeat_bootstrap and ns.bootstrap is None:
        ap.error("--repeat-bootstrap requires --bootstrap")
    ns.output.write_bytes(compose(ns.installer.read_bytes(), ns.probe.read_bytes(),
                                  ns.foreign_hatabs, ns.own_hatabs,
                                  ns.bootstrap.read_bytes() if ns.bootstrap else None,
                                  ns.repeat_bootstrap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
