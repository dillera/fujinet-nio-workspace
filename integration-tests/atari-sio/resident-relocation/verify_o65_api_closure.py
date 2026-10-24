#!/usr/bin/env python3
"""Inspect and relocate the real Atari public-API o65 closure for testing.

This is intentionally a host-side feasibility loader, not a production Atari
loader.  It accepts only the subset that cc65's checked-in `modload.s`
accepts, and fails closed on every other record form.
"""
from __future__ import annotations

import argparse
import collections
import struct
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"\x01\x00o65"
TEXT, DATA, BSS, ZP = 2, 3, 4, 5
WORD, HIGH, LOW = 0x80, 0x40, 0x20


@dataclass
class Module:
    text: bytes
    data: bytes
    bss_size: int
    zp_size: int
    imports: list[str]
    text_reloc: list[tuple[int, int, int, int]]
    data_reloc: list[tuple[int, int, int, int]]
    trailing_exports: int

    @property
    def initialized_size(self) -> int:
        return len(self.text) + len(self.data)

    @property
    def allocation_size(self) -> int:
        return self.initialized_size + self.bss_size


def u16(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<H", blob, offset)[0]


def parse_reloc(blob: bytes, pos: int, limit: int) -> tuple[list[tuple[int, int, int, int]], int]:
    records: list[tuple[int, int, int, int]] = []
    offset = -1
    while True:
        if pos >= len(blob):
            raise ValueError("truncated relocation stream")
        delta = blob[pos]
        pos += 1
        if delta == 0:
            return records, pos
        if delta == 0xFF:
            offset += 0xFE
            continue
        offset += delta
        if pos >= len(blob):
            raise ValueError("truncated relocation descriptor")
        descriptor = blob[pos]
        pos += 1
        kind, segment = descriptor & 0xE0, descriptor & 0x07
        if kind not in (WORD, HIGH, LOW) or segment not in (TEXT, DATA, BSS, ZP):
            raise ValueError(f"unsupported relocation record type=${kind:02x} segment={segment}")
        high_addend = 0
        if kind == HIGH:
            if pos >= len(blob):
                raise ValueError("truncated high-byte relocation addend")
            high_addend = blob[pos]
            pos += 1
        width = 2 if kind == WORD else 1
        if offset < 0 or offset + width > limit:
            raise ValueError(f"relocation offset {offset} escapes {limit}-byte segment")
        records.append((offset, kind, segment, high_addend))


def parse(path: Path) -> Module:
    blob = path.read_bytes()
    if len(blob) < 27 or blob[:5] != MAGIC or blob[5] != 0:
        raise ValueError("not a supported 16-bit cc65 o65 module")
    # Mode must remain cc65's 6502/small/simple-addressing output.
    if u16(blob, 6) != 0x0800:
        raise ValueError(f"unsupported o65 mode ${u16(blob, 6):04x}")
    text_base, text_len, data_base, data_len, bss_base, bss_len, zp_base, zp_len, stack = struct.unpack_from("<9H", blob, 8)
    if text_base != 0:
        raise ValueError(f"unsupported nonzero o65 text base ${text_base:04x}")
    if data_base != text_base + text_len or bss_base != data_base + data_len:
        raise ValueError("non-contiguous cc65 module allocation")
    if stack:
        raise ValueError("module requests an unbounded external C stack")
    pos = 26
    while True:
        if pos >= len(blob):
            raise ValueError("truncated o65 options")
        length = blob[pos]
        pos += 1
        if length == 0:
            break
        if length < 2 or pos + length - 1 > len(blob):
            raise ValueError("malformed o65 option")
        pos += length - 1
    text = blob[pos:pos + text_len]
    pos += text_len
    data = blob[pos:pos + data_len]
    pos += data_len
    if len(text) != text_len or len(data) != data_len:
        raise ValueError("truncated text/data payload")
    import_count = u16(blob, pos)
    pos += 2
    imports: list[str] = []
    for _ in range(import_count):
        end = blob.index(0, pos)
        imports.append(blob[pos:end].decode("ascii"))
        pos = end + 1
    text_reloc, pos = parse_reloc(blob, pos, text_len)
    data_reloc, pos = parse_reloc(blob, pos, data_len)
    exports = u16(blob, pos)
    # Exports are currently optional metadata.  The closure's companion map
    # supplies its entry/result offsets, while the runtime loader needs no
    # names.  Reject trailing garbage even when no exports are emitted.
    pos += 2
    if exports != 0 or pos != len(blob):
        raise ValueError("unexpected o65 export metadata; add an explicit parser before accepting it")
    if imports:
        raise ValueError(f"unresolved o65 imports: {', '.join(imports)}")
    if zp_base != 0:
        raise ValueError(f"unexpected o65 ZP base ${zp_base:04x}")
    return Module(text, data, bss_len, zp_len, imports, text_reloc, data_reloc, exports)


def relocate(module: Module, base: int, zp_base: int) -> bytes:
    image = bytearray(module.text + module.data + bytes(module.bss_size))

    def apply(records: list[tuple[int, int, int, int]], start: int) -> None:
        for offset, kind, segment, high_addend in records:
            target = start + offset
            addend = zp_base if segment == ZP else base
            if kind == WORD:
                value = image[target] | (image[target + 1] << 8)
                value = (value + addend) & 0xFFFF
                image[target:target + 2] = value.to_bytes(2, "little")
            elif kind == LOW:
                image[target] = (image[target] + (addend & 0xFF)) & 0xFF
            else:  # cc65 o65 HIGH includes an encoded low-byte carry addend.
                # The preceding parser validated the record's form; emulate
                # the checked-in modload.s high-byte calculation.
                carry = 1 if high_addend + (addend & 0xFF) > 0xFF else 0
                image[target] = (image[target] + ((addend >> 8) & 0xFF) + carry) & 0xFF

    apply(module.text_reloc, 0)
    apply(module.data_reloc, len(module.text))
    return bytes(image)


def summary(module: Module) -> str:
    def describe(records: list[tuple[int, int, int, int]]) -> str:
        counts = collections.Counter((kind, seg) for _, kind, seg, _ in records)
        labels = {WORD: "word", HIGH: "high", LOW: "low"}
        segs = {TEXT: "text", DATA: "data", BSS: "bss", ZP: "zp"}
        return ", ".join(f"{labels[kind]}/{segs[seg]}={count}"
                         for (kind, seg), count in sorted(counts.items()))
    return (f"o65 public closure: initialized={module.initialized_size} "
            f"bss={module.bss_size} allocation={module.allocation_size} zp={module.zp_size}; "
            f"text relocations: {describe(module.text_reloc)}; "
            f"data relocations: {describe(module.data_reloc) or 'none'}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("module", type=Path, nargs="?")
    parser.add_argument("--output-a", type=Path)
    parser.add_argument("--output-b", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        # The supported cc65 loader accepts only low/high/word relocation
        # forms.  SEGADR (0xc0) must be a hard failure, not a silently
        # mis-relocated pseudo-address.
        try:
            parse_reloc(bytes((1, 0xC2, 0)), 0, 1)
        except ValueError as exc:
            if "unsupported relocation" not in str(exc):
                raise
        else:
            raise SystemExit("unsupported SEGADR relocation was accepted")
        print("o65 parser negative: unsupported SEGADR relocation rejected")
        return 0
    if args.module is None:
        parser.error("module is required unless --self-test is supplied")
    module = parse(args.module)
    if args.output_a:
        args.output_a.write_bytes(relocate(module, 0x2000, 0x0082))
    if args.output_b:
        args.output_b.write_bytes(relocate(module, 0x5000, 0x0082))
    print(summary(module))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
