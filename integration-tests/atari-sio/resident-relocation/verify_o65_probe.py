#!/usr/bin/env python3
"""Validate the minimum independently inspectable properties of an o65 probe."""
from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path


def word(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<H", blob, offset)[0]


def main() -> int:
    path = Path(sys.argv[1])
    blob = path.read_bytes()
    # o65 header: marker $01,$00, magic "o65", version, mode, then the five
    # 16-bit base/length pairs.  This is deliberately a format-level check;
    # co65 has already parsed the full object above.
    if len(blob) < 27 or blob[:5] != b"\x01\x00o65":
        raise SystemExit(f"{path}: not an o65 object")
    text_size = word(blob, 10)
    data_size = word(blob, 14)
    if not text_size or not data_size:
        raise SystemExit(f"{path}: probe lost text or data segment")
    # The variable-length option area precedes the text/data and relocation
    # streams.  `co65 --no-output --verbose` above is the authoritative parser
    # and reports the one relocation required by this CODE-to-DATA operand.
    parsed = subprocess.run(
        ["co65", "--verbose", "--no-output", str(path)],
        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ).stdout
    if "Number of text segment relocations:     1" not in parsed:
        raise SystemExit(f"{path}: expected exactly one CODE-to-DATA relocation\n{parsed}")
    print(f"o65 probe: text={text_size} data={data_size}; one relocation parsed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
