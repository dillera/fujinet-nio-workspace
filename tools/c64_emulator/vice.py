"""Drive a C64 in VICE: FujiNet NIO on its serial bus, the binary monitor for eyes and hands.

VICE here is the vice-fn build, whose real-device support reaches devices 8-30 through
the opencbm-netiec bridge (see its fujinet/README.md). The bus runs through the KERNAL
traps, so this exercises everything above the bus's electrical timing, not that.
"""

from __future__ import annotations

import os
import re
import socket
import struct
import subprocess
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

# Binary monitor protocol.
API_STX = 0x02
API_VERSION = 0x02
CMD_MEM_GET = 0x01
CMD_KEYBOARD_FEED = 0x72
CMD_PING = 0x81
CMD_DISPLAY_GET = 0x84
CMD_PALETTE_GET = 0x91
CMD_EXIT = 0xAA
CMD_RESET = 0xCC
RESPONSE_HEADER = struct.Struct("<BBIBBI")  # stx, api, body length, type, error, request id
ERROR_OK = 0

SCREEN_START = 0x0400
SCREEN_END = 0x07E7
SCREEN_COLS = 40
VIC_MEMORY_SETUP = 0xD018
KEYBOARD_COUNT = 0x00C6
KEYBOARD_FEED_CHUNK = 32

# PETSCII for keys with no printable form.
KEY_RETURN = 0x0D
KEY_DOWN = 0x11
KEY_DEL = 0x14
KEY_F1 = 0x85
KEY_F3 = 0x86
KEY_F5 = 0x87
KEY_RUN_STOP = 0x03


def petscii(text: str) -> bytes:
    """Text as the keyboard gives it: letters unshifted, newlines as RETURN.

    In the power-on character set an unshifted letter shows as a capital; in the
    lower/upper case set it is a small letter. Either way the same code is sent.
    """
    out = bytearray()
    for ch in text:
        if ch == "\n":
            out.append(KEY_RETURN)
        elif "a" <= ch <= "z":
            out.append(ord(ch) - 0x20)
        elif "A" <= ch <= "Z":
            out.append(ord(ch) + 0x80)
        elif 0x20 <= ord(ch) <= 0x5D:
            out.append(ord(ch))
        else:
            raise ValueError(f"no PETSCII key for {ch!r}")
    return bytes(out)


def screen_code_to_text(code: int, lower_upper_set: bool) -> str:
    """One screen cell as text; reverse video reads as the same character."""
    code &= 0x7F
    if code == 0x00:
        return "@"
    if 0x01 <= code <= 0x1A:
        # Small letters in the lower/upper set, capitals on the power-on set. They
        # read as small here on both, so what BASIC shows matches what was typed.
        return chr(code + 0x60)
    if code == 0x1B:
        return "["
    if code == 0x1C:
        return "\\"
    if code == 0x1D:
        return "]"
    if code == 0x1E:
        return "^"
    if code == 0x1F:
        return "<"
    if 0x20 <= code <= 0x3F:
        return chr(code)
    if lower_upper_set and 0x41 <= code <= 0x5A:
        return chr(code)
    return " " if code == 0x60 else "#"


def write_png(path: Path, width: int, height: int, rgb_rows: list[bytes]) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\0" + row for row in rgb_rows)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw))
    png += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


@dataclass(frozen=True)
class ViceConfig:
    root: Path                       # the vice-fn checkout (external/vice-fn)
    build: Path                      # its builds, headless/ and sdl2/ (scripts/build-vice-fn.sh)
    units: tuple[int, ...] = (8, 30)
    monitor_port: int = 6502
    headless: bool = True
    netiec_port: int = 1541

    @property
    def launcher(self) -> Path:
        return self.root / "fujinet" / "run-vice-fujinet.sh"

    @property
    def build_dir(self) -> Path:
        return self.build / ("headless" if self.headless else "sdl2")


class Vice:
    """One running x64sc, with its binary monitor connected for its whole life."""

    def __init__(self, config: ViceConfig, log_path: Path) -> None:
        self.config = config
        self.log_path = log_path
        self.process: subprocess.Popen | None = None
        self.sock: socket.socket | None = None
        self._request_id = 0

    def start(self, timeout: float = 20.0) -> None:
        # Connecting to another VICE's monitor would type into that machine.
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", self.config.monitor_port)) == 0:
                raise RuntimeError(f"monitor port {self.config.monitor_port} is already in use")
        env = dict(os.environ)
        env["FUJINET_UNITS"] = " ".join(str(u) for u in self.config.units)
        env["VICE_BUILD"] = str(self.config.build_dir)
        env["NETIEC_PORT"] = str(self.config.netiec_port)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("wb") as log:  # VICE keeps its own copy of the file
            self.process = subprocess.Popen(
                [
                    str(self.config.launcher),
                    "-default",
                    "-binarymonitor",
                    "-binarymonitoraddress",
                    f"ip4://127.0.0.1:{self.config.monitor_port}",
                    "+sound",
                ],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"VICE exited at once; see {self.log_path}")
            try:
                self.sock = socket.create_connection(("127.0.0.1", self.config.monitor_port), timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("VICE's binary monitor did not open")
        self.sock.settimeout(30)
        self._call(CMD_PING)
        self._resume()

    def stop(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None

    def _recv_exact(self, length: int) -> bytes:
        assert self.sock is not None
        data = b""
        while len(data) < length:
            chunk = self.sock.recv(length - len(data))
            if not chunk:
                raise RuntimeError("VICE closed its monitor")
            data += chunk
        return data

    def _call(self, command: int, body: bytes = b"") -> bytes:
        """One request. Any request stops the machine until _resume()."""
        assert self.sock is not None
        self._request_id += 1
        request_id = self._request_id
        self.sock.sendall(struct.pack("<BBIIB", API_STX, API_VERSION, len(body), request_id, command) + body)
        while True:
            header = self._recv_exact(RESPONSE_HEADER.size)
            _, _, length, _, error, response_id = RESPONSE_HEADER.unpack(header)
            payload = self._recv_exact(length)
            if response_id == request_id:  # the rest are stop/resume events
                if error != ERROR_OK:
                    raise RuntimeError(f"VICE monitor command {command:#x} failed: error {error:#x}")
                return payload

    def _resume(self) -> None:
        self._call(CMD_EXIT)

    def reset(self) -> None:
        """What the reset button does. The firmware keeps its mounts."""
        self._call(CMD_RESET, bytes([0]))
        self._resume()

    def _read_memory(self, start: int, end: int) -> bytes:
        body = struct.pack("<BHHBH", 0, start, end, 0, 0)  # no side effects, main memory, default bank
        payload = self._call(CMD_MEM_GET, body)
        return payload[2:]  # a 16-bit length, then the bytes

    def peek(self, start: int, end: int | None = None) -> bytes:
        data = self._read_memory(start, start if end is None else end)
        self._resume()
        return data

    def screen(self) -> list[str]:
        """The text screen, one string per row, without trailing blanks."""
        cells = self._read_memory(SCREEN_START, SCREEN_END)
        memory_setup = self._read_memory(VIC_MEMORY_SETUP, VIC_MEMORY_SETUP)[0]
        self._resume()
        lower_upper = bool(memory_setup & 0x02)
        rows = []
        for start in range(0, len(cells), SCREEN_COLS):
            row = cells[start : start + SCREEN_COLS]
            rows.append("".join(screen_code_to_text(c, lower_upper) for c in row).rstrip())
        return rows

    def screen_text(self) -> str:
        return "\n".join(self.screen())

    def press(self, keys: bytes, settle: float = 0.15) -> None:
        """PETSCII keys into the keyboard, as if typed, and wait until they are taken."""
        for start in range(0, len(keys), KEYBOARD_FEED_CHUNK):
            chunk = keys[start : start + KEYBOARD_FEED_CHUNK]
            self._call(CMD_KEYBOARD_FEED, bytes([len(chunk)]) + chunk)
            self._resume()
            time.sleep(0.1)
            deadline = time.monotonic() + 10
            while self.peek(KEYBOARD_COUNT)[0] != 0 and time.monotonic() < deadline:
                time.sleep(0.05)
        time.sleep(settle)

    def type_text(self, text: str) -> None:
        """Type text, a line at a time: BASIC can drop what is queued while a line runs."""
        for line in text.splitlines(keepends=True):
            self.press(petscii(line), settle=0.4 if line.endswith("\n") else 0.15)

    def wait_for(self, pattern: str, timeout: float = 30.0, poll: float = 0.3) -> str:
        """Wait for a regular expression on the screen (case-insensitive); returns the screen."""
        regex = re.compile(pattern, re.IGNORECASE)
        deadline = time.monotonic() + timeout
        text = ""
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise RuntimeError(f"VICE exited; see {self.log_path}")
            text = self.screen_text()
            if regex.search(text):
                return text
            time.sleep(poll)
        raise TimeoutError(f"{pattern!r} never appeared; the screen is:\n{text}")

    def screenshot(self, path: Path) -> None:
        """A PNG of the display, borders included, in VICE's own palette."""
        display = self._call(CMD_DISPLAY_GET, bytes([1, 0]))  # the VIC-II, 8 bits per pixel
        palette = self._call(CMD_PALETTE_GET, bytes([1]))
        self._resume()

        field_length = struct.unpack_from("<I", display, 0)[0]
        width, height, x_offset, y_offset, inner_width, inner_height, _ = struct.unpack_from("<HHHHHHB", display, 4)
        pixels = display[4 + field_length + 4 :]

        count = struct.unpack_from("<H", palette, 0)[0]
        colors = []
        at = 2
        for _ in range(count):
            item_size = palette[at]
            colors.append(bytes(palette[at + 1 : at + 4]))
            at += 1 + item_size

        rows = []
        for y in range(y_offset, y_offset + inner_height):
            row = pixels[y * width + x_offset : y * width + x_offset + inner_width]
            rows.append(b"".join(colors[p] for p in row))
        write_png(path, inner_width, inner_height, rows)
