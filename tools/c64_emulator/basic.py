"""Small C64 programs, as the PRG files a test puts on a disk."""

from __future__ import annotations

BASIC_START = 0x0801
TOKEN_PRINT = 0x99


def basic_hello(message: str) -> bytes:
    """A one-line tokenised BASIC program, 10 PRINT"message", with its load address."""
    line = bytes([TOKEN_PRINT]) + b'"' + message.encode("ascii") + b'"\0'
    next_line = BASIC_START + 4 + len(line)  # past the link and the line number
    header = bytes([BASIC_START & 0xFF, BASIC_START >> 8, next_line & 0xFF, next_line >> 8, 10, 0])
    return header + line + b"\0\0"  # a zero link ends the program
