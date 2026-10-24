#!/usr/bin/env python3
"""Package the bounded Story 2.5 o65 resident payload for Atari staging.

The small FNR1 prefix supplies the entry and CIO-table offsets that vanilla
cc65 o65 does not export.  It is metadata for one NIO payload, not a general
module format or loader.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

MAGIC = b"FNR1"
VERSION = 1
HEADER_SIZE = 22
DEFAULT_CSTACK = 0x100


def label(path: Path, name: str) -> int:
    needle = f"._{name}"
    for line in path.read_text(errors="replace").splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == "al" and fields[2] == needle:
            return int(fields[1], 16)
    raise ValueError(f"{path} lacks {name}")


def package(module: bytes, labels: Path, cstack: int) -> bytes:
    if len(module) < 26 or module[:8] != b"\x01\x00o65\x00\x00\x08":
        raise ValueError("resident module is not cc65's supported 16-bit o65 form")
    text_base, text_len, data_base, data_len, bss_base, bss_len, zp_base, zp_len, stack = struct.unpack_from(
        "<9H", module, 8)
    if (text_base != 0 or data_base != text_len or bss_base != text_len + data_len or
            zp_base != 0 or stack != 0 or not text_len or not zp_len):
        raise ValueError("resident module has unsupported o65 layout")
    entry = label(labels, "fnresident_module_entry")
    table = label(labels, "fnresident_module_handler_table")
    marker = label(labels, "fnresident_module_marker")
    initialized = text_len + data_len
    allocation = initialized + bss_len
    if not (entry < initialized and table < initialized and marker < initialized):
        raise ValueError("resident entry metadata escapes initialized image")
    if len(module) > 0xffff or allocation > 0xffff or cstack > 0xffff:
        raise ValueError("resident module exceeds the bounded Atari loader format")
    header = struct.pack("<4sBB7HBB", MAGIC, VERSION, HEADER_SIZE, entry, table,
                         marker, len(module), allocation, initialized, cstack,
                         zp_len, 0)
    if len(header) != HEADER_SIZE:
        raise AssertionError("FNR1 header size changed without loader update")
    return header + module


def xex_segment(address: int, payload: bytes) -> bytes:
    if not payload or address + len(payload) - 1 > 0xffff:
        raise ValueError("staging segment does not fit Atari address space")
    end = address + len(payload) - 1
    return b"\xff\xff" + struct.pack("<HH", address, end) + payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", required=True, type=Path)
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--cstack", type=lambda text: int(text, 0), default=DEFAULT_CSTACK)
    ap.add_argument("--stage", type=lambda text: int(text, 0))
    ns = ap.parse_args()
    image = package(ns.module.read_bytes(), ns.labels, ns.cstack)
    ns.output.write_bytes(xex_segment(ns.stage, image) if ns.stage is not None else image)
    print(f"FNR1 resident image: module={len(image) - HEADER_SIZE} initialized="
          f"{struct.unpack_from('<H', image, 16)[0]} allocation={struct.unpack_from('<H', image, 14)[0]} "
          f"cstack={ns.cstack} staged={len(image)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
